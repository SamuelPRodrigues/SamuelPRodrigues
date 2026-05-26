#!/usr/bin/env python3
from __future__ import annotations

import email.utils
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

ROAD_EVENTS = Path('data/road_events.json')
ROAD_CORRIDORS = Path('data/road_corridors.csv')
STATE_FILE = Path('data/planned_road_events_state.json')
STATUS_FILE = Path('data/planned_road_events_status.json')
BR_TZ = timezone(timedelta(hours=-3))
MAX_ROAD_BLOCKING_RISK = 69
LOOKBACK_HOURS = float(os.environ.get('NEWS_PUBLIC_LOOKBACK_HOURS', '12'))
WATCH_URLS = [u.strip() for u in os.environ.get('PLANNED_ROAD_NEWS_URLS', '').replace(',', ' ').split() if u.strip()]

ROAD_RE = re.compile(r'\b(BR|SP|MG|RJ|ES|PR|SC|RS|MS|MT|GO|DF|BA|PE|CE|RN|PB|AL|SE|PI|MA|PA|AM|RO|RR|AP|AC|TO)-?\s?(\d{2,4})\b', re.I)
BLOCKING_RE = re.compile(r'interdit|bloque|fechad|pista interditada|rodovia interditada|pista bloqueada|rodovia bloqueada', re.I)
WORK_RE = re.compile(r'obra|obras|manuten[cç][aã]o|interven[cç][aã]o|servi[cç]os?', re.I)
RELEASE_RE = re.compile(r'liberad|normalizad|reabert|sem bloqueio|sem interdi[cç][aã]o|fluxo normal|volta ao normal', re.I)
MONTHS = {
    'janeiro': 1, 'fevereiro': 2, 'março': 3, 'marco': 3, 'abril': 4, 'maio': 5, 'junho': 6,
    'julho': 7, 'agosto': 8, 'setembro': 9, 'outubro': 10, 'novembro': 11, 'dezembro': 12,
}

GOOGLE_NEWS_QUERIES = [
    '"BR-265" (interditado OR interditada OR bloqueado OR bloqueada OR obras OR manutenção OR manutencao) when:2d',
    '(rodovia OR BR OR pista) ("totalmente interditado" OR "totalmente interditada" OR "interditado para obras" OR "interditada para obras" OR "interditado para manutenção" OR "interditada para manutenção") when:2d -futebol -jogo',
]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_utc().strftime('%Y-%m-%dT%H:%M:%SZ')


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
    raw = text(value)
    try:
        dt = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    try:
        dt = email.utils.parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=BR_TZ)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def iso(dt: datetime | None) -> str:
    return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ') if dt else ''


def normalize_road(raw: str) -> str:
    m = ROAD_RE.search(raw or '')
    if not m:
        return ''
    return f'{m.group(1).upper()}-{m.group(2)}'


def url_date(url: str) -> datetime | None:
    m = re.search(r'/([12]\d{3})/(\d{1,2})/(\d{1,2})/', url)
    if not m:
        return None
    try:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=BR_TZ).astimezone(timezone.utc)
    except Exception:
        return None


def title_from_slug(url: str) -> str:
    path = urllib.parse.urlsplit(url).path
    slug = path.rsplit('/', 1)[-1].replace('.ghtml', '').replace('.html', '')
    words = slug.replace('-', ' ').strip()
    return words[:1].upper() + words[1:] if words else url


def fetch_url(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; planned-road-events/1.0; +https://github.com/)',
        'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.6',
    })
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode('utf-8', errors='replace')


def html_unescape(value: str) -> str:
    import html
    return html.unescape(re.sub(r'<[^>]+>', ' ', value or ''))


def meta_content(html: str, key: str) -> str:
    patterns = [
        rf'<meta[^>]+property=["\']{re.escape(key)}["\'][^>]+content=["\']([^"\']+)',
        rf'<meta[^>]+name=["\']{re.escape(key)}["\'][^>]+content=["\']([^"\']+)',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']{re.escape(key)}["\']',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']{re.escape(key)}["\']',
    ]
    for pattern in patterns:
        m = re.search(pattern, html, flags=re.I | re.S)
        if m:
            return html_unescape(m.group(1)).strip()
    return ''


