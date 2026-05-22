#!/usr/bin/env python3
"""Atualiza data/road_events.json com incidentes rodoviários da TomTom Traffic API.

Também grava data/road_events_status.json para diagnosticar se a chave foi aceita,
quantas áreas foram consultadas, quantos incidentes chegaram e quais erros ocorreram.
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


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def brazil_bboxes(step: float = 6.0) -> list[tuple[float, float, float, float]]:
    # Cobertura aproximada do Brasil em blocos menores. Rodando 1x por hora,
    # fica bem abaixo de 2.500 consultas/dia do plano gratuito da TomTom.
    west, east = -74.2, -34.5
    south, north = -34.0, 5.4
    boxes: list[tuple[float, float, float, float]] = []
    lon = west
    while lon < east:
        lat = south
        while lat < north:
            boxes.append((round(lon, 3), round(lat, 3), round(min(lon + step, east), 3), round(min(lat + step, north), 3)))
            lat += step
        lon += step
    return boxes


def load_existing() -> list[dict[str, Any]]:
    try:
        if OUTPUT.exists():
            data = json.loads(OUTPUT.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
    except Exception:
        return []
    return []


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
    req = urllib.request.Request(url, headers={"User-Agent": "rodovias-clima-github-action/1.1"})
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
    status: dict[str, Any] = {
        "updatedAt": now_iso(),
        "provider": "TomTom Traffic API",
        "tomtomKeyConfigured": bool(API_KEY),
        "bboxRequestsPlanned": 0,
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
    boxes = brazil_bboxes()
    status["bboxRequestsPlanned"] = len(boxes)

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
