#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CURRENT_STATE = Path('data/event_lifecycle_state.json')
PREVIOUS_STATE = Path('data/event_lifecycle_state_before.json')
ROAD_EVENTS = Path('data/road_events.json')
DEACTIVATED = Path('data/deactivated_events.json')
STATUS = Path('data/news_reconfirmation_status.json')
STALE_HOURS = float(os.environ.get('ROAD_NEWS_STALE_HOURS', '4'))
NEWS_RE = re.compile(r'not[ií]cias? p[uú]blicas?|google news|gdelt|fonte p[uú]blica|noticia publica|notícia pública', re.I)
ROAD_RE = re.compile(r'\b(BR|SP|MG|RJ|ES|PR|SC|RS|MS|MT|GO|DF|BA|PE|CE|RN|PB|AL|SE|PI|MA|PA|AM|RO|RR|AP|AC|TO)-?\s?(\d{2,4})\b', re.I)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


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


def norm_space(value: Any) -> str:
    return re.sub(r'\s+', ' ', text(value)).strip()


def norm_url(value: Any) -> str:
    raw = text(value)
    if not raw:
        return ''
    try:
        parsed = urllib.parse.urlsplit(raw)
        query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        filtered = [(k, v) for k, v in query if not k.lower().startswith('utm_') and k.lower() not in {'fbclid', 'gclid', 'oc', 'ceid'}]
        return urllib.parse.urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, urllib.parse.urlencode(filtered), ''))
    except Exception:
        return raw


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


def age_hours(value: Any) -> float:
    dt = parse_dt(value)
    if not dt:
        return 0.0
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 3600)


def blob(row: dict[str, Any]) -> str:
    keys = ('source', 'sourceProvider', 'provider', 'eventType', 'event_type', 'name', 'description', 'headline', 'road', 'sourceUrl', 'source_url')
    return ' '.join(text(row.get(k)) for k in keys)


def is_public_road_news(row: dict[str, Any]) -> bool:
    source_type = text(row.get('source_type') or row.get('type')).lower()
    haystack = blob(row)
    return (source_type == 'road' or ROAD_RE.search(haystack)) and bool(NEWS_RE.search(haystack))


def source_items(row: dict[str, Any]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    raw = row.get('sources') or row.get('sourceList') or []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                items.append({
                    'source': norm_space(item.get('source') or item.get('name') or item.get('provider') or 'Fonte pública'),
                    'url': norm_url(item.get('url') or item.get('source_url') or item.get('sourceUrl')),
                    'headline': norm_space(item.get('headline') or item.get('title') or item.get('description')),
                    'date': norm_space(item.get('date') or item.get('published') or item.get('newsDate')),
                })
    items.append({
        'source': norm_space(row.get('source') or row.get('sourceProvider') or row.get('provider') or 'Fonte pública'),
        'url': norm_url(row.get('sourceUrl') or row.get('source_url')),
        'headline': norm_space(row.get('headline') or row.get('description') or row.get('name')),
        'date': norm_space(row.get('newsDate') or row.get('published') or row.get('updatedAt') or row.get('updated_at')),
    })
    unique: dict[str, dict[str, str]] = {}
    for item in items:
        key = item.get('url') or f"{item.get('source')}|{item.get('headline')}|{item.get('date')}"
        if key and key not in unique:
            unique[key] = item
    return sorted(unique.values(), key=lambda item: (item.get('date') or '', item.get('url') or '', item.get('headline') or ''))


def signature(row: dict[str, Any]) -> str:
    parts = []
    for item in source_items(row):
        parts.append('|'.join([
            norm_url(item.get('url')),
            norm_space(item.get('source')).casefold(),
            norm_space(item.get('headline')).casefold(),
            norm_space(item.get('date')),
        ]))
    payload = '\n'.join(sorted(set(parts)))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()[:24] if payload else ''


def event_key(row: dict[str, Any]) -> str:
    for key in ('stable_event_id', 'event_id', 'hash'):
        value = text(row.get(key))
        if value:
            return value
    return hashlib.sha256(blob(row).encode('utf-8')).hexdigest()[:24]


def deactivated_event(event: dict[str, Any], row: dict[str, Any], reason: str) -> dict[str, Any]:
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
        'description': event.get('description') or '',
        'source': event.get('source') or '',
        'sourceUrl': event.get('sourceUrl') or event.get('source_url') or '',
        'first_seen_at': row.get('first_seen_at') or '',
        'last_seen_at': row.get('last_seen_at') or '',
        'deactivated_at': now_iso(),
        'active': False,
        'lifecycle_status': 'stale_deactivated',
        'tracker_reason': reason,
        'updatedAt': now_iso(),
    }


