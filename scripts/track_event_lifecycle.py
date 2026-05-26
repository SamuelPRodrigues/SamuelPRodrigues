#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

STATE_FILE = Path('data/event_lifecycle_state.json')
STATUS_FILE = Path('data/event_lifecycle_status.json')
DEACTIVATED_FILE = Path('data/deactivated_events.json')
TRACKED_FILES = [
    ('climate', Path('data/climate_events.json')),
    ('road', Path('data/road_events.json')),
    ('operational', Path('data/operational_alerts.json')),
    ('manual', Path('data/manual_events.json')),
]

BR_TZ = timezone(timedelta(hours=-3))
ROAD_NEWS_STALE_HOURS = float(os.environ.get('ROAD_NEWS_STALE_HOURS', '24'))
ROAD_LIVE_FEED_GRACE_RUNS = int(os.environ.get('ROAD_LIVE_FEED_GRACE_RUNS', '1'))
NEWS_RELEASE_LOOKUP_LIMIT = int(os.environ.get('NEWS_RELEASE_LOOKUP_LIMIT', '10'))
ROAD_RE = re.compile(r'\b(BR|SP|MG|RJ|ES|PR|SC|RS|MS|MT|GO|DF|BA|PE|CE|RN|PB|AL|SE|PI|MA|PA|AM|RO|RR|AP|AC|TO)-?\s?(\d{2,4})\b', re.I)
RELEASE_TERMS = (
    'liberado', 'liberada', 'liberação', 'liberacao', 'normalizado', 'normalizada',
    'reaberto', 'reaberta', 'pista liberada', 'rodovia liberada', 'trânsito liberado',
    'transito liberado', 'tráfego liberado', 'trafego liberado', 'sem bloqueio',
    'sem interdição', 'sem interdicao', 'fluxo normal', 'volta ao normal', 'foi liberada',
    'foi liberado', 'desbloqueado', 'desbloqueada',
)
BLOCKING_TERMS = (
    'interdit', 'bloque', 'pista bloqueada', 'pista interditada', 'rodovia bloqueada',
    'rodovia interditada', 'queda de barreira', 'deslizamento', 'cratera', 'erosão', 'erosao',
)


def now_dt() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_dt().strftime('%Y-%m-%dT%H:%M:%SZ')


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    raw = str(value).strip().replace('Z', '+00:00')
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def iso(dt: datetime | None) -> str:
    return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ') if dt else ''


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


def event_blob(event: dict[str, Any]) -> str:
    keys = ('source_type', 'type', 'source', 'sourceProvider', 'provider', 'eventType', 'event_type', 'name', 'description', 'headline', 'road', 'corridor')
    return ' '.join(text(event.get(k)) for k in keys)


def road_code(event: dict[str, Any]) -> str:
    blob = event_blob(event)
    match = ROAD_RE.search(blob)
    if match:
        return f'{match.group(1).upper()}-{match.group(2)}'
    road = text(event.get('road'))
    return road.upper().replace(' ', '') if road else ''


def is_release_text(blob: str) -> bool:
    folded = blob.casefold()
    return any(term.casefold() in folded for term in RELEASE_TERMS)


def is_blocking_text(blob: str) -> bool:
    folded = blob.casefold()
    return any(term.casefold() in folded for term in BLOCKING_TERMS)


def is_road_event(source_type: str, event: dict[str, Any]) -> bool:
    return source_type == 'road' or text(event.get('type')).lower() == 'road' or bool(road_code(event))


def is_public_news_event(event: dict[str, Any]) -> bool:
    blob = event_blob(event).casefold()
    return 'notícia pública' in blob or 'noticia publica' in blob or 'notícias públicas' in blob or 'noticias publicas' in blob or 'google news' in blob or 'gdelt' in blob


def event_key(source_type: str, event: dict[str, Any]) -> str:
    for key in ('stable_event_id', 'event_id', 'hash'):
        value = text(event.get(key))
        if value:
            return value
    lat = ''
    lon = ''
    try:
        lat = f"{float(event.get('lat')):.3f}"
        lon = f"{float(event.get('lon')):.3f}"
    except Exception:
        pass
    stable = '|'.join([
        source_type,
        text(event.get('name') or event.get('road') or event.get('eventType') or event.get('event_type')),
        text(event.get('eventType') or event.get('event_type') or event.get('category')),
        road_code(event) or text(event.get('road')),
        text(event.get('city')),
        text(event.get('state')),
        lat,
        lon,
        text(event.get('sourceUrl') or event.get('source_url')),
    ])
    return hashlib.sha256(stable.encode('utf-8')).hexdigest()[:24]


