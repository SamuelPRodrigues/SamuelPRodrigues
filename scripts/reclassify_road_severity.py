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

MAX_ROAD_BLOCKING_RISK = int(os.environ.get('MAX_ROAD_BLOCKING_RISK', '69'))
ROAD_HIGH_SEVERITY = 'Alto'
STATUS_OUTPUT = Path('data/road_severity_reclassify_status.json')
SUPABASE_URL = os.environ.get('SUPABASE_URL', '').strip().rstrip('/')
SUPABASE_SERVICE_ROLE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '').strip()
SHEETS_WEBAPP_URL = os.environ.get('SHEETS_WEBAPP_URL', '').strip()
SHEETS_WEBAPP_KEY = os.environ.get('SHEETS_WEBAPP_KEY', '').strip()

LOCAL_JSON_FILES = [
    Path('data/road_events.json'),
    Path('data/manual_events.json'),
]
LOCAL_CACHE_FILES = [
    Path('data/analytics_cache.json'),
    Path('data/supabase_analytics_cache.json'),
]
SUPABASE_TABLE_CANDIDATES = [
    'event_snapshots',
    'events',
    'event_history',
    'dashboard_events',
    'dashboard_event_snapshots',
]

BLOCKING_TERMS = (
    'interdit', 'bloque', 'bloqueio', 'fechad', 'pista interditada', 'pista bloqueada',
    'rodovia interditada', 'rodovia bloqueada', 'faixa interditada', 'faixa bloqueada',
    'trânsito bloqueado', 'transito bloqueado', 'tráfego bloqueado', 'trafego bloqueado',
    'queda de barreira', 'deslizamento', 'rodovia fechada', 'pista fechada',
)


def now_iso() -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def read_json(path: Path, fallback: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding='utf-8') or 'null')
    except Exception:
        pass
    return fallback


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def safe_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except Exception:
        return 0


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace('Z', '+00:00')
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def severity_from_risk(risk: Any) -> str:
    value = safe_int(risk)
    if value >= 80:
        return 'Crítico'
    if value >= 60:
        return 'Alto'
    if value >= 35:
        return 'Moderado'
    if value >= 1:
        return 'Baixo'
    return 'Sem risco'


def normalized_source_type(row: dict[str, Any]) -> str:
    return str(row.get('source_type') or row.get('type') or '').strip().lower()


def text_blob(row: dict[str, Any]) -> str:
    keys = (
        'event_type', 'eventType', 'category', 'name', 'description', 'summary', 'headline',
        'road', 'corridor', 'source', 'sourceProvider', 'provider',
    )
    return ' '.join(str(row.get(key) or '') for key in keys).casefold()


def is_road_blocking_event(row: dict[str, Any]) -> bool:
    source_type = normalized_source_type(row)
    if source_type == 'road':
        return True
    blob = text_blob(row)
    has_road = bool(row.get('road') or 'rodovia' in blob or 'br-' in blob or 'br ' in blob)
    has_blocking = any(term.casefold() in blob for term in BLOCKING_TERMS)
    return has_road and has_blocking


def reclassify_row(row: dict[str, Any]) -> bool:
    if not isinstance(row, dict) or not is_road_blocking_event(row):
        return False
    changed = False
    current_risk = safe_int(row.get('risk'))
    if current_risk > MAX_ROAD_BLOCKING_RISK:
        row['risk'] = MAX_ROAD_BLOCKING_RISK
        changed = True
    if str(row.get('severity') or '').strip().casefold() in {'crítico', 'critico', 'critical'} or changed:
        row['severity'] = ROAD_HIGH_SEVERITY if safe_int(row.get('risk')) >= 60 else severity_from_risk(row.get('risk'))
        changed = True
    row['severityRule'] = f'Eventos rodoviários de bloqueio/interdição têm teto {MAX_ROAD_BLOCKING_RISK} ({ROAD_HIGH_SEVERITY}).'
    return changed


def count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or 'Sem classificação')
        out[value] = out.get(value, 0) + 1
    return dict(sorted(out.items(), key=lambda item: item[1], reverse=True))


def event_dt(row: dict[str, Any]) -> datetime | None:
    return parse_dt(row.get('last_seen_at') or row.get('snapshot_at') or row.get('updated_at') or row.get('created_at'))


def filter_days(rows: list[dict[str, Any]], days: int) -> list[dict[str, Any]]:
    cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
    out = []
    for row in rows:
        dt = event_dt(row)
        if not dt or dt.timestamp() >= cutoff:
            out.append(row)
    return out


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


def rebuild_cache_windows(cache: dict[str, Any]) -> None:
    rows = cache.get('rows')
    if not isinstance(rows, list):
        return
    compact_rows = [row for row in rows if isinstance(row, dict)]
    windows: dict[str, Any] = {}
    for days in (7, 30, 90):
        subset = filter_days(compact_rows, days)
        risks = [safe_int(row.get('risk')) for row in subset]
        climate = [row for row in subset if str(row.get('source_type') or row.get('type') or '') == 'climate']
        rainy = [row for row in climate if safe_int(row.get('precipitation')) > 0 or 'chuva' in text_blob(row)]
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
    cache['windows'] = windows
    cache['roadSeverityRule'] = f'Eventos rodoviários de bloqueio/interdição têm teto {MAX_ROAD_BLOCKING_RISK} ({ROAD_HIGH_SEVERITY}).'
    cache['updatedAt'] = now_iso()