def article_text_from_url(url: str) -> tuple[str, str, datetime | None, str]:
    title = title_from_slug(url)
    description = ''
    published = url_date(url)
    html = ''
    try:
        html = fetch_url(url)
    except Exception:
        return title, description, published, ''
    title = meta_content(html, 'og:title') or meta_content(html, 'twitter:title') or title
    description = meta_content(html, 'og:description') or meta_content(html, 'description')
    published_raw = meta_content(html, 'article:published_time') or meta_content(html, 'datePublished')
    published = parse_dt(published_raw) or published
    body_bits = []
    for pattern in (r'"articleBody"\s*:\s*"(.{80,3000}?)"', r'<p[^>]*>(.{20,600}?)</p>'):
        for m in re.finditer(pattern, html, flags=re.I | re.S):
            bit = html_unescape(m.group(1))
            if bit and bit not in body_bits:
                body_bits.append(bit)
            if len(' '.join(body_bits)) > 5000:
                break
    return title, description, published, ' '.join(body_bits)


def fetch_google_news() -> list[dict[str, Any]]:
    articles = []
    for query in GOOGLE_NEWS_QUERIES:
        params = {'q': query, 'hl': 'pt-BR', 'gl': 'BR', 'ceid': 'BR:pt-419'}
        try:
            xml = fetch_url('https://news.google.com/rss/search?' + urllib.parse.urlencode(params), timeout=20)
            root = ET.fromstring(xml)
            for item in root.findall('.//item'):
                source_el = item.find('source')
                published = item.findtext('pubDate') or ''
                articles.append({
                    'title': item.findtext('title') or '',
                    'url': item.findtext('link') or '',
                    'source': source_el.text if source_el is not None and source_el.text else 'Google News',
                    'published': published,
                    'published_dt': parse_dt(published),
                    'provider': 'Google News RSS planejado',
                })
        except Exception:
            pass
    return articles


def load_corridors() -> list[dict[str, Any]]:
    out = []
    if not ROAD_CORRIDORS.exists():
        return out
    import csv
    with ROAD_CORRIDORS.open('r', encoding='utf-8') as handle:
        for row in csv.DictReader(handle, delimiter='|'):
            try:
                out.append({
                    'state': row.get('state', ''), 'city': row.get('city', ''), 'region': row.get('region', ''),
                    'lat': float(row.get('lat', '')), 'lon': float(row.get('lon', '')), 'road': row.get('road', ''),
                    'name': f"{row.get('city', '').strip()} • {row.get('road', '').strip()}",
                })
            except Exception:
                pass
    return out


def corridor_for(road: str, article_blob: str, corridors: list[dict[str, Any]]) -> dict[str, Any] | None:
    road_key = road.upper().replace(' ', '')
    candidates = [c for c in corridors if road_key and road_key in str(c.get('road') or c.get('name') or '').upper().replace(' ', '')]
    blob = article_blob.casefold()
    for c in candidates:
        city = text(c.get('city')).casefold()
        if city and city in blob:
            return c
    if candidates:
        return candidates[0]
    if road == 'BR-265':
        return {'state': 'MG', 'city': 'Sul de Minas', 'region': 'Sudeste', 'lat': -21.25, 'lon': -44.90, 'road': 'BR-265', 'name': 'Sul de Minas • BR-265'}
    return None


def date_from_day(day: int, base: datetime) -> datetime:
    local = base.astimezone(BR_TZ)
    month = local.month
    year = local.year
    if day < local.day - 10:
        month += 1
        if month > 12:
            month = 1
            year += 1
    return datetime(year, month, day, tzinfo=BR_TZ).astimezone(timezone.utc)


