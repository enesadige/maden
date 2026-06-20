from __future__ import annotations

import csv
from pathlib import Path

from _env import bootstrap

bootstrap()

from madenguard.config import ensure_project_dirs, load_config, project_path
from madenguard.io_utils import percentile, read_json, write_json


METHANE_COLUMNS = ["MM252", "MM261", "MM262", "MM263", "MM264", "MM256", "MM211"]


def to_float(value: str | None) -> float:
    try:
        return float(value or 0.0)
    except ValueError:
        return 0.0


def main() -> None:
    ensure_project_dirs()
    config = load_config()
    methane_path = Path(config["paths"]["methane_csv"])
    segments = read_json(project_path("processed", "features", "segments.json"))
    preferred_segments = [seg for seg in segments if seg.get("is_chokepoint")] or sorted(segments, key=lambda s: s.get("length", 0), reverse=True)
    sensor_segments = preferred_segments[:3] if preferred_segments else segments[:3]
    sensors = [
        {"sensor_id": f"GAS_SENSOR_{idx+1:02d}", "segment_id": seg["segment_id"], "placement_reason": "chokepoint_or_long_segment"}
        for idx, seg in enumerate(sensor_segments)
    ]

    max_rows = int(config["runtime"].get("max_methane_rows", 200000))
    target_steps = int(config["runtime"].get("gas_timeline_steps", 90))
    values: list[float] = []
    raw_samples: list[dict[str, object]] = []
    with methane_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for idx, row in enumerate(reader):
            if idx >= max_rows:
                break
            methane_values = [to_float(row.get(col)) for col in METHANE_COLUMNS if col in row]
            methane = sum(methane_values) / len(methane_values) if methane_values else 0.0
            values.append(methane)
            if idx % max(1, max_rows // target_steps) == 0 and len(raw_samples) < target_steps:
                raw_samples.append({"source_row": idx, "methane_value": methane})

    p99 = percentile(values, 99) or max(values or [1.0])
    timeline = []
    for step, sample in enumerate(raw_samples):
        for sensor in sensors:
            methane = float(sample["methane_value"])
            risk = min(100.0, max(0.0, methane / p99 * 100.0)) if p99 else 0.0
            if risk >= 80:
                status = "critical"
            elif risk >= 60:
                status = "high"
            elif risk >= 30:
                status = "medium"
            else:
                status = "normal"
            timeline.append({
                "time_step": step,
                "sensor_id": sensor["sensor_id"],
                "segment_id": sensor["segment_id"],
                "methane_value": round(methane, 6),
                "methane_risk_score": round(risk, 3),
                "status": status,
                "placement_reason": sensor["placement_reason"],
            })

    write_json(project_path("processed", "timelines", "gas_sensors_timeline.json"), timeline)
    write_json(project_path("simulation_ready", "gas_sensors_timeline.json"), timeline)
    report = [
        "# Gas Risk Report",
        "",
        f"- Source CSV: `{methane_path}`",
        f"- Rows scanned in local-safe pass: {len(values)}",
        f"- Methane columns used: {', '.join(METHANE_COLUMNS)}",
        f"- Robust p99 normalizer: {p99:.6f}",
        f"- Sensor placements: {', '.join(sensor['segment_id'] for sensor in sensors)}",
    ]
    project_path("reports", "gas_risk_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"Wrote gas timeline with {len(timeline)} records")


if __name__ == "__main__":
    main()

