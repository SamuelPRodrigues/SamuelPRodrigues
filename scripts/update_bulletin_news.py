#!/usr/bin/env python3
from __future__ import annotations

import email.utils
import hashlib
import html
import json
import os
import re
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

OUTPUT = Path('data/boletim_news.json')
STATUS = Path('data/boletim_news_status.json')
ROAD_EVENTS = Path('data/road_events.json')
MANUAL_EVENTS = Path('data/manual_events.json')
MAX_ITEMS_PER_QUERY = int(os.environ.get('BULLETIN_MAX_ITEMS_PER_QUERY', '18'))
MAX_STORED_ITEMS = int(os.environ.get('BULLETIN_MAX_STORED_ITEMS', '220'))

QUERIES = [
    ('road', '(rodovia OR estrada OR pista OR BR) (acidente OR interdição OR interditada OR bloqueio OR bloqueada OR obras OR deslizamento OR erosão) when:7d'),
    ('road', '(BR-101 OR BR-116 OR BR-040 OR BR-381 OR BR-153 OR BR-163 OR BR-262 OR BR-277 OR BR-364) (acidente OR interdição OR bloqueio OR obras) when:7d'),
    ('weather_news', '(chuva forte OR temporal OR alagamento OR inundação OR deslizamento OR enxurrada) (rodovia OR estrada OR trânsito OR cidade OR rota) when:7d'),
    ('mobilization', '(caminhoneiros OR transporte OR carga) (greve OR paralisação OR manifestação OR bloqueio) (rodovia OR estrada OR via OR acesso) when:14d'),
    ('security', '(operação policial OR bloqueio policial OR fiscalização OR apreensão) (rodovia OR estrada OR BR OR caminhão OR carga OR trânsito) when:7d'),
    ('operational', '(porto OR terminal OR acesso OR aeroporto OR balsa) (bloqueio OR interditado OR interdição OR restrição OR fila OR paralisação) when:14d'),
]

REGION_HINTS = {
    'Norte': ['acre', 'amazonas', 'amapá', 'amapa', 'pará', 'para', 'rondônia', 'rondonia', 'roraima', 'tocantins', 'manaus', 'belém', 'belem', 'porto velho'],
    'Nordeste': ['bahia', 'ceará', 'ceara', 'pernambuco', 'paraíba', 'paraiba', 'rio grande do norte', 'alagoas', 'sergipe', 'piauí', 'piaui', 'maranhão', 'maranhao', 'recife', 'salvador', 'fortaleza'],
    'Centro-Oeste': ['goiás', 'goias', 'mato grosso', 'mato grosso do sul', 'distrito federal', 'brasília', 'brasilia', 'goiânia', 'goiania', 'cuiabá', 'cuiaba', 'campo grande'],
    'Sudeste': ['são paulo', 'sao paulo', 'rio de janeiro', 'minas gerais', 'espírito santo', 'espirito santo', 'belo horizonte', 'vitória', 'vitoria'],
    'Sul': ['paraná', 'parana', 'santa catarina', 'rio grande do sul', 'curitiba', 'florianópolis', 'florianopolis', 'porto alegre'],
}

CATEGORY_LABELS = {
    'road': 'Rodovia',
    'weather_news': 'Clima',
    'mobilization': 'Mobilização',
    'security': 'Segurança pública',
    'operational': 'Operacional',
}

RISK_HINTS = {
    'interdit': 69, 'bloque': 66, 'acidente': 58, 'deslizamento': 64, 'erosao': 60,
    'alagamento': 58, 'inundacao': 62, 'greve': 55, 'paralisacao': 55, 'manifestacao': 52,
    'operacao policial': 48, 'fiscalizacao': 42, 'temporal': 45, 'chuva forte': 45,
}

BLOCKLIST_TERMS = {
    # Notícias sem impacto operacional direto.
    'elefante marinho', 'baleia', 'golfinho', 'tartaruga', 'animal silvestre', 'praia de conceicao',
    'celebridade', 'famoso', 'reality', 'bbb', 'futebol', 'campeonato', 'show', 'festival', 'cinema',
    'novela', 'horoscopo', 'loteria', 'mega sena', 'dinheiro falso', 'moeda falsa', 'nota falsa',
}

