from __future__ import annotations

from typing import Any


MEASUREMENT_RANGES: dict[str, tuple[float, float]] = {
    "methane_ppm": (0.0, 10000.0),
    "co_ppm": (0.0, 250.0),
    "oxygen_percent": (15.0, 21.0),
    "temperature_c": (-10.0, 60.0),
    "humidity_percent": (0.0, 100.0),
    "pressure_hpa": (950.0, 1050.0),
}

REQUIRED_MEASUREMENTS = (
    "methane_ppm",
    "co_ppm",
    "oxygen_percent",
    "temperature_c",
    "humidity_percent",
    "pressure_hpa",
)


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _as_float(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _status_from_score(score: float) -> str:
    if score >= 0.85:
        return "reliable"
    if score >= 0.65:
        return "partially_reliable"
    if score >= 0.40:
        return "uncertain"
    return "unreliable"


def _range_penalty(measurements: dict[str, Any]) -> tuple[float, list[str]]:
    """
    Checks whether generated environmental measurements stay in expected demo ranges.

    This does not validate against official mine safety thresholds. It only checks
    whether the sensor stream is internally plausible for the MVP simulation.
    """
    penalty = 0.0
    reasons: list[str] = []

    for key in REQUIRED_MEASUREMENTS:
        value = _as_float(measurements.get(key))
        if value is None:
            penalty += 0.18
            reasons.append(f"missing_{key}")
            continue

        low, high = MEASUREMENT_RANGES[key]
        if value < low or value > high:
            penalty += 0.16
            reasons.append(f"{key}_outside_demo_range")

    return penalty, reasons


def _stuck_signal_penalty(
    recent_measurements: list[dict[str, Any]] | None,
    *,
    min_window: int = 8,
) -> tuple[float, list[str]]:
    """
    Detects a simple stuck-sensor pattern from a recent measurement window.

    This is optional. If no recent window is passed, no penalty is applied.
    The methane pipeline can later pass rolling windows here if needed.
    """
    if not recent_measurements or len(recent_measurements) < min_window:
        return 0.0, []

    window = recent_measurements[-min_window:]
    checked_keys = (
        "methane_ppm",
        "co_ppm",
        "oxygen_percent",
        "temperature_c",
    )

    flat_keys = 0
    for key in checked_keys:
        values = [_as_float(item.get(key)) for item in window]
        values = [item for item in values if item is not None]
        if len(values) < min_window:
            continue

        spread = max(values) - min(values)
        if spread <= 0.0001:
            flat_keys += 1

    if flat_keys >= 3:
        return 0.20, ["possible_stuck_sensor_pattern"]

    return 0.0, []


def _anomaly_uncertainty_penalty(anomaly_score: float) -> tuple[float, list[str]]:
    """
    High anomaly is not treated as a sensor failure.

    Mine safety logic should not suppress a dangerous-looking measurement just
    because it is anomalous. Instead, very high anomaly slightly lowers confidence
    and adds a verification reason.
    """
    anomaly_score = clamp(float(anomaly_score or 0.0), 0.0, 1.0)

    if anomaly_score >= 0.95:
        return 0.10, ["very_high_anomaly_measurement_should_be_verified"]
    if anomaly_score >= 0.80:
        return 0.06, ["high_anomaly_measurement_should_be_monitored"]
    return 0.0, []


def build_sensor_reliability(
    *,
    measurements: dict[str, Any],
    anomaly_score: float,
    recent_measurements: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Build reliability/confidence metadata for one environmental sensor record.

    Definitions:
    - sensor_reliability_score:
      Data quality / plausibility score of the sensor stream in the 0.0-1.0 range.

    - confidence:
      Confidence of using this measurement in the environmental risk decision.
      It is close to reliability, but very high anomaly can slightly reduce it.

    Important design decision:
    - Reliability/confidence does not directly reduce environmental_risk here.
    - A dangerous measurement should remain visible.
    - Low confidence is exposed as metadata so backend/frontend can show
      "measurement should be verified" instead of hiding the risk.
    """
    range_penalty, range_reasons = _range_penalty(measurements)
    stuck_penalty, stuck_reasons = _stuck_signal_penalty(recent_measurements)
    anomaly_penalty, anomaly_reasons = _anomaly_uncertainty_penalty(anomaly_score)

    reliability_penalty = range_penalty + stuck_penalty
    reliability_score = round(clamp(1.0 - reliability_penalty, 0.0, 1.0), 3)

    confidence_penalty = reliability_penalty + anomaly_penalty
    confidence = round(clamp(1.0 - confidence_penalty, 0.0, 1.0), 3)

    reasons = range_reasons + stuck_reasons + anomaly_reasons
    if not reasons:
        reasons = ["complete_plausible_demo_sensor_record"]

    return {
        "sensor_reliability_score": reliability_score,
        "confidence": confidence,
        "reliability_status": _status_from_score(reliability_score),
        "reliability_reason": "; ".join(reasons),
        "reliability_reasons": reasons,
    }