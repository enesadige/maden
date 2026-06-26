from __future__ import annotations

from typing import Any

from apps.common.ids import normalize_record_ids, normalize_segment_id
from apps.common.json_store import load_json


def _reliability_from_motion(item: dict[str, Any]) -> float:
    motion = item.get("motion_status")
    if motion == "fast_motion":
        return 0.78
    if motion == "stationary":
        return 0.92
    return 0.86


def _normalize_worker_record(item: dict[str, Any]) -> dict[str, Any]:
    worker = normalize_record_ids(item)
    mapped_segment = worker.get("mapped_segment_id") or worker.get("current_segment")
    worker["current_segment"] = normalize_segment_id(mapped_segment)
    worker["position"] = worker.get("uwb_pose") or worker.get("position", {})
    worker.setdefault("uwb_pose", worker["position"])
    worker.setdefault("mapped_segment_id", worker["current_segment"])
    worker.setdefault("motion_status", worker.get("status", "safe"))
    worker.setdefault("position_reliability", _reliability_from_motion(worker))
    worker.setdefault("status", "safe")
    return worker


def _latest_workers() -> list[dict[str, Any]]:
    records = load_json("workers/workers.json", default=[])
    return [_normalize_worker_record(item) for item in records]


def _historical_workers(time_step: int) -> list[dict[str, Any]]:
    records = load_json("workers/worker_segment_timeline.json", default=[])
    selected = [item for item in records if item.get("time_step") == time_step]
    return [_normalize_worker_record(item) for item in selected]


def get_workers(time_step: int | None = 0) -> list[dict[str, Any]]:
    if time_step in (None, 0):
        return _latest_workers()

    workers = _historical_workers(time_step)
    if workers:
        return workers
    return _latest_workers()
