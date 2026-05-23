#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SOURCE_CONFIG = Path("data/manual_events_source.json")
OUTPUT = Path("data/manual_events.json")
STATUS_OUTPUT = Path("data/manual_events_status.json")

HEADER_ALIASES = {
    "ativo": ["ativo", "active", "status", "publicar", "exibir"],
    "tipo": ["tipo", "type", "categoria", "camada"],
    "nome": ["nome", "name", "titulo", "título", "local", "cidade"],
    "evento": ["evento", "event", "eventtype", "tipo_evento", "ocorrencia", "ocorrência"],
    "regiao": ["regiao", "região", "region"],
    "uf": ["uf", "estado", "state"],
    "latitude": ["latitude", "lat"],
    "longitude": ["longitude", "lon", "lng", "long"],
    "risco": ["risco", "risk", "severidade", "severity"],
    "via_ou_area": ["via_ou_area", "via/area", "via/área", "via", "area", "área", "road", "rodovia"],
    "descricao": ["descricao", "descrição", "description", "detalhes", "motivo"],
    "raio_metros": ["raio_metros", "raio", "radius", "radiusmeters", "radius_meters"],
    "expira_em": ["expira_em", "expira", "expiresat", "expires_at", "validade", "fim"],
    "fonte_url": ["fonte_url", "sourceurl", "source_url", "link", "url", "fonte"],
}

TRUE_VALUES = {"1", "true", "sim", "s", "yes", "y", "ativo", "ativa", "publicar", "mostrar", "ok"}
FALSE_VALUES = {"0", "false", "nao", "não", "n", "no", "inativo", "inativa", "ocultar", "desativado", "desativada"}
TYPE_MAP = {
    "clima": "climate",
    "climatico": "climate",
    "climático": "climate",
    "weather": "climate",
    "rodovia": "road",
    "rodoviario": "road",
    "rodoviário": "road",
    "road": "road",
    "estrada": "road",
    "operacional": "operational",
    "operational": "operational",
    "alerta": "operational",
}


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def normalize_key(value: str) -> str:
    s = value.strip().lower()
    table = str.maketrans("áàãâäéèêëíìîïóòõôöúùûüçñ", "aaaaaeeeeiiiiooooouuuucn")
    s = s.translate(table)
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def load_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else fallback
    except Exception:
        return fallback


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sheet_csv_url(source: dict[str, Any]) -> str:
    if source.get("csvUrl"):
        return str(source["csvUrl"])
    sheet_id = str(source.get("sheetId") or "").strip()
    gid = str(source.get("gid") or "0").strip()
    if not sheet_id:
        raise ValueError("Fonte sem sheetId")
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={urllib.parse.quote(gid)}"


def fetch_csv(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "manual-events-importer/1.0"})
    with urllib.request.urlopen(req, timeout=25) as response:
        raw = response.read().decode("utf-8-sig", errors="replace")
    if "<html" in raw[:300].lower() or "<!doctype" in raw[:300].lower():
        raise RuntimeError("A planilha não retornou CSV. Verifique se o compartilhamento permite leitura por link.")
    return raw


def build_header_map(headers: list[str]) -> dict[str, str]:
    normalized = {normalize_key(h): h for h in headers}
    mapping: dict[str, str] = {}
    for canonical, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            key = normalize_key(alias)
            if key in normalized:
                mapping[canonical] = normalized[key]
                break
    return mapping


def val(row: dict[str, str], mapping: dict[str, str], key: str, default: str = "") -> str:
    header = mapping.get(key)
    if not header:
        return default
    return str(row.get(header, default) or "").strip()


def parse_bool(value: str) -> bool:
    s = normalize_key(value)
    if not s:
        return True
    if s in TRUE_VALUES:
        return True
    if s in FALSE_VALUES:
        return False
    return True


def parse_float(value: str, default: float | None = None) -> float | None:
    s = str(value or "").strip().replace("\u2212", "-").replace(",", ".")
    if not s:
        return default
    try:
        return float(s)
    except Exception:
        return default


def parse_risk(value: str) -> int:
    parsed = parse_float(value, 50)
    return int(max(0, min(100, round(parsed if parsed is not None else 50))))


def normalize_type(value: str) -> str:
    key = normalize_key(value)
    return TYPE_MAP.get(key, key if key in {"climate", "road", "operational"} else "operational")


