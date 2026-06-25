from __future__ import annotations

from collections import defaultdict
from typing import Any

from backend.methane_processing.anomaly import rolling_anomaly_scores
from backend.methane_processing.core import PRIMARY_METHANE_COLUMNS, risk_level, risk_status
from backend.methane_processing.risk_scoring import methane_risk_scores


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
            record = {
                "time_step": int(sample["time_step"]),
                "timestamp": sample.get("timestamp", ""),
                "source_row": int(sample.get("source_row", 0)),
                "sensor_id": mapping["sensor_id"],
                "segment_id": mapping["segment_id"],
                "source_column": source_column,
                "methane_value": round(float(methane_value), 6),
                "methane_risk_score": round(float(risk_score), 3),
                "anomaly_score": round(float(anomaly_score), 6),
                "environmental_risk": round(float(risk_score), 3),
                "status": risk_status(float(risk_score)),
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
    """
    records: list[dict[str, Any]] = []

    for item in gas_timeline:
        risk_score = float(item.get("methane_risk_score", 0.0))

        records.append(
            {
                "time_step": int(item["time_step"]),
                "timestamp": item.get("timestamp", ""),
                "segment_id": item["segment_id"],
                "sensor_id": item["sensor_id"],
                "source_column": item.get("source_column"),
                "methane_value": item.get("methane_value", 0.0),
                "methane_risk_score": round(risk_score, 3),
                "anomaly_score": item.get("anomaly_score", 0.0),
                "environmental_risk": round(risk_score, 3),
                "risk_level": risk_level(risk_score),
                "reason": "methane value score fused with rolling anomaly score",
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
        risk = float(record.get("methane_risk_score", 0.0))

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
        "max_methane_risk_score": round(max_risk, 3),
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
            f"- Status counts: `{summary.get('status_counts')}`",
            "",
            "## Method",
            "",
            "Each methane channel is treated as an independent gas sensor. "
            "Rolling z-score is used for anomaly scoring. Methane risk is calculated "
            "from a robust methane value score and the rolling anomaly score.",
        ]
    )

    return "\n".join(lines) + "\n"
