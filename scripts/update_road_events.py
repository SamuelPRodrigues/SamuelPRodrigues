#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

CONFIG = Path("data/config.json")
OUTPUT = Path("data/road_events.json")
STATUS_OUTPUT = Path("data/road_events_status.json")
API_KEY = os.environ.get("TOMTOM_API_KEY", "").strip()

CATEGORY_LABELS = {
    1: "Acidente", 2: "Neblina", 3: "Condição perigosa", 4: "Chuva",
    5: "Gelo/neve", 6: "Congestionamento", 7: "Faixa bloqueada",
    8: "Interdição", 9: "Obra", 10: "Vento forte", 11: "Alagamento",
    14: "Veículo parado",
}
CATEGORY_RISK = {1: 82, 2: 65, 3: 72, 4: 55, 5: 80, 6: 62, 7: 70, 8: 92, 9: 58, 10: 65, 11: 86, 14: 52}
ENDED_WORDS = ("encerrado", "encerrada", "ended", "cleared", "terminado", "terminada")
ROAD_CODE_RE = re.compile(r"\b(BR|SP|MG|RJ|ES|PR|SC|RS|MS|MT|GO|DF|BA|PE|CE|RN|PB|AL|SE|PI|MA|PA|AM|RO|RR|AP|AC|TO)-?\s?\d{2,4}\b", re.I)
ROAD_WORD_RE = re.compile(r"\b(rodovia|autoestrada|freeway|rodoanel|anel rodovi[aá]rio|marginal tiet[eê]|marginal pinheiros|linha amarela|linha vermelha|via dutra|via expressa)\b", re.I)
LOCAL_WORD_RE = re.compile(r"^\s*(rua|r\.|avenida|av\.?|pra[çc]a|travessa|alameda|largo|beco|viela|estrada municipal)\b", re.I)

DEFAULT_WATCH_POINTS = [
    {"name": "Régis Bittencourt", "lat": -24.50, "lon": -47.85, "road": "BR-116"},
    {"name": "Rio-Santos", "lat": -23.20, "lon": -44.75, "road": "BR-101"},
    {"name": "Brasília-BH-Rio", "lat": -19.78, "lon": -44.06, "road": "BR-040"},
    {"name": "Fernão Dias", "lat": -21.85, "lon": -45.20, "road": "BR-381"},
    {"name": "Cuiabá-Santarém", "lat": -10.55, "lon": -55.30, "road": "BR-163"},
    {"name": "Freeway RS", "lat": -30.02, "lon": -51.05, "road": "BR-290"},
    {"name": "Curitiba-Paranaguá", "lat": -25.45, "lon": -49.00, "road": "BR-277"},
    {"name": "Vale do Itajaí", "lat": -27.05, "lon": -49.15, "road": "BR-470"},
]


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


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


def bbox_around(lat: float, lon: float, delta: float = 0.07) -> tuple[float, float, float, float]:
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


def is_finished(description: str) -> bool:
    text = description.casefold()
    return any(word in text for word in ENDED_WORDS)


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
    for key in ("roadName", "from", "to"):
        for name in split_names(properties.get(key)):
            if LOCAL_WORD_RE.search(name):
                return True
    return False


def get_road(properties: dict[str, Any]) -> str | None:
    for key in ("roadNumbers", "roadNumber", "roadName", "from", "to"):
        for name in split_names(properties.get(key)):
            if is_road_allowed(name):
                return name
    return None


def fetch_bbox(bbox: tuple[float, float, float, float]) -> list[dict[str, Any]]:
    west, south, east, north = bbox
    fields = "{incidents{type,geometry{type,coordinates},properties{iconCategory,magnitudeOfDelay,events{description,code},from,to,roadNumbers,roadNumber,roadName,length,delay}}}"
    query = urllib.parse.urlencode({
        "key": API_KEY,
        "bbox": f"{west},{south},{east},{north}",
        "fields": fields,
        "language": "pt-PT",
    }, safe="{},")
    url = f"https://api.tomtom.com/traffic/services/5/incidentDetails?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": "rodovias-clima-github-action/1.9"})
    with urllib.request.urlopen(req, timeout=25) as response:
        payload = json.loads(response.read().decode("utf-8"))
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
    road = get_road(props)
    fallback_used = False
    if not road:
        if has_local_street(props):
            return None, "local_street"
        road = str(corridor.get("road") or corridor.get("name") or "Corredor rodoviário")
        fallback_used = True
    lat, lon = coord
    risk = CATEGORY_RISK.get(category, 60)
    delay = props.get("delay") or props.get("magnitudeOfDelay")
    if isinstance(delay, (int, float)) and delay > 600:
        risk = min(100, risk + 10)
    return {
        "active": True,
        "name": f"{label} • {road}",
        "road": road,
        "corridor": corridor.get("name") or road,
        "isMainRoad": True,
        "fallbackCorridor": fallback_used,
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "eventType": label,
        "description": description,
        "risk": risk,
        "source": "TomTom Traffic API",
        "updatedAt": now_iso(),
    }, "ok"


def main() -> None:
    points = monitored_points()
    status: dict[str, Any] = {
        "updatedAt": now_iso(),
        "provider": "TomTom Traffic API",
        "tomtomKeyConfigured": bool(API_KEY),
        "language": "pt-PT",
        "riskRule": "Meio-termo: aceita rodovias/códigos claros e ocorrências próximas a corredores monitorados, descartando ruas e avenidas locais.",
        "monitoredPoints": len(points),
        "bboxRequestsPlanned": len(points),
        "bboxRequestsSucceeded": 0,
        "rawIncidents": 0,
        "eventsWritten": 0,
        "skippedFinishedOrInvalid": 0,
        "skippedLocalStreet": 0,
        "errors": [],
    }

    if not API_KEY:
        write_json(OUTPUT, load_json(OUTPUT, []))
        status["errors"].append("TOMTOM_API_KEY não está configurada nos Secrets do GitHub Actions.")
        write_json(STATUS_OUTPUT, status)
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return

    seen = set()
    output = []
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

    output.sort(key=lambda item: int(item.get("risk", 0)), reverse=True)
    status["eventsWritten"] = len(output)
    write_json(OUTPUT, output)
    write_json(STATUS_OUTPUT, status)
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