def reclassify_local_json() -> dict[str, Any]:
    summary = {'files': [], 'rowsChanged': 0}
    for path in LOCAL_JSON_FILES:
        data = read_json(path, [])
        if not isinstance(data, list):
            continue
        changed = 0
        for row in data:
            if isinstance(row, dict) and reclassify_row(row):
                changed += 1
        if changed:
            write_json(path, data)
        summary['files'].append({'path': str(path), 'rowsChanged': changed})
        summary['rowsChanged'] += changed
    return summary


def reclassify_local_caches() -> dict[str, Any]:
    summary = {'files': [], 'rowsChanged': 0}
    for path in LOCAL_CACHE_FILES:
        cache = read_json(path, {})
        if not isinstance(cache, dict):
            continue
        rows = cache.get('rows')
        if not isinstance(rows, list):
            continue
        changed = 0
        for row in rows:
            if isinstance(row, dict) and reclassify_row(row):
                changed += 1
        if changed:
            rebuild_cache_windows(cache)
            write_json(path, cache)
        summary['files'].append({'path': str(path), 'rowsChanged': changed})
        summary['rowsChanged'] += changed
    return summary


def webapp_cleanup_payload() -> dict[str, Any]:
    return {
        'key': SHEETS_WEBAPP_KEY,
        'action': 'reclassify_road_severity',
        'operation': 'cap_road_blocking_severity',
        'max_road_blocking_risk': MAX_ROAD_BLOCKING_RISK,
        'maxRoadBlockingRisk': MAX_ROAD_BLOCKING_RISK,
        'severity': ROAD_HIGH_SEVERITY,
        'source_type': 'road',
        'sourceType': 'road',
    }


