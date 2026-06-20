from __future__ import annotations

from typing import Any

from apps.common.ids import normalize_record_ids
from apps.common.json_store import filter_time_step, load_json


def _active_reasons(item: dict[str, Any]) -> list[str]:
    reason_breakdown = item.get("reason_breakdown") or {}
    return [str(value) for value in reason_breakdown.values() if value]


def get_segment_risks(time_step: int | None = 0) -> list[dict[str, Any]]:
    records = load_json("risk/risk_segments.json", default=[])
    selected = filter_time_step(records, time_step)
    risks = []
    for item in selected:
        risk = normalize_record_ids(item)
        risk["final_risk_score"] = risk.get("final_segment_risk", risk.get("final_risk_score", 0.0))
        risk["geometry_risk"] = risk.get("lidar_geometry_risk", risk.get("geometry_risk", 0.0))
        risk["environmental_risk"] = risk.get("methane_risk_score", risk.get("environmental_risk", 0.0))
        risk["worker_exposure_risk"] = risk.get("worker_exposure_score", risk.get("worker_exposure_risk", 0.0))
        risk["route_blockage_risk"] = risk.get("graph_risk_score", risk.get("route_blockage_risk", 0.0))
        risk["active_reasons"] = _active_reasons(risk)
        risks.append(risk)
    return risks


def risk_by_segment(time_step: int | None = 0) -> dict[str, dict[str, Any]]:
    return {item["segment_id"]: item for item in get_segment_risks(time_step)}
