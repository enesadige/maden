from collections import defaultdict
from typing import Any

from backend.methane_processing.anomaly import rolling_anomaly_scores
from backend.methane_processing.core import PRIMARY_METHANE_COLUMNS, risk_level, risk_status
from backend.methane_processing.environmental_sensors import build_environmental_measurements
from backend.methane_processing.reliability import build_sensor_reliability
from backend.methane_processing.risk_scoring import (
    build_multisensor_environmental_risk,
    methane_risk_scores,
)

def build_gas_sensor_timeline(
    samples: list[dict[str, Any]],
    sensor_mapping: dict[str, dict[str, Any]],
    methane_columns: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Methane sample kayıtlarından backend ve fusion uyumlu gas sensor timeline üretir.
    """
    if methane_columns is None:
        methane_columns = PRIMARY_METHANE_COLUMNS

    timeline: list[dict[str, Any]] = []

    for source_column in methane_columns:
        if source_column not in sensor_mapping:
            raise ValueError(f"Sensor mapping içinde kolon yok: {source_column}")

        mapping = sensor_mapping[source_column]
        values = [float(sample.get(source_column, 0.0)) for sample in samples]

        anomaly_scores = rolling_anomaly_scores(values)
        risk_scores = methane_risk_scores(values, anomaly_scores)

        for sample, methane_value, anomaly_score, risk_score in zip(
            samples,
            values,
            anomaly_scores,
            risk_scores,
        ):
            time_step = int(sample["time_step"])
            sensor_id = mapping["sensor_id"]

            measurements = build_environmental_measurements(
                methane_value=float(methane_value),
                methane_risk_score=float(risk_score),
                anomaly_score=float(anomaly_score),
                time_step=time_step,
                sensor_id=sensor_id,
            )
            reliability = build_sensor_reliability(
                measurements=measurements,
                anomaly_score=float(anomaly_score),
            )
            environmental_package = build_multisensor_environmental_risk(
                measurements=measurements,
                methane_risk_score=float(risk_score),
                confidence=float(reliability["confidence"]),
            )

            environmental_risk = float(environmental_package["environmental_risk"])

            record = {
                "time_step": time_step,
                "timestamp": sample.get("timestamp", ""),
                "source_row": int(sample.get("source_row", 0)),
                "sensor_id": sensor_id,
                "segment_id": mapping["segment_id"],
                "source_column": source_column,
                "methane_value": round(float(methane_value), 6),
                "methane_risk_score": round(float(risk_score), 3),
                "anomaly_score": round(float(anomaly_score), 6),
                "environmental_risk": round(environmental_risk, 3),
                "weighted_multi_sensor_risk": environmental_package["weighted_multi_sensor_risk"],
                "status": risk_status(environmental_risk),
                "risk_level": environmental_package["risk_level"],
                "measurements": measurements,
                "component_scores": environmental_package["component_scores"],
                "sensor_reliability_score": reliability["sensor_reliability_score"],
                "confidence": reliability["confidence"],
                "reliability_status": reliability["reliability_status"],
                "reliability_reason": reliability["reliability_reason"],
                "reliability_reasons": reliability["reliability_reasons"],
                "environmental_risk_reason": environmental_package["environmental_risk_reason"],
                "environmental_risk_formula": environmental_package["environmental_risk_formula"],
                "placement_reason": mapping.get(
                    "placement_reason",
                    "methane_sensor_segment_mapping",
                ),
                "segment_type": mapping.get("segment_type"),
                "segment_role": mapping.get("segment_role"),
                "geometry_risk": round(float(mapping.get("geometry_risk", 0.0)), 3),
            }
            timeline.append(record)

    timeline.sort(key=lambda item: (item["time_step"], item["sensor_id"]))
    return timeline


def build_environmental_risk_records(
    gas_timeline: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Gas sensor timeline içinden risk odaklı environmental_risk.json üretir.

    Backward compatibility:
    - Existing methane fields are preserved.
    - New multi-sensor fields are added as optional enrichment.
    """
    records: list[dict[str, Any]] = []

    for item in gas_timeline:
        risk_score = float(item.get("environmental_risk", item.get("methane_risk_score", 0.0)))

        records.append(
            {
                "time_step": int(item["time_step"]),
                "timestamp": item.get("timestamp", ""),
                "segment_id": item["segment_id"],
                "sensor_id": item["sensor_id"],
                "source_column": item.get("source_column"),
                "methane_value": item.get("methane_value", 0.0),
                "methane_risk_score": round(float(item.get("methane_risk_score", 0.0)), 3),
                "anomaly_score": item.get("anomaly_score", 0.0),
                "environmental_risk": round(risk_score, 3),
                "weighted_multi_sensor_risk": item.get("weighted_multi_sensor_risk"),
                "risk_level": risk_level(risk_score),
                "reason": "; ".join(
                    item.get(
                        "environmental_risk_reason",
                        ["multi-sensor environmental risk score"],
                    )
                ),
                "measurements": item.get("measurements", {}),
                "component_scores": item.get("component_scores", {}),
                "sensor_reliability_score": item.get("sensor_reliability_score"),
                "confidence": item.get("confidence"),
                "reliability_status": item.get("reliability_status"),
                "reliability_reason": item.get("reliability_reason"),
                "reliability_reasons": item.get("reliability_reasons", []),
                "environmental_risk_reason": item.get("environmental_risk_reason", []),
                "environmental_risk_formula": item.get("environmental_risk_formula"),
            }
        )

    return records

def summarize_timeline(
    gas_timeline: list[dict[str, Any]],
    environmental_risk: list[dict[str, Any]],
    sensor_mapping: dict[str, dict[str, Any]],
    methane_csv_path: str,
    max_rows: int,
    target_steps: int,
) -> dict[str, Any]:
    """
    Üretilen methane pipeline çıktısı için kısa özet üretir.
    """
    status_counts: dict[str, int] = defaultdict(int)
    sensor_counts: dict[str, int] = defaultdict(int)
    segment_counts: dict[str, int] = defaultdict(int)

    max_risk = 0.0
    max_record: dict[str, Any] | None = None

    for record in gas_timeline:
        status = str(record.get("status", "unknown"))
        sensor_id = str(record.get("sensor_id", "unknown"))
        segment_id = str(record.get("segment_id", "unknown"))
        risk = float(record.get("environmental_risk", record.get("methane_risk_score", 0.0)))

        status_counts[status] += 1
        sensor_counts[sensor_id] += 1
        segment_counts[segment_id] += 1

        if risk >= max_risk:
            max_risk = risk
            max_record = record

    return {
        "module": "methane_processing",
        "methane_csv_path": methane_csv_path,
        "max_rows_scanned": int(max_rows),
        "target_steps": int(target_steps),
        "gas_timeline_record_count": len(gas_timeline),
        "environmental_risk_record_count": len(environmental_risk),
        "sensor_mapping": sensor_mapping,
        "status_counts": dict(sorted(status_counts.items())),
        "sensor_counts": dict(sorted(sensor_counts.items())),
        "segment_counts": dict(sorted(segment_counts.items())),
        "max_methane_risk_score": round(
            max((float(record.get("methane_risk_score", 0.0)) for record in gas_timeline), default=0.0),
            3,
        ),
        "max_environmental_risk_score": round(max_risk, 3),
        "max_risk_record": max_record,
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    """
    reports/gas_risk_report.md için okunabilir kısa rapor üretir.
    """
    mapping = summary.get("sensor_mapping", {})
    lines = [
        "# Gas / Methane Risk Report",
        "",
        "This report is generated by backend/methane_processing.",
        "",
        "## Source",
        "",
        f"- Methane CSV: `{summary.get('methane_csv_path')}`",
        f"- Max rows scanned: `{summary.get('max_rows_scanned')}`",
        f"- Target time steps: `{summary.get('target_steps')}`",
        "",
        "## Outputs",
        "",
        "- backend/data_processed/sample/sensors/gas_sensors.json",
        "- backend/data_processed/sample/risk/environmental_risk.json",
        "- processed/timelines/gas_sensors_timeline.json",
        "- simulation_ready/gas_sensors_timeline.json",
        "",
        "## Sensor Mapping",
        "",
    ]

    for source_column, item in mapping.items():
        lines.append(
            f"- `{source_column}` → `{item.get('sensor_id')}` → `{item.get('segment_id')}` "
            f"({item.get('placement_reason')}, geometry_risk={item.get('geometry_risk')})"
        )

    lines.extend(
        [
            "",
            "## Risk Summary",
            "",
            f"- Gas timeline records: `{summary.get('gas_timeline_record_count')}`",
            f"- Environmental risk records: `{summary.get('environmental_risk_record_count')}`",
            f"- Max methane risk score: `{summary.get('max_methane_risk_score')}`",
            f"- Max environmental risk score: `{summary.get('max_environmental_risk_score')}`",            
            f"- Status counts: `{summary.get('status_counts')}`",
            "",
            "## Method",
            "",
            "Each methane channel is treated as an independent gas sensor. "
            "Rolling z-score is used for anomaly scoring. Methane risk is calculated "
            "from a robust methane value score and the rolling anomaly score. "
            "The pipeline also adds deterministic MVP/demo environmental context "
            "measurements for CO, O2, temperature, humidity and pressure. "
            "A weighted_multi_sensor_risk score is calculated from methane, CO, O2, "
            "temperature, humidity and pressure component scores. "
            "For safety and backward compatibility, the final environmental_risk field "
            "is calculated as max(methane_risk_score, weighted_multi_sensor_risk), "
            "so the new multi-sensor extension never suppresses the previous methane risk signal. "
            "These additional measurements are simulation context values, not real field measurements.",
        ]
    )

    return "\n".join(lines) + "\n"
