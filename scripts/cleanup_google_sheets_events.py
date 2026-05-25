#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATUS_OUTPUT = Path('data/google_sheets_cleanup_status.json')
WEBAPP_URL = os.environ.get('SHEETS_WEBAPP_URL', '').strip()
WEBAPP_KEY = os.environ.get('SHEETS_WEBAPP_KEY', '').strip()
DEFAULT_SPREADSHEET_ID = '1d6NXWJzyK08tH0lYdVUo1bn8BMlyQPDEICG37Mnfgqo'
DEFAULT_SHEET_GID = '2041905510'
SPREADSHEET_ID = os.environ.get('SHEETS_CLEANUP_SPREADSHEET_ID', DEFAULT_SPREADSHEET_ID).strip()
SHEET_GID = os.environ.get('SHEETS_CLEANUP_GID', DEFAULT_SHEET_GID).strip()
CUTOFF_UTC = os.environ.get('CLEANUP_CUTOFF_UTC', '2026-05-25T16:21:57Z').strip()
DRY_RUN = os.environ.get('DRY_RUN', 'true').strip().lower() in {'1', 'true', 'yes', 'sim'}
CONFIRM_DELETE = os.environ.get('CONFIRM_DELETE', '').strip()


def now_iso() -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def parse_cutoff(value: str) -> str:
    text = value.strip().replace('Z', '+00:00')
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def post_to_webapp(payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        WEBAPP_URL,
        data=data,
        headers={'Content-Type': 'application/json', 'User-Agent': 'github-actions-sheets-cleanup/1.0'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=90) as response:
        raw = response.read().decode('utf-8')
        if not raw:
            return {'ok': True, 'emptyResponse': True}
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {'ok': True, 'response': parsed}
        except Exception:
            return {'ok': False, 'rawResponse': raw[:1000]}


def cleanup_payload(cutoff: str) -> dict[str, Any]:
    return {
        'key': WEBAPP_KEY,
        'action': 'cleanup',
        'operation': 'delete_before_cutoff',
        'cutoff_utc': cutoff,
        'cutoffUtc': cutoff,
        'dry_run': DRY_RUN,
        'dryRun': DRY_RUN,
        'confirm_delete': CONFIRM_DELETE,
        'confirmDelete': CONFIRM_DELETE,
        'spreadsheet_id': SPREADSHEET_ID,
        'spreadsheetId': SPREADSHEET_ID,
        'sheet_gid': SHEET_GID,
        'sheetGid': SHEET_GID,
    }


def main() -> None:
    status: dict[str, Any] = {
        'updatedAt': now_iso(),
        'configured': bool(WEBAPP_URL and WEBAPP_KEY),
        'authMode': 'SHEETS_WEBAPP_URL + SHEETS_WEBAPP_KEY',
        'spreadsheetId': SPREADSHEET_ID,
        'gid': SHEET_GID,
        'cutoffUtc': None,
        'dryRun': DRY_RUN,
        'confirmed': CONFIRM_DELETE == 'DELETE_OLD_EVENTS',
        'webappResponse': None,
        'rowsMatched': 0,
        'rowsDeleted': 0,
        'error': None,
        'note': None,
    }

    try:
        cutoff = parse_cutoff(CUTOFF_UTC)
        status['cutoffUtc'] = cutoff
        if not WEBAPP_URL or not WEBAPP_KEY:
            raise RuntimeError('SHEETS_WEBAPP_URL e/ou SHEETS_WEBAPP_KEY não configurados nos Secrets do GitHub.')
        if not DRY_RUN and not status['confirmed']:
            raise RuntimeError('Para apagar de verdade, defina CONFIRM_DELETE=DELETE_OLD_EVENTS. Use DRY_RUN=true para simular.')

        response = post_to_webapp(cleanup_payload(cutoff))
        status['webappResponse'] = response
        status['rowsMatched'] = int(response.get('rowsMatched') or response.get('matchedRows') or response.get('wouldDelete') or 0)
        status['rowsDeleted'] = int(response.get('rowsDeleted') or response.get('deletedRows') or 0)
        ok = bool(response.get('ok', False))
        if not ok:
            raise RuntimeError(
                'O Web App respondeu, mas não confirmou ok=true. '
                'Provavelmente a API da planilha ainda precisa implementar a ação cleanup/delete_before_cutoff. '
                f'Resposta: {json.dumps(response, ensure_ascii=False)[:800]}'
            )
        if response.get('unsupportedAction') or response.get('error'):
            raise RuntimeError(
                'A API da planilha não reconheceu a ação de limpeza. '
                'É preciso adicionar suporte a action=cleanup no Apps Script.'
            )
    except urllib.error.HTTPError as exc:
        body = ''
        try:
            body = exc.read().decode('utf-8')[:1000]
        except Exception:
            pass
        status['error'] = f'HTTP {exc.code}: {body or exc}'
    except Exception as exc:
        status['error'] = str(exc)

    if status['error'] and 'action=cleanup' in status['error']:
        status['note'] = 'A autenticação já foi trocada para a API existente; falta o Apps Script aceitar a operação de limpeza.'

    write_json(STATUS_OUTPUT, status)
    print(json.dumps(status, ensure_ascii=False, indent=2))
    if status['error']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
