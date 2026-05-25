#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATUS_OUTPUT = Path('data/road_news_dedupe_status.json')
EVENT_FILES = [Path('data/road_events.json'), Path('data/manual_events.json')]
CACHE_FILES = [Path('data/analytics_cache.json'), Path('data/supabase_analytics_cache.json')]
ROAD_RE = re.compile(r'\b(BR|SP|MG|RJ|ES|PR|SC|RS|MS|MT|GO|DF|BA|PE|CE|RN|PB|AL|SE|PI|MA|PA|AM|RO|RR|AP|AC|TO)-?\s?(\d{2,4})\b', re.I)
NEWS_RE = re.compile(r'noticias publicas|noticias públicas|noticia publica|notícia pública|google news|gdelt|fonte publica|fonte pública', re.I)
OFFICIAL = ('gov.br', 'dnit', 'antt', 'prf', 'defesa civil')
NATIONAL = ('g1', 'globo', 'folha', 'estadao', 'uol', 'r7', 'cnn', 'band')


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


def text(value: Any) -> str:
    return str(value or '').strip()


def safe_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except Exception:
        return 0


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    raw = text(value).replace('Z', '+00:00')
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def road_code(row: dict[str, Any]) -> str:
    blob = ' '.join(text(row.get(k)) for k in ('road', 'name', 'description', 'headline'))
    match = ROAD_RE.search(blob)
    if match:
        return f'{match.group(1).upper()}-{match.group(2)}'
    return text(row.get('road') or 'rodovia').upper().replace(' ', '')


def row_blob(row: dict[str, Any]) -> str:
    keys = ('source_type', 'type', 'source', 'sourceProvider', 'provider', 'event_type', 'eventType', 'name', 'description', 'headline', 'road', 'corridor')
    return ' '.join(text(row.get(k)) for k in keys)


def is_public_road_news(row: dict[str, Any]) -> bool:
    blob = row_blob(row)
    source_type = text(row.get('source_type') or row.get('type')).lower()
    if source_type != 'road' and not ROAD_RE.search(blob):
        return False
    return bool(NEWS_RE.search(blob))


def day_key(row: dict[str, Any]) -> str:
    dt = parse_dt(row.get('newsDate') or row.get('snapshot_at') or row.get('last_seen_at') or row.get('updated_at') or row.get('updatedAt'))
    return dt.date().isoformat() if dt else 'sem-data'


def loc_key(row: dict[str, Any]) -> str:
    parts = [text(row.get('region')), text(row.get('state')), text(row.get('city'))]
    try:
        parts.append(f"{round(float(row.get('lat')), 1)},{round(float(row.get('lon')), 1)}")
    except Exception:
        pass
    return '|'.join(p for p in parts if p) or 'sem-local'


def group_key(row: dict[str, Any]) -> str:
    return '|'.join([road_code(row), loc_key(row), day_key(row)])


def source_rank(source: str, url: str) -> int:
    hay = f'{source} {url}'.casefold()
    if any(x in hay for x in OFFICIAL):
        return 100
    if any(x in hay for x in NATIONAL):
        return 80
    if 'portal' in hay or 'noticias' in hay or 'notícias' in hay:
        return 55
    return 40


def source_item(row: dict[str, Any]) -> dict[str, Any]:
    source = text(row.get('source') or row.get('sourceProvider') or row.get('provider') or 'Fonte pública')
    url = text(row.get('source_url') or row.get('sourceUrl'))
    headline = text(row.get('headline') or row.get('description') or row.get('name'))[:240]
    date = text(row.get('newsDate') or row.get('updated_at') or row.get('updatedAt') or row.get('snapshot_at'))
    return {'source': source, 'url': url, 'headline': headline, 'date': date, '_rank': source_rank(source, url)}


