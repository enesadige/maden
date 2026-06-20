from __future__ import annotations

import csv
import math
from pathlib import Path

from _env import bootstrap

bootstrap()

from madenguard.config import ensure_project_dirs, load_config, project_path
from madenguard.io_utils import read_json, write_json


def to_float(value: str | None, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except ValueError:
        return default


def motion_status(acc: float, prev_pose: tuple[float, float, float] | None, pose: tuple[float, float, float]) -> str:
    if prev_pose is None:
        return "moving"
    dist = math.dist(prev_pose, pose)
    if acc > 18.0:
        return "possible_fall"
    if dist < 0.01:
        return "still"
    if dist > 1.5:
        return "fast_motion"
    return "moving"


def main() -> None:
    ensure_project_dirs()
    config = load_config()
    uwb_path = Path(config["paths"]["uwb_csv"])
    segments = read_json(project_path("processed", "features", "segments.json"))
    max_rows = int(config["runtime"].get("max_uwb_rows", 120000))
    target_steps = int(config["runtime"].get("worker_timeline_steps", 90))
    sampled_rows: list[dict[str, str]] = []

    with uwb_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for idx, row in enumerate(reader):
            if idx >= max_rows:
                break
            if idx % max(1, max_rows // target_steps) == 0:
                sampled_rows.append(row)
            if len(sampled_rows) >= target_steps:
                break

    poses = [
        (to_float(row.get("pose_x")), to_float(row.get("pose_y")), to_float(row.get("pose_z")))
        for row in sampled_rows
    ]
    xs = [p[0] for p in poses] or [0.0]
    min_x, max_x = min(xs), max(xs)
    span = max(max_x - min_x, 1e-9)
    timeline = []
    prev_pose: tuple[float, float, float] | None = None
    for step, row in enumerate(sampled_rows):
        pose = (to_float(row.get("pose_x")), to_float(row.get("pose_y")), to_float(row.get("pose_z")))
        acc = math.sqrt(to_float(row.get("acc_x")) ** 2 + to_float(row.get("acc_y")) ** 2 + to_float(row.get("acc_z")) ** 2)
        progress = (pose[0] - min_x) / span
        seg_idx = min(len(segments) - 1, max(0, int(progress * len(segments)))) if segments else 0
        seg_id = segments[seg_idx]["segment_id"] if segments else "SEG_001"
        timeline.append({
            "time_step": step,
            "worker_id": "WORKER_01",
            "uwb_pose": {"x": pose[0], "y": pose[1], "z": pose[2]},
            "mapped_segment_id": seg_id,
            "acc_magnitude": round(acc, 4),
            "motion_status": motion_status(acc, prev_pose, pose),
            "source_row_policy": f"decimated_from_first_{max_rows}_rows",
        })
        prev_pose = pose

    write_json(project_path("processed", "timelines", "workers_timeline.json"), timeline)
    write_json(project_path("simulation_ready", "workers_timeline.json"), timeline)
    report = [
        "# UWB Worker Timeline Report",
        "",
        f"- Source CSV: `{uwb_path}`",
        f"- Timeline records: {len(timeline)}",
        f"- Mapping: UTIL pose_x is normalized onto ordered DARPA EX graph segments for MVP.",
        f"- Raw TDOA solving is not attempted in this first local pipeline.",
    ]
    project_path("reports", "uwb_worker_timeline_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"Wrote worker timeline with {len(timeline)} records")


if __name__ == "__main__":
    main()

