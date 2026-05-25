#!/usr/bin/env python3
from __future__ import annotations

import email.utils
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

CONFIG = Path("data/config.json")
OUTPUT = Path("data/road_events.json")
STATUS_OUTPUT = Path("data/road_events_status.json")
API_KEY = os.environ.get("TOMTOM_API_KEY", "").strip()
BR_TZ = timezone(timedelta(hours=-3))
MAX_ROAD_BLOCKING_RISK = 69

CATEGORY_LABELS = {
    1: "Acidente", 2: "Neblina", 3: "Condição perigosa", 4: "Chuva",
    5: "Gelo/neve", 6: "Congestionamento", 7: "Faixa bloqueada",
    8: "Interdição", 9: "Obra", 10: "Vento forte", 11: "Alagamento",
    14: "Veículo parado",
}
CATEGORY_RISK = {1: 69, 2: 65, 3: 69, 4: 55, 5: 69, 6: 62, 7: 69, 8: 69, 9: 58, 10: 65, 11: 69, 14: 52}
ENDED_WORDS = (
    "encerrado", "encerrada", "ended", "cleared", "terminado", "terminada",
    "liberado", "liberada", "liberação", "liberacao", "desbloqueado", "desbloqueada",
    "tráfego liberado", "trafego liberado", "trânsito liberado", "transito liberado",
    "pista liberada", "rodovia liberada", "via liberada", "fluxo liberado",
)
ROAD_CODE_RE = re.compile(r"\b(BR|SP|MG|RJ|ES|PR|SC|RS|MS|MT|GO|DF|BA|PE|CE|RN|PB|AL|SE|PI|MA|PA|AM|RO|RR|AP|AC|TO)-?\s?\d{2,4}\b", re.I)
ROAD_WORD_RE = re.compile(r"\b(rodovia|autoestrada|freeway|rodoanel|anel rodovi[aá]rio|marginal tiet[eê]|marginal pinheiros|linha amarela|linha vermelha|via dutra|via expressa)\b", re.I)
LOCAL_WORD_RE = re.compile(r"^\s*(rua|r\.|avenida|av\.?|pra[çc]a|travessa|alameda|largo|beco|viela|estrada municipal)\b", re.I)

BLOCKAGE_TERMS = (
    "interdit", "bloque", "fechad", "pista interditada", "pista bloqueada",
    "rodovia interditada", "rodovia bloqueada", "faixa interditada", "faixa bloqueada",
    "trânsito bloqueado", "transito bloqueado", "tráfego bloqueado", "trafego bloqueado",
    "bloqueio total", "bloqueio parcial", "interdição total", "interdicao total",
    "interdição parcial", "interdicao parcial", "queda de barreira", "deslizamento",
)
RELEASE_TERMS = ENDED_WORDS + (
    "normalizado", "normalizada", "tráfego normal", "trafego normal", "trânsito normal",
    "transito normal", "sem interdição", "sem interdicao", "sem bloqueio", "foi liberada",
    "foi liberado", "volta a fluir", "volta ao normal", "pista reaberta", "rodovia reaberta",
)
PUBLIC_ROAD_TERMS = [
    "interdição", "interdicao", "interditada", "interditado", "bloqueio", "bloqueada",
    "bloqueado", "pista bloqueada", "pista interditada", "rodovia bloqueada", "rodovia interditada",
    "faixa bloqueada", "faixa interditada", "trânsito bloqueado", "transito bloqueado",
    "queda de barreira", "deslizamento", "rodovia fechada", "pista fechada",
]
IRRELEVANT_TERMS = [
    "futebol", "campeonato", "partida", "jogo", "jogador", "time", "placar", "rodada",
    "orçamento", "orçamentos", "mercado", "ações", "dólar", "selic", "inflação",
]

DEFAULT_WATCH_POINTS = [
    {"name": "BR-116 • Régis Bittencourt", "lat": -24.50, "lon": -47.85, "road": "BR-116"},
    {"name": "BR-101 • Rio-Santos", "lat": -23.20, "lon": -44.75, "road": "BR-101"},
    {"name": "BR-040 • Brasília-BH-Rio", "lat": -19.78, "lon": -44.06, "road": "BR-040"},
    {"name": "BR-381 • Fernão Dias", "lat": -21.85, "lon": -45.20, "road": "BR-381"},
    {"name": "BR-163 • Cuiabá-Santarém", "lat": -10.55, "lon": -55.30, "road": "BR-163"},
]

