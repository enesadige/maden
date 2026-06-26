from __future__ import annotations

from typing import Any

from apps.common.ids import normalize_record_ids
from apps.common.json_store import filter_time_step, load_json


def _risk_level_from_sensor(sensor: dict[str, Any]) -> str:
    level = sensor.get("risk_level") or sensor.get("status") or "normal"
    if level == "normal":
        return "low"
    if level == "alarm":
        return "critical"
    return str(level).lower()


def get_gas_sensors(time_step: int | None = 0) -> list[dict[str, Any]]:
    records = load_json("sensors/gas_sensors.json", default=[])
    selected = filter_time_step(records, time_step)
    sensors = []
    for item in selected:
        sensor = normalize_record_ids(item)
        sensor["risk_score"] = sensor.get("methane_risk_score", sensor.get("risk_score", 0.0))
        sensor["risk_level"] = _risk_level_from_sensor(sensor)
        sensor.setdefault("gas_type", "methane")
        sensors.append(sensor)
    return sensors


def get_environmental_risks(time_step: int | None = 0) -> list[dict[str, Any]]:
    records = load_json("risk/environmental_risk.json", default=[])
    selected = filter_time_step(records, time_step)
    risks = []
    for item in selected:
        risk = normalize_record_ids(item)
        risk["risk_score"] = risk.get("environmental_risk", risk.get("methane_risk_score", 0.0))
        risk["gas_risk_score"] = risk["risk_score"]
        risk["methane_ppm"] = risk.get("methane_value", 0.0)
        risks.append(risk)
    return risks
