from __future__ import annotations

from typing import Any

from apps.common.ids import normalize_record_ids
from apps.common.json_store import available_time_steps, filter_time_step, load_json


def _risk_level_from_sensor(sensor: dict[str, Any]) -> str:
    level = sensor.get("risk_level") or sensor.get("status") or "normal"
    if level == "normal":
        return "low"
    if level == "alarm":
        return "critical"
    return str(level).lower()


def get_gas_sensors(time_step: int | None = 0, fallback: str = "first") -> list[dict[str, Any]]:
    records = load_json("sensors/gas_sensors.json", default=[])
    selected = filter_time_step(records, time_step, fallback=fallback)
    sensors = []
    for item in selected:
        sensor = normalize_record_ids(item)
        sensor["risk_score"] = sensor.get(
            "environmental_risk",
            sensor.get("methane_risk_score", sensor.get("risk_score", 0.0)),
        )
        sensor["risk_level"] = _risk_level_from_sensor(sensor)
        sensor.setdefault("gas_type", "methane")
        sensors.append(sensor)
    return sensors


def get_environmental_risks(time_step: int | None = 0, fallback: str = "first") -> list[dict[str, Any]]:
    records = load_json("risk/environmental_risk.json", default=[])
    selected = filter_time_step(records, time_step, fallback=fallback)
    risks = []
    for item in selected:
        risk = normalize_record_ids(item)
        measurements = risk.get("measurements") if isinstance(risk.get("measurements"), dict) else {}
        risk["risk_score"] = risk.get("environmental_risk", risk.get("methane_risk_score", 0.0))
        risk["gas_risk_score"] = risk["risk_score"]
        risk["methane_ppm"] = measurements.get("methane_ppm", risk.get("methane_value", 0.0))
        for key in ("co_ppm", "oxygen_percent", "temperature_c", "humidity_percent", "pressure_hpa"):
            if key in measurements:
                risk[key] = measurements[key]
        risks.append(risk)
    return risks


def get_gas_time_steps() -> list[int]:
    return available_time_steps("sensors/gas_sensors.json")
