#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATUS_OUTPUT = Path('data/google_sheets_cleanup_status.json')
DEFAULT_SPREADSHEET_ID = '1d6NXWJzyK08tH0lYdVUo1bn8BMlyQPDEICG37Mnfgqo'
DEFAULT_SHEET_GID = '2041905510'
SPREADSHEET_ID = os.environ.get('SHEETS_CLEANUP_SPREADSHEET_ID', DEFAULT_SPREADSHEET_ID).strip()
SHEET_GID = os.environ.get('SHEETS_CLEANUP_GID', DEFAULT_SHEET_GID).strip()
CUTOFF_UTC = os.environ.get('CLEANUP_CUTOFF_UTC', '2026-05-25T16:21:57Z').strip()
DRY_RUN = os.environ.get('DRY_RUN', 'true').strip().lower() in {'1', 'true', 'yes', 'sim'}
CONFIRM_DELETE = os.environ.get('CONFIRM_DELETE', '').strip()
SERVICE_ACCOUNT_JSON = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON', '').strip()
HEADER_SCAN_ROWS = int(os.environ.get('HEADER_SCAN_ROWS', '8'))
DATE_HEADERS = [
    'snapshot_at', 'last_seen_at', 'updated_at', 'created_at', 'time', 'newsDate', 'news_date',
    'data', 'date', 'timestamp', 'generated_at', 'first_seen_at'
]


def now_iso() -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    # Tenta ISO primeiro.
    cleaned = text.replace('Z', '+00:00')
    try:
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    # Tenta formatos comuns em pt-BR/planilhas.
    for fmt in ('%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%d/%m/%Y', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            dt = datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            continue
    return None


def parse_cutoff(value: str) -> datetime:
    dt = parse_dt(value)
    if not dt:
        raise ValueError(f'Não foi possível interpretar CLEANUP_CUTOFF_UTC={value!r}')
    return dt


def normalize_header(value: Any) -> str:
    text = str(value or '').strip()
    text = text.replace(' ', '_').replace('-', '_')
    return re.sub(r'[^A-Za-z0-9_]', '', text).lower()


def get_service():
    if not SERVICE_ACCOUNT_JSON:
        raise RuntimeError('GOOGLE_SERVICE_ACCOUNT_JSON não está configurado nos Secrets do GitHub.')
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except Exception as exc:
        raise RuntimeError(f'Dependências Google não instaladas: {exc}') from exc

    try:
        info = json.loads(SERVICE_ACCOUNT_JSON)
    except Exception as exc:
        raise RuntimeError(f'GOOGLE_SERVICE_ACCOUNT_JSON não é um JSON válido: {exc}') from exc

    scopes = ['https://www.googleapis.com/auth/spreadsheets']
    creds = service_account.Credentials.from_service_account_info(info, scopes=scopes)
    return build('sheets', 'v4', credentials=creds, cache_discovery=False), info.get('client_email', '')


def sheet_metadata(service) -> dict[str, Any]:
    return service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()


def sheet_by_gid(metadata: dict[str, Any]) -> dict[str, Any]:
    for sheet in metadata.get('sheets', []):
        props = sheet.get('properties', {})
        if str(props.get('sheetId')) == str(SHEET_GID):
            return props
    available = [f"{s.get('properties', {}).get('title')} ({s.get('properties', {}).get('sheetId')})" for s in metadata.get('sheets', [])]
    raise RuntimeError(f'Não encontrei aba com gid={SHEET_GID}. Abas disponíveis: {available}')


def values_for_sheet(service, title: str) -> list[list[Any]]:
    response = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"'{title}'",
        majorDimension='ROWS',
    ).execute()
    return response.get('values', [])


def find_header(values: list[list[Any]]) -> tuple[int, list[str]]:
    best_index = 0
    best_score = -1
    best_headers: list[str] = []
    for i, row in enumerate(values[:HEADER_SCAN_ROWS]):
        headers = [normalize_header(cell) for cell in row]
        score = sum(1 for h in headers if h in DATE_HEADERS or h in {'event_id', 'stable_event_id', 'source_type', 'risk', 'severity', 'region'})
        if score > best_score:
            best_index, best_score, best_headers = i, score, headers
    if best_score <= 0:
        raise RuntimeError('Não consegui detectar a linha de cabeçalho da aba.')
    return best_index, best_headers