def main() -> None:
    current_state = read_json(CURRENT_STATE, {})
    previous_state = read_json(PREVIOUS_STATE, {})
    road_events = read_json(ROAD_EVENTS, [])
    deactivated = read_json(DEACTIVATED, [])
    if not isinstance(current_state, dict):
        current_state = {}
    if not isinstance(previous_state, dict):
        previous_state = {}
    current_events = current_state.get('events') if isinstance(current_state.get('events'), dict) else {}
    previous_events = previous_state.get('events') if isinstance(previous_state.get('events'), dict) else {}
    if not isinstance(road_events, list):
        road_events = []
    if not isinstance(deactivated, list):
        deactivated = []

    kept = []
    unchanged = 0
    renewed = 0
    removed = 0
    restored = 0
    samples = []

    for event in road_events:
        if not isinstance(event, dict) or not is_public_road_news(event):
            kept.append(event)
            continue
        key = event_key(event)
        sig = signature(event)
        prev = previous_events.get(key) if isinstance(previous_events.get(key), dict) else {}
        cur = current_events.get(key) if isinstance(current_events.get(key), dict) else {}
        previous_sig = text(prev.get('news_signature')) or signature(prev.get('last_payload') or {})
        if previous_sig and sig == previous_sig:
            unchanged += 1
            previous_last_seen = prev.get('last_seen_at') or prev.get('last_confirmed_at') or prev.get('first_seen_at')
            age = age_hours(previous_last_seen)
            if age >= STALE_HOURS:
                reason = f'unchanged_public_news>{STALE_HOURS:g}h'
                removed += 1
                if cur:
                    cur['active'] = False
                    cur['deactivated_at'] = now_iso()
                    cur['tracker_reason'] = reason
                    cur['last_seen_at'] = previous_last_seen
                    cur['last_confirmed_at'] = prev.get('last_confirmed_at') or previous_last_seen
                    cur['news_signature'] = sig
                    current_events[key] = cur
                deactivated.append(deactivated_event(event, cur or prev, reason))
                samples.append({'name': event.get('name'), 'road': event.get('road'), 'reason': reason, 'last_seen_at': previous_last_seen})
                continue
            if cur:
                cur['last_seen_at'] = previous_last_seen
                cur['last_confirmed_at'] = prev.get('last_confirmed_at') or previous_last_seen
                cur['tracker_reason'] = 'unchanged_public_news_not_reconfirmed'
                cur['news_signature'] = sig
                cur['news_signature_policy'] = 'Mesma matéria não reconfirma evento; apenas URL, título, data ou fonte nova renova last_seen_at.'
                current_events[key] = cur
                restored += 1
            event['last_seen_at'] = previous_last_seen
            event['last_confirmed_at'] = prev.get('last_confirmed_at') or previous_last_seen
            event['tracker_reason'] = 'unchanged_public_news_not_reconfirmed'
            event['news_signature'] = sig
            event['news_signature_policy'] = 'Mesma matéria não reconfirma evento; apenas URL, título, data ou fonte nova renova last_seen_at.'
            kept.append(event)
        else:
            renewed += 1
            if cur:
                cur['news_signature'] = sig
                cur['news_signature_policy'] = 'Mesma matéria não reconfirma evento; apenas URL, título, data ou fonte nova renova last_seen_at.'
                current_events[key] = cur
            event['news_signature'] = sig
            event['news_signature_policy'] = 'Mesma matéria não reconfirma evento; apenas URL, título, data ou fonte nova renova last_seen_at.'
            kept.append(event)

    current_state['events'] = current_events
    current_state['updatedAt'] = now_iso()
    settings = current_state.get('settings') if isinstance(current_state.get('settings'), dict) else {}
    settings['sameNewsDoesNotReconfirm'] = True
    settings['sameNewsStaleHours'] = STALE_HOURS
    current_state['settings'] = settings

    write_json(ROAD_EVENTS, kept)
    write_json(CURRENT_STATE, current_state)
    write_json(DEACTIVATED, deactivated)
    if PREVIOUS_STATE.exists():
        try:
            PREVIOUS_STATE.unlink()
        except Exception:
            pass
    write_json(STATUS, {
        'updatedAt': now_iso(),
        'sameNewsDoesNotReconfirm': True,
        'staleHours': STALE_HOURS,
        'roadEventsInput': len(road_events),
        'roadEventsKept': len(kept),
        'unchangedPublicNews': unchanged,
        'renewedByNewOrUpdatedNews': renewed,
        'lastSeenRestored': restored,
        'removedAsStale': removed,
        'removedSample': samples[:25],
        'policy': 'A mesma notícia não renova last_seen_at. O evento só é reconfirmado por URL, título, data ou fonte nova.',
    })
    print(json.dumps(read_json(STATUS, {}), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
