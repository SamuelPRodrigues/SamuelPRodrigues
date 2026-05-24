#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DATA_FILES = [
    ('climate', Path('data/climate_events.json')),
    ('road', Path('data/road_events.json')),
    ('operational', Path('data/operational_alerts.json')),
]
STATUS_OUTPUT = Path('data/sheets_sync_status.json')
WEBAPP_URL = os.environ.get('SHEETS_WEBAPP_URL', '').strip()
WEBAPP_KEY = os.environ.get('SHEETS_WEBAPP_KEY', '').strip()


def now_iso() -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


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


def hour_bucket(value: str | None) -> str:
    text = str(value or now_iso())
    if len(text) >= 13:
        return text[:13]
    return now_iso()[:13]


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


def normalize_event(source_type: str, event: dict[str, Any], generated_at: str) -> dict[str, Any] | None:
    try:
        lat = float(event.get('lat'))
        lon = float(event.get('lon'))
    except Exception:
        return None
    risk = int(float(event.get('risk') or 0))
    updated = str(event.get('updatedAt') or event.get('updated_at') or event.get('time') or generated_at)
    bucket = hour_bucket(updated)
    name = str(event.get('name') or event.get('road') or event.get('eventType') or source_type)
    event_type = str(event.get('eventType') or event.get('event_type') or event.get('category') or source_type)
    key = '|'.join([source_type, bucket, name, event_type, f'{lat:.3f}', f'{lon:.3f}'])
    event_hash = hashlib.sha256(key.encode('utf-8')).hexdigest()[:24]
    return {
        'event_id': event_hash,
        'hash': event_hash,
        'snapshot_at': generated_at,
        'updated_at': updated,
        'source_type': source_type,
        'category': event.get('category') or '',
        'event_type': event_type,
        'name': name,
        'risk': risk,
        'severity': severity(risk),
        'lat': round(lat, 6),
        'lon': round(lon, 6),
        'city': event.get('city') or event.get('name') or '',
        'state': event.get('state') or '',
        'region': region_from_event(event),
        'road': event.get('road') or '',
        'description': event.get('description') or '; '.join(event.get('reasons') or []),
        'source': event.get('source') or '',
        'source_url': event.get('sourceUrl') or event.get('source_url') or '',
        'active': event.get('active', True),
        'expires_at': event.get('expiresAt') or event.get('expires_at') or '',
        'raw': event,
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
    return out


def post_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    payload = json.dumps({'key': WEBAPP_KEY, 'generated_at': now_iso(), 'events': events}, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(WEBAPP_URL, data=payload, headers={'Content-Type': 'application/json', 'User-Agent': 'github-actions-sheets-sync/1.0'}, method='POST')
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode('utf-8'))


def main() -> None:
    events = collect_events()
    status = {'updatedAt': now_iso(), 'configured': bool(WEBAPP_URL and WEBAPP_KEY), 'eventsPrepared': len(events), 'ok': False, 'response': None, 'error': None}
    if not WEBAPP_URL or not WEBAPP_KEY:
        status['error'] = 'SHEETS_WEBAPP_URL e/ou SHEETS_WEBAPP_KEY não configurados nos Secrets.'
        write_json(STATUS_OUTPUT, status)
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return
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
    write_json(STATUS_OUTPUT, status)
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
