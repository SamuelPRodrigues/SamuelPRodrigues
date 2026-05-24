#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DATA_FILES = [
    ('climate', Path('data/climate_events.json')),
    ('road', Path('data/road_events.json')),
    ('operational', Path('data/operational_alerts.json')),
    ('manual', Path('data/manual_events.json')),
]
STATUS_OUTPUT = Path('data/sheets_sync_status.json')
ANALYTICS_OUTPUT = Path('data/analytics_cache.json')
WEBAPP_URL = os.environ.get('SHEETS_WEBAPP_URL', '').strip()
WEBAPP_KEY = os.environ.get('SHEETS_WEBAPP_KEY', '').strip()
SHEET_MODE = os.environ.get('SHEETS_SYNC_MODE', 'current_state_upsert').strip() or 'current_state_upsert'


def now_iso() -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).replace('Z', '+00:00')
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def load_json(path: Path, fallback: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        pass
    return fallback


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def snapshot_bucket(value: str | None, minutes: int = 15) -> str:
    dt = parse_dt(value) or datetime.now(timezone.utc)
    minute = (dt.minute // minutes) * minutes
    bucket = dt.replace(minute=minute, second=0, microsecond=0)
    return bucket.strftime('%Y-%m-%dT%H:%MZ')


def region_from_event(event: dict[str, Any]) -> str:
    region = str(event.get('region') or '')
    if region:
        return region
    state = str(event.get('state') or '').upper()
    north = {'AC','AM','AP','PA','RO','RR','TO'}
    northeast = {'AL','BA','CE','MA','PB','PE','PI','RN','SE'}
    midwest = {'DF','GO','MT','MS'}
    southeast = {'ES','MG','RJ','SP'}
    south = {'PR','RS','SC'}
    if state in north: return 'Norte'
    if state in northeast: return 'Nordeste'
    if state in midwest: return 'Centro-Oeste'
    if state in southeast: return 'Sudeste'
    if state in south: return 'Sul'
    try:
        lat = float(event.get('lat'))
        lon = float(event.get('lon'))
        if lat <= -24: return 'Sul'
        if lon > -45 and lat > -18: return 'Nordeste'
        if lon > -52 and lat < -14: return 'Sudeste'
        if lon < -45 and lat > -12: return 'Norte'
    except Exception:
        pass
    return 'Sem região'


def severity(risk: int | float) -> str:
    risk = float(risk or 0)
    if risk >= 80: return 'Crítico'
    if risk >= 60: return 'Alto'
    if risk >= 35: return 'Moderado'
    if risk >= 1: return 'Baixo'
    return 'Sem risco'


def stable_text(*parts: Any) -> str:
    return '|'.join(str(part or '').strip() for part in parts)


def normalize_event(source_type: str, event: dict[str, Any], generated_at: str) -> dict[str, Any] | None:
    try:
        lat = float(event.get('lat'))
        lon = float(event.get('lon'))
    except Exception:
        return None

    risk = int(float(event.get('risk') or 0))
    updated = str(event.get('updatedAt') or event.get('updated_at') or event.get('time') or event.get('createdAt') or generated_at)
    bucket = snapshot_bucket(generated_at)
    name = str(event.get('name') or event.get('road') or event.get('eventType') or source_type)
    event_type = str(event.get('eventType') or event.get('event_type') or event.get('category') or source_type)
    road = str(event.get('road') or '')
    city = str(event.get('city') or event.get('name') or '')
    state = str(event.get('state') or '')
    description = event.get('description') or '; '.join(event.get('reasons') or [])
    source = event.get('source') or ''
    source_url = event.get('sourceUrl') or event.get('source_url') or ''
    precipitation = (event.get('current') or {}).get('precipitation') if isinstance(event.get('current'), dict) else event.get('precipitation', 0)

    stable_key = stable_text(source_type, name, event_type, road, city, state, f'{lat:.3f}', f'{lon:.3f}', source_url)
    stable_event_id = hashlib.sha256(stable_key.encode('utf-8')).hexdigest()[:24]
    observation_key = stable_text(stable_event_id, risk, event_type, description, source, source_url, precipitation)
    observation_hash = hashlib.sha256(observation_key.encode('utf-8')).hexdigest()[:24]

    # IMPORTANTE: para o Google Sheets, event_id agora é estável.
    # Assim, o Apps Script faz upsert da mesma linha em vez de criar uma linha nova a cada 15 minutos.
    event_id = stable_event_id if SHEET_MODE == 'current_state_upsert' else hashlib.sha256(stable_text(bucket, stable_key).encode('utf-8')).hexdigest()[:24]

    return {
        'event_id': event_id,
        'hash': event_id,
        'stable_event_id': stable_event_id,
        'observation_hash': observation_hash,
        'snapshot_bucket': bucket,
        'snapshot_at': generated_at,
        'last_seen_at': generated_at,
        'updated_at': updated,
        'source_type': source_type,
        'category': event.get('category') or '',
        'event_type': event_type,
        'name': name,
        'risk': risk,
        'severity': severity(risk),
        'lat': round(lat, 6),
        'lon': round(lon, 6),
        'city': city,
        'state': state,
        'region': region_from_event(event),
        'road': road,
        'description': description,
        'source': source,
        'source_url': source_url,
        'active': event.get('active', True),
        'expires_at': event.get('expiresAt') or event.get('expires_at') or '',
        'precipitation': precipitation,
        'storage_mode': SHEET_MODE,
    }


def collect_events() -> list[dict[str, Any]]:
    generated_at = now_iso()
    out: list[dict[str, Any]] = []
    for source_type, path in DATA_FILES:
        data = load_json(path, [])
        if not isinstance(data, list):
            continue
        for event in data:
            if isinstance(event, dict):
                item = normalize_event(source_type, event, generated_at)
                if item:
                    out.append(item)
    # dedupe local por event_id para reduzir payload e linhas do Sheets
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in out:
        key = str(item.get('event_id') or item.get('stable_event_id'))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def post_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    payload = json.dumps({
        'key': WEBAPP_KEY,
        'generated_at': now_iso(),
        'mode': SHEET_MODE,
        'events': events,
    }, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(WEBAPP_URL, data=payload, headers={'Content-Type': 'application/json', 'User-Agent': 'github-actions-sheets-sync/2.0'}, method='POST')
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode('utf-8'))


def fetch_history_from_sheets(days: int = 90) -> list[dict[str, Any]]:
    if not WEBAPP_URL:
        return []
    query = urllib.parse.urlencode({'action': 'query', 'days': str(days), 'limit': '2000', 'sort': 'recent'})
    sep = '&' if '?' in WEBAPP_URL else '?'
    req = urllib.request.Request(WEBAPP_URL + sep + query, headers={'User-Agent': 'github-actions-analytics-cache/2.0'})
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode('utf-8'))
    rows = payload.get('rows', []) if isinstance(payload, dict) else []
    return rows if isinstance(rows, list) else []


def safe_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except Exception:
        return 0


def event_dt(row: dict[str, Any]) -> datetime | None:
    return parse_dt(row.get('snapshot_at') or row.get('last_seen_at') or row.get('updated_at'))


def filter_days(rows: list[dict[str, Any]], days: int) -> list[dict[str, Any]]:
    if days <= 0:
        return rows
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return [r for r in rows if (event_dt(r) or cutoff) >= cutoff]


def count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or 'Sem classificação')
        out[value] = out.get(value, 0) + 1
    return dict(sorted(out.items(), key=lambda item: item[1], reverse=True))


