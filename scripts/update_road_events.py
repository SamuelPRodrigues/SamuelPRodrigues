#!/usr/bin/env python3
"""Atualiza data/road_events.json com incidentes rodoviários da TomTom Traffic API.

Requer a variável de ambiente TOMTOM_API_KEY. Quando a chave não existe,
o script mantém o arquivo atual e termina sem erro, para não quebrar o Pages.
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

OUTPUT = Path("data/road_events.json")
API_KEY = os.environ.get("TOMTOM_API_KEY", "").strip()

# BBoxes em formato: oeste, sul, leste, norte. Divididas para reduzir carga e
# cobrir o território brasileiro sem depender de uma única consulta enorme.
BRAZIL_BBOXES = [
    (-74.2, -10.5, -58.0, 5.4),   # Amazônia oeste
    (-58.0, -10.5, -44.0, 5.4),   # Amazônia leste / Norte
    (-44.0, -18.5, -34.5, 1.5),   # Nordeste / litoral norte
    (-60.5, -25.5, -44.0, -10.0), # Centro-Oeste
    (-49.5, -25.5, -39.0, -14.0), # Sudeste / MG / ES
    (-58.0, -34.0, -44.0, -22.0), # Sul / SP oeste
]

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


def load_existing() -> list[dict[str, Any]]:
    try:
        if OUTPUT.exists():
            data = json.loads(OUTPUT.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
    except Exception:
        return []
    return []


def write_events(events: list[dict[str, Any]]) -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(events, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def first_coordinate(geometry: dict[str, Any]) -> tuple[float, float] | None:
    coords = geometry.get("coordinates")
    if not coords:
        return None
    # Pode vir como [lon, lat] ou [[lon, lat], ...]
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
    if descriptions:
        return "; ".join(descriptions[:3])
    return f"Evento detectado pela TomTom Traffic API: {label}."


def get_road(properties: dict[str, Any]) -> str:
    for key in ("roadNumbers", "roadNumber", "roadName", "from", "to"):
        value = properties.get(key)
        if isinstance(value, list) and value:
            return str(value[0])
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "Rodovia"


def fetch_bbox(bbox: tuple[float, float, float, float]) -> list[dict[str, Any]]:
    west, south, east, north = bbox
    fields = "{incidents{type,geometry{type,coordinates},properties{iconCategory,magnitudeOfDelay,events{description,code},from,to,roadNumbers,length,delay}}}"
    query = urllib.parse.urlencode({
        "key": API_KEY,
        "bbox": f"{west},{south},{east},{north}",
        "fields": fields,
        "language": "pt-BR",
    }, safe="{},")
    url = f"https://api.tomtom.com/traffic/services/5/incidentDetails?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": "rodovias-clima-github-action/1.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    incidents = payload.get("incidents", [])
    return incidents if isinstance(incidents, list) else []


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
    description = event_description(props, label)
    return {
        "active": True,
        "name": f"{label} • {road}",
        "road": road,
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "eventType": label,
        "description": description,
        "risk": risk,
        "source": "TomTom Traffic API",
        "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def main() -> None:
    if not API_KEY:
        print("TOMTOM_API_KEY não configurada; mantendo road_events.json atual.")
        write_events(load_existing())
        return

    seen: set[tuple[str, float, float, str]] = set()
    output: list[dict[str, Any]] = []
    errors: list[str] = []

    for bbox in BRAZIL_BBOXES:
        try:
            for incident in fetch_bbox(bbox):
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
        except Exception as exc:
            errors.append(f"bbox {bbox}: {exc}")

    output.sort(key=lambda item: int(item.get("risk", 0)), reverse=True)
    write_events(output)
    print(f"Eventos rodoviários atualizados: {len(output)}")
    if errors:
        print("Avisos:")
        for error in errors:
            print("-", error)


if __name__ == "__main__":
    main()