def active_hours(first_seen: str, end_time: str | None = None) -> float:
    start = parse_dt(first_seen)
    end = parse_dt(end_time) or now_dt()
    if not start:
        return 0.0
    return round(max(0.0, (end - start).total_seconds() / 3600), 2)


def human_duration(hours: float) -> str:
    if hours < 1:
        return f'{round(hours * 60)} min'
    if hours < 48:
        return f'{hours:.1f} h'
    return f'{hours / 24:.1f} dias'


def classify_tracker_status(active: bool, reason: str = '') -> str:
    if active:
        return 'active'
    if reason.startswith('release_news'):
        return 'released'
    if reason.startswith('missing_from_live_feed'):
        return 'not_seen_anymore'
    if reason.startswith('stale_public_news'):
        return 'stale_deactivated'
    return 'inactive'


def fetch_release_news_for_road(road: str) -> list[dict[str, str]]:
    if not road or NEWS_RELEASE_LOOKUP_LIMIT <= 0:
        return []
    query = f'"{road}" (liberada OR liberado OR normalizado OR normalizada OR reaberta OR reaberto OR "trânsito liberado" OR "pista liberada" OR "rodovia liberada") when:3d'
    params = urllib.parse.urlencode({'q': query, 'hl': 'pt-BR', 'gl': 'BR', 'ceid': 'BR:pt-419'})
    url = 'https://news.google.com/rss/search?' + params
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'event-lifecycle-tracker/1.0'})
        with urllib.request.urlopen(req, timeout=30) as response:
            xml = response.read()
        root = ET.fromstring(xml)
        out: list[dict[str, str]] = []
        for item in root.findall('.//item')[:NEWS_RELEASE_LOOKUP_LIMIT]:
            title = text(item.findtext('title'))
            link = text(item.findtext('link'))
            source_node = item.find('source')
            source = text(source_node.text if source_node is not None else 'Google News')
            blob = f'{title} {source}'
            if road.upper() in blob.upper() and is_release_text(blob):
                out.append({'title': title, 'url': link, 'source': source})
        return out
    except Exception:
        return []


def load_current_events() -> tuple[list[tuple[str, Path, int, dict[str, Any]]], dict[str, Any]]:
    records: list[tuple[str, Path, int, dict[str, Any]]] = []
    raw_by_path: dict[str, Any] = {}
    for source_type, path in TRACKED_FILES:
        data = read_json(path, [])
        raw_by_path[str(path)] = data
        if not isinstance(data, list):
            continue
        for index, event in enumerate(data):
            if isinstance(event, dict):
                records.append((source_type, path, index, event))
    return records, raw_by_path


def compact_event(source_type: str, event: dict[str, Any], state_row: dict[str, Any], active: bool, reason: str) -> dict[str, Any]:
    end_time = state_row.get('deactivated_at') if not active else now_iso()
    hours = active_hours(state_row.get('first_seen_at'), end_time)
    return {
        'event_id': state_row.get('event_id') or event_key(source_type, event),
        'stable_event_id': state_row.get('stable_event_id') or event_key(source_type, event),
        'name': event.get('name') or event.get('road') or event.get('eventType') or source_type,
        'type': source_type,
        'source_type': source_type,
        'eventType': event.get('eventType') or event.get('event_type') or event.get('category') or source_type,
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
        'first_seen_at': state_row.get('first_seen_at') or '',
        'last_seen_at': state_row.get('last_seen_at') or '',
        'active_duration_hours': hours,
        'active_duration_label': human_duration(hours),
        'lifecycle_status': classify_tracker_status(active, reason),
        'tracker_reason': reason,
        'deactivated_at': state_row.get('deactivated_at') or '',
        'active': active,
        'updatedAt': now_iso(),
    }


