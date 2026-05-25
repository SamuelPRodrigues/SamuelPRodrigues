from __future__ import annotations

from typing import Any

MAX_ROAD_BLOCKING_RISK = 69
ROAD_BLOCKING_SEVERITY = 'Alto'


def safe_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except Exception:
        return 0


def severity_from_risk(risk: Any) -> str:
    value = safe_int(risk)
    if value >= 80:
        return 'Critico'
    if value >= 60:
        return 'Alto'
    if value >= 35:
        return 'Moderado'
    if value >= 1:
        return 'Baixo'
    return 'Sem risco'


def is_road_event(row: dict[str, Any]) -> bool:
    return str(row.get('source_type') or row.get('type') or '').strip().lower() == 'road'


def apply_road_blocking_cap(row: dict[str, Any]) -> bool:
    if not isinstance(row, dict) or not is_road_event(row):
        return False
    changed = False
    current_risk = safe_int(row.get('risk'))
    if current_risk > MAX_ROAD_BLOCKING_RISK:
        row['risk'] = MAX_ROAD_BLOCKING_RISK
        changed = True
    current_severity = str(row.get('severity') or '').strip().casefold()
    if changed or current_severity in {'critico', 'critical'}:
        row['severity'] = ROAD_BLOCKING_SEVERITY if safe_int(row.get('risk')) >= 60 else severity_from_risk(row.get('risk'))
        changed = True
    row['severityRule'] = f'Eventos rodoviarios de bloqueio/interdicao tem teto {MAX_ROAD_BLOCKING_RISK} ({ROAD_BLOCKING_SEVERITY}).'
    return changed
