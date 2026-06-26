from __future__ import annotations

from typing import Any

from apps.common.ids import normalize_record_ids, normalize_segment_id
from apps.common.json_store import filter_time_step, load_json
from apps.lidar.services import get_geometry_risks, get_segments
from apps.sensors.services import get_environmental_risks
from apps.workers.services import get_workers


RISK_WEIGHTS = {
    "geometry": 0.40,
    "environmental": 0.35,
    "worker": 0.20,
    "tracking": 0.05,
}


def _active_reasons(item: dict[str, Any]) -> list[str]:
    reason_breakdown = item.get("reason_breakdown") or {}
    return [str(value) for value in reason_breakdown.values() if value]


def _risk_level(score: float) -> str:
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 30:
        return "medium"
    return "low"


def _recommended_action(risk_level: str, has_worker: bool) -> str:
    if risk_level == "critical":
        return "Segmenti tahliye et, rota ve gaz ölçümünü doğrula."
    if risk_level == "high":
        return "Erişimi sınırla, işçi konumunu ve sensörleri yakından izle."
    if has_worker:
        return "İşçi varlığı nedeniyle periyodik kontrolü sürdür."
    return "Standart izleme yeterli."


def _build_risk_breakdown(
    geometry_risk: float,
    environmental_risk: float,
    worker_risk: float,
    tracking_risk: float,
) -> dict[str, Any]:
    contributions = {
        "geometry": round(geometry_risk * RISK_WEIGHTS["geometry"], 3),
        "environmental": round(environmental_risk * RISK_WEIGHTS["environmental"], 3),
        "worker": round(worker_risk * RISK_WEIGHTS["worker"], 3),
        "tracking": round(tracking_risk * RISK_WEIGHTS["tracking"], 3),
    }
    total = round(sum(contributions.values()), 3)
    return {
        "weights": dict(RISK_WEIGHTS),
        "raw": {
            "geometry": round(geometry_risk, 3),
            "environmental": round(environmental_risk, 3),
            "worker": round(worker_risk, 3),
            "tracking": round(tracking_risk, 3),
        },
        "contributions": contributions,
        "total": total,
        "formula": "0.40*geometry + 0.35*environmental + 0.20*worker + 0.05*tracking",
    }


def _environmental_by_segment(time_step: int | None, fallback: str = "first") -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for item in get_environmental_risks(time_step, fallback=fallback):
        segment_id = item.get("segment_id")
        if not segment_id:
            continue
        current = grouped.get(segment_id)
        if current is None or item.get("risk_score", 0.0) > current.get("risk_score", 0.0):
            grouped[segment_id] = item
    return grouped


