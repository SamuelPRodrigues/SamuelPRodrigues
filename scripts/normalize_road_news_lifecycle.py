#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROAD_EVENTS = Path('data/road_events.json')
STATE_FILE = Path('data/event_lifecycle_state.json')
DEACTIVATED_FILE = Path('data/deactivated_events.json')
STATUS_FILE = Path('data/road_news_lifecycle_normalize_status.json')
LOOKBACK_HOURS = float(os.environ.get('NEWS_PUBLIC_LOOKBACK_HOURS', '12'))
ROAD_NEWS_STALE_HOURS = float(os.environ.get('ROAD_NEWS_STALE_HOURS', '4'))
NEWS_RE = re.compile(r'not[ií]cias? p[uú]blicas?|google news|gdelt|fonte p[uú]blica|noticia publica|notícia pública', re.I)
ROAD_RE = re.compile(r'\b(BR|SP|MG|RJ|ES|PR|SC|RS|MS|MT|GO|DF|BA|PE|CE|RN|PB|AL|SE|PI|MA|PA|AM|RO|RR|AP|AC|TO)-?\s?(\d{2,4})\b', re.I)
TRACKING_RE = re.compile(r'\s*Rastreio:\s*primeiro registro em .*?(?:\.|$)', re.I | re.S)


def now_dt() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_dt().strftime('%Y-%m-%dT%H:%M:%SZ')