def extract_planned_period(blob: str, published: datetime | None) -> tuple[str, str, str]:
    base = published or now_utc()
    dates: list[datetime] = []
    for m in re.finditer(r'\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b', blob):
        day, month = int(m.group(1)), int(m.group(2))
        year = int(m.group(3)) if m.group(3) else base.astimezone(BR_TZ).year
        if year < 100:
            year += 2000
        try:
            dates.append(datetime(year, month, day, tzinfo=BR_TZ).astimezone(timezone.utc))
        except Exception:
            pass
    for month_name, month in MONTHS.items():
        m = re.search(rf'(?:dias?\s+)?(\d{{1,2}})(?:\s*(?:a|até|e)\s*(\d{{1,2}}))?\s+de\s+{month_name}', blob, flags=re.I)
        if m:
            year = base.astimezone(BR_TZ).year
            for group in (1, 2):
                if m.group(group):
                    dates.append(datetime(year, month, int(m.group(group)), tzinfo=BR_TZ).astimezone(timezone.utc))
    for m in re.finditer(r'\((\d{1,2})\)', blob):
        day = int(m.group(1))
        if 1 <= day <= 31:
            try:
                dates.append(date_from_day(day, base))
            except Exception:
                pass
    times = []
    for m in re.finditer(r'\b(\d{1,2})h(?:(\d{2}))?\b', blob, flags=re.I):
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            times.append((hour, minute))
    start = min(dates) if dates else base
    end = max(dates) if dates else None
    if end and len(times) >= 2:
        h, mi = times[-1]
        local = end.astimezone(BR_TZ).replace(hour=h, minute=mi, second=0, microsecond=0)
        end = local.astimezone(timezone.utc)
    elif end:
        end = end.astimezone(BR_TZ).replace(hour=23, minute=59, second=59, microsecond=0).astimezone(timezone.utc)
    elif len(times) >= 2:
        h, mi = times[-1]
        end = base.astimezone(BR_TZ).replace(hour=h, minute=mi, second=0, microsecond=0).astimezone(timezone.utc)
    elif times and re.search(r'\bat[eé]\b', blob, flags=re.I):
        h, mi = times[-1]
        end = base.astimezone(BR_TZ).replace(hour=h, minute=mi, second=0, microsecond=0).astimezone(timezone.utc)
    rule = 'Período extraído do texto da notícia.' if end else ''
    return iso(start), iso(end), rule


def event_id_for(url: str, road: str) -> str:
    return hashlib.sha256(f'planned-road-news|{road}|{url}'.encode('utf-8')).hexdigest()[:24]


def make_event(article: dict[str, Any], corridors: list[dict[str, Any]]) -> dict[str, Any] | None:
    url = text(article.get('url'))
    title = text(article.get('title'))
    description = ''
    body = ''
    published = article.get('published_dt') if isinstance(article.get('published_dt'), datetime) else parse_dt(article.get('published'))
    if url and not url.startswith('https://news.google.com/'):
        fetched_title, fetched_description, fetched_published, fetched_body = article_text_from_url(url)
        title = fetched_title or title
        description = fetched_description
        published = fetched_published or published
        body = fetched_body
    if not title:
        title = title_from_slug(url)
    blob = f'{title} {description} {body} {url}'
    if RELEASE_RE.search(blob) or not BLOCKING_RE.search(blob):
        return None
    road = normalize_road(blob)
    if not road:
        return None
    corridor = corridor_for(road, blob, corridors)
    if not corridor:
        return None
    planned_start, planned_end, planned_rule = extract_planned_period(blob, published)
    now = now_utc()
    start_dt = parse_dt(planned_start)
    end_dt = parse_dt(planned_end)
    publication_age_hours = round((now - (published or now)).total_seconds() / 3600, 2)
    if not end_dt and publication_age_hours > LOOKBACK_HOURS:
        return None
    if start_dt and now < start_dt:
        active = False
        lifecycle = 'scheduled'
    elif end_dt and now > end_dt:
        active = False
        lifecycle = 'planned_window_ended'
    else:
        active = True
        lifecycle = 'active_planned_closure' if end_dt else 'active_recent_public_news'
    eid = event_id_for(url or title, road)
    period_text = ''
    if planned_start or planned_end:
        period_text = f' Período informado: {planned_start or "início não identificado"} até {planned_end or "fim não identificado"}.'
    return {
        'active': active,
        'event_id': eid,
        'stable_event_id': eid,
        'name': f'Interdição planejada por notícia pública • {road}',
        'road': road,
        'corridor': corridor.get('name') or road,
        'isMainRoad': True,
        'fallbackCorridor': True,
        'lat': float(corridor['lat']),
        'lon': float(corridor['lon']),
        'city': corridor.get('city') or '',
        'state': corridor.get('state') or '',
        'region': corridor.get('region') or '',
        'eventType': 'Interdição planejada por notícia pública',
        'description': f'{title}. {description}{period_text} Localização aproximada pelo corredor monitorado.'.strip(),
        'risk': MAX_ROAD_BLOCKING_RISK,
        'severity': 'Alto',
        'severityRule': 'Eventos rodoviários de bloqueio/interdição têm teto 69 (Alta).',
        'source': f"Notícias públicas - {article.get('source') or 'fonte pública'}",
        'sourceProvider': article.get('provider') or 'Fonte pública planejada',
        'sourceUrl': url,
        'headline': title[:240],
        'newsDate': iso(published) or article.get('published') or None,
        'plannedStartAt': planned_start,
        'plannedEndAt': planned_end,
        'plannedWindowRule': planned_rule or 'Sem período explícito; vale a regra de frescor da notícia.',
        'lifecycle_status': lifecycle,
        'tracker_reason': 'planned_road_news_window' if planned_end else 'recent_public_news_without_window',
        'updatedAt': now_iso(),
        'sources': [{'source': article.get('source') or 'Fonte pública', 'url': url, 'headline': title[:240], 'date': iso(published) or article.get('published') or ''}],
    }


