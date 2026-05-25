#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any

from update_operational_alerts import (
    CITIES,
    LOCATION_ALIASES,
    TRUSTED_NEWS_SITES,
    fetch_url,
    has_any,
    now_br,
    now_iso,
    parse_rss_date,
    region_from_event,
    write_json,
)

CLIMATE_OUTPUT = Path('data/climate_events.json')
ROAD_OUTPUT = Path('data/road_events.json')
STATUS_OUTPUT = Path('data/news_supplemental_events_status.json')
PROVIDER = 'Google News RSS - eventos suplementares'

IRRELEVANT_TERMS = [
    'futebol','campeonato','partida','jogo','jogador','time','clube','rodada','placar',
    'orçamento','mercado','ações','dólar','selic','inflação','lucro','prejuízo',
    'confronto contra','duelo contra','enfrenta','escalação','atacante','goleiro'
]

CLIMATE_TERMS = [
    'chuva forte','chuvas fortes','temporal','temporais','alagamento','alagamentos',
    'enchente','enchentes','inundação','inundações','deslizamento','deslizamentos',
    'queda de barreira','queda de árvore','vendaval','ventania','granizo','frente fria',
    'alerta laranja','alerta vermelho','defesa civil','inmet'
]
CLIMATE_HARD_TERMS = ['alagamento','enchente','inundação','deslizamento','queda de barreira','alerta vermelho','temporal']

ROAD_BLOCK_TERMS = [
    'interditada','interditado','interdição','interdicao','bloqueada','bloqueado','bloqueio',
    'pista interditada','pista bloqueada','rodovia interditada','rodovia bloqueada',
    'faixa interditada','faixa bloqueada','trânsito bloqueado','transito bloqueado',
    'tráfego bloqueado','trafego bloqueado','bloqueio total','bloqueio parcial',
    'interdição total','interdicao total','interdição parcial','interdicao parcial',
    'queda de barreira','deslizamento','rodovia fechada','pista fechada','via fechada'
]
ROAD_RELEASE_TERMS = [
    'liberada','liberado','liberação','liberacao','pista liberada','rodovia liberada',
    'via liberada','tráfego liberado','trafego liberado','trânsito liberado','transito liberado',
    'fluxo liberado','desbloqueada','desbloqueado','normalizado','normalizada',
    'tráfego normal','trafego normal','trânsito normal','transito normal','sem interdição',
    'sem interdicao','sem bloqueio','pista reaberta','rodovia reaberta','volta ao normal'
]

ROAD_PATTERNS = [
    r'\b(?:BR|SP|MG|RJ|PR|SC|RS|BA|PE|CE|GO|MT|MS|ES|PA|AM|RO|TO|DF)-?\s?\d{2,4}\b',
]
NAMED_HIGHWAYS = {
    'dutra': 'Rodovia Presidente Dutra',
    'régis bittencourt': 'Rodovia Régis Bittencourt',
    'regis bittencourt': 'Rodovia Régis Bittencourt',
    'fernão dias': 'Rodovia Fernão Dias',
    'fernao dias': 'Rodovia Fernão Dias',
    'anhanguera': 'Rodovia Anhanguera',
    'bandeirantes': 'Rodovia dos Bandeirantes',
    'castello branco': 'Rodovia Castello Branco',
    'castelo branco': 'Rodovia Castello Branco',
    'anchieta': 'Rodovia Anchieta',
    'imigrantes': 'Rodovia dos Imigrantes',
    'raposo tavares': 'Rodovia Raposo Tavares',
    'ayrton senna': 'Rodovia Ayrton Senna',
    'washington luís': 'Rodovia Washington Luís',
    'washington luis': 'Rodovia Washington Luís',
    'rodoanel': 'Rodoanel',
}

REGION_FALLBACKS = {
    'norte de mg': (-16.7282, -43.8578, 'Norte de MG', 'MG'),
    'norte de minas': (-16.7282, -43.8578, 'Norte de MG', 'MG'),
    'norte de minas gerais': (-16.7282, -43.8578, 'Norte de MG', 'MG'),
    'grande minas': (-16.7282, -43.8578, 'Grande Minas', 'MG'),
    'sul de minas': (-21.5560, -45.4360, 'Sul de MG', 'MG'),
    'zona da mata': (-21.7642, -43.3503, 'Zona da Mata', 'MG'),
    'triângulo mineiro': (-18.9186, -48.2772, 'Triângulo Mineiro', 'MG'),
    'triangulo mineiro': (-18.9186, -48.2772, 'Triângulo Mineiro', 'MG'),
    'vale do aço': (-19.4683, -42.5367, 'Vale do Aço', 'MG'),
    'vale do aco': (-19.4683, -42.5367, 'Vale do Aço', 'MG'),
}

