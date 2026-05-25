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

STATUS_OUTPUT = Path('data/supabase_cleanup_status.json')
ANALYTICS_OUTPUT = Path('data/analytics_cache.json')
SUPABASE_CACHE_OUTPUT = Path('data/supabase_analytics_cache.json')
SUPABASE_URL = os.environ.get('SUPABASE_URL', '').strip().rstrip('/')
SUPABASE_SERVICE_ROLE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '').strip()
CUTOFF_UTC = os.environ.get('CLEANUP_CUTOFF_UTC', '2026-05-25T16:21:57Z').strip()
CONFIRM_DELETE = os.environ.get('CONFIRM_DELETE', '').strip()
DRY_RUN = os.environ.get('DRY_RUN', 'false').strip().lower() in {'1', 'true', 'yes', 'sim'}

# Tabelas prováveis do histórico permanente. O script tenta com segurança e registra quais existem.
TABLE_CANDIDATES = [
    {'table': 'event_snapshots', 'date_columns': ['snapshot_at', 'last_seen_at', 'updated_at', 'created_at']},
    {'table': 'events', 'date_columns': ['last_seen_at', 'updated_at', 'first_seen_at', 'created_at']},
    {'table': 'event_history', 'date_columns': ['snapshot_at', 'last_seen_at', 'updated_at', 'created_at']},
    {'table': 'dashboard_events', 'date_columns': ['last_seen_at', 'updated_at', 'created_at']},
    {'table': 'dashboard_event_snapshots', 'date_columns': ['snapshot_at', 'last_seen_at', 'updated_at', 'created_at']},
]


def now_iso() -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def parse_dt(value: str) -> datetime:
    text = value.strip().replace('Z', '+00:00')
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def headers(prefer_count: bool = False) -> dict[str, str]:
    out = {
        'Content-Type': 'application/json',
        'apikey': SUPABASE_SERVICE_ROLE_KEY,
        'Authorization': f'Bearer {SUPABASE_SERVICE_ROLE_KEY}',
        'User-Agent': 'github-actions-supabase-cleanup/1.0',
    }
    if prefer_count:
        out['Prefer'] = 'count=exact'
    return out


def request(url: str, method: str = 'GET', prefer_count: bool = False) -> tuple[int, Any, dict[str, str]]:
    req = urllib.request.Request(url, headers=headers(prefer_count=prefer_count), method=method)
    with urllib.request.urlopen(req, timeout=60) as response:
        raw = response.read().decode('utf-8')
        payload = None
        if raw:
            try:
                payload = json.loads(raw)
            except Exception:
                payload = raw
        return response.status, payload, dict(response.headers)


def rest_url(table: str, params: dict[str, str]) -> str:
    return f"{SUPABASE_URL}/rest/v1/{table}?{urllib.parse.urlencode(params)}"


def fetch_recent_count() -> int | None:
    try:
        _, payload, _ = request(rest_url('dashboard_events_recent', {'select': 'stable_event_id', 'limit': '1'}))
        if isinstance(payload, list):
            return len(payload)
    except Exception:
        return None
    return None


def count_old_rows(table: str, column: str, cutoff: str) -> int | None:
    url = rest_url(table, {'select': '*', column: f'lt.{cutoff}', 'limit': '1'})
    try:
        _, _, hdrs = request(url, prefer_count=True)
        content_range = hdrs.get('Content-Range') or hdrs.get('content-range') or ''
        if '/' in content_range:
            total = content_range.rsplit('/', 1)[-1]
            if total != '*':
                return int(total)
        return 0
    except urllib.error.HTTPError as exc:
        if exc.code in (400, 404):
            return None
        raise


def delete_old_rows(table: str, column: str, cutoff: str) -> int | None:
    count = count_old_rows(table, column, cutoff)
    if not count:
        return count
    if DRY_RUN:
        return count
    url = rest_url(table, {column: f'lt.{cutoff}'})
    request(url, method='DELETE', prefer_count=True)
    return count


def try_refresh_cache(status: dict[str, Any]) -> None:
    # Evita manter visualizações/caches antigos no site após a limpeza.
    empty_cache = {
        'updatedAt': now_iso(),
        'source': 'supabase_cleanup',
        'storageMode': 'permanent_history',
        'rows': [],
        'windows': {
            '7': {'events': 0, 'avgRisk': 0, 'maxRisk': 0, 'rainChance': 0, 'byType': {}, 'byRegion': {}, 'bySeverity': {}, 'dailyRisk': []},
            '30': {'events': 0, 'avgRisk': 0, 'maxRisk': 0, 'rainChance': 0, 'byType': {}, 'byRegion': {}, 'bySeverity': {}, 'dailyRisk': []},
            '90': {'events': 0, 'avgRisk': 0, 'maxRisk': 0, 'rainChance': 0, 'byType': {}, 'byRegion': {}, 'bySeverity': {}, 'dailyRisk': []},
        },
        'cleanup': status,
    }
    write_json(SUPABASE_CACHE_OUTPUT, empty_cache)
    write_json(ANALYTICS_OUTPUT, empty_cache)


def main() -> None:
    status: dict[str, Any] = {
        'updatedAt': now_iso(),
        'configured': bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY),
        'cutoffUtc': None,
        'dryRun': DRY_RUN,
        'confirmed': CONFIRM_DELETE == 'DELETE_OLD_EVENTS',
        'tablesChecked': [],
        'deletedOrMatchedRows': 0,
        'cacheReset': False,
        'error': None,
    }

    try:
        cutoff = iso_z(parse_dt(CUTOFF_UTC))
        status['cutoffUtc'] = cutoff
    except Exception as exc:
        status['error'] = f'CLEANUP_CUTOFF_UTC inválido: {exc}'
        write_json(STATUS_OUTPUT, status)
        raise SystemExit(1)

    if not status['configured']:
        status['error'] = 'SUPABASE_URL e/ou SUPABASE_SERVICE_ROLE_KEY não configurados nos Secrets.'
        write_json(STATUS_OUTPUT, status)
        raise SystemExit(1)

    if not DRY_RUN and not status['confirmed']:
        status['error'] = 'Para apagar de verdade, defina CONFIRM_DELETE=DELETE_OLD_EVENTS. Use DRY_RUN=true para simular.'
        write_json(STATUS_OUTPUT, status)
        raise SystemExit(1)

    try:
        status['dashboardRecentReachable'] = fetch_recent_count() is not None
        for candidate in TABLE_CANDIDATES:
            table = candidate['table']
            table_result = {'table': table, 'columns': [], 'matchedRows': 0, 'deletedRows': 0, 'exists': False}
            for column in candidate['date_columns']:
                matched = delete_old_rows(table, column, status['cutoffUtc'])
                if matched is None:
                    continue
                table_result['exists'] = True
                table_result['columns'].append({'column': column, 'matchedRows': matched, 'deletedRows': 0 if DRY_RUN else matched})
                table_result['matchedRows'] += int(matched or 0)
                table_result['deletedRows'] += 0 if DRY_RUN else int(matched or 0)
                # Se uma coluna existe e encontrou linhas, não tenta outras colunas da mesma tabela para evitar contagem duplicada.
                if matched:
                    break
            status['tablesChecked'].append(table_result)
            status['deletedOrMatchedRows'] += table_result['matchedRows'] if DRY_RUN else table_result['deletedRows']

        if not DRY_RUN:
            try_refresh_cache(status)
            status['cacheReset'] = True
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
