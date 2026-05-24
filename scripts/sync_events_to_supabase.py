#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sync_events_to_sheets import collect_events, severity, write_json

STATUS_OUTPUT = Path('data/supabase_sync_status.json')
SUPABASE_CACHE_OUTPUT = Path('data/supabase_analytics_cache.json')
ANALYTICS_OUTPUT = Path('data/analytics_cache.json')
SUPABASE_URL = os.environ.get('SUPABASE_URL', '').strip().rstrip('/')
SUPABASE_SERVICE_ROLE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '').strip()


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


def safe_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except Exception:
        return 0


def supabase_headers() -> dict[str, str]:
    return {
        'Content-Type': 'application/json',
        'apikey': SUPABASE_SERVICE_ROLE_KEY,
        'Authorization': f'Bearer {SUPABASE_SERVICE_ROLE_KEY}',
        'User-Agent': 'github-actions-supabase-sync/1.0',
    }


def request_json(url: str, method: str = 'GET', payload: Any | None = None) -> Any:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=supabase_headers(), method=method)
    with urllib.request.urlopen(req, timeout=60) as response:
        raw = response.read().decode('utf-8')
        if not raw:
            return None
        return json.loads(raw)


def ingest_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    url = f'{SUPABASE_URL}/rest/v1/rpc/ingest_event_batch'
    response = request_json(url, method='POST', payload={'events_payload': events})
    return response if isinstance(response, dict) else {'ok': True, 'response': response}


def fetch_recent_events(limit: int = 2500) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({
        'select': '*',
        'order': 'last_seen_at.desc',
        'limit': str(limit),
    })
    url = f'{SUPABASE_URL}/rest/v1/dashboard_events_recent?{query}'
    response = request_json(url)
    return response if isinstance(response, list) else []


def normalize_supabase_row(row: dict[str, Any]) -> dict[str, Any]:
    first_seen = row.get('first_seen_at') or ''
    last_seen = row.get('last_seen_at') or ''
    stable = row.get('stable_event_id') or ''
    return {
        'event_id': stable,
        'stable_event_id': stable,
        'observation_hash': row.get('current_observation_hash') or '',
        'snapshot_bucket': '',
        'snapshot_at': last_seen or row.get('updated_at') or now_iso(),
        'first_seen_at': first_seen,
        'last_seen_at': last_seen,
        'updated_at': row.get('updated_at') or '',
        'source_type': row.get('source_type') or '',
        'category': row.get('category') or '',
        'event_type': row.get('event_type') or '',
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
        'source_url': row.get('source_url') or '',
        'total_snapshots': safe_int(row.get('total_snapshots')),
        'estimated_hours': row.get('estimated_hours') or 0,
        'active': row.get('active'),
        'storage': 'supabase',
    }


def count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or 'Sem classificação')
        out[value] = out.get(value, 0) + 1
    return dict(sorted(out.items(), key=lambda item: item[1], reverse=True))


def event_dt(row: dict[str, Any]) -> datetime | None:
    return parse_dt(row.get('last_seen_at') or row.get('snapshot_at') or row.get('updated_at'))


def filter_days(rows: list[dict[str, Any]], days: int) -> list[dict[str, Any]]:
    if days <= 0:
        return rows
    cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
    result = []
    for row in rows:
        dt = event_dt(row)
        if not dt or dt.timestamp() >= cutoff:
            result.append(row)
    return result


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


def build_cache(rows: list[dict[str, Any]]) -> dict[str, Any]:
    compact_rows = [normalize_supabase_row(row) for row in rows]
    windows: dict[str, Any] = {}
    for days in (7, 30, 90):
        subset = filter_days(compact_rows, days)
        risks = [safe_int(row.get('risk')) for row in subset]
        climate = [r for r in subset if r.get('source_type') == 'climate']
        rainy = [r for r in climate if 'chuva' in str(r.get('description') or r.get('event_type') or r.get('name')).lower()]
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
        'source': 'supabase',
        'storageMode': 'permanent_history',
        'rows': compact_rows,
        'windows': windows,
    }


def main() -> None:
    status: dict[str, Any] = {
        'updatedAt': now_iso(),
        'configured': bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY),
        'eventsPrepared': 0,
        'ingestOk': False,
        'ingestResponse': None,
        'cacheRows': 0,
        'cacheWritten': False,
        'error': None,
    }

    if not status['configured']:
        status['error'] = 'SUPABASE_URL e/ou SUPABASE_SERVICE_ROLE_KEY não configurados nos Secrets.'
        write_json(STATUS_OUTPUT, status)
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return

    try:
        events = collect_events()
        status['eventsPrepared'] = len(events)
        ingest = ingest_events(events)
        status['ingestOk'] = bool(ingest.get('ok', True))
        status['ingestResponse'] = ingest
        rows = fetch_recent_events()
        cache = build_cache(rows)
        status['cacheRows'] = len(cache.get('rows', []))
        write_json(SUPABASE_CACHE_OUTPUT, cache)
        write_json(ANALYTICS_OUTPUT, cache)
        status['cacheWritten'] = True
    except urllib.error.HTTPError as exc:
        body = ''
        try:
            body = exc.read().decode('utf-8')[:1000]
        except Exception:
            pass
        status['error'] = f'HTTP {exc.code}: {body or exc}'
    except Exception as exc:
        status['error'] = str(exc)

    write_json(STATUS_OUTPUT, status)
    print(json.dumps(status, ensure_ascii=False, indent=2))
    if status['error']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
