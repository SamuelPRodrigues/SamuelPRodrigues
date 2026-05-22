#!/usr/bin/env python3
"""Atualiza data/road_events.json com incidentes rodoviários da TomTom Traffic API.

A API da TomTom limita a área do bbox. Por isso, este script consulta áreas
pequenas ao redor de corredores/pontos rodoviários monitorados, mantendo o uso
compatível com o plano gratuito.
"""
from __future__ import annotations

import json
import os
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
    1: "Acidente",
    2: "Neblina",
    3: "Condição perigosa",
    4: "Chuva",
    5: "Gelo/neve",
    6: "Congestionamento",
    7: "Faixa bloqueada",
    8: "Interdição",
    9: "Obra",
    10: "Vento forte",
    11: "Alagamento",
    14: "Veículo parado",
}

CATEGORY_RISK = {
    1: 82,
    2: 65,
    3: 72,
    4: 55,
    5: 80,
    6: 62,
    7: 70,
    8: 92,
    9: 58,
    10: 65,
    11: 86,
    14: 52,
}

DEFAULT_WATCH_POINTS = [
    {"name": "Régis Bittencourt", "lat": -24.50, "lon": -47.85, "road": "BR-116"},
    {"name": "Rio-Santos", "lat": -23.20, "lon": -44.75, "road": "BR-101"},
    {"name": "Brasília-BH-Rio", "lat": -19.78, "lon": -44.06, "road": "BR-040"},
    {"name": "Fernão Dias", "lat": -21.85, "lon": -45.20, "road": "BR-381"},
    {"name": "Cuiabá-Santarém", "lat": -10.55, "lon": -55.30, "road": "BR-163"},
    {"name": "Freeway RS", "lat": -30.02, "lon": -51.05, "road": "BR-290"},
    {"name": "Curitiba-Paranaguá", "lat": -25.45, "lon": -49.00, "road": "BR-277"},
    {"name": "Vale do Itajaí", "lat": -27.05, "lon": -49.15, "road": "BR-470"},
    {"name": "SP Capital", "lat": -23.55, "lon": -46.63, "road": "SP"},
    {"name": "RJ Capital", "lat": -22.90, "lon": -43.20, "road": "RJ"},
]


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def load_json(path: Path, fallback: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback
    return fallback


def load_existing() -> list[dict[str, Any]]:
    data = load_json(OUTPUT, [])
    return data if isinstance(data, list) else []


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
    if not points:
        points = DEFAULT_WATCH_POINTS

    unique: dict[tuple[float, float], dict[str, Any]] = {}
    for item in points:
        try:
            lat = round(float(item["lat"]), 4)
            lon = round(float(item["lon"]), 4)
        except Exception:
            continue
        unique[(lat, lon)] = {**item, "lat": lat, "lon": lon}
    return list(unique.values())


def bbox_around(lat: float, lon: float, delta: float = 0.18) -> tuple[float, float, float, float]:
    # Aproximadamente 40 km x 40 km no equador: bem abaixo do limite de 10.000 km².
    return (round(lon - delta, 4), round(lat - delta, 4), round(lon + delta, 4), round(lat + delta, 4))


def bboxes_from_points(points: list[dict[str, Any]]) -> list[tuple[float, float, float, float]]:
    return [bbox_around(float(point["lat"]), float(point["lon"])) for point in points]


def first_coordinate(geometry: dict[str, Any]) -> tuple[float, float] | None:
    coords = geometry.get("coordinates")
    if not coords:
        return None
    if isinstance(coords, list) and len(coords) >= 2 and all(isinstance(x, (int, float)) for x in coords[:2]):
        lon, lat = float(coords[0]), float(coords[1])
        return lat, lon
    if isinstance(coords, list):
        for item in coords:
            if isinstance(item, list) and len(item) >= 2:
                lon, lat = float(item[0]), float(item[1])
                return lat, lon
    return None


def event_description(properties: dict[str, Any], label: str) -> str:
    events = properties.get("events") or []
    descriptions: list[str] = []
    if isinstance(events, list):
        for event in events:
            if isinstance(event, dict):
                text = event.get("description") or event.get("phrase") or event.get("eventDescription")
                if text and text not in descriptions:
                    descriptions.append(str(text))
    return "; ".join(descriptions[:3]) if descriptions else f"Evento detectado pela TomTom Traffic API: {label}."


def get_road(properties: dict[str, Any]) -> str:
    for key in ("roadNumbers", "roadNumber", "roadName", "from", "to"):
        value = properties.get(key)
        if isinstance(value, list) and value:
            return str(value[0])
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "Rodovia"


def fetch_bbox(bbox: tuple[float, float, float, float]) -> tuple[list[dict[str, Any]], int]:
    west, south, east, north = bbox
    fields = "{incidents{type,geometry{type,coordinates},properties{iconCategory,magnitudeOfDelay,events{description,code},from,to,roadNumbers,length,delay}}}"
    query = urllib.parse.urlencode({
        "key": API_KEY,
        "bbox": f"{west},{south},{east},{north}",
        "fields": fields,
        "language": "pt-BR",
    }, safe="{},")
    url = f"https://api.tomtom.com/traffic/services/5/incidentDetails?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": "rodovias-clima-github-action/1.2"})
    with urllib.request.urlopen(req, timeout=25) as response:
        payload = json.loads(response.read().decode("utf-8"))
        incidents = payload.get("incidents", [])
        return incidents if isinstance(incidents, list) else [], int(response.status)


