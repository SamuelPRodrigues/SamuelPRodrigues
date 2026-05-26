#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

INPUT = Path('data/road_events.json')
STATUS_OUTPUT = Path('data/road_news_freshness_status.json')
LOOKBACK_HOURS = float(os.environ.get('NEWS_PUBLIC_LOOKBACK_HOURS', '12'))
BR_TZ = timezone(timedelta(hours=-3))
NEWS_RE = re.compile(r'not[ií]cias? p[uú]blicas?|google news|gdelt|fonte p[uú]blica|noticia publica|notícia pública', re.I)
RELEASE_RE = re.compile(r'liberad|normalizad|reabert|sem bloqueio|sem interdi[cç][aã]o|fluxo normal|volta ao normal', re.I)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_utc().strftime('%Y-%m-%dT%H:%M:%SZ')


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


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    raw = text(value)
    try:
        dt = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    try:
        import email.utils
        dt = email.utils.parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=BR_TZ)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def event_blob(event: dict[str, Any]) -> str:
    keys = ('source', 'sourceProvider', 'provider', 'eventType', 'event_type', 'name', 'description', 'headline', 'sourceUrl', 'source_url')
    return ' '.join(text(event.get(key)) for key in keys)


def is_public_news_event(event: dict[str, Any]) -> bool:
    return bool(NEWS_RE.search(event_blob(event)))


def event_date(event: dict[str, Any]) -> datetime | None:
    for key in ('newsDate', 'published', 'updatedAt', 'updated_at', 'last_seen_at', 'snapshot_at'):
        dt = parse_dt(event.get(key))
        if dt:
            return dt
    return None


def planned_window_active(event: dict[str, Any]) -> bool:
    end = parse_dt(event.get('plannedEndAt'))
    start = parse_dt(event.get('plannedStartAt'))
    now = now_utc()
    if end and now <= end and (not start or now >= start):
        event['active'] = True
        event['lifecycle_status'] = 'active_planned_closure'
        event['newsFreshnessRule'] = 'Evento preservado porque a notícia informa período de interdição ainda vigente.'
        return True
    if start and now < start:
        event['active'] = False
        event['lifecycle_status'] = 'scheduled'
        event['newsFreshnessRule'] = 'Evento planejado preservado, mas ainda fora do horário de início.'
        return True
    return False


def main() -> None:
    events = read_json(INPUT, [])
    if not isinstance(events, list):
        events = []
    cutoff = now_utc() - timedelta(hours=LOOKBACK_HOURS)
    kept: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    release_like = 0
    undated = 0
    planned_preserved = 0

    for event in events:
        if not isinstance(event, dict):
            continue
        if not is_public_news_event(event):
            kept.append(event)
            continue
        blob = event_blob(event)
        if RELEASE_RE.search(blob):
            release_like += 1
            removed.append({
                'name': event.get('name'),
                'road': event.get('road'),
                'source': event.get('source'),
                'reason': 'release_like_public_news',
                'date': event.get('newsDate') or event.get('updatedAt') or event.get('updated_at'),
            })
            continue
        if planned_window_active(event):
            planned_preserved += 1
            kept.append(event)
            continue
        dt = event_date(event)
        if not dt:
            undated += 1
            removed.append({
                'name': event.get('name'),
                'road': event.get('road'),
                'source': event.get('source'),
                'reason': 'public_news_without_reliable_date',
                'date': event.get('newsDate') or event.get('updatedAt') or event.get('updated_at'),
            })
            continue
        if dt < cutoff:
            removed.append({
                'name': event.get('name'),
                'road': event.get('road'),
                'source': event.get('source'),
                'reason': f'public_news_older_than_{LOOKBACK_HOURS:g}h',
                'date': dt.strftime('%Y-%m-%dT%H:%M:%SZ'),
            })
            continue
        event['newsFreshnessHours'] = round((now_utc() - dt).total_seconds() / 3600, 2)
        event['newsFreshnessRule'] = f'Notícias públicas rodoviárias só ficam ativas se tiverem até {LOOKBACK_HOURS:g}h, exceto interdições planejadas dentro do período informado.'
        kept.append(event)

    if len(kept) != len(events):
        write_json(INPUT, kept)
    status = {
        'updatedAt': now_iso(),
        'lookbackHours': LOOKBACK_HOURS,
        'inputEvents': len(events),
        'keptEvents': len(kept),
        'removedEvents': len(removed),
        'plannedWindowPreserved': planned_preserved,
        'releaseLikeRemoved': release_like,
        'undatedRemoved': undated,
        'removedSample': removed[:25],
        'policy': 'Notícias públicas antigas não reconfirmam eventos, exceto interdições planejadas com plannedEndAt ainda vigente.',
    }
    write_json(STATUS_OUTPUT, status)
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