ROAD_TERMS = {'rodovia', 'estrada', 'pista', 'transito', 'trafego', 'km', 'br-', 'serra', 'anel viario', 'via expressa'}
ROAD_IMPACT_TERMS = {'interdit', 'bloque', 'acidente', 'obra', 'deslizamento', 'erosao', 'queda de barreira', 'congestionamento', 'liberada parcialmente'}
WEATHER_TERMS = {'chuva', 'temporal', 'alagamento', 'inundacao', 'enxurrada', 'deslizamento', 'granizo', 'vendaval', 'neblina', 'baixa visibilidade', 'frente fria'}
WEATHER_IMPACT_TERMS = {'rodovia', 'estrada', 'transito', 'rota', 'deslocamento', 'interdit', 'bloque', 'alagamento', 'deslizamento', 'queda de arvore', 'cidade em alerta', 'defesa civil'}
MOBILIZATION_TERMS = {'caminhoneiro', 'greve', 'paralisacao', 'manifestacao', 'protesto', 'bloqueio'}
MOBILIZATION_CONTEXT = {'rodovia', 'estrada', 'br-', 'via', 'acesso', 'carga', 'transporte', 'porto', 'terminal'}
SECURITY_TERMS = {'operacao policial', 'policia', 'prf', 'fiscalizacao', 'apreensao', 'bloqueio policial'}
SECURITY_CONTEXT = {'rodovia', 'estrada', 'br-', 'caminhao', 'carga', 'transito', 'rota', 'porto', 'terminal', 'acesso'}
OPERATIONAL_TERMS = {'porto', 'terminal', 'aeroporto', 'balsa', 'acesso', 'fila', 'restricao', 'interdicao', 'bloqueio', 'paralisacao'}

BR_RE = re.compile(r'\b(?:BR|SP|MG|RJ|ES|PR|SC|RS|MS|MT|GO|DF|BA|PE|CE|RN|PB|AL|SE|PI|MA|PA|AM|RO|RR|AP|AC|TO)[-\s]?\d{2,4}\b', re.I)


def now_iso() -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def text(value: Any) -> str:
    return str(value or '').strip()


def clean(value: Any) -> str:
    value = html.unescape(text(value))
    value = re.sub(r'<[^>]+>', ' ', value)
    return re.sub(r'\s+', ' ', value).strip()


def fold(value: Any) -> str:
    value = unicodedata.normalize('NFD', clean(value).casefold())
    value = ''.join(ch for ch in value if unicodedata.category(ch) != 'Mn')
    return re.sub(r'\s+', ' ', value).strip()


def has_any(blob: str, terms: set[str]) -> bool:
    return any(term in blob for term in terms)


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


def parse_dt(value: Any) -> str:
    raw = text(value)
    if not raw:
        return ''
    try:
        dt = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    except Exception:
        pass
    try:
        dt = email.utils.parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    except Exception:
        return ''


def normalize_url(value: Any) -> str:
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


def infer_region(blob: str) -> str:
    folded = fold(blob)
    for region, hints in REGION_HINTS.items():
        if any(fold(h) in folded for h in hints):
            return region
    return 'Sem região'


def is_blocked(blob: str) -> bool:
    folded = fold(blob)
    return any(term in folded for term in BLOCKLIST_TERMS)


def is_relevant(category: str, blob: str) -> bool:
    folded = fold(blob)
    if is_blocked(folded):
        return False
    has_road_code = bool(BR_RE.search(blob))
    if category == 'road':
        return (has_road_code or has_any(folded, ROAD_TERMS)) and has_any(folded, ROAD_IMPACT_TERMS)
    if category == 'weather_news':
        return has_any(folded, WEATHER_TERMS) and (has_any(folded, WEATHER_IMPACT_TERMS) or has_road_code)
    if category == 'mobilization':
        return has_any(folded, MOBILIZATION_TERMS) and (has_any(folded, MOBILIZATION_CONTEXT) or has_road_code)
    if category == 'security':
        return has_any(folded, SECURITY_TERMS) and (has_any(folded, SECURITY_CONTEXT) or has_road_code)
    if category == 'operational':
        return has_any(folded, OPERATIONAL_TERMS)
    return False


def is_relevant_item(item: dict[str, Any]) -> bool:
    category = text(item.get('category') or 'operational')
    blob = ' '.join(text(item.get(k)) for k in ('title', 'description', 'source', 'region', 'url'))
    return is_relevant(category, blob)


def infer_risk(blob: str, category: str) -> int:
    folded = fold(blob)
    risk = {'road': 45, 'weather_news': 38, 'mobilization': 40, 'security': 34, 'operational': 30}.get(category, 30)
    for key, value in RISK_HINTS.items():
        if key in folded:
            risk = max(risk, value)
    return min(79, risk)


def severity(risk: int) -> str:
    if risk >= 80:
        return 'Crítica'
    if risk >= 60:
        return 'Alta'
    if risk >= 35:
        return 'Moderada'
    if risk >= 1:
        return 'Baixa'
    return 'Sem risco'


def news_id(url: str, title: str) -> str:
    return hashlib.sha256(f'{normalize_url(url)}|{clean(title).casefold()}'.encode('utf-8')).hexdigest()[:24]