def parse_expiry(value: str) -> str | None:
    s = str(value or "").strip()
    if not s:
        return None
    if re.fullmatch(r"\d+(?:[,.]\d+)?", s):
        hours = float(s.replace(",", "."))
        return datetime.fromtimestamp(time.time() + hours * 3600, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        pass
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            continue
    return None


def normalize_row(row: dict[str, str], mapping: dict[str, str], source_name: str, index: int) -> tuple[dict[str, Any] | None, str]:
    event_type = normalize_type(val(row, mapping, "tipo", "operational"))
    lat = parse_float(val(row, mapping, "latitude"))
    lon = parse_float(val(row, mapping, "longitude"))
    name = val(row, mapping, "nome")
    if not name and not val(row, mapping, "evento") and lat is None and lon is None:
        return None, "empty"
    if lat is None or lon is None:
        return None, "missing_coordinates"
    if not (-34 <= lat <= 6 and -75 <= lon <= -30):
        return None, "coordinates_outside_brazil"

    risk = parse_risk(val(row, mapping, "risco", "50"))
    active = parse_bool(val(row, mapping, "ativo", "sim"))
    label = val(row, mapping, "evento") or ("Evento climático" if event_type == "climate" else "Evento rodoviário" if event_type == "road" else "Alerta operacional")
    road_or_area = val(row, mapping, "via_ou_area")
    description = val(row, mapping, "descricao") or label
    region = val(row, mapping, "regiao")
    state = val(row, mapping, "uf")
    source_url = val(row, mapping, "fonte_url")

    event: dict[str, Any] = {
        "active": active,
        "type": event_type,
        "name": name or label,
        "eventType": label,
        "description": description,
        "lat": round(float(lat), 6),
        "lon": round(float(lon), 6),
        "risk": risk,
        "source": source_name,
        "createdAt": now_iso(),
        "manualSheetRow": index,
    }
    if region:
        event["region"] = region
    if state:
        event["state"] = state
    if road_or_area:
        event["road"] = road_or_area
        event["corridor"] = road_or_area
    if source_url:
        event["sourceUrl"] = source_url

    if event_type == "climate":
        event["reasons"] = [description]
        event["current"] = {}
    elif event_type == "road":
        event["isMainRoad"] = True
        event["reasons"] = [description]
    else:
        event["category"] = label
        event["confidence"] = "planilha manual"
        event["radiusMeters"] = int(parse_float(val(row, mapping, "raio_metros", "1500"), 1500) or 1500)
        event["reasons"] = [description]
        expiry = parse_expiry(val(row, mapping, "expira_em"))
        if expiry:
            event["expiresAt"] = expiry

    return event, "ok"


def main() -> None:
    cfg = load_json(SOURCE_CONFIG, {"sources": []})
    sources = cfg.get("sources") if isinstance(cfg, dict) else []
    status: dict[str, Any] = {
        "updatedAt": now_iso(),
        "provider": "Google Sheets CSV",
        "sourcesConfigured": len(sources or []),
        "sourcesSucceeded": 0,
        "rowsRead": 0,
        "eventsWritten": 0,
        "skipped": {},
        "errors": [],
    }
    all_events: list[dict[str, Any]] = []

    for source in sources or []:
        source_name = str(source.get("name") or "Google Sheets")
        try:
            url = sheet_csv_url(source)
            raw = fetch_csv(url)
            rows = list(csv.DictReader(raw.splitlines()))
            status["rowsRead"] += len(rows)
            status["sourcesSucceeded"] += 1
            mapping = build_header_map(rows[0].keys() if rows else [])
            for idx, row in enumerate(rows, start=2):
                event, reason = normalize_row(row, mapping, source_name, idx)
                if event:
                    all_events.append(event)
                else:
                    status["skipped"][reason] = status["skipped"].get(reason, 0) + 1
        except Exception as exc:
            status["errors"].append({"source": source_name, "message": str(exc)})

    if all_events or not OUTPUT.exists():
        write_json(OUTPUT, all_events)
    elif status["errors"]:
        status["keptPreviousOnFailure"] = True
    else:
        write_json(OUTPUT, [])

    status["eventsWritten"] = len(load_json(OUTPUT, []))
    write_json(STATUS_OUTPUT, status)
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
