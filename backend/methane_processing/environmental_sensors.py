from __future__ import annotations

import math
import re
from typing import Any


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _sensor_index(sensor_id: str | None) -> int:
    if not sensor_id:
        return 1

    match = re.search(r"(\d+)$", str(sensor_id))
    if not match:
        return 1

    return max(1, int(match.group(1)))


def _wave(time_step: int, sensor_id: str | None, amplitude: float = 1.0) -> float:
    """
    Small deterministic variation.

    No random is used here. The same input always produces the same output.
    This keeps generated demo data stable across pipeline runs.
    """
    idx = _sensor_index(sensor_id)
    return math.sin((time_step * 0.37) + (idx * 0.91)) * amplitude


def build_environmental_measurements(
    *,
    methane_value: float,
    methane_risk_score: float,
    anomaly_score: float,
    time_step: int,
    sensor_id: str | None,
) -> dict[str, float]:
    """
    Build deterministic demo environmental measurements around the methane signal.

    Important:
    - CH4/methane is the real source channel already used by the existing pipeline.
    - CO, O2, temperature, humidity and pressure are MVP/demo environmental
      context values derived deterministically from methane risk and anomaly.
    - These values are not claimed as real field measurements.
    - They exist to enrich the closed underground mine environment simulation.
    """
    risk_ratio = clamp(float(methane_risk_score or 0.0), 0.0, 100.0) / 100.0
    anomaly_ratio = clamp(float(anomaly_score or 0.0), 0.0, 1.0)

    sensor_phase = _sensor_index(sensor_id)

    methane_ppm = clamp(
        250.0 + (risk_ratio * 4800.0) + (anomaly_ratio * 500.0) + _wave(time_step, sensor_id, 40.0),
        0.0,
        10000.0,
    )

    co_ppm = clamp(
        4.0 + (risk_ratio * 58.0) + (anomaly_ratio * 18.0) + _wave(time_step + 3, sensor_id, 2.5),
        0.0,
        250.0,
    )

    oxygen_percent = clamp(
        20.9 - (risk_ratio * 3.1) - (anomaly_ratio * 0.45) + _wave(time_step + 5, sensor_id, 0.08),
        15.0,
        21.0,
    )

    temperature_c = clamp(
        23.0 + (risk_ratio * 10.5) + (anomaly_ratio * 3.0) + (sensor_phase * 0.15) + _wave(time_step + 7, sensor_id, 0.6),
        -10.0,
        60.0,
    )

    humidity_percent = clamp(
        55.0 + (risk_ratio * 23.0) + _wave(time_step + 11, sensor_id, 3.5),
        0.0,
        100.0,
    )

    pressure_hpa = clamp(
        1013.0 - (risk_ratio * 7.5) + _wave(time_step + 13, sensor_id, 1.2),
        950.0,
        1050.0,
    )

    return {
        "methane_value": round(float(methane_value or 0.0), 6),
        "methane_ppm": round(methane_ppm, 3),
        "co_ppm": round(co_ppm, 3),
        "oxygen_percent": round(oxygen_percent, 3),
        "temperature_c": round(temperature_c, 3),
        "humidity_percent": round(humidity_percent, 3),
        "pressure_hpa": round(pressure_hpa, 3),
    }


def _linear_risk(value: float, safe: float, critical: float, *, reverse: bool = False) -> float:
    """
    Convert a measurement into a simple 0-100 risk score.

    reverse=False:
        higher value means higher risk.

    reverse=True:
        lower value means higher risk.
    """
    if reverse:
        if value >= safe:
            return 0.0
        if value <= critical:
            return 100.0
        return clamp(((safe - value) / (safe - critical)) * 100.0, 0.0, 100.0)

    if value <= safe:
        return 0.0
    if value >= critical:
        return 100.0
    return clamp(((value - safe) / (critical - safe)) * 100.0, 0.0, 100.0)


def build_component_scores(
    *,
    measurements: dict[str, Any],
    methane_risk_score: float,
) -> dict[str, float]:
    """
    Build explainable component-level environmental risk scores.

    The thresholds are MVP/demo scoring thresholds. They are intentionally simple
    and should be documented as simulation scoring, not field-calibrated safety limits.
    """
    methane_risk = clamp(float(methane_risk_score or 0.0), 0.0, 100.0)

    co_risk = _linear_risk(
        float(measurements.get("co_ppm", 0.0) or 0.0),
        safe=10.0,
        critical=80.0,
    )

    oxygen_risk = _linear_risk(
        float(measurements.get("oxygen_percent", 20.9) or 20.9),
        safe=20.5,
        critical=18.0,
        reverse=True,
    )

    temperature_risk = _linear_risk(
        float(measurements.get("temperature_c", 23.0) or 23.0),
        safe=28.0,
        critical=42.0,
    )

    humidity_risk = _linear_risk(
        float(measurements.get("humidity_percent", 55.0) or 55.0),
        safe=75.0,
        critical=95.0,
    )

    pressure_deviation = abs(float(measurements.get("pressure_hpa", 1013.0) or 1013.0) - 1013.0)
    pressure_risk = _linear_risk(
        pressure_deviation,
        safe=4.0,
        critical=20.0,
    )

    return {
        "methane_risk": round(methane_risk, 3),
        "co_risk": round(co_risk, 3),
        "oxygen_risk": round(oxygen_risk, 3),
        "temperature_risk": round(temperature_risk, 3),
        "humidity_risk": round(humidity_risk, 3),
        "pressure_risk": round(pressure_risk, 3),
    }


def combine_environmental_risk(component_scores: dict[str, Any]) -> float:
    """
    Combine component scores into one environmental risk score.

    Current MVP weights:
    - Methane is the dominant explosive gas risk component.
    - CO and O2 represent toxic/respirable atmosphere risk.
    - Temperature gives thermal/fire context.
    - Humidity and pressure are lower-weight environmental context signals.
    """
    weights = {
        "methane_risk": 0.40,
        "co_risk": 0.20,
        "oxygen_risk": 0.20,
        "temperature_risk": 0.10,
        "humidity_risk": 0.05,
        "pressure_risk": 0.05,
    }

    total = 0.0
    for key, weight in weights.items():
        total += float(component_scores.get(key, 0.0) or 0.0) * weight

    return round(clamp(total, 0.0, 100.0), 3)


def build_environmental_risk_reasons(component_scores: dict[str, Any], confidence: float | None = None) -> list[str]:
    reasons: list[str] = []

    if float(component_scores.get("methane_risk", 0.0) or 0.0) >= 60:
        reasons.append("methane_level_elevated")
    if float(component_scores.get("co_risk", 0.0) or 0.0) >= 60:
        reasons.append("co_level_elevated")
    if float(component_scores.get("oxygen_risk", 0.0) or 0.0) >= 60:
        reasons.append("oxygen_level_decreased")
    if float(component_scores.get("temperature_risk", 0.0) or 0.0) >= 60:
        reasons.append("temperature_level_elevated")
    if float(component_scores.get("humidity_risk", 0.0) or 0.0) >= 60:
        reasons.append("humidity_level_elevated")
    if float(component_scores.get("pressure_risk", 0.0) or 0.0) >= 60:
        reasons.append("pressure_deviation_detected")

    if confidence is not None and confidence < 0.6:
        reasons.append("low_sensor_confidence_measurement_should_be_verified")

    if not reasons:
        reasons.append("environmental_conditions_within_demo_baseline")

    return reasons