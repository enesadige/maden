from __future__ import annotations

from typing import Any

from apps.common.ids import normalize_record_ids, normalize_segment_id
from apps.common.json_store import available_time_steps, filter_time_step, load_json


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


def get_workers_at_time_step(time_step: int, fallback: str = "none") -> list[dict[str, Any]]:
    records = load_json("workers/worker_segment_timeline.json", default=[])
    selected = filter_time_step(records, time_step, fallback=fallback)
    return [_normalize_worker_record(item) for item in selected]


def get_worker_time_steps() -> list[int]:
    return available_time_steps("workers/worker_segment_timeline.json")


def get_workers(time_step: int | None = 0) -> list[dict[str, Any]]:
    if time_step in (None, 0):
        return _latest_workers()

    workers = _historical_workers(time_step)
    if workers:
        return workers
    return _latest_workers()


def _behavior_anomaly_payload() -> dict[str, Any]:
    raw = load_json("workers/behavior_anomaly_events.json", default={})
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        return {
            "source": "uwb_behavior_anomaly",
            "mvp_rule_based": True,
            "events": raw,
            "summary": {},
            "warnings": [],
        }
    return {
        "source": "uwb_behavior_anomaly",
        "mvp_rule_based": True,
        "events": [],
        "summary": {},
        "warnings": [],
    }


def get_worker_anomalies(
    time_step: int | None = None,
    worker_id: str | None = None,
    event_type: str | None = None,
    severity: str | None = None,
) -> list[dict[str, Any]]:
    payload = _behavior_anomaly_payload()
    events = payload.get("events", [])
    if not isinstance(events, list):
        return []

    normalized_events = [normalize_record_ids(item) for item in events if isinstance(item, dict)]
    if time_step is not None:
        normalized_events = [item for item in normalized_events if item.get("time_step") == time_step]
    if worker_id:
        normalized_events = [item for item in normalized_events if item.get("worker_id") == worker_id]
    if event_type:
        normalized_events = [item for item in normalized_events if item.get("event_type") == event_type]
    if severity:
        normalized_events = [item for item in normalized_events if item.get("severity") == severity]
    return normalized_events


def get_worker_anomaly_summary() -> dict[str, Any]:
    payload = _behavior_anomaly_payload()
    summary = payload.get("summary", {})
    return {
        "source": payload.get("source", "uwb_behavior_anomaly"),
        "mvp_rule_based": payload.get("mvp_rule_based", True),
        "summary": summary if isinstance(summary, dict) else {},
        "warnings": payload.get("warnings", []),
    }