PUBLIC_QUERIES = [
    '(rodovia OR BR OR pista) (interditada OR interditado OR bloqueada OR bloqueado OR "pista interditada" OR "pista bloqueada" OR "rodovia interditada" OR "rodovia bloqueada" OR "queda de barreira") Brasil when:1d -futebol -jogo -mercado',
    '("BR-101" OR "BR 101" OR "BR-116" OR "BR 116" OR "BR-381" OR "BR 381" OR "BR-040" OR "BR 040" OR "BR-163" OR "BR 163") (interdição OR interdicao OR interditada OR bloqueio OR bloqueada OR "pista bloqueada" OR "pista interditada") when:1d -futebol -jogo',
]
GDELT_QUERY = '(rodovia OR "BR-" OR "pista interditada" OR "rodovia interditada" OR "pista bloqueada" OR "rodovia bloqueada" OR "bloqueio na BR" OR "interdição na BR" OR "queda de barreira") sourcecountry:BR'


def cap_road_blocking_risk(risk: int | float) -> int:
    return min(MAX_ROAD_BLOCKING_RISK, int(float(risk or 0)))


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def now_br() -> datetime:
    return datetime.now(timezone.utc).astimezone(BR_TZ)


def load_json(path: Path, fallback: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return fallback


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def monitored_points() -> list[dict[str, Any]]:
    config = load_json(CONFIG, {})
    points: list[dict[str, Any]] = []
    if isinstance(config, dict):
        for key in ("roadCorridors", "roads"):
            value = config.get(key)
            if isinstance(value, list):
                points.extend(item for item in value if isinstance(item, dict))
    points = points or DEFAULT_WATCH_POINTS
    result = []
    seen = set()
    for item in points:
        try:
            lat = round(float(item["lat"]), 4)
            lon = round(float(item["lon"]), 4)
        except Exception:
            continue
        if (lat, lon) in seen:
            continue
        seen.add((lat, lon))
        result.append({**item, "lat": lat, "lon": lon, "road": item.get("road") or item.get("name") or "Corredor rodoviário"})
    return result


def bbox_around(lat: float, lon: float, delta: float = 0.09) -> tuple[float, float, float, float]:
    return (round(lon - delta, 4), round(lat - delta, 4), round(lon + delta, 4), round(lat + delta, 4))


def first_coordinate(geometry: dict[str, Any]) -> tuple[float, float] | None:
    coords = geometry.get("coordinates")
    if isinstance(coords, list) and len(coords) >= 2 and all(isinstance(x, (int, float)) for x in coords[:2]):
        return float(coords[1]), float(coords[0])
    if isinstance(coords, list):
        for item in coords:
            if isinstance(item, list) and len(item) >= 2:
                return float(item[1]), float(item[0])
    return None


def event_description(properties: dict[str, Any], label: str) -> str:
    texts = []
    for event in properties.get("events") or []:
        if isinstance(event, dict):
            text = event.get("description") or event.get("phrase") or event.get("eventDescription")
            if text and text not in texts:
                texts.append(str(text))
    return "; ".join(texts[:3]) if texts else f"Evento detectado pela TomTom Traffic API: {label}."


def has_any_text(text: str, terms: tuple[str, ...] | list[str]) -> bool:
    folded = text.casefold()
    return any(term.casefold() in folded for term in terms)


def is_release_notice(text: str) -> bool:
    return has_any_text(text, RELEASE_TERMS)


def is_blocking_notice(text: str) -> bool:
    return has_any_text(text, BLOCKAGE_TERMS) and not is_release_notice(text)


def is_finished(description: str) -> bool:
    return is_release_notice(description)


def split_names(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value]
    names: list[str] = []
    for item in values:
        if isinstance(item, str):
            for part in re.split(r"\s*/\s*|\s*;\s*|\s+--\s+", item):
                part = part.strip(" ,;|-")
                if part:
                    names.append(part)
    return names


def is_road_allowed(text: str) -> bool:
    if not text or LOCAL_WORD_RE.search(text):
        return False
    return bool(ROAD_CODE_RE.search(text) or ROAD_WORD_RE.search(text))


def has_local_street(properties: dict[str, Any]) -> bool:
    for key in ("from", "to"):
        for name in split_names(properties.get(key)):
            if LOCAL_WORD_RE.search(name):
                return True
    return False


def get_road(properties: dict[str, Any]) -> str | None:
    for key in ("roadNumbers", "from", "to"):
        for name in split_names(properties.get(key)):
            if is_road_allowed(name):
                return name
    return None


def fetch_url(url: str, timeout: int = 45) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "rodovias-clima-github-action/2.3"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def fetch_bbox(bbox: tuple[float, float, float, float]) -> list[dict[str, Any]]:
    west, south, east, north = bbox
    fields = "{incidents{type,geometry{type,coordinates},properties{iconCategory,magnitudeOfDelay,events{description,code},from,to,roadNumbers,length,delay}}}"
    query = urllib.parse.urlencode({"key": API_KEY, "bbox": f"{west},{south},{east},{north}", "fields": fields, "language": "pt-PT"}, safe="{},")
    url = f"https://api.tomtom.com/traffic/services/5/incidentDetails?{query}"
    payload = json.loads(fetch_url(url, timeout=25).decode("utf-8"))
    incidents = payload.get("incidents", [])
    return incidents if isinstance(incidents, list) else []


def normalize_incident(incident: dict[str, Any], corridor: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    geometry = incident.get("geometry") or {}
    props = incident.get("properties") or {}
    if not isinstance(geometry, dict) or not isinstance(props, dict):
        return None, "invalid"
    coord = first_coordinate(geometry)
    if not coord:
        return None, "invalid"
    category = int(props.get("iconCategory") or 0)
    label = CATEGORY_LABELS.get(category, "Ocorrência rodoviária")
    description = event_description(props, label)
    if is_finished(description):
        return None, "finished"
    blocking = category in (7, 8) or is_blocking_notice(description) or is_blocking_notice(json.dumps(props, ensure_ascii=False))
    if not blocking:
        return None, "not_blocking"
    road = get_road(props)
    fallback_used = False
    if not road:
        if has_local_street(props):
            return None, "local_street"
        road = str(corridor.get("road") or corridor.get("name") or "Corredor rodoviário")
        fallback_used = True
    lat, lon = coord
    risk = cap_road_blocking_risk(CATEGORY_RISK.get(category, MAX_ROAD_BLOCKING_RISK))
    return {
        "active": True, "name": f"{label} • {road}", "road": road,
        "corridor": corridor.get("name") or road, "isMainRoad": True,
        "fallbackCorridor": fallback_used, "lat": round(lat, 6), "lon": round(lon, 6),
        "eventType": label, "description": description, "risk": risk,
        "severity": "Alto" if risk >= 60 else "Moderado",
        "severityRule": "Eventos rodoviários de bloqueio/interdição têm teto 69 (Alta).",
        "source": "TomTom Traffic API", "updatedAt": now_iso(),
    }, "ok"


def normalize_road_code(raw: str) -> str:
    raw = raw.upper().replace(" ", "").replace("--", "-")
    m = re.match(r"^([A-Z]{2})-?(\d{2,4})$", raw)
    return f"{m.group(1)}-{m.group(2)}" if m else raw


def detect_road(text: str) -> str | None:
    match = ROAD_CODE_RE.search(text)
    if match:
        return normalize_road_code(match.group(0))
    t = text.casefold()
    names = {
        "dutra": "BR-116", "régis bittencourt": "BR-116", "regis bittencourt": "BR-116",
        "fernão dias": "BR-381", "fernao dias": "BR-381", "rio-santos": "BR-101",
        "transbrasiliana": "BR-153", "cuiabá-santarém": "BR-163", "cuiaba-santarem": "BR-163",
    }
    for needle, road in names.items():
        if needle in t:
            return road
    return None


def article_dt(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(BR_TZ)
    except Exception:
        return None


def same_day(dt: datetime | None) -> bool:
    return bool(dt and dt.date() == now_br().date())


def public_event_type(text: str) -> tuple[str, int] | None:
    t = text.casefold()
    if any(term in t for term in IRRELEVANT_TERMS):
        return None
    if is_release_notice(t):
        return None
    if not is_blocking_notice(t):
        return None
    return "Interdição ou bloqueio por notícia pública", MAX_ROAD_BLOCKING_RISK


def corridor_for_article(text: str, road: str | None, points: list[dict[str, Any]]) -> dict[str, Any] | None:
    t = text.casefold()
    if road:
        for p in points:
            if road.upper().replace(" ", "") in str(p.get("road") or p.get("name") or "").upper().replace(" ", ""):
                return p
    best = None
    for p in points:
        city = str(p.get("city") or "").casefold()
        state = str(p.get("state") or "").casefold()
        name = str(p.get("name") or "").casefold()
        if city and city in t:
            return p
        if state and re.search(rf"\b{re.escape(state)}\b", t):
            best = best or p
        if name and name in t:
            return p
    return best


def clean_title(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip()[:180]


def fetch_google_news(status: dict[str, Any]) -> list[dict[str, Any]]:
    articles: list[dict[str, Any]] = []
    for query in PUBLIC_QUERIES:
        params = {"q": query, "hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"}
        try:
            root = ET.fromstring(fetch_url("https://news.google.com/rss/search?" + urllib.parse.urlencode(params), timeout=45))
            status["publicFallbackRequestsSucceeded"] += 1
            for item in root.findall(".//item"):
                source_el = item.find("source")
                articles.append({
                    "title": item.findtext("title") or "",
                    "url": item.findtext("link") or "",
                    "source": source_el.text if source_el is not None and source_el.text else "Google News",
                    "published": item.findtext("pubDate") or "",
                    "published_dt": article_dt(item.findtext("pubDate") or ""),
                    "provider": "Google News RSS",
                })
        except Exception as exc:
            status["publicFallbackRequestFailures"] += 1
            status["errors"].append(f"google-news-fallback: {exc}")
    return articles


def fetch_gdelt(status: dict[str, Any]) -> list[dict[str, Any]]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=30)
    params = {
        "query": GDELT_QUERY,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": "100",
        "sort": "HybridRel",
        "startdatetime": start.strftime("%Y%m%d%H%M%S"),
        "enddatetime": end.strftime("%Y%m%d%H%M%S"),
    }
    try:
        payload = json.loads(fetch_url("https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode(params), timeout=60).decode("utf-8", errors="replace"))
        status["publicFallbackRequestsSucceeded"] += 1
        out = []
        for article in payload.get("articles", []) if isinstance(payload, dict) else []:
            seen = str(article.get("seendate") or "")
            dt = None
            m = re.search(r"(\d{8})T?(\d{6})", seen)
            if m:
                try:
                    dt = datetime.strptime("".join(m.groups()), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc).astimezone(BR_TZ)
                except Exception:
                    pass
            out.append({
                "title": article.get("title") or "",
                "url": article.get("url") or "",
                "source": article.get("sourceCommonName") or article.get("domain") or "GDELT",
                "published": dt.isoformat() if dt else "",
                "published_dt": dt,
                "provider": "GDELT DOC 2.0",
            })
        return out
    except Exception as exc:
        status["publicFallbackRequestFailures"] += 1
        status["errors"].append(f"gdelt-fallback: {exc}")
        return []


def public_fallback_events(points: list[dict[str, Any]], status: dict[str, Any]) -> list[dict[str, Any]]:
    articles = fetch_gdelt(status) + fetch_google_news(status)
    status["publicFallbackRawArticles"] = len(articles)
    release_by_road: dict[str, datetime] = {}
    for article in articles:
        text = f"{article.get('title','')} {article.get('source','')}"
        road = detect_road(text)
        dt = article.get("published_dt")
        if road and is_release_notice(text) and isinstance(dt, datetime):
            current = release_by_road.get(road)
            if current is None or dt > current:
                release_by_road[road] = dt
    out = []
    seen = set()
    for article in articles:
        text = f"{article.get('title','')} {article.get('source','')}"
        road = detect_road(text)
        classification = public_event_type(text)
        if not road or not classification:
            continue
        dt = article.get("published_dt")
        if dt and not same_day(dt) and dt < now_br() - timedelta(hours=36):
            continue
        release_dt = release_by_road.get(road)
        if release_dt and (not isinstance(dt, datetime) or release_dt >= dt):
            status["publicFallbackSkippedReleased"] += 1
            continue
        corridor = corridor_for_article(text, road, points)
        if not corridor:
            status["publicFallbackSkippedNoCorridor"] += 1
            continue
        event_type, risk = classification
        risk = cap_road_blocking_risk(risk)
        key = article.get("url") or clean_title(article.get("title") or "")
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "active": True,
            "name": f"{event_type} • {road}",
            "road": road,
            "corridor": corridor.get("name") or road,
            "isMainRoad": True,
            "fallbackCorridor": True,
            "lat": float(corridor["lat"]),
            "lon": float(corridor["lon"]),
            "eventType": event_type,
            "description": f"{clean_title(article.get('title') or '')}. Localização aproximada pelo corredor monitorado.",
            "risk": risk,
            "severity": "Alto" if risk >= 60 else "Moderado",
            "severityRule": "Eventos rodoviários de bloqueio/interdição têm teto 69 (Alta).",
            "source": f"Notícias públicas - {article.get('source') or article.get('provider') or 'fonte pública'}",
            "sourceProvider": article.get("provider") or "Fonte pública sem chave",
            "sourceUrl": article.get("url") or "",
            "headline": clean_title(article.get("title") or ""),
            "newsDate": article.get("published") or None,
            "updatedAt": now_iso(),
        })
    out.sort(key=lambda item: int(item.get("risk", 0)), reverse=True)
    status["publicFallbackEventsWritten"] = len(out[:50])
    return out[:50]


def hard_api_failure(status: dict[str, Any]) -> bool:
    if status.get("bboxRequestsSucceeded", 0) > 0:
        return False
    text = json.dumps(status.get("errors", []), ensure_ascii=False).casefold()
    return bool(status.get("errors")) and any(term in text for term in ("insufficientfunds", "forbidden", "403", "quota", "credit"))


def main() -> None:
    points = monitored_points()
    status: dict[str, Any] = {
        "updatedAt": now_iso(),
        "provider": "TomTom Traffic API + fallback público GDELT/Google News RSS",
        "tomtomKeyConfigured": bool(API_KEY),
        "language": "pt-PT",
        "riskRule": "Só gera evento rodoviário quando houver bloqueio/interdição ativa; eventos rodoviários de bloqueio/interdição têm teto 69, severidade Alta.",
        "maxRoadBlockingRisk": MAX_ROAD_BLOCKING_RISK,
        "monitoredPoints": len(points),
        "bboxRequestsPlanned": len(points) if API_KEY else 0,
        "bboxRequestsSucceeded": 0,
        "rawIncidents": 0,
        "eventsWritten": 0,
        "skippedFinishedOrInvalid": 0,
        "skippedNonBlocking": 0,
        "skippedLocalStreet": 0,
        "publicFallbackUsed": False,
        "publicFallbackRequestsSucceeded": 0,
        "publicFallbackRequestFailures": 0,
        "publicFallbackRawArticles": 0,
        "publicFallbackEventsWritten": 0,
        "publicFallbackSkippedNoCorridor": 0,
        "publicFallbackSkippedReleased": 0,
        "keptPreviousOnApiFailure": False,
        "errors": [],
    }

    output = []
    seen = set()
    if API_KEY:
        for point in points:
            bbox = bbox_around(float(point["lat"]), float(point["lon"]))
            try:
                incidents = fetch_bbox(bbox)
                status["bboxRequestsSucceeded"] += 1
                status["rawIncidents"] += len(incidents)
                for incident in incidents:
                    normalized, reason = normalize_incident(incident, point)
                    if not normalized:
                        if reason == "local_street":
                            status["skippedLocalStreet"] += 1
                        elif reason == "not_blocking":
                            status["skippedNonBlocking"] += 1
                        else:
                            status["skippedFinishedOrInvalid"] += 1
                        continue
                    key = (normalized["eventType"], round(float(normalized["lat"]), 3), round(float(normalized["lon"]), 3), normalized["road"])
                    if key in seen:
                        continue
                    seen.add(key)
                    output.append(normalized)
            except urllib.error.HTTPError as exc:
                body = ""
                try:
                    body = exc.read().decode("utf-8")[:400]
                except Exception:
                    pass
                status["errors"].append({"bbox": bbox, "httpStatus": exc.code, "message": body or str(exc)})
            except Exception as exc:
                status["errors"].append({"bbox": bbox, "message": str(exc)})
    else:
        status["errors"].append("TOMTOM_API_KEY não está configurada nos Secrets do GitHub Actions.")

    output.sort(key=lambda item: int(item.get("risk", 0)), reverse=True)

    if not output and (hard_api_failure(status) or not API_KEY):
        fallback = public_fallback_events(points, status)
        if fallback:
            output = fallback
            status["publicFallbackUsed"] = True

    status["eventsWritten"] = len(output)
    write_json(OUTPUT, output)
    write_json(STATUS_OUTPUT, status)
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