def fetch_rss(category: str, query: str) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    params = {'q': query, 'hl': 'pt-BR', 'gl': 'BR', 'ceid': 'BR:pt-419'}
    url = 'https://news.google.com/rss/search?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'User-Agent': 'boletim-news/1.0'})
    with urllib.request.urlopen(req, timeout=25) as response:
        xml = response.read()
    root = ET.fromstring(xml)
    rows: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    for item in root.findall('.//item')[:MAX_ITEMS_PER_QUERY]:
        title = clean(item.findtext('title'))
        link = normalize_url(item.findtext('link'))
        description = clean(item.findtext('description'))
        published = parse_dt(item.findtext('pubDate'))
        source_node = item.find('source')
        source = clean(source_node.text if source_node is not None else 'Google News')
        blob = f'{title} {description} {source} {link}'
        if not is_relevant(category, blob):
            rejected.append({'category': category, 'title': title[:180], 'reason': 'not_operationally_relevant'})
            continue
        risk = infer_risk(blob, category)
        rows.append({
            'news_id': news_id(link, title),
            'title': title,
            'description': description or title,
            'category': category,
            'categoryLabel': CATEGORY_LABELS.get(category, 'Operacional'),
            'region': infer_region(blob),
            'risk': risk,
            'severity': severity(risk),
            'source': source,
            'url': link,
            'publishedAt': published,
            'collectedAt': now_iso(),
            'provider': 'Google News RSS',
            'sourceKind': 'news',
        })
    return rows, rejected


def road_news_from_events() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in (ROAD_EVENTS, MANUAL_EVENTS):
        data = read_json(path, [])
        if not isinstance(data, list):
            continue
        for event in data:
            if not isinstance(event, dict):
                continue
            blob = ' '.join(text(event.get(k)) for k in ('source', 'sourceProvider', 'name', 'description', 'headline', 'eventType', 'event_type', 'road'))
            if not re.search(r'not[ií]cias? p[uú]blicas?|google news|fonte p[uú]blica|g1|portal|jornal', blob, flags=re.I):
                continue
            if not is_relevant('road', blob):
                continue
            url = normalize_url(event.get('sourceUrl') or event.get('source_url'))
            title = clean(event.get('headline') or event.get('name') or event.get('eventType') or 'Notícia rodoviária')
            description = clean(event.get('description') or title)
            risk = min(79, int(float(event.get('risk') or 45)))
            sources = []
            raw_sources = event.get('sources') or []
            if isinstance(raw_sources, list):
                for src in raw_sources:
                    if isinstance(src, dict):
                        src_url = normalize_url(src.get('url') or src.get('sourceUrl') or src.get('source_url'))
                        if src_url:
                            sources.append({'source': clean(src.get('source') or src.get('name') or 'Fonte pública'), 'url': src_url, 'headline': clean(src.get('headline') or src.get('title') or title)})
            rows.append({
                'news_id': news_id(url or text(event.get('stable_event_id')), title),
                'title': title,
                'description': description,
                'category': 'road',
                'categoryLabel': 'Rodovia',
                'region': text(event.get('region') or event.get('state') or event.get('city') or 'Sem região'),
                'risk': risk,
                'severity': severity(risk),
                'source': clean(event.get('source') or event.get('sourceProvider') or 'Notícia rodoviária salva'),
                'url': url,
                'publishedAt': parse_dt(event.get('newsDate') or event.get('plannedStartAt') or event.get('updatedAt') or event.get('updated_at') or event.get('last_seen_at')),
                'collectedAt': now_iso(),
                'provider': 'Eventos rodoviários salvos',
                'sourceKind': 'saved_road_news',
                'sources': sources,
            })
    return rows


def merge_with_previous(new_items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    previous_payload = read_json(OUTPUT, {})
    previous = previous_payload.get('items') if isinstance(previous_payload, dict) else []
    if not isinstance(previous, list):
        previous = []
    removed_previous = 0
    merged: dict[str, dict[str, Any]] = {}
    for item in previous + new_items:
        if not isinstance(item, dict):
            continue
        if not is_relevant_item(item):
            removed_previous += 1
            continue
        key = text(item.get('news_id')) or news_id(item.get('url', ''), item.get('title', ''))
        if not key:
            continue
        current = merged.get(key)
        if not current or text(item.get('collectedAt')) > text(current.get('collectedAt')):
            merged[key] = item
    out = list(merged.values())
    out.sort(key=lambda x: (text(x.get('publishedAt')), text(x.get('collectedAt'))), reverse=True)
    return out[:MAX_STORED_ITEMS], removed_previous


def main() -> None:
    items: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    for category, query in QUERIES:
        try:
            fetched, skipped = fetch_rss(category, query)
            items.extend(fetched)
            rejected.extend(skipped)
        except Exception as exc:
            errors.append({'category': category, 'query': query, 'error': str(exc)[:240]})
    road_saved = road_news_from_events()
    items.extend(road_saved)
    final_items, removed_previous = merge_with_previous(items)
    payload = {
        'updatedAt': now_iso(),
        'source': 'bulletin_news_collection',
        'policy': 'Boletim usa notícias reais salvas/coletadas. Eventos climáticos do mapa não são usados; clima entra apenas por notícia pública validada por relevância operacional.',
        'items': final_items,
    }
    write_json(OUTPUT, payload)
    status = {
        'updatedAt': now_iso(),
        'queries': len(QUERIES),
        'newItemsBeforeMerge': len(items),
        'savedRoadNewsReused': len(road_saved),
        'storedItems': len(final_items),
        'rejectedAsIrrelevant': len(rejected),
        'removedPreviouslyStoredIrrelevant': removed_previous,
        'rejectedSample': rejected[:25],
        'errors': errors,
    }
    write_json(STATUS, status)
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
