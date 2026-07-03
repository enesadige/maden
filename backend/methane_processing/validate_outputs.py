from __future__ import annotations

import math
import re
from typing import Any

from backend.methane_processing.segment_mapper import valid_segment_ids


VALID_STATUS_VALUES = {"normal", "low", "medium", "high", "critical"}

REQUIRED_MEASUREMENT_FIELDS = {
    "methane_ppm",
    "co_ppm",
    "oxygen_percent",
    "temperature_c",
    "humidity_percent",
    "pressure_hpa",
}

REQUIRED_COMPONENT_SCORE_FIELDS = {
    "methane_risk",
    "co_risk",
    "oxygen_risk",
    "temperature_risk",
    "humidity_risk",
    "pressure_risk",
}

VALID_RELIABILITY_STATUS_VALUES = {
    "reliable",
    "partially_reliable",
    "uncertain",
    "unreliable",
}


def is_finite_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def _validate_0_100_score(
    *,
    value: Any,
    field_name: str,
    record_name: str,
    index: int,
    errors: list[str],
) -> None:
    if not is_finite_number(value) or not 0 <= float(value) <= 100:
        errors.append(f"{record_name}[{index}] {field_name} aralık dışı")


def _validate_0_1_score(
    *,
    value: Any,
    field_name: str,
    record_name: str,
    index: int,
    errors: list[str],
) -> None:
    if not is_finite_number(value) or not 0 <= float(value) <= 1:
        errors.append(f"{record_name}[{index}] {field_name} aralık dışı")


def _validate_measurements(
    *,
    measurements: Any,
    record_name: str,
    index: int,
    errors: list[str],
) -> None:
    if not isinstance(measurements, dict):
        errors.append(f"{record_name}[{index}] measurements dict değil")
        return

    missing = sorted(REQUIRED_MEASUREMENT_FIELDS - set(measurements.keys()))
    if missing:
        errors.append(f"{record_name}[{index}] measurements eksik alanlar: {missing}")
        return

    for field_name in REQUIRED_MEASUREMENT_FIELDS:
        value = measurements.get(field_name)
        if not is_finite_number(value):
            errors.append(f"{record_name}[{index}] measurements.{field_name} geçersiz")


def _validate_component_scores(
    *,
    component_scores: Any,
    record_name: str,
    index: int,
    errors: list[str],
) -> None:
    if not isinstance(component_scores, dict):
        errors.append(f"{record_name}[{index}] component_scores dict değil")
        return

    missing = sorted(REQUIRED_COMPONENT_SCORE_FIELDS - set(component_scores.keys()))
    if missing:
        errors.append(f"{record_name}[{index}] component_scores eksik alanlar: {missing}")
        return

    for field_name in REQUIRED_COMPONENT_SCORE_FIELDS:
        _validate_0_100_score(
            value=component_scores.get(field_name),
            field_name=f"component_scores.{field_name}",
            record_name=record_name,
            index=index,
            errors=errors,
        )


def _validate_reliability_fields(
    *,
    record: dict[str, Any],
    record_name: str,
    index: int,
    errors: list[str],
) -> None:
    _validate_0_1_score(
        value=record.get("sensor_reliability_score"),
        field_name="sensor_reliability_score",
        record_name=record_name,
        index=index,
        errors=errors,
    )

    _validate_0_1_score(
        value=record.get("confidence"),
        field_name="confidence",
        record_name=record_name,
        index=index,
        errors=errors,
    )

    reliability_status = record.get("reliability_status")
    if reliability_status not in VALID_RELIABILITY_STATUS_VALUES:
        errors.append(
            f"{record_name}[{index}] reliability_status geçersiz: {reliability_status}"
        )

    if not isinstance(record.get("reliability_reason"), str) or not record.get("reliability_reason"):
        errors.append(f"{record_name}[{index}] reliability_reason geçersiz")

    if not isinstance(record.get("reliability_reasons"), list):
        errors.append(f"{record_name}[{index}] reliability_reasons liste değil")