def _worker_exposure_from_workers(workers: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for worker in workers:
        segment_id = worker.get("current_segment")
        if not segment_id:
            continue
        bucket = grouped.setdefault(
            segment_id,
            {
                "worker_exposure_risk": 0.0,
                "active_worker_ids": [],
                "tracking_risk_score": 0.0,
            },
        )
        bucket["worker_exposure_risk"] = 100.0
        if worker.get("worker_id") not in bucket["active_worker_ids"]:
            bucket["active_worker_ids"].append(worker.get("worker_id"))
        bucket["tracking_risk_score"] = max(bucket["tracking_risk_score"], float(worker.get("tracking_risk_score", 0.0)))
    return grouped


def _worker_exposure_by_segment(
    time_step: int | None,
    workers_override: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    if workers_override is not None:
        return _worker_exposure_from_workers(workers_override)

    if time_step in (None, 0):
        return _worker_exposure_from_workers(get_workers(0))

    raw = load_json("risk/worker_exposure_risk.json", default={})
    records = raw.get("records", raw if isinstance(raw, list) else [])
    selected = filter_time_step(records, time_step)
    grouped = {}
    for item in selected:
        record = normalize_record_ids(item)
        segment_id = record.get("segment_id")
        if not segment_id:
            continue
        bucket = grouped.setdefault(
            segment_id,
            {
                "worker_exposure_risk": 0.0,
                "active_worker_ids": [],
                "tracking_risk_score": 0.0,
            },
        )
        bucket["worker_exposure_risk"] = max(bucket["worker_exposure_risk"], float(record.get("worker_exposure_risk", 0.0)))
        bucket["tracking_risk_score"] = max(bucket["tracking_risk_score"], float(record.get("tracking_risk_score", 0.0)))
        if record.get("worker_id") not in bucket["active_worker_ids"]:
            bucket["active_worker_ids"].append(record.get("worker_id"))
    return grouped


def get_segment_risks(
    time_step: int | None = 0,
    workers_override: list[dict[str, Any]] | None = None,
    sensor_fallback: str = "first",
) -> list[dict[str, Any]]:
    segments = get_segments()
    geometry = {item["segment_id"]: item for item in get_geometry_risks()}
    environmental = _environmental_by_segment(time_step, fallback=sensor_fallback)
    worker_exposure = _worker_exposure_by_segment(time_step, workers_override=workers_override)

    risks = []
    for segment in segments:
        segment_id = normalize_segment_id(segment.get("segment_id"))
        geo = geometry.get(segment_id, {})
        env = environmental.get(segment_id, {})
        worker = worker_exposure.get(segment_id, {})

        geometry_risk = float(geo.get("geometry_risk", segment.get("geometry_risk", 0.0)) or 0.0)
        environmental_risk = float(env.get("risk_score", env.get("environmental_risk", 0.0)) or 0.0)
        worker_risk = float(worker.get("worker_exposure_risk", 0.0) or 0.0)
        tracking_risk = float(worker.get("tracking_risk_score", 0.0) or 0.0)

        breakdown = _build_risk_breakdown(
            geometry_risk=geometry_risk,
            environmental_risk=environmental_risk,
            worker_risk=worker_risk,
            tracking_risk=tracking_risk,
        )
        final_score = breakdown["total"]
        level = _risk_level(final_score)
        active_reasons = []
        if geo.get("reasons"):
            active_reasons.extend(geo["reasons"][:3])
        if environmental_risk > 0:
            active_reasons.append(f"Methane/environmental risk {environmental_risk:.1f}")
        if worker_risk > 0:
            active_reasons.append("Worker occupancy in segment")
        if tracking_risk > 0:
            active_reasons.append(f"Tracking reliability risk {tracking_risk:.1f}")
        if not active_reasons:
            active_reasons.append("No active anomaly")

        risk = {
            "time_step": time_step,
            "segment_id": segment_id,
            "final_risk_score": final_score,
            "final_segment_risk": final_score,
            "risk_score": final_score,
            "risk_level": level,
            "risk_breakdown": breakdown,
            "geometry_risk": geometry_risk,
            "lidar_geometry_risk": geometry_risk,
            "environmental_risk": environmental_risk,
            "methane_risk_score": environmental_risk,
            "worker_exposure_risk": worker_risk,
            "worker_exposure_score": worker_risk,
            "tracking_risk_score": tracking_risk,
            "route_blockage_risk": 0.0,
            "active_worker_ids": worker.get("active_worker_ids", []),
            "active_sensor_ids": [env["sensor_id"]] if env.get("sensor_id") else [],
            "active_reasons": active_reasons,
            "recommended_action": _recommended_action(level, worker_risk > 0),
            "fusion_policy": "0.40*geometry + 0.35*environment + 0.20*worker + 0.05*tracking",
        }
        risks.append(risk)
    return risks


def risk_by_segment(time_step: int | None = 0) -> dict[str, dict[str, Any]]:
    return {item["segment_id"]: item for item in get_segment_risks(time_step)}


def get_geometry_risk_records() -> list[dict[str, Any]]:
    records = []
    for item in get_geometry_risks():
        record = normalize_record_ids(item)
        record["structural_risk_score"] = record.get("geometry_risk", 0.0)
        record["notes"] = "; ".join(record.get("reasons", [])) or "No geometry note"
        records.append(record)
    return records
