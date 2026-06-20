from __future__ import annotations

from collections import defaultdict

from _env import bootstrap

bootstrap()

from madenguard.config import ensure_project_dirs, project_path
from madenguard.io_utils import read_json, write_json


def level(score: float) -> str:
    if score >= 80:
        return "CRITICAL"
    if score >= 60:
        return "HIGH"
    if score >= 30:
        return "MEDIUM"
    return "LOW"


def main() -> None:
    ensure_project_dirs()
    segments = read_json(project_path("processed", "features", "segments.json"))
    lidar_rows = read_json(project_path("simulation_ready", "lidar_geometry_risk.json"))
    graph_rows = read_json(project_path("simulation_ready", "graph_risk_scores.json"))
    workers = read_json(project_path("simulation_ready", "workers_timeline.json"))
    gas = read_json(project_path("simulation_ready", "gas_sensors_timeline.json"))
    reliability = read_json(project_path("simulation_ready", "sensor_reliability_scores.json"))

    lidar_by_segment: dict[str, float] = defaultdict(float)
    for row in lidar_rows:
        lidar_by_segment[row["segment_id"]] = max(lidar_by_segment[row["segment_id"]], float(row["lidar_geometry_risk"]))
    graph_by_segment = {row["segment_id"]: float(row["graph_risk_score"]) for row in graph_rows}
    reliability_by_sensor: dict[str, float] = defaultdict(lambda: 100.0)
    for row in reliability:
        reliability_by_sensor[row["sensor_id"]] = min(reliability_by_sensor[row["sensor_id"]], float(row["sensor_reliability_score"]))

    worker_by_time = {row["time_step"]: row for row in workers}
    gas_by_time_segment: dict[tuple[int, str], list[dict[str, object]]] = defaultdict(list)
    for row in gas:
        gas_by_time_segment[(int(row["time_step"]), row["segment_id"])].append(row)
    max_time = max([int(row["time_step"]) for row in workers + gas] or [0])
    combined = []
    for t in range(max_time + 1):
        worker = worker_by_time.get(t)
        worker_segment = worker["mapped_segment_id"] if worker else None
        for seg in segments:
            segment_id = seg["segment_id"]
            gas_rows = gas_by_time_segment.get((t, segment_id), [])
            methane_risk = max([float(row["methane_risk_score"]) for row in gas_rows] or [0.0])
            active_sensors = [str(row["sensor_id"]) for row in gas_rows]
            reliability_score = min([reliability_by_sensor[sensor_id] for sensor_id in active_sensors] or [100.0])
            confidence_factor = max(0.65, reliability_score / 100.0)
            adjusted_methane = methane_risk * confidence_factor
            worker_exposure = 100.0 if worker_segment == segment_id else 0.0
            lidar_risk = lidar_by_segment.get(segment_id, 0.0)
            graph_risk = graph_by_segment.get(segment_id, 0.0)
            final = 0.35 * lidar_risk + 0.25 * graph_risk + 0.25 * adjusted_methane + 0.15 * worker_exposure
            reasons = {
                "lidar": f"LiDAR geometry risk {lidar_risk:.1f}",
                "graph": f"Graph blocking risk {graph_risk:.1f}",
                "gas": f"Methane risk {methane_risk:.1f}, confidence-adjusted {adjusted_methane:.1f}",
                "worker": "worker is inside this segment" if worker_exposure else "no active worker exposure",
            }
            combined.append({
                "time_step": t,
                "segment_id": segment_id,
                "lidar_geometry_risk": round(lidar_risk, 3),
                "graph_risk_score": round(graph_risk, 3),
                "methane_risk_score": round(adjusted_methane, 3),
                "raw_methane_risk_score": round(methane_risk, 3),
                "sensor_reliability_score": round(reliability_score, 3),
                "worker_exposure_score": round(worker_exposure, 3),
                "final_segment_risk": round(final, 3),
                "risk_level": level(final),
                "active_worker_ids": ["WORKER_01"] if worker_exposure else [],
                "active_sensor_ids": active_sensors,
                "reason_breakdown": reasons,
            })

    write_json(project_path("processed", "timelines", "combined_simulation_timeline.json"), combined)
    write_json(project_path("simulation_ready", "combined_simulation_timeline.json"), combined)
    write_json(project_path("simulation_ready", "final_segment_risk_timeline.json"), combined)

    top = sorted(combined, key=lambda item: item["final_segment_risk"], reverse=True)[:10]
    report = ["# Final Risk Fusion Report", "", "Formula: `0.35*LiDAR + 0.25*Graph + 0.25*Methane + 0.15*WorkerExposure`.", "", "## Top Risk Records"]
    for item in top:
        report.append(
            f"- t={item['time_step']} {item['segment_id']}: final={item['final_segment_risk']} ({item['risk_level']}), "
            f"lidar={item['lidar_geometry_risk']}, graph={item['graph_risk_score']}, gas={item['methane_risk_score']}, worker={item['worker_exposure_score']}"
        )
    project_path("reports", "final_risk_fusion_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"Wrote fused risk timeline with {len(combined)} records")


if __name__ == "__main__":
    main()