def daily_risk(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[int]] = {}
    for row in rows:
        dt = event_dt(row)
        key = dt.date().isoformat() if dt else 'sem-data'
        grouped.setdefault(key, []).append(safe_int(row.get('risk')))
    return [
        {'date': key, 'avgRisk': round(sum(values) / max(1, len(values))), 'events': len(values), 'maxRisk': max(values or [0])}
        for key, values in sorted(grouped.items())
    ]


def build_analytics_cache(history_rows: list[dict[str, Any]], current_rows: list[dict[str, Any]], source: str, error: str | None = None) -> dict[str, Any]:
    rows = history_rows or current_rows
    compact_rows = []
    for row in rows[:2000]:
        compact_rows.append({
            'event_id': row.get('event_id') or row.get('hash') or '',
            'stable_event_id': row.get('stable_event_id') or row.get('event_id') or '',
            'observation_hash': row.get('observation_hash') or '',
            'snapshot_bucket': row.get('snapshot_bucket') or '',
            'snapshot_at': row.get('snapshot_at') or row.get('last_seen_at') or row.get('updated_at') or now_iso(),
            'last_seen_at': row.get('last_seen_at') or row.get('snapshot_at') or '',
            'updated_at': row.get('updated_at') or '',
            'source_type': row.get('source_type') or row.get('type') or '',
            'category': row.get('category') or '',
            'event_type': row.get('event_type') or row.get('eventType') or '',
            'name': row.get('name') or '',
            'risk': safe_int(row.get('risk')),
            'severity': row.get('severity') or severity(safe_int(row.get('risk'))),
            'lat': row.get('lat'),
            'lon': row.get('lon'),
            'city': row.get('city') or '',
            'state': row.get('state') or '',
            'region': row.get('region') or '',
            'road': row.get('road') or '',
            'description': row.get('description') or '',
            'source': row.get('source') or '',
            'source_url': row.get('source_url') or row.get('sourceUrl') or '',
            'precipitation': row.get('precipitation') or 0,
        })
    windows: dict[str, Any] = {}
    for days in (7, 30, 90):
        subset = filter_days(compact_rows, days)
        risks = [safe_int(row.get('risk')) for row in subset]
        climate = [r for r in subset if r.get('source_type') == 'climate']
        rainy = [r for r in climate if safe_int(r.get('precipitation')) > 0 or 'chuva' in str(r.get('description') or r.get('event_type') or r.get('name')).lower()]
        windows[str(days)] = {
            'events': len(subset),
            'avgRisk': round(sum(risks) / max(1, len(risks))) if risks else 0,
            'maxRisk': max(risks or [0]),
            'rainChance': round(len(rainy) / max(1, len(climate)) * 100) if climate else 0,
            'byType': count_by(subset, 'source_type'),
            'byRegion': count_by(subset, 'region'),
            'bySeverity': count_by(subset, 'severity'),
            'dailyRisk': daily_risk(subset),
        }
    return {
        'updatedAt': now_iso(),
        'source': source,
        'storageMode': SHEET_MODE,
        'error': error,
        'rows': compact_rows,
        'windows': windows,
    }