def _validate_environmental_reason_fields(
    *,
    record: dict[str, Any],
    record_name: str,
    index: int,
    errors: list[str],
) -> None:
    if not isinstance(record.get("environmental_risk_reason"), list):
        errors.append(f"{record_name}[{index}] environmental_risk_reason liste değil")

    formula = record.get("environmental_risk_formula")
    if not isinstance(formula, str) or "methane_risk" not in formula:
        errors.append(f"{record_name}[{index}] environmental_risk_formula geçersiz")


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
        "environmental_risk",
        "weighted_multi_sensor_risk",
        "status",
        "risk_level",
        "measurements",
        "component_scores",
        "sensor_reliability_score",
        "confidence",
        "reliability_status",
        "reliability_reason",
        "reliability_reasons",
        "environmental_risk_reason",
        "environmental_risk_formula",
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

        _validate_0_100_score(
            value=record["methane_risk_score"],
            field_name="methane_risk_score",
            record_name="gas",
            index=index,
            errors=errors,
        )

        _validate_0_100_score(
            value=record["environmental_risk"],
            field_name="environmental_risk",
            record_name="gas",
            index=index,
            errors=errors,
        )

        _validate_0_100_score(
            value=record["weighted_multi_sensor_risk"],
            field_name="weighted_multi_sensor_risk",
            record_name="gas",
            index=index,
            errors=errors,
        )

        anomaly = record["anomaly_score"]
        if not is_finite_number(anomaly) or not 0 <= float(anomaly) <= 1:
            errors.append(f"gas[{index}] anomaly_score aralık dışı")

        if record["status"] not in VALID_STATUS_VALUES:
            errors.append(f"gas[{index}] status geçersiz: {record['status']}")

        if record["risk_level"] not in VALID_STATUS_VALUES:
            errors.append(f"gas[{index}] risk_level geçersiz: {record['risk_level']}")

        _validate_measurements(
            measurements=record.get("measurements"),
            record_name="gas",
            index=index,
            errors=errors,
        )

        _validate_component_scores(
            component_scores=record.get("component_scores"),
            record_name="gas",
            index=index,
            errors=errors,
        )

        _validate_reliability_fields(
            record=record,
            record_name="gas",
            index=index,
            errors=errors,
        )

        _validate_environmental_reason_fields(
            record=record,
            record_name="gas",
            index=index,
            errors=errors,
        )

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
        "weighted_multi_sensor_risk",
        "risk_level",
        "measurements",
        "component_scores",
        "sensor_reliability_score",
        "confidence",
        "reliability_status",
        "reliability_reason",
        "reliability_reasons",
        "environmental_risk_reason",
        "environmental_risk_formula",
    }

    for index, record in enumerate(records):
        missing = sorted(required_fields - set(record.keys()))
        if missing:
            errors.append(f"risk[{index}] eksik alanlar: {missing}")
            continue

        if record["segment_id"] not in segments:
            errors.append(f"risk[{index}] bilinmeyen segment_id: {record['segment_id']}")

        _validate_0_100_score(
            value=record["methane_risk_score"],
            field_name="methane_risk_score",
            record_name="risk",
            index=index,
            errors=errors,
        )

        _validate_0_100_score(
            value=record["environmental_risk"],
            field_name="environmental_risk",
            record_name="risk",
            index=index,
            errors=errors,
        )

        _validate_0_100_score(
            value=record["weighted_multi_sensor_risk"],
            field_name="weighted_multi_sensor_risk",
            record_name="risk",
            index=index,
            errors=errors,
        )

        anomaly = record["anomaly_score"]
        if not is_finite_number(anomaly) or not 0 <= float(anomaly) <= 1:
            errors.append(f"risk[{index}] anomaly_score aralık dışı")

        if record["risk_level"] not in VALID_STATUS_VALUES:
            errors.append(f"risk[{index}] risk_level geçersiz: {record['risk_level']}")

        _validate_measurements(
            measurements=record.get("measurements"),
            record_name="risk",
            index=index,
            errors=errors,
        )

        _validate_component_scores(
            component_scores=record.get("component_scores"),
            record_name="risk",
            index=index,
            errors=errors,
        )

        _validate_reliability_fields(
            record=record,
            record_name="risk",
            index=index,
            errors=errors,
        )

        _validate_environmental_reason_fields(
            record=record,
            record_name="risk",
            index=index,
            errors=errors,
        )

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