from __future__ import annotations

from typing import Any

from apps.common.ids import normalize_record_ids, normalize_segment_id
from apps.common.json_store import filter_time_step, load_json


def _reliability_from_motion(item: dict[str, Any]) -> float:
    motion = item.get("motion_status")
    if motion == "fast_motion":
        return 0.78
    if motion == "stationary":
        return 0.92
    return 0.86


def get_workers(time_step: int | None = 0) -> list[dict[str, Any]]:
    records = load_json("workers/workers.json", default=[])
    selected = filter_time_step(records, time_step)
    workers = []
    for item in selected:
        worker = normalize_record_ids(item)
        mapped_segment = worker.get("mapped_segment_id")
        worker["current_segment"] = normalize_segment_id(mapped_segment)
        worker["position"] = worker.get("uwb_pose", {})
        worker.setdefault("position_reliability", _reliability_from_motion(worker))
        worker.setdefault("status", "safe")
        workers.append(worker)
    return workers
