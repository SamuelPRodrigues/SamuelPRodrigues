#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CONFIG = Path('data/config.json')
OUTPUT = Path('data/climate_events.json')
STATUS = Path('data/climate_events_status.json')


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def fetch_json(url: str, timeout: int = 45) -> Any:
    req = urllib.request.Request(url, headers={'User-Agent': 'climate-road-map/1.0'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8', errors='replace'))


def chunks(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def norm(value: float, maximum: float) -> float:
    if maximum <= 0:
        return 0.0
    return clamp(value / maximum, 0.0, 1.0)


def code_risk(code: Any) -> int:
    try:
        c = int(code)
    except Exception:
        return 0
    if c in (95, 96, 99):
        return 78
    if 80 <= c <= 82:
        return 60
    if 61 <= c <= 67:
        return 52
    if 51 <= c <= 57:
        return 35
    if c in (45, 48):
        return 25
    return 0


def code_text(code: Any) -> str:
    try:
        c = int(code)
    except Exception:
        return ''
    if c in (95, 96, 99):
        return 'Tempestade detectada'
    if 80 <= c <= 82:
        return 'Pancadas de chuva detectadas'
    if 61 <= c <= 67:
        return 'Chuva detectada'
    if 51 <= c <= 57:
        return 'Garoa detectada'
    if c in (45, 48):
        return 'Neblina detectada'
    return ''


def weather_risk(current: dict[str, Any]) -> int:
    rain = float(current.get('precipitation') or 0) + float(current.get('rain') or 0) + float(current.get('showers') or 0)
    wind = max(float(current.get('wind_speed_10m') or current.get('windspeed') or 0), float(current.get('wind_gusts_10m') or 0) * 0.75)
    temp = float(current.get('temperature_2m') or current.get('temperature') or 0)
    score = max(code_risk(current.get('weather_code', current.get('weathercode'))), norm(rain, 18) * 54)
    score += norm(wind, 75) * 28
    if temp >= 34:
        score += norm(temp - 33, 10) * 12
    if temp <= 8:
        score += norm(8 - temp, 10) * 10
    return int(round(clamp(score, 0, 100)))


def reasons(current: dict[str, Any], risk: int) -> list[str]:
    out: list[str] = []
    rain = float(current.get('precipitation') or 0) + float(current.get('rain') or 0) + float(current.get('showers') or 0)
    wind = float(current.get('wind_speed_10m') or current.get('windspeed') or 0)
    gust = float(current.get('wind_gusts_10m') or 0)
    temp = float(current.get('temperature_2m') or current.get('temperature') or 0)
    text = code_text(current.get('weather_code', current.get('weathercode')))
    if text:
        out.append(text)
    if rain >= 0.2:
        out.append(f'Chuva/precipitação detectada ({rain:.1f} mm)')
    if wind >= 35:
        out.append(f'Vento forte ({wind:.0f} km/h)')
    if gust >= 50:
        out.append(f'Rajadas fortes ({gust:.0f} km/h)')
    if temp >= 34:
        out.append(f'Calor extremo ({temp:.1f} °C)')
    if temp <= 8:
        out.append(f'Frio intenso ({temp:.1f} °C)')
    if not out and risk >= 35:
        out.append(f'Risco climático agregado relevante ({risk}/100)')
    return out


def fetch_batch(batch: list[dict[str, Any]]) -> list[dict[str, Any] | None]:
    lat = ','.join(f"{float(p['lat']):.4f}" for p in batch)
    lon = ','.join(f"{float(p['lon']):.4f}" for p in batch)
    params = {
        'latitude': lat,
        'longitude': lon,
        'current': 'temperature_2m,precipitation,rain,showers,wind_speed_10m,wind_gusts_10m,weather_code',
        'forecast_days': '1',
        'timezone': 'America/Sao_Paulo',
    }
    url = 'https://api.open-meteo.com/v1/forecast?' + urllib.parse.urlencode(params)
    try:
        data = fetch_json(url)
        items = data if isinstance(data, list) else [data]
        return items
    except Exception:
        legacy = []
        for point in batch:
            try:
                params2 = {
                    'latitude': f"{float(point['lat']):.4f}",
                    'longitude': f"{float(point['lon']):.4f}",
                    'current_weather': 'true',
                    'timezone': 'America/Sao_Paulo',
                }
                data2 = fetch_json('https://api.open-meteo.com/v1/forecast?' + urllib.parse.urlencode(params2), timeout=30)
                cw = data2.get('current_weather') if isinstance(data2, dict) else None
                legacy.append({'current': {
                    'temperature_2m': cw.get('temperature'),
                    'wind_speed_10m': cw.get('windspeed'),
                    'weather_code': cw.get('weathercode'),
                    'time': cw.get('time'),
                }} if cw else None)
            except Exception:
                legacy.append(None)
        return legacy


def main() -> None:
    config = read_json(CONFIG, {})
    points = config.get('climatePoints') or []
    clean = []
    for p in points:
        try:
            lat = float(p.get('lat'))
            lon = float(p.get('lon'))
            if math.isfinite(lat) and math.isfinite(lon):
                clean.append({**p, 'lat': lat, 'lon': lon})
        except Exception:
            continue

    status = {
        'updatedAt': now_iso(),
        'provider': 'Open-Meteo via GitHub Actions',
        'pointsConfigured': len(points),
        'pointsValid': len(clean),
        'pointsUpdated': 0,
        'eventsWritten': 0,
        'failedPoints': 0,
        'errors': [],
    }
    events: list[dict[str, Any]] = []
    for batch in chunks(clean, 10):
        items = fetch_batch(batch)
        for point, item in zip(batch, items):
            if not item or not isinstance(item, dict) or not item.get('current'):
                status['failedPoints'] += 1
                continue
            current = item.get('current') or {}
            risk = weather_risk(current)
            why = reasons(current, risk)
            status['pointsUpdated'] += 1
            if why and risk >= 1:
                events.append({
                    'active': True,
                    'type': 'climate',
                    'name': point.get('name') or 'Ponto climático',
                    'region': point.get('region') or '',
                    'state': point.get('state') or '',
                    'lat': point['lat'],
                    'lon': point['lon'],
                    'risk': risk,
                    'current': current,
                    'reasons': why,
                    'time': current.get('time') or now_iso(),
                    'source': 'Open-Meteo',
                    'createdAt': now_iso(),
                })
    events.sort(key=lambda e: int(e.get('risk', 0)), reverse=True)
    write_json(OUTPUT, events)
    status['eventsWritten'] = len(events)
    write_json(STATUS, status)
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