def main() -> None:
    events = read_json(ROAD_EVENTS, [])
    if not isinstance(events, list):
        events = []
    state = read_json(STATE_FILE, {})
    if not isinstance(state, dict):
        state = {}
    stored = state.get('events') if isinstance(state.get('events'), dict) else {}
    corridors = load_corridors()
    articles: list[dict[str, Any]] = []
    for url in WATCH_URLS:
        articles.append({'url': url, 'title': title_from_slug(url), 'source': urllib.parse.urlsplit(url).netloc or 'Fonte pública', 'published': '', 'published_dt': url_date(url), 'provider': 'URL monitorada'})
    articles.extend(fetch_google_news())

    fresh_events: dict[str, dict[str, Any]] = {}
    for article in articles:
        event = make_event(article, corridors)
        if event:
            fresh_events[str(event['stable_event_id'])] = event
            stored[str(event['stable_event_id'])] = event

    now = now_utc()
    kept_state: dict[str, dict[str, Any]] = {}
    active_from_state = 0
    for key, event in stored.items():
        if not isinstance(event, dict):
            continue
        end = parse_dt(event.get('plannedEndAt'))
        start = parse_dt(event.get('plannedStartAt'))
        if end and now > end:
            continue
        if start and now < start:
            event['active'] = False
            event['lifecycle_status'] = 'scheduled'
        else:
            event['active'] = True
            event['lifecycle_status'] = 'active_planned_closure' if end else event.get('lifecycle_status') or 'active_recent_public_news'
        kept_state[key] = event
        if key not in fresh_events:
            active_from_state += 1

    existing_keys = {text(e.get('stable_event_id') or e.get('event_id') or e.get('sourceUrl')) for e in events if isinstance(e, dict)}
    merged = list(events)
    added = 0
    for key, event in kept_state.items():
        if key not in existing_keys and event.get('active') is not False:
            merged.append(event)
            added += 1

    write_json(ROAD_EVENTS, merged)
    write_json(STATE_FILE, {'updatedAt': now_iso(), 'events': kept_state})
    status = {
        'updatedAt': now_iso(),
        'watchUrls': len(WATCH_URLS),
        'articlesChecked': len(articles),
        'freshPlannedEvents': len(fresh_events),
        'activeFromState': active_from_state,
        'eventsAddedToRoadEvents': added,
        'stateEvents': len(kept_state),
        'policy': 'Interdições planejadas por notícia ficam ativas durante plannedStartAt/plannedEndAt, mesmo após a janela normal de 12h da notícia, salvo notícia posterior de liberação tratada pelo rastreador.',
    }
    write_json(STATUS_FILE, status)
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