def main() -> None:
    events = collect_events()
    current_bucket = events[0].get('snapshot_bucket') if events else snapshot_bucket(now_iso())
    status = {
        'updatedAt': now_iso(),
        'configured': bool(WEBAPP_URL and WEBAPP_KEY),
        'eventsPrepared': len(events),
        'historyMode': 'current state upsert in Google Sheets; permanent history should use external database',
        'storageMode': SHEET_MODE,
        'snapshotBucket': current_bucket,
        'ok': False,
        'response': None,
        'analyticsCache': False,
        'error': None,
    }
    history_rows: list[dict[str, Any]] = []
    cache_error: str | None = None

    if WEBAPP_URL and WEBAPP_KEY:
        try:
            response = post_events(events)
            status['ok'] = bool(response.get('ok'))
            status['response'] = response
        except urllib.error.HTTPError as exc:
            body = ''
            try:
                body = exc.read().decode('utf-8')[:500]
            except Exception:
                pass
            status['error'] = f'HTTP {exc.code}: {body or exc}'
        except Exception as exc:
            status['error'] = str(exc)

        try:
            history_rows = fetch_history_from_sheets(90)
        except Exception as exc:
            cache_error = str(exc)
    else:
        status['error'] = 'SHEETS_WEBAPP_URL e/ou SHEETS_WEBAPP_KEY não configurados nos Secrets.'

    source = 'google_sheets_current_state' if history_rows else 'current_json_fallback'
    cache = build_analytics_cache(history_rows, events, source, cache_error)
    write_json(ANALYTICS_OUTPUT, cache)
    status['analyticsCache'] = True
    status['analyticsRows'] = len(cache.get('rows', []))
    if cache_error:
        status['analyticsCacheWarning'] = cache_error

    write_json(STATUS_OUTPUT, status)
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