def date_column_indexes(headers: list[str]) -> list[int]:
    preferred = []
    for name in DATE_HEADERS:
        if name in headers:
            preferred.append(headers.index(name))
    return preferred


def rows_to_delete(values: list[list[Any]], header_index: int, headers: list[str], cutoff: datetime) -> list[dict[str, Any]]:
    date_indexes = date_column_indexes(headers)
    if not date_indexes:
        raise RuntimeError(f'Não encontrei coluna de data. Cabeçalhos detectados: {headers}')

    out: list[dict[str, Any]] = []
    for zero_index, row in enumerate(values):
        if zero_index <= header_index:
            continue
        row_number = zero_index + 1
        parsed_dt = None
        parsed_column = None
        raw_value = ''
        for idx in date_indexes:
            raw_value = row[idx] if idx < len(row) else ''
            parsed_dt = parse_dt(raw_value)
            if parsed_dt:
                parsed_column = headers[idx]
                break
        if parsed_dt and parsed_dt < cutoff:
            out.append({
                'rowNumber': row_number,
                'zeroIndex': zero_index,
                'dateColumn': parsed_column,
                'dateValue': str(raw_value),
                'parsedUtc': parsed_dt.strftime('%Y-%m-%dT%H:%M:%SZ'),
            })
    return out


def delete_rows(service, sheet_id: int, deletions: list[dict[str, Any]]) -> int:
    if not deletions:
        return 0
    # Deleta de baixo para cima para não deslocar índices ainda pendentes.
    requests = []
    for item in sorted(deletions, key=lambda x: int(x['zeroIndex']), reverse=True):
        idx = int(item['zeroIndex'])
        requests.append({
            'deleteDimension': {
                'range': {
                    'sheetId': sheet_id,
                    'dimension': 'ROWS',
                    'startIndex': idx,
                    'endIndex': idx + 1,
                }
            }
        })
    # Google aceita lote; particiona para evitar payload muito grande.
    total = 0
    for start in range(0, len(requests), 200):
        chunk = requests[start:start + 200]
        service.spreadsheets().batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body={'requests': chunk},
        ).execute()
        total += len(chunk)
    return total


def main() -> None:
    status: dict[str, Any] = {
        'updatedAt': now_iso(),
        'spreadsheetId': SPREADSHEET_ID,
        'gid': SHEET_GID,
        'cutoffUtc': None,
        'dryRun': DRY_RUN,
        'confirmed': CONFIRM_DELETE == 'DELETE_OLD_EVENTS',
        'serviceAccountEmail': '',
        'sheetTitle': '',
        'headerRowNumber': None,
        'dateColumnsDetected': [],
        'rowsScanned': 0,
        'rowsMatched': 0,
        'rowsDeleted': 0,
        'sampleMatchedRows': [],
        'error': None,
    }

    try:
        cutoff = parse_cutoff(CUTOFF_UTC)
        status['cutoffUtc'] = cutoff.strftime('%Y-%m-%dT%H:%M:%SZ')
        if not DRY_RUN and not status['confirmed']:
            raise RuntimeError('Para apagar de verdade, defina CONFIRM_DELETE=DELETE_OLD_EVENTS. Use DRY_RUN=true para simular.')

        service, email = get_service()
        status['serviceAccountEmail'] = email
        metadata = sheet_metadata(service)
        props = sheet_by_gid(metadata)
        title = props['title']
        sheet_id = int(props['sheetId'])
        status['sheetTitle'] = title

        values = values_for_sheet(service, title)
        status['rowsScanned'] = max(0, len(values) - 1)
        header_index, headers = find_header(values)
        status['headerRowNumber'] = header_index + 1
        status['dateColumnsDetected'] = [headers[i] for i in date_column_indexes(headers)]
        matched = rows_to_delete(values, header_index, headers, cutoff)
        status['rowsMatched'] = len(matched)
        status['sampleMatchedRows'] = matched[:20]
        if not DRY_RUN:
            status['rowsDeleted'] = delete_rows(service, sheet_id, matched)
    except Exception as exc:
        status['error'] = str(exc)

    write_json(STATUS_OUTPUT, status)
    print(json.dumps(status, ensure_ascii=False, indent=2))
    if status['error']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
