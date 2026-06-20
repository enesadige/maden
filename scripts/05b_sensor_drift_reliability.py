from __future__ import annotations

from pathlib import Path

from _env import bootstrap

bootstrap()

from madenguard.config import ensure_project_dirs, load_config, project_path
from madenguard.io_utils import mean, stdev, write_json


def parse_batch(path: Path, max_lines: int = 20000) -> dict[str, object]:
    concentrations: list[float] = []
    classes: dict[str, int] = {}
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for idx, line in enumerate(handle):
            if idx >= max_lines:
                break
            first = line.split(maxsplit=1)[0]
            if ";" not in first:
                continue
            cls, conc = first.split(";", 1)
            classes[cls] = classes.get(cls, 0) + 1
            try:
                concentrations.append(float(conc))
            except ValueError:
                pass
    return {
        "file": str(path),
        "rows_scanned": len(concentrations),
        "class_counts": classes,
        "concentration_mean": mean(concentrations),
        "concentration_stdev": stdev(concentrations),
    }


def main() -> None:
    ensure_project_dirs()
    config = load_config()
    drift_dir = Path(config["paths"]["uci_gas_drift_dir"])
    batch_paths = sorted(drift_dir.glob("batch*.dat"))
    summaries = [parse_batch(path) for path in batch_paths]
    stdevs = [float(item["concentration_stdev"]) for item in summaries]
    max_std = max(stdevs or [1.0])
    reliability = []
    for idx, item in enumerate(summaries):
        drift_ratio = float(item["concentration_stdev"]) / max_std if max_std else 0.0
        score = max(45.0, 100.0 - drift_ratio * 35.0)
        reliability.append({
            "sensor_id": f"GAS_SENSOR_{idx % 3 + 1:02d}",
            "source_batch": Path(str(item["file"])).name,
            "sensor_reliability_score": round(score, 3),
            "drift_warning": score < 70.0,
            "sensor_anomaly_score": round(100.0 - score, 3),
            "interpretation": "gas reading is considered reliable" if score >= 70.0 else "drift/anomaly warning should reduce confidence",
            "batch_summary": item,
        })
    write_json(project_path("processed", "features", "sensor_reliability_scores.json"), reliability)
    write_json(project_path("simulation_ready", "sensor_reliability_scores.json"), reliability)
    report = ["# Sensor Drift Report", "", f"- Batch files scanned: {len(batch_paths)}"]
    for item in reliability[:10]:
        report.append(f"- {item['source_batch']} -> {item['sensor_id']}: reliability={item['sensor_reliability_score']}, warning={item['drift_warning']}")
    project_path("reports", "sensor_drift_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"Wrote reliability scores for {len(reliability)} batch summaries")


if __name__ == "__main__":
    main()
