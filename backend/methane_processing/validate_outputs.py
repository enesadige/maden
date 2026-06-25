from __future__ import annotations

import math
import re
from typing import Any

from backend.methane_processing.segment_mapper import valid_segment_ids


VALID_STATUS_VALUES = {"normal", "low", "medium", "high", "critical"}


def is_finite_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def validate_gas_timeline(records: list[dict[str, Any]]) -> list[str]:
    """
    gas_sensors.json / gas_sensors_timeline.json kayıtlarını doğrular.
    """
    errors: list[str] = []
    segments = valid_segment_ids()

    if not records:
        return ["gas timeline boş"]

    required_fields = {
        "time_step",
        "sensor_id",
        "segment_id",
        "methane_value",
        "methane_risk_score",
        "anomaly_score",
        "status",
    }

    for index, record in enumerate(records):
        missing = sorted(required_fields - set(record.keys()))
        if missing:
            errors.append(f"gas[{index}] eksik alanlar: {missing}")
            continue

        if not isinstance(record["time_step"], int) or record["time_step"] < 0:
            errors.append(f"gas[{index}] time_step geçersiz")

        if not re.fullmatch(r"GAS_SENSOR_\d{2}", str(record["sensor_id"])):
            errors.append(f"gas[{index}] sensor_id formatı geçersiz: {record['sensor_id']}")

        if record["segment_id"] not in segments:
            errors.append(f"gas[{index}] bilinmeyen segment_id: {record['segment_id']}")

        if not is_finite_number(record["methane_value"]) or float(record["methane_value"]) < 0:
            errors.append(f"gas[{index}] methane_value geçersiz")

        risk = record["methane_risk_score"]
        if not is_finite_number(risk) or not 0 <= float(risk) <= 100:
            errors.append(f"gas[{index}] methane_risk_score aralık dışı")

        anomaly = record["anomaly_score"]
        if not is_finite_number(anomaly) or not 0 <= float(anomaly) <= 1:
            errors.append(f"gas[{index}] anomaly_score aralık dışı")

        if record["status"] not in VALID_STATUS_VALUES:
            errors.append(f"gas[{index}] status geçersiz: {record['status']}")

    return errors


def validate_environmental_risk(records: list[dict[str, Any]]) -> list[str]:
    """
    environmental_risk.json kayıtlarını doğrular.
    """
    errors: list[str] = []
    segments = valid_segment_ids()

    if not records:
        return ["environmental_risk boş"]

    required_fields = {
        "time_step",
        "segment_id",
        "sensor_id",
        "methane_risk_score",
        "anomaly_score",
        "environmental_risk",
        "risk_level",
    }

    for index, record in enumerate(records):
        missing = sorted(required_fields - set(record.keys()))
        if missing:
            errors.append(f"risk[{index}] eksik alanlar: {missing}")
            continue

        if record["segment_id"] not in segments:
            errors.append(f"risk[{index}] bilinmeyen segment_id: {record['segment_id']}")

        risk = record["environmental_risk"]
        if not is_finite_number(risk) or not 0 <= float(risk) <= 100:
            errors.append(f"risk[{index}] environmental_risk aralık dışı")

        if record["risk_level"] not in VALID_STATUS_VALUES:
            errors.append(f"risk[{index}] risk_level geçersiz: {record['risk_level']}")

    return errors


def validate_all_outputs(
    gas_timeline: list[dict[str, Any]],
    environmental_risk: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Tüm methane handoff çıktısını doğrular.
    """
    errors = []
    errors.extend(validate_gas_timeline(gas_timeline))
    errors.extend(validate_environmental_risk(environmental_risk))

    return {
        "ok": len(errors) == 0,
        "error_count": len(errors),
        "errors": errors,
        "gas_record_count": len(gas_timeline),
        "environmental_risk_record_count": len(environmental_risk),
    }
