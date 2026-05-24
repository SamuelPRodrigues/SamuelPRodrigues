#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
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

ROAD_TERMS = [
    'rodovia interditada','rodovia bloqueada','pista interditada','pista bloqueada',
    'interdição na rodovia','acidente na rodovia','acidente deixa','congestionamento na rodovia',
    'queda de barreira na rodovia','caminhão tomba','carreta tomba','bloqueio na br',
    'trânsito parado','faixa interditada','km '
]
ROAD_HARD_TERMS = ['interditada','interditado','bloqueada','bloqueado','acidente','tomba','congestionamento','queda de barreira']
ROAD_CONTEXT_TERMS = ['rodovia','br-','br ','sp-','mg-','rj-','pr-','sc-','rs-','ba-','pe-','ce-','go-','mt-','ms-','es-','km ']

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

GENERAL_QUERIES = [
    '("chuva forte" OR temporal OR alagamento OR enchente OR deslizamento OR "queda de barreira" OR "alerta laranja" OR "alerta vermelho") Brasil when:1d -futebol -jogo -mercado',
    '((rodovia OR BR OR "pista interditada" OR "rodovia interditada") (acidente OR bloqueio OR interdição OR congestionamento OR "queda de barreira" OR "carreta tomba")) Brasil when:1d -futebol -jogo -mercado',
]
SOURCE_QUERIES = []
for _, domain in TRUSTED_NEWS_SITES:
    SOURCE_QUERIES.append(f'("chuva forte" OR temporal OR alagamento OR enchente OR deslizamento OR "alerta vermelho") site:{domain} when:1d -futebol -jogo')
    SOURCE_QUERIES.append(f'(rodovia OR BR OR "pista interditada" OR "rodovia interditada" OR acidente OR bloqueio) site:{domain} when:1d -futebol -jogo')


def load_list(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def same_day(dt: datetime | None) -> bool:
    return bool(dt and dt.astimezone(now_br().tzinfo).date() == now_br().date())


def clean_title(title: str) -> str:
    return re.sub(r'\s+', ' ', title).strip()[:160]


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
    padded = f' {t} '
    for alias, city in LOCATION_ALIASES.items():
        if f' {alias} ' in padded or alias in t:
            lat, lon, uf = CITIES[city]
            status['locationAliasMatches'] += 1
            return lat, lon, city.title(), uf
    return None


def detect_road(text: str) -> str | None:
    t = text.casefold()
    for pattern in ROAD_PATTERNS:
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(0).upper().replace(' ', '').replace('BR', 'BR-').replace('SP', 'SP-').replace('MG', 'MG-').replace('RJ', 'RJ-').replace('PR', 'PR-').replace('SC', 'SC-').replace('RS', 'RS-').replace('BA', 'BA-').replace('PE', 'PE-').replace('CE', 'CE-').replace('GO', 'GO-').replace('MT', 'MT-').replace('MS', 'MS-').replace('ES', 'ES-').replace('--', '-')
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
    if not (has_any(t, ROAD_HARD_TERMS) or has_any(t, ROAD_TERMS)):
        return None
    if has_any(t, ['interditada','interditado','bloqueada','bloqueado','queda de barreira']):
        return 'Interdição ou bloqueio por notícia', 72, road
    if has_any(t, ['acidente','tomba','carreta','caminhão']):
        return 'Acidente rodoviário por notícia', 64, road
    return 'Ocorrência rodoviária por notícia', 58, road


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
    event = {
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
    return event


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
        'description': f"{clean_title(article.get('title') or '')}. Região aproximada por cidade/UF citada na notícia.",
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


def main() -> None:
    status: dict[str, Any] = {
        'updatedAt': now_iso(),
        'provider': PROVIDER,
        'datePolicy': 'same-day Brazil time only',
        'queriesPlanned': len(GENERAL_QUERIES) + len(SOURCE_QUERIES),
        'googleNewsRequestsSucceeded': 0,
        'googleNewsRequestFailures': 0,
        'rawArticles': 0,
        'climateEventsAdded': 0,
        'roadEventsAdded': 0,
        'skippedByDate': 0,
        'skippedClimateNoCity': 0,
        'skippedRoadNoCity': 0,
        'locationAliasMatches': 0,
        'errors': [],
    }

    articles: list[dict[str, Any]] = []
    for query in GENERAL_QUERIES + SOURCE_QUERIES:
        articles.extend(fetch_google_news(query, status))
        time.sleep(0.4)
    status['rawArticles'] = len(articles)

    climate_events = dedupe_by_url([event for article in articles if (event := make_climate_event(article, status))])[:25]
    road_events = dedupe_by_url([event for article in articles if (event := make_road_event(article, status))])[:25]

    existing_climate = strip_previous_supplemental(load_list(CLIMATE_OUTPUT))
    existing_road = strip_previous_supplemental(load_list(ROAD_OUTPUT))

    if climate_events:
        write_json(CLIMATE_OUTPUT, (climate_events + existing_climate)[:120])
    if road_events:
        write_json(ROAD_OUTPUT, (road_events + existing_road)[:120])

    status['climateEventsAdded'] = len(climate_events)
    status['roadEventsAdded'] = len(road_events)
    write_json(STATUS_OUTPUT, status)
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
