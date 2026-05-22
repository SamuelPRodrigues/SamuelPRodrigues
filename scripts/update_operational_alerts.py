#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

OUTPUT = Path("data/operational_alerts.json")
STATUS = Path("data/operational_alerts_status.json")

# Pontos aproximados para geocodificação simples por cidade. Não marca local exato.
CITIES = {
    "são paulo": (-23.550, -46.633, "SP"), "rio de janeiro": (-22.906, -43.173, "RJ"),
    "belo horizonte": (-19.916, -43.934, "MG"), "brasília": (-15.793, -47.882, "DF"),
    "curitiba": (-25.428, -49.273, "PR"), "porto alegre": (-30.034, -51.217, "RS"),
    "salvador": (-12.977, -38.501, "BA"), "recife": (-8.047, -34.877, "PE"),
    "fortaleza": (-3.731, -38.526, "CE"), "manaus": (-3.119, -60.021, "AM"),
    "belém": (-1.455, -48.490, "PA"), "goiânia": (-16.686, -49.264, "GO"),
    "campinas": (-22.907, -47.063, "SP"), "santos": (-23.960, -46.333, "SP"),
    "guarulhos": (-23.454, -46.533, "SP"), "osasco": (-23.532, -46.791, "SP"),
    "niterói": (-22.883, -43.103, "RJ"), "duque de caxias": (-22.785, -43.311, "RJ"),
    "são gonçalo": (-22.826, -43.063, "RJ"), "contagem": (-19.932, -44.053, "MG"),
    "betim": (-19.967, -44.198, "MG"), "joinville": (-26.304, -48.849, "SC"),
    "florianópolis": (-27.594, -48.548, "SC"), "cuiabá": (-15.601, -56.098, "MT"),
    "campo grande": (-20.469, -54.620, "MS"), "vitória": (-20.315, -40.312, "ES"),
    "maceió": (-9.665, -35.735, "AL"), "natal": (-5.795, -35.209, "RN"),
    "joão pessoa": (-7.119, -34.845, "PB"), "teresina": (-5.091, -42.803, "PI"),
    "são luís": (-2.530, -44.306, "MA"), "aracaju": (-10.947, -37.073, "SE"),
    "palmas": (-10.184, -48.334, "TO"), "rio branco": (-9.975, -67.824, "AC"),
    "porto velho": (-8.761, -63.901, "RO"), "boa vista": (2.824, -60.675, "RR"), "macapá": (0.035, -51.070, "AP"),
}

RULES = [
    ("Segurança operacional", "Ocorrência de segurança", 78, 2, ["tiroteio", "confronto", "disparos", "arrastão"]),
    ("Segurança operacional", "Ação policial com impacto", 65, 2, ["ação policial", "operação policial", "polícia fecha", "polícia interditou"]),
    ("Bloqueio urbano", "Manifestação ou bloqueio", 58, 6, ["manifestação", "protesto", "bloqueio", "interdição", "interditada", "interditado"]),
    ("Emergência urbana", "Incêndio ou emergência", 62, 4, ["incêndio", "explosão", "fumaça", "desabamento"]),
    ("Risco logístico", "Risco para carga ou entrega", 72, 12, ["roubo de carga", "carga roubada", "saque de carga"]),
    ("Infraestrutura", "Falha de infraestrutura", 45, 4, ["queda de árvore", "semáforo apagado", "falta de energia", "alagamento"]),
]
BLOCKED_DETAIL_TERMS = ["posição da polícia", "onde a polícia está", "rota da polícia", "viatura em", "blitz em tempo real"]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fetch_gdelt() -> list[dict[str, Any]]:
    query = '("tiroteio" OR "confronto" OR "ação policial" OR "operação policial" OR "bloqueio" OR "manifestação" OR "protesto" OR "incêndio" OR "roubo de carga" OR "interdição" OR "alagamento") sourcecountry:BR'
    params = {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "timespan": "6h",
        "maxrecords": "75",
        "sort": "HybridRel",
    }
    url = "https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "operational-alerts-brazil/1.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    return payload.get("articles", []) if isinstance(payload, dict) else []


def classify(text: str) -> tuple[str, str, int, int] | None:
    t = text.casefold()
    if any(term in t for term in BLOCKED_DETAIL_TERMS):
        return None
    for category, event_type, risk, expires_hours, terms in RULES:
        if any(term in t for term in terms):
            return category, event_type, risk, expires_hours
    return None


def geocode(text: str) -> tuple[float, float, str, str] | None:
    t = text.casefold()
    best = None
    for city, (lat, lon, uf) in CITIES.items():
        if city in t:
            if not best or len(city) > len(best[0]):
                best = (city, lat, lon, uf)
    if not best:
        return None
    city, lat, lon, uf = best
    return lat, lon, city.title(), uf


def clean_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title).strip()
    return title[:140]


def normalize(article: dict[str, Any]) -> dict[str, Any] | None:
    title = str(article.get("title") or "")
    desc = str(article.get("seendate") or "")
    url = str(article.get("url") or "")
    source = str(article.get("sourceCommonName") or article.get("domain") or "GDELT")
    text = f"{title} {source}"
    cls = classify(text)
    geo = geocode(text)
    if not cls or not geo or not url:
        return None
    category, event_type, risk, expires_hours = cls
    lat, lon, city, uf = geo
    expires = datetime.now(timezone.utc) + timedelta(hours=expires_hours)
    return {
        "active": True,
        "type": "other",
        "category": category,
        "eventType": event_type,
        "name": f"{event_type} • {city}/{uf}",
        "description": "Alerta operacional detectado em fonte pública. Região aproximada; evite a área se estiver em rota.",
        "lat": lat,
        "lon": lon,
        "radiusMeters": 2000 if category == "Segurança operacional" else 1200,
        "risk": risk,
        "confidence": "fonte pública automatizada",
        "source": source,
        "sourceUrl": url,
        "headline": clean_title(title),
        "createdAt": now_iso(),
        "expiresAt": expires.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }


def main() -> None:
    status = {"updatedAt": now_iso(), "provider": "GDELT DOC 2.0", "rawArticles": 0, "eventsWritten": 0, "errors": []}
    try:
        articles = fetch_gdelt()
        status["rawArticles"] = len(articles)
        seen: set[str] = set()
        events = []
        for article in articles:
            event = normalize(article)
            if not event:
                continue
            key = event["sourceUrl"]
            if key in seen:
                continue
            seen.add(key)
            events.append(event)
        events.sort(key=lambda e: int(e.get("risk", 0)), reverse=True)
        write_json(OUTPUT, events[:40])
        status["eventsWritten"] = len(events[:40])
    except Exception as exc:
        status["errors"].append(str(exc))
        if not OUTPUT.exists():
            write_json(OUTPUT, [])
    write_json(STATUS, status)
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