def normalize_incident(incident: dict[str, Any]) -> dict[str, Any] | None:
    geometry = incident.get("geometry") or {}
    props = incident.get("properties") or {}
    if not isinstance(geometry, dict) or not isinstance(props, dict):
        return None
    coord = first_coordinate(geometry)
    if not coord:
        return None
    lat, lon = coord
    category = int(props.get("iconCategory") or 0)
    label = CATEGORY_LABELS.get(category, "Ocorrência rodoviária")
    risk = CATEGORY_RISK.get(category, 60)
    delay = props.get("delay") or props.get("magnitudeOfDelay")
    if isinstance(delay, (int, float)) and delay > 600:
        risk = min(100, risk + 10)
    road = get_road(props)
    return {
        "active": True,
        "name": f"{label} • {road}",
        "road": road,
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "eventType": label,
        "description": event_description(props, label),
        "risk": risk,
        "source": "TomTom Traffic API",
        "updatedAt": now_iso(),
    }


def main() -> None:
    points = monitored_points()
    boxes = bboxes_from_points(points)
    status: dict[str, Any] = {
        "updatedAt": now_iso(),
        "provider": "TomTom Traffic API",
        "tomtomKeyConfigured": bool(API_KEY),
        "monitoredPoints": len(points),
        "bboxRequestsPlanned": len(boxes),
        "bboxRequestsSucceeded": 0,
        "rawIncidents": 0,
        "eventsWritten": 0,
        "errors": [],
    }

    if not API_KEY:
        write_json(OUTPUT, load_existing())
        status["errors"].append("TOMTOM_API_KEY não está configurada nos Secrets do GitHub Actions.")
        write_json(STATUS_OUTPUT, status)
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return

    seen: set[tuple[str, float, float, str]] = set()
    output: list[dict[str, Any]] = []

    for bbox in boxes:
        try:
            incidents, http_status = fetch_bbox(bbox)
            status["bboxRequestsSucceeded"] += 1
            status["rawIncidents"] += len(incidents)
            for incident in incidents:
                normalized = normalize_incident(incident)
                if not normalized:
                    continue
                key = (
                    normalized["eventType"],
                    round(float(normalized["lat"]), 3),
                    round(float(normalized["lon"]), 3),
                    normalized["road"],
                )
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