GENERAL_QUERIES = [
    '("chuva forte" OR temporal OR alagamento OR enchente OR deslizamento OR "queda de barreira" OR "alerta laranja" OR "alerta vermelho") Brasil when:1d -futebol -jogo -mercado',
    '((rodovia OR BR OR pista) (interditada OR interditado OR interdição OR bloqueada OR bloqueado OR bloqueio OR "pista interditada" OR "pista bloqueada" OR "rodovia interditada" OR "rodovia bloqueada" OR "queda de barreira")) Brasil when:1d -futebol -jogo -mercado',
]
SOURCE_QUERIES = []
for _, domain in TRUSTED_NEWS_SITES:
    SOURCE_QUERIES.append(f'("chuva forte" OR temporal OR alagamento OR enchente OR deslizamento OR "alerta vermelho") site:{domain} when:1d -futebol -jogo')
    SOURCE_QUERIES.append(f'(rodovia OR BR OR pista) (interditada OR interditado OR interdição OR bloqueada OR bloqueado OR bloqueio OR "pista interditada" OR "pista bloqueada" OR "rodovia interditada" OR "rodovia bloqueada") site:{domain} when:1d -futebol -jogo')


def load_list(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def same_day(dt: datetime | None) -> bool:
    return bool(dt and dt.astimezone(now_br().tzinfo).date() == now_br().date())


def clean_title(title: str) -> str:
    return re.sub(r'\s+', ' ', title).strip()[:180]


def has_release(text: str) -> bool:
    return has_any(text.casefold(), ROAD_RELEASE_TERMS)


def has_active_block(text: str) -> bool:
    t = text.casefold()
    return has_any(t, ROAD_BLOCK_TERMS) and not has_release(t)


def fetch_google_news(query: str, status: dict[str, Any]) -> list[dict[str, Any]]:
    articles: list[dict[str, Any]] = []
    params = {'q': query, 'hl': 'pt-BR', 'gl': 'BR', 'ceid': 'BR:pt-419'}
    try:
        root = ET.fromstring(fetch_url('https://news.google.com/rss/search?' + urllib.parse.urlencode(params), timeout=45))
        status['googleNewsRequestsSucceeded'] += 1
        for item in root.findall('.//item'):
            source_el = item.find('source')
            dt = parse_rss_date(item.findtext('pubDate') or '')
            articles.append({
                'title': item.findtext('title') or '',
                'url': item.findtext('link') or '',
                'source': source_el.text if source_el is not None and source_el.text else 'Google News',
                'published': dt.isoformat() if dt else '',
                'published_dt': dt,
            })
    except Exception as exc:
        status['googleNewsRequestFailures'] += 1
        status['errors'].append(f'google-news: {exc}')
    return articles


def geocode(text: str, status: dict[str, Any]) -> tuple[float, float, str, str] | None:
    t = text.casefold()
    best = None
    for city, (lat, lon, uf) in CITIES.items():
        if city in t and (not best or len(city) > len(best[0])):
            best = (city, lat, lon, uf)
    if best:
        city, lat, lon, uf = best
        return lat, lon, city.title(), uf
    for needle, data in REGION_FALLBACKS.items():
        if needle in t:
            status['regionFallbackMatches'] += 1
            return data
    padded = f' {t} '
    for alias, city in LOCATION_ALIASES.items():
        if f' {alias} ' in padded or alias in t:
            lat, lon, uf = CITIES[city]
            status['locationAliasMatches'] += 1
            return lat, lon, city.title(), uf
    return None


def normalize_road_code(raw: str) -> str:
    raw = raw.upper().replace(' ', '').replace('--', '-')
    m = re.match(r'^([A-Z]{2})-?(\d{2,4})$', raw)
    return f'{m.group(1)}-{m.group(2)}' if m else raw


def detect_road(text: str) -> str | None:
    t = text.casefold()
    for pattern in ROAD_PATTERNS:
        match = re.search(pattern, text, re.I)
        if match:
            return normalize_road_code(match.group(0))
    for needle, name in NAMED_HIGHWAYS.items():
        if needle in t:
            return name
    return None


def classify_climate(text: str) -> tuple[str, int] | None:
    t = text.casefold()
    if has_any(t, IRRELEVANT_TERMS):
        return None
    if not has_any(t, CLIMATE_TERMS):
        return None
    if has_any(t, ['alerta vermelho','deslizamento','queda de barreira','enchente','inundação']):
        return 'Evento climático severo por notícia', 78
    if has_any(t, CLIMATE_HARD_TERMS):
        return 'Chuva/temporal com impacto operacional', 66
    return 'Condição climática relevante por notícia', 54


def classify_road(text: str) -> tuple[str, int, str] | None:
    t = text.casefold()
    if has_any(t, IRRELEVANT_TERMS):
        return None
    road = detect_road(text)
    if not road:
        return None
    if has_release(t):
        return None
    if not has_active_block(t):
        return None
    return 'Interdição ou bloqueio por notícia', 84, road


def make_climate_event(article: dict[str, Any], status: dict[str, Any]) -> dict[str, Any] | None:
    text = f"{article.get('title','')} {article.get('source','')}"
    classification = classify_climate(text)
    if not classification:
        return None
    geo = geocode(text, status)
    if not geo:
        status['skippedClimateNoCity'] += 1
        return None
    if not same_day(article.get('published_dt')):
        status['skippedByDate'] += 1
        return None
    event_type, risk = classification
    lat, lon, city, uf = geo
    return {
        'active': True,
        'type': 'climate',
        'name': city,
        'region': region_from_event({'state': uf, 'lat': lat, 'lon': lon}),
        'state': uf,
        'lat': lat,
        'lon': lon,
        'risk': risk,
        'current': {'time': article.get('published') or now_iso(), 'precipitation': 0},
        'reasons': [event_type, clean_title(article.get('title') or '')],
        'time': article.get('published') or now_iso(),
        'source': f"Notícias - {article.get('source') or 'Google News'}",
        'sourceProvider': PROVIDER,
        'sourceUrl': article.get('url') or '',
        'headline': clean_title(article.get('title') or ''),
        'createdAt': now_iso(),
    }


def make_road_event(article: dict[str, Any], status: dict[str, Any]) -> dict[str, Any] | None:
    text = f"{article.get('title','')} {article.get('source','')}"
    classification = classify_road(text)
    if not classification:
        return None
    geo = geocode(text, status)
    if not geo:
        status['skippedRoadNoCity'] += 1
        return None
    if not same_day(article.get('published_dt')):
        status['skippedByDate'] += 1
        return None
    event_type, risk, road = classification
    lat, lon, city, uf = geo
    return {
        'active': True,
        'name': f'{event_type} • {road}',
        'road': road,
        'corridor': f'{road} • notícia pública',
        'isMainRoad': True,
        'fallbackCorridor': False,
        'lat': lat,
        'lon': lon,
        'eventType': event_type,
        'description': f"{clean_title(article.get('title') or '')}. Localização aproximada por cidade/região/UF citada na notícia.",
        'risk': risk,
        'source': f"Notícias - {article.get('source') or 'Google News'}",
        'sourceProvider': PROVIDER,
        'sourceUrl': article.get('url') or '',
        'headline': clean_title(article.get('title') or ''),
        'newsDate': article.get('published') or None,
        'updatedAt': now_iso(),
    }


def dedupe_by_url(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for event in events:
        key = str(event.get('sourceUrl') or event.get('headline') or event.get('name'))
        if key and key not in seen:
            seen.add(key)
            out.append(event)
    return out


def strip_previous_supplemental(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [event for event in events if event.get('sourceProvider') != PROVIDER]


def latest_releases_by_road(articles: list[dict[str, Any]]) -> dict[str, datetime]:
    releases: dict[str, datetime] = {}
    for article in articles:
        text = f"{article.get('title','')} {article.get('source','')}"
        road = detect_road(text)
        dt = article.get('published_dt')
        if road and isinstance(dt, datetime) and has_release(text):
            if road not in releases or dt > releases[road]:
                releases[road] = dt
    return releases


def remove_released_events(events: list[dict[str, Any]], releases: dict[str, datetime]) -> list[dict[str, Any]]:
    if not releases:
        return events
    out = []
    for event in events:
        road = str(event.get('road') or '')
        release_dt = releases.get(road)
        if not release_dt:
            out.append(event)
            continue
        news_dt = parse_rss_date(str(event.get('newsDate') or ''))
        if news_dt and news_dt > release_dt:
            out.append(event)
    return out


def main() -> None:
    status: dict[str, Any] = {
        'updatedAt': now_iso(),
        'provider': PROVIDER,
        'datePolicy': 'same-day Brazil time only',
        'roadPolicy': 'only active road blocks/closures; release news removes supplemental road events',
        'queriesPlanned': len(GENERAL_QUERIES) + len(SOURCE_QUERIES),
        'googleNewsRequestsSucceeded': 0,
        'googleNewsRequestFailures': 0,
        'rawArticles': 0,
        'climateEventsAdded': 0,
        'roadEventsAdded': 0,
        'roadReleaseNoticesFound': 0,
        'skippedByDate': 0,
        'skippedClimateNoCity': 0,
        'skippedRoadNoCity': 0,
        'locationAliasMatches': 0,
        'regionFallbackMatches': 0,
        'errors': [],
    }

    articles: list[dict[str, Any]] = []
    for query in GENERAL_QUERIES + SOURCE_QUERIES:
        articles.extend(fetch_google_news(query, status))
        time.sleep(0.4)
    status['rawArticles'] = len(articles)

    releases = latest_releases_by_road(articles)
    status['roadReleaseNoticesFound'] = len(releases)

    climate_events = dedupe_by_url([event for article in articles if (event := make_climate_event(article, status))])[:25]
    road_events = dedupe_by_url([event for article in articles if (event := make_road_event(article, status))])[:25]
    road_events = remove_released_events(road_events, releases)

    existing_climate = strip_previous_supplemental(load_list(CLIMATE_OUTPUT))
    existing_road = strip_previous_supplemental(load_list(ROAD_OUTPUT))

    if climate_events:
        write_json(CLIMATE_OUTPUT, (climate_events + existing_climate)[:120])
    write_json(ROAD_OUTPUT, (road_events + existing_road)[:120])

    status['climateEventsAdded'] = len(climate_events)
    status['roadEventsAdded'] = len(road_events)
    write_json(STATUS_OUTPUT, status)
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