def main() -> None:
    current_time = now_iso()
    old_state = read_json(STATE_FILE, {})
    if not isinstance(old_state, dict):
        old_state = {}
    old_events = old_state.get('events') if isinstance(old_state.get('events'), dict) else {}
    new_events: dict[str, Any] = dict(old_events)
    current_records, raw_by_path = load_current_events()
    seen_keys: set[str] = set()
    deactivated: list[dict[str, Any]] = []
    release_cache: dict[str, list[dict[str, str]]] = {}
    status = {
        'updatedAt': current_time,
        'eventsSeen': 0,
        'newEvents': 0,
        'updatedEvents': 0,
        'deactivatedEvents': 0,
        'releaseNewsMatches': 0,
        'stalePublicNewsDeactivated': 0,
        'liveFeedMissingDeactivated': 0,
        'filesUpdated': [],
        'policy': 'first_seen_at persistente; last_seen_at por execução; desativação por sinal de liberação, desaparecimento de feed ao vivo ou notícia pública sem reconfirmação.',
    }

    for source_type, path, index, event in current_records:
        key = event_key(source_type, event)
        seen_keys.add(key)
        previous = dict(old_events.get(key) or {})
        first_seen = previous.get('first_seen_at') or event.get('first_seen_at') or event.get('createdAt') or event.get('updatedAt') or event.get('updated_at') or current_time
        row = {
            **previous,
            'event_id': key,
            'stable_event_id': key,
            'source_type': source_type,
            'first_seen_at': first_seen,
            'last_seen_at': current_time,
            'last_confirmed_at': current_time,
            'active': True,
            'missing_runs': 0,
            'deactivated_at': '',
            'tracker_reason': 'seen_in_current_feed',
        }
        hours = active_hours(first_seen)
        event['stable_event_id'] = event.get('stable_event_id') or key
        event['event_id'] = event.get('event_id') or key
        event['first_seen_at'] = first_seen
        event['last_seen_at'] = current_time
        event['active_duration_hours'] = hours
        event['active_duration_label'] = human_duration(hours)
        event['lifecycle_status'] = 'active'
        event['tracker_reason'] = 'seen_in_current_feed'
        event['active'] = event.get('active', True)
        if 'Rastreio:' not in text(event.get('description')):
            event['description'] = (text(event.get('description')) + f" Rastreio: primeiro registro em {first_seen}; ativo há {human_duration(hours)}.").strip()
        new_events[key] = row
        status['eventsSeen'] += 1
        status['newEvents' if not previous else 'updatedEvents'] += 1

    for key, row in list(new_events.items()):
        if key in seen_keys or not isinstance(row, dict) or not row.get('active', True):
            continue
        source_type = text(row.get('source_type'))
        # Recria um evento mínimo para desativação histórica.
        event = row.get('last_payload') if isinstance(row.get('last_payload'), dict) else row
        missing_runs = int(row.get('missing_runs') or 0) + 1
        row['missing_runs'] = missing_runs
        reason = ''
        should_deactivate = False
        if is_road_event(source_type, event):
            road = road_code(event)
            if road and road not in release_cache:
                release_cache[road] = fetch_release_news_for_road(road)
            releases = release_cache.get(road, [])
            if releases:
                should_deactivate = True
                reason = 'release_news:' + '; '.join(item.get('source', 'fonte') for item in releases[:3])
                row['release_sources'] = releases[:5]
                status['releaseNewsMatches'] += len(releases)
            elif not is_public_news_event(event) and missing_runs >= ROAD_LIVE_FEED_GRACE_RUNS:
                should_deactivate = True
                reason = 'missing_from_live_feed'
                status['liveFeedMissingDeactivated'] += 1
            else:
                last_seen = parse_dt(row.get('last_seen_at')) or parse_dt(row.get('first_seen_at')) or now_dt()
                age_hours = (now_dt() - last_seen).total_seconds() / 3600
                if is_public_news_event(event) and age_hours >= ROAD_NEWS_STALE_HOURS:
                    should_deactivate = True
                    reason = f'stale_public_news>{ROAD_NEWS_STALE_HOURS:g}h'
                    status['stalePublicNewsDeactivated'] += 1
        if should_deactivate:
            row['active'] = False
            row['deactivated_at'] = current_time
            row['tracker_reason'] = reason
            inactive = compact_event(source_type or 'road', event, row, False, reason)
            deactivated.append(inactive)
            status['deactivatedEvents'] += 1
        new_events[key] = row

    # Guarda uma cópia mínima do último payload dos eventos vistos para futura desativação.
    for source_type, path, index, event in current_records:
        key = event_key(source_type, event)
        if key in new_events:
            payload = {k: event.get(k) for k in ('name', 'eventType', 'event_type', 'road', 'lat', 'lon', 'city', 'state', 'region', 'risk', 'severity', 'description', 'source', 'sourceUrl', 'source_url', 'type')}
            payload['source_type'] = source_type
            new_events[key]['last_payload'] = payload

    for path_str, data in raw_by_path.items():
        if isinstance(data, list):
            write_json(Path(path_str), data)
            status['filesUpdated'].append(path_str)

    state = {
        'updatedAt': current_time,
        'events': new_events,
        'settings': {
            'roadNewsStaleHours': ROAD_NEWS_STALE_HOURS,
            'roadLiveFeedGraceRuns': ROAD_LIVE_FEED_GRACE_RUNS,
            'releaseLookupLimit': NEWS_RELEASE_LOOKUP_LIMIT,
        },
    }
    write_json(STATE_FILE, state)
    write_json(DEACTIVATED_FILE, deactivated)
    write_json(STATUS_FILE, status)
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