def text(value: Any) -> str:
    return str(value or '').strip()


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
        pass
    try:
        import email.utils
        dt = email.utils.parsedate_to_datetime(text(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def iso(dt: datetime | None) -> str:
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ') if dt else ''


def duration_hours(start: Any, end: Any = None) -> float:
    start_dt = parse_dt(start)
    end_dt = parse_dt(end) or now_dt()
    if not start_dt:
        return 0.0
    return round(max(0.0, (end_dt - start_dt).total_seconds() / 3600), 2)


def human_duration(hours: float) -> str:
    if hours < 1:
        return f'{round(hours * 60)} min'
    if hours < 48:
        return f'{hours:.1f} h'
    return f'{hours / 24:.1f} dias'


def event_blob(event: dict[str, Any]) -> str:
    keys = ('source_type', 'type', 'source', 'sourceProvider', 'provider', 'eventType', 'event_type', 'name', 'description', 'headline', 'road', 'corridor')
    return ' '.join(text(event.get(k)) for k in keys)


def is_public_road_news(event: dict[str, Any]) -> bool:
    blob = event_blob(event)
    source_type = text(event.get('source_type') or event.get('type')).lower()
    return (source_type == 'road' or bool(ROAD_RE.search(blob))) and bool(NEWS_RE.search(blob))


def event_key(event: dict[str, Any]) -> str:
    for key in ('stable_event_id', 'event_id', 'hash'):
        value = text(event.get(key))
        if value:
            return value
    import hashlib
    return hashlib.sha256(event_blob(event).encode('utf-8')).hexdigest()[:24]


def news_dt(event: dict[str, Any]) -> datetime | None:
    for key in ('newsDate', 'published', 'first_seen_at', 'updated_at', 'updatedAt', 'snapshot_at'):
        dt = parse_dt(event.get(key))
        if dt:
            return dt
    sources = event.get('sources') or []
    if isinstance(sources, list):
        dates = []
        for item in sources:
            if isinstance(item, dict):
                dt = parse_dt(item.get('date') or item.get('published') or item.get('newsDate'))
                if dt:
                    dates.append(dt)
        if dates:
            return min(dates)
    return None


def planned_window(event: dict[str, Any]) -> tuple[datetime | None, datetime | None]:
    return parse_dt(event.get('plannedStartAt')), parse_dt(event.get('plannedEndAt'))


def planned_window_keeps_event(event: dict[str, Any]) -> bool:
    start, end = planned_window(event)
    now = now_dt()
    if end and now <= end and (not start or now >= start):
        return True
    if start and now < start:
        return True
    return False


def clean_description(description: Any) -> str:
    desc = TRACKING_RE.sub('', text(description)).strip()
    return desc.rstrip()


def append_tracking(event: dict[str, Any], first_seen: str, hours: float) -> None:
    base = clean_description(event.get('description'))
    suffix = f'Rastreio: primeiro registro em {first_seen}; ativo há {human_duration(hours)}.'
    event['description'] = f'{base} {suffix}'.strip()


def deactivate_event(event: dict[str, Any], state_row: dict[str, Any], reason: str) -> dict[str, Any]:
    first_seen = state_row.get('first_seen_at') or event.get('first_seen_at') or iso(news_dt(event)) or now_iso()
    last_seen = state_row.get('last_seen_at') or event.get('last_seen_at') or first_seen
    hours = duration_hours(first_seen, last_seen)
    return {
        'event_id': event_key(event),
        'stable_event_id': event_key(event),
        'name': event.get('name') or event.get('road') or event.get('eventType') or 'Evento rodoviário',
        'type': 'road',
        'source_type': 'road',
        'eventType': event.get('eventType') or event.get('event_type') or 'Interdição ou bloqueio por notícia pública',
        'road': event.get('road') or '',
        'lat': event.get('lat'),
        'lon': event.get('lon'),
        'city': event.get('city') or '',
        'state': event.get('state') or '',
        'region': event.get('region') or '',
        'risk': event.get('risk') or 0,
        'severity': event.get('severity') or '',
        'description': clean_description(event.get('description')),
        'source': event.get('source') or '',
        'sourceUrl': event.get('sourceUrl') or event.get('source_url') or '',
        'first_seen_at': first_seen,
        'last_seen_at': last_seen,
        'active_duration_hours': hours,
        'active_duration_label': human_duration(hours),
        'lifecycle_status': 'stale_deactivated',
        'tracker_reason': reason,
        'deactivated_at': now_iso(),
        'active': False,
        'updatedAt': now_iso(),
    }


def main() -> None:
    events = read_json(ROAD_EVENTS, [])
    state = read_json(STATE_FILE, {})
    deactivated = read_json(DEACTIVATED_FILE, [])
    if not isinstance(events, list):
        events = []
    if not isinstance(state, dict):
        state = {}
    state_events = state.get('events') if isinstance(state.get('events'), dict) else {}
    if not isinstance(deactivated, list):
        deactivated = []

    kept: list[dict[str, Any]] = []
    corrected_first_seen = 0
    updated_descriptions = 0
    removed_old = 0
    removed_no_date = 0
    planned_preserved = 0
    samples: list[dict[str, Any]] = []
    cutoff_hours = LOOKBACK_HOURS

    for event in events:
        if not isinstance(event, dict) or not is_public_road_news(event):
            kept.append(event)
            continue

        key = event_key(event)
        state_row = state_events.get(key) if isinstance(state_events.get(key), dict) else {}
        dt = news_dt(event)
        start, end = planned_window(event)
        if not dt:
            reason = 'public_news_without_reliable_publication_date'
            deactivated.append(deactivate_event(event, state_row, reason))
            removed_no_date += 1
            samples.append({'name': event.get('name'), 'road': event.get('road'), 'reason': reason})
            continue

        if not planned_window_keeps_event(event):
            age = duration_hours(iso(dt))
            if age > cutoff_hours:
                reason = f'public_news_older_than_{cutoff_hours:g}h'
                deactivated.append(deactivate_event(event, state_row, reason))
                if key in state_events:
                    state_events[key]['active'] = False
                    state_events[key]['deactivated_at'] = now_iso()
                    state_events[key]['tracker_reason'] = reason
                removed_old += 1
                samples.append({'name': event.get('name'), 'road': event.get('road'), 'reason': reason, 'newsDate': iso(dt)})
                continue
        else:
            planned_preserved += 1
            event['active'] = bool(not start or now_dt() >= start)
            event['lifecycle_status'] = 'active_planned_closure' if event['active'] else 'scheduled'
            event['tracker_reason'] = 'planned_road_news_window'

        first_seen_dt = parse_dt(event.get('first_seen_at'))
        start_basis = start or dt
        if not first_seen_dt or first_seen_dt > start_basis:
            event['first_seen_at'] = iso(start_basis)
            corrected_first_seen += 1
        first_seen = text(event.get('first_seen_at')) or iso(start_basis)
        end_for_duration = now_iso()
        if end and now_dt() > end:
            end_for_duration = iso(end)
        hours = duration_hours(first_seen, end_for_duration)
        event['active_duration_hours'] = hours
        event['active_duration_label'] = human_duration(hours)
        event['last_seen_at'] = event.get('last_seen_at') or now_iso()
        event['lifecycle_status'] = event.get('lifecycle_status') or 'active'
        event['tracker_reason'] = event.get('tracker_reason') or 'public_news_recent'
        event['newsLifecycleRule'] = f'Notícias públicas rodoviárias ativas precisam ter até {LOOKBACK_HOURS:g}h, exceto quando há plannedEndAt ainda vigente.'
        old_desc = text(event.get('description'))
        append_tracking(event, first_seen, hours)
        if event.get('description') != old_desc:
            updated_descriptions += 1

        if key in state_events:
            row = state_events[key]
            row['first_seen_at'] = first_seen
            row['active_duration_hours'] = hours
            row['active_duration_label'] = human_duration(hours)
            row['active'] = event.get('active', True)
            row['tracker_reason'] = event.get('tracker_reason')
            row['news_lifecycle_rule'] = event['newsLifecycleRule']
            if event.get('plannedStartAt'):
                row['plannedStartAt'] = event.get('plannedStartAt')
            if event.get('plannedEndAt'):
                row['plannedEndAt'] = event.get('plannedEndAt')
            state_events[key] = row
        kept.append(event)

    state['events'] = state_events
    settings = state.get('settings') if isinstance(state.get('settings'), dict) else {}
    settings['roadNewsDurationUsesPublicationDate'] = True
    settings['newsPublicLookbackHours'] = LOOKBACK_HOURS
    settings['roadNewsStaleHours'] = ROAD_NEWS_STALE_HOURS
    settings['plannedRoadNewsWindowPreserved'] = True
    state['settings'] = settings
    state['updatedAt'] = now_iso()

    write_json(ROAD_EVENTS, kept)
    write_json(STATE_FILE, state)
    write_json(DEACTIVATED_FILE, deactivated)
    status = {
        'updatedAt': now_iso(),
        'lookbackHours': LOOKBACK_HOURS,
        'staleHours': ROAD_NEWS_STALE_HOURS,
        'inputEvents': len(events),
        'keptEvents': len(kept),
        'correctedFirstSeen': corrected_first_seen,
        'updatedDescriptions': updated_descriptions,
        'plannedWindowPreserved': planned_preserved,
        'removedOldPublicNews': removed_old,
        'removedWithoutReliableDate': removed_no_date,
        'removedSample': samples[:25],
        'policy': 'Notícias públicas usam a data da notícia como first_seen_at; plannedStartAt/plannedEndAt mantém interdições planejadas ativas durante o período informado.',
    }
    write_json(STATUS_FILE, status)
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