def collect_sources(row: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    raw = row.get('sources') or row.get('sourceList') or []
    if isinstance(raw, list):
        for src in raw:
            if isinstance(src, dict):
                items.append({
                    'source': text(src.get('source') or src.get('name') or src.get('provider') or 'Fonte pública'),
                    'url': text(src.get('url') or src.get('source_url') or src.get('sourceUrl')),
                    'headline': text(src.get('headline') or src.get('title') or src.get('description'))[:240],
                    'date': text(src.get('date') or src.get('published') or src.get('newsDate')),
                    '_rank': safe_int(src.get('_rank')),
                })
    items.append(source_item(row))
    dedup: dict[str, dict[str, Any]] = {}
    for item in items:
        key = item.get('url') or f"{item.get('source')}|{item.get('headline')}"
        if key not in dedup or safe_int(item.get('_rank')) > safe_int(dedup[key].get('_rank')):
            dedup[key] = item
    return sorted(dedup.values(), key=lambda x: (safe_int(x.get('_rank')), text(x.get('date'))), reverse=True)


def best_base(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return dict(max(rows, key=lambda r: (source_item(r)['_rank'], len(text(r.get('description') or r.get('headline'))), text(r.get('newsDate') or r.get('updated_at') or r.get('updatedAt')))))


def stable_id(row: dict[str, Any]) -> str:
    base = '|'.join([road_code(row), loc_key(row), day_key(row), text(row.get('event_type') or row.get('eventType') or 'road')])
    return hashlib.sha256(base.encode('utf-8')).hexdigest()[:24]


def merge_group(rows: list[dict[str, Any]]) -> dict[str, Any]:
    base = best_base(rows)
    all_sources: list[dict[str, Any]] = []
    for row in rows:
        all_sources.extend(collect_sources(row))
    dedup: dict[str, dict[str, Any]] = {}
    for item in all_sources:
        key = item.get('url') or f"{item.get('source')}|{item.get('headline')}"
        if key not in dedup or safe_int(item.get('_rank')) > safe_int(dedup[key].get('_rank')):
            dedup[key] = item
    sources = sorted(dedup.values(), key=lambda x: (safe_int(x.get('_rank')), text(x.get('date'))), reverse=True)
    primary = sources[0] if sources else source_item(base)
    names: list[str] = []
    for item in sources:
        name = text(item.get('source'))
        if name and name not in names:
            names.append(name)
    source_text = '; '.join(names[:6])
    if len(names) > 6:
        source_text += f'; +{len(names)-6} fonte(s)'
    desc = text(base.get('description') or base.get('headline') or base.get('name'))
    desc = re.sub(r'\s*Localização aproximada pelo corredor monitorado\.?', '', desc).strip()
    base['description'] = f'{desc}. Fontes consolidadas: {source_text}. Localização aproximada pelo corredor monitorado.' if desc else f'Evento consolidado a partir de {len(sources)} fonte(s): {source_text}. Localização aproximada pelo corredor monitorado.'
    base['source'] = text(primary.get('source')) if len(sources) == 1 else f"{text(primary.get('source'))} + {len(sources)-1} fonte(s)"
    base['sourceProvider'] = 'Noticias publicas consolidadas'
    base['source_url'] = text(primary.get('url') or base.get('source_url') or base.get('sourceUrl'))
    base['sourceUrl'] = base['source_url']
    base['headline'] = text(primary.get('headline') or base.get('headline'))
    base['sources'] = [{k: v for k, v in item.items() if k != '_rank'} for item in sources]
    base['sourceCount'] = len(sources)
    base['dedupedFrom'] = len(rows)
    base['duplicatePolicy'] = 'Noticias publicas da mesma situacao rodoviaria sao consolidadas em um unico evento.'
    sid = stable_id(base)
    base['stable_event_id'] = sid
    base['event_id'] = base.get('event_id') or sid
    base['risk'] = min(69, safe_int(base.get('risk')) or 69)
    base['severity'] = 'Alto' if safe_int(base.get('risk')) >= 60 else severity(base.get('risk'))
    return base


def dedupe_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    kept: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict) and is_public_road_news(row):
            groups.setdefault(group_key(row), []).append(row)
        else:
            kept.append(row)
    merged = [merge_group(group) for group in groups.values()]
    out = kept + merged
    out.sort(key=lambda row: (safe_int(row.get('risk')), text(row.get('newsDate') or row.get('snapshot_at') or row.get('last_seen_at') or row.get('updated_at') or row.get('updatedAt'))), reverse=True)
    return out, {
        'groups': len(groups),
        'roadNewsRows': sum(len(group) for group in groups.values()),
        'mergedRows': len(merged),
        'duplicatesRemoved': sum(max(0, len(group) - 1) for group in groups.values()),
        'multiSourceGroups': sum(1 for group in groups.values() if len(group) > 1),
    }


def event_dt(row: dict[str, Any]) -> datetime | None:
    return parse_dt(row.get('last_seen_at') or row.get('snapshot_at') or row.get('updated_at') or row.get('updatedAt'))


def filter_days(rows: list[dict[str, Any]], days: int) -> list[dict[str, Any]]:
    cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
    return [row for row in rows if not event_dt(row) or event_dt(row).timestamp() >= cutoff]


def count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        if key == 'source_type':
            value = text(row.get('source_type') or row.get('type')) or 'Sem classificacao'
        else:
            value = text(row.get(key)) or 'Sem classificacao'
        out[value] = out.get(value, 0) + 1
    return dict(sorted(out.items(), key=lambda item: item[1], reverse=True))


def daily_risk(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, list[int]] = {}
    for row in rows:
        dt = event_dt(row)
        key = dt.date().isoformat() if dt else 'sem-data'
        buckets.setdefault(key, []).append(safe_int(row.get('risk')))
    return [{'date': key, 'avgRisk': round(sum(values) / max(1, len(values))), 'events': len(values), 'maxRisk': max(values or [0])} for key, values in sorted(buckets.items())]


def rebuild_cache(cache: dict[str, Any]) -> None:
    rows = [row for row in cache.get('rows', []) if isinstance(row, dict)]
    windows: dict[str, Any] = {}
    for days in (7, 30, 90):
        subset = filter_days(rows, days)
        risks = [safe_int(row.get('risk')) for row in subset]
        climate = [row for row in subset if text(row.get('source_type') or row.get('type')) == 'climate']
        rainy = [row for row in climate if safe_int(row.get('precipitation')) > 0 or 'chuva' in row_blob(row).casefold()]
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
    cache['updatedAt'] = now_iso()
    cache['roadNewsDuplicatePolicy'] = 'Noticias publicas da mesma situacao rodoviaria sao consolidadas em um unico evento.'


def process_event_files() -> dict[str, Any]:
    result = {'files': [], 'duplicatesRemoved': 0}
    for path in EVENT_FILES:
        rows = read_json(path, [])
        if not isinstance(rows, list):
            continue
        deduped, stats = dedupe_rows([row for row in rows if isinstance(row, dict)])
        if stats['duplicatesRemoved'] or stats['multiSourceGroups']:
            write_json(path, deduped)
        result['files'].append({'path': str(path), **stats})
        result['duplicatesRemoved'] += stats['duplicatesRemoved']
    return result


def process_cache_files() -> dict[str, Any]:
    result = {'files': [], 'duplicatesRemoved': 0}
    for path in CACHE_FILES:
        cache = read_json(path, {})
        if not isinstance(cache, dict) or not isinstance(cache.get('rows'), list):
            continue
        deduped, stats = dedupe_rows([row for row in cache['rows'] if isinstance(row, dict)])
        cache['rows'] = deduped
        rebuild_cache(cache)
        if stats['duplicatesRemoved'] or stats['multiSourceGroups']:
            write_json(path, cache)
        result['files'].append({'path': str(path), **stats})
        result['duplicatesRemoved'] += stats['duplicatesRemoved']
    return result


def main() -> None:
    status = {
        'updatedAt': now_iso(),
        'policy': 'Consolidar noticias publicas duplicadas de uma mesma situacao rodoviaria em evento unico com lista de fontes.',
        'eventFiles': process_event_files(),
        'cacheFiles': process_cache_files(),
    }
    write_json(STATUS_OUTPUT, status)
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