def post_sheets_reclassify() -> dict[str, Any]:
    if not SHEETS_WEBAPP_URL or not SHEETS_WEBAPP_KEY:
        return {'configured': False, 'ok': False, 'note': 'SHEETS_WEBAPP_URL e/ou SHEETS_WEBAPP_KEY ausentes.'}
    data = json.dumps(webapp_cleanup_payload(), ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        SHEETS_WEBAPP_URL,
        data=data,
        headers={'Content-Type': 'application/json', 'User-Agent': 'github-actions-road-severity-reclassify/1.0'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            raw = response.read().decode('utf-8')
            payload = json.loads(raw) if raw else {'ok': True, 'emptyResponse': True}
            if not isinstance(payload, dict):
                payload = {'ok': True, 'response': payload}
            payload['configured'] = True
            if not payload.get('ok'):
                payload.setdefault('note', 'O Web App respondeu, mas não confirmou ok=true. Talvez falte implementar action=reclassify_road_severity no Apps Script.')
            return payload
    except urllib.error.HTTPError as exc:
        body = ''
        try:
            body = exc.read().decode('utf-8')[:1000]
        except Exception:
            pass
        return {'configured': True, 'ok': False, 'error': f'HTTP {exc.code}: {body or exc}'}
    except Exception as exc:
        return {'configured': True, 'ok': False, 'error': str(exc)}


def supabase_headers(prefer_count: bool = False) -> dict[str, str]:
    headers = {
        'Content-Type': 'application/json',
        'apikey': SUPABASE_SERVICE_ROLE_KEY,
        'Authorization': f'Bearer {SUPABASE_SERVICE_ROLE_KEY}',
        'User-Agent': 'github-actions-road-severity-reclassify/1.0',
    }
    if prefer_count:
        headers['Prefer'] = 'return=minimal,count=exact'
    return headers


def supabase_request(url: str, method: str = 'GET', payload: Any | None = None, prefer_count: bool = False) -> tuple[int, Any, dict[str, str]]:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=supabase_headers(prefer_count=prefer_count), method=method)
    with urllib.request.urlopen(req, timeout=60) as response:
        raw = response.read().decode('utf-8')
        parsed = None
        if raw:
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = raw
        return response.status, parsed, dict(response.headers)


def parse_content_range(headers: dict[str, str]) -> int | None:
    value = headers.get('Content-Range') or headers.get('content-range') or ''
    if '/' not in value:
        return None
    total = value.rsplit('/', 1)[-1]
    if total == '*':
        return None
    try:
        return int(total)
    except Exception:
        return None


def patch_supabase_table(table: str) -> dict[str, Any]:
    query = urllib.parse.urlencode({'source_type': 'eq.road', 'risk': f'gt.{MAX_ROAD_BLOCKING_RISK}'})
    url = f'{SUPABASE_URL}/rest/v1/{table}?{query}'
    payloads = [
        {'risk': MAX_ROAD_BLOCKING_RISK, 'severity': ROAD_HIGH_SEVERITY},
        {'risk': MAX_ROAD_BLOCKING_RISK},
    ]
    last_error = None
    for payload in payloads:
        try:
            _, _, headers = supabase_request(url, method='PATCH', payload=payload, prefer_count=True)
            return {'table': table, 'ok': True, 'payloadKeys': list(payload.keys()), 'updatedRows': parse_content_range(headers)}
        except urllib.error.HTTPError as exc:
            body = ''
            try:
                body = exc.read().decode('utf-8')[:500]
            except Exception:
                pass
            last_error = f'HTTP {exc.code}: {body or exc}'
            if exc.code not in (400, 404):
                break
        except Exception as exc:
            last_error = str(exc)
            break
    return {'table': table, 'ok': False, 'error': last_error}


def fetch_supabase_recent(limit: int = 2500) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({'select': '*', 'order': 'last_seen_at.desc', 'limit': str(limit)})
    url = f'{SUPABASE_URL}/rest/v1/dashboard_events_recent?{query}'
    _, payload, _ = supabase_request(url)
    return payload if isinstance(payload, list) else []


def normalize_supabase_row(row: dict[str, Any]) -> dict[str, Any]:
    stable = row.get('stable_event_id') or row.get('event_id') or ''
    out = {
        'event_id': stable,
        'stable_event_id': stable,
        'observation_hash': row.get('current_observation_hash') or row.get('observation_hash') or '',
        'snapshot_bucket': row.get('snapshot_bucket') or '',
        'snapshot_at': row.get('last_seen_at') or row.get('snapshot_at') or row.get('updated_at') or now_iso(),
        'first_seen_at': row.get('first_seen_at') or '',
        'last_seen_at': row.get('last_seen_at') or '',
        'updated_at': row.get('updated_at') or '',
        'source_type': row.get('source_type') or row.get('type') or '',
        'category': row.get('category') or '',
        'event_type': row.get('event_type') or row.get('eventType') or '',
        'name': row.get('name') or '',
        'risk': safe_int(row.get('risk')),
        'severity': row.get('severity') or severity_from_risk(row.get('risk')),
        'lat': row.get('lat'),
        'lon': row.get('lon'),
        'city': row.get('city') or '',
        'state': row.get('state') or '',
        'region': row.get('region') or '',
        'road': row.get('road') or '',
        'description': row.get('description') or '',
        'source': row.get('source') or '',
        'source_url': row.get('source_url') or row.get('sourceUrl') or '',
        'total_snapshots': safe_int(row.get('total_snapshots')),
        'estimated_hours': row.get('estimated_hours') or 0,
        'active': row.get('active'),
        'storage': 'supabase',
    }
    reclassify_row(out)
    return out


def build_cache(rows: list[dict[str, Any]], source: str) -> dict[str, Any]:
    cache = {
        'updatedAt': now_iso(),
        'source': source,
        'storageMode': 'permanent_history' if source == 'supabase' else 'local_cache',
        'rows': rows[:2500],
        'windows': {},
        'roadSeverityRule': f'Eventos rodoviários de bloqueio/interdição têm teto {MAX_ROAD_BLOCKING_RISK} ({ROAD_HIGH_SEVERITY}).',
    }
    rebuild_cache_windows(cache)
    return cache


def reclassify_supabase() -> dict[str, Any]:
    summary: dict[str, Any] = {
        'configured': bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY),
        'tables': [],
        'cacheRows': 0,
        'cacheWritten': False,
        'error': None,
    }
    if not summary['configured']:
        summary['error'] = 'SUPABASE_URL e/ou SUPABASE_SERVICE_ROLE_KEY ausentes.'
        return summary
    for table in SUPABASE_TABLE_CANDIDATES:
        summary['tables'].append(patch_supabase_table(table))
    try:
        rows = [normalize_supabase_row(row) for row in fetch_supabase_recent()]
        cache = build_cache(rows, 'supabase')
        write_json(Path('data/supabase_analytics_cache.json'), cache)
        write_json(Path('data/analytics_cache.json'), cache)
        summary['cacheRows'] = len(rows)
        summary['cacheWritten'] = True
    except Exception as exc:
        summary['error'] = str(exc)
    return summary


def main() -> None:
    status: dict[str, Any] = {
        'updatedAt': now_iso(),
        'maxRoadBlockingRisk': MAX_ROAD_BLOCKING_RISK,
        'severityCap': ROAD_HIGH_SEVERITY,
        'rule': 'Eventos de bloqueio/interdição de rodovia não podem passar de severidade Alta.',
        'localJson': {},
        'localCaches': {},
        'googleSheets': {},
        'supabase': {},
    }
    status['localJson'] = reclassify_local_json()
    status['localCaches'] = reclassify_local_caches()
    status['googleSheets'] = post_sheets_reclassify()
    status['supabase'] = reclassify_supabase()
    write_json(STATUS_OUTPUT, status)
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
