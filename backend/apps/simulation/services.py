from __future__ import annotations

from typing import Any

from apps.common.ids import normalize_segment_id
from apps.lidar.services import get_graph, get_segments
from apps.routing.services import get_emergency_route
from apps.scenarios.services import get_collapse_result
from apps.risk.services import get_segment_risks
from apps.sensors.services import get_environmental_risks, get_gas_sensors, get_gas_time_steps
from apps.workers.services import get_worker_time_steps, get_workers_at_time_step


def _source_time_bounds(worker_steps: list[int], gas_steps: list[int]) -> dict[str, Any]:
    all_steps = sorted(set(worker_steps) | set(gas_steps))
    return {
        "min": all_steps[0] if all_steps else 0,
        "max": all_steps[-1] if all_steps else 0,
        "worker": {
            "min": worker_steps[0] if worker_steps else None,
            "max": worker_steps[-1] if worker_steps else None,
            "count": len(worker_steps),
        },
        "gas": {
            "min": gas_steps[0] if gas_steps else None,
            "max": gas_steps[-1] if gas_steps else None,
            "count": len(gas_steps),
            "fallback_policy": "hold_last_known_value",
        },
    }


def _group_by_segment(records: list[dict[str, Any]], key: str = "segment_id") -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        segment_id = normalize_segment_id(record.get(key))
        if not segment_id:
            continue
        grouped.setdefault(segment_id, []).append(record)
    return grouped


def _risk_summary(risks: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"critical": 0, "high": 0, "medium": 0, "low": 0, "unknown": 0}
    for risk in risks:
        level = str(risk.get("risk_level") or "unknown")
        summary[level if level in summary else "unknown"] += 1
    return summary


def _trapped_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    trapped = [item for item in records if item.get("trapped")]
    return {
        "trapped_count": len(trapped),
        "safe_count": len(records) - len(trapped),
        "trapped_worker_ids": [item.get("worker_id") for item in trapped],
        "blocked_segment": records[0].get("blocked_segment") if records else None,
        "scenario_status": "trapped" if trapped else "safe",
    }


def _clone_record(record: dict[str, Any]) -> dict[str, Any]:
    cloned = dict(record)
    for key in ("active_reasons", "active_worker_ids", "active_sensor_ids", "route_segments", "route_nodes"):
        if isinstance(cloned.get(key), list):
            cloned[key] = list(cloned[key])
    if isinstance(cloned.get("risk"), dict):
        cloned["risk"] = dict(cloned["risk"])
    return cloned


def _clone_record_list(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_clone_record(record) for record in records]


def _select_worker(workers: list[dict[str, Any]], worker_id: str | None = None) -> dict[str, Any] | None:
    if worker_id:
        selected = next((item for item in workers if item.get("worker_id") == worker_id), None)
        if selected:
            return selected
    return workers[0] if workers else None


def _enrich_segments(
    segments: list[dict[str, Any]],
    risks: list[dict[str, Any]],
    workers: list[dict[str, Any]],
    gas_sensors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    risk_by_segment = {item["segment_id"]: item for item in risks}
    workers_by_segment = _group_by_segment(workers, key="current_segment")
    sensors_by_segment = _group_by_segment(gas_sensors)

    enriched = []
    for segment in segments:
        segment_id = normalize_segment_id(segment.get("segment_id"))
        risk = risk_by_segment.get(segment_id, {})
        segment_workers = workers_by_segment.get(segment_id, [])
        segment_sensors = sensors_by_segment.get(segment_id, [])
        enriched.append(
            {
                **segment,
                "segment_id": segment_id,
                "risk": risk,
                "final_risk_score": risk.get("final_risk_score", 0.0),
                "risk_level": risk.get("risk_level", segment.get("risk_level", "low")),
                "active_worker_ids": [worker.get("worker_id") for worker in segment_workers],
                "active_sensor_ids": [sensor.get("sensor_id") for sensor in segment_sensors],
                "worker_count": len(segment_workers),
                "gas_sensor_count": len(segment_sensors),
                "has_active_worker": bool(segment_workers),
                "has_active_gas_sensor": bool(segment_sensors),
            }
        )
    return enriched


def _apply_methane_spike(segments: list[dict[str, Any]], risks: list[dict[str, Any]], gas_sensors: list[dict[str, Any]]) -> dict[str, Any]:
    segments_by_id = {item["segment_id"]: item for item in segments}
    risks_by_id = {item["segment_id"]: item for item in risks}

    target_segment_id = None
    for sensor in gas_sensors:
        if str(sensor.get("status") or "").lower() == "alarm":
            target_segment_id = normalize_segment_id(sensor.get("segment_id"))
            break
    if not target_segment_id:
        target_segment_id = "S004"

    mutated_segment = segments_by_id.get(target_segment_id)
    mutated_risk = risks_by_id.get(target_segment_id)
    mutated_sensor = next(
        (sensor for sensor in gas_sensors if normalize_segment_id(sensor.get("segment_id")) == target_segment_id),
        None,
    )
    if not mutated_sensor and gas_sensors:
        mutated_sensor = gas_sensors[0]
        target_segment_id = normalize_segment_id(mutated_sensor.get("segment_id")) or target_segment_id

    if mutated_segment:
        mutated_segment["status"] = "gas_alert"
        mutated_segment["is_blocked"] = False
    if mutated_risk:
        mutated_risk["risk_level"] = "critical"
        mutated_risk["final_risk_score"] = max(float(mutated_risk.get("final_risk_score", 0.0) or 0.0), 90.0)
        mutated_risk["risk_score"] = mutated_risk["final_risk_score"]
        mutated_risk.setdefault("active_reasons", [])
        if "metan anomalisi tespit edildi" not in mutated_risk["active_reasons"]:
            mutated_risk["active_reasons"].append("metan anomalisi tespit edildi")
        mutated_risk.setdefault("risk_breakdown", {})
        mutated_risk["risk_breakdown"]["scenario_boost"] = 12.0
    if mutated_sensor:
        mutated_sensor["risk_level"] = "critical"
        mutated_sensor["risk_score"] = max(float(mutated_sensor.get("risk_score", 0.0) or 0.0), 91.0)
        mutated_sensor["status"] = "alarm"

    return {
        "scenario_id": "methane_spike",
        "label": "Methane Spike",
        "blocked_segment": None,
        "affected_segment": target_segment_id,
        "segment": _clone_record(mutated_segment) if mutated_segment else None,
        "risk": _clone_record(mutated_risk) if mutated_risk else None,
        "gas_sensor": _clone_record(mutated_sensor) if mutated_sensor else None,
        "message": "Methane spike scenario applied to the highest-risk gas segment.",
    }


def _apply_worker_at_risk(
    workers: list[dict[str, Any]],
    risks: list[dict[str, Any]],
    worker_id: str | None = None,
) -> dict[str, Any]:
    target_worker = _select_worker(workers, worker_id)
    if target_worker:
        target_worker["status"] = "at_risk"
        target_worker.setdefault("scenario_flags", [])
        if "at_risk" not in target_worker["scenario_flags"]:
            target_worker["scenario_flags"].append("at_risk")

    target_segment_id = normalize_segment_id(target_worker.get("current_segment")) if target_worker else None
    target_risk = next((item for item in risks if item.get("segment_id") == target_segment_id), None)
    if target_risk:
        target_risk["risk_level"] = "critical"
        target_risk["final_risk_score"] = max(float(target_risk.get("final_risk_score", 0.0) or 0.0), 85.0)
        target_risk["risk_score"] = target_risk["final_risk_score"]
        target_risk.setdefault("active_reasons", [])
        if "işçi riskli segmentte" not in target_risk["active_reasons"]:
            target_risk["active_reasons"].append("işçi riskli segmentte")

    return {
        "scenario_id": "worker_at_risk",
        "label": "Worker At Risk",
        "blocked_segment": None,
        "worker_id": target_worker.get("worker_id") if target_worker else None,
        "segment_id": target_segment_id,
        "worker": _clone_record(target_worker) if target_worker else None,
        "risk": _clone_record(target_risk) if target_risk else None,
        "message": "Worker marked as at risk and the segment risk boosted.",
    }


def _apply_collapse(workers: list[dict[str, Any]], segments: list[dict[str, Any]], risks: list[dict[str, Any]]) -> dict[str, Any]:
    collapse = get_collapse_result()
    blocked_segment = normalize_segment_id(collapse.get("blocked_segment"))
    affected_workers = []
    for worker in workers:
        if normalize_segment_id(worker.get("current_segment")) == blocked_segment:
            worker["status"] = "trapped"
            worker["scenario_flags"] = ["blocked_segment"]
            affected_workers.append(worker.get("worker_id"))

    segment = next((item for item in segments if item.get("segment_id") == blocked_segment), None)
    if segment:
        segment["status"] = "blocked"
        segment["is_blocked"] = True
    risk = next((item for item in risks if item.get("segment_id") == blocked_segment), None)
    if risk:
        risk["risk_level"] = "critical"
        risk["final_risk_score"] = max(float(risk.get("final_risk_score", 0.0) or 0.0), 90.0)
        risk["risk_score"] = risk["final_risk_score"]
        risk.setdefault("active_reasons", [])
        if "göçük / segment kapalı" not in risk["active_reasons"]:
            risk["active_reasons"].append("göçük / segment kapalı")

    return {
        "scenario_id": "collapse_s004",
        "label": "Collapse S004",
        "blocked_segment": blocked_segment,
        "collapse": collapse,
        "affected_workers": affected_workers,
        "segment": _clone_record(segment) if segment else None,
        "risk": _clone_record(risk) if risk else None,
        "message": "Collapse scenario applied to the blocked segment and impacted workers.",
    }


def build_scenario_state(scenario_id: str, time_step: int = 0, worker_id: str | None = None) -> dict[str, Any]:
    scenario_id = str(scenario_id or "normal")
    segments = _clone_record_list(get_segments())
    graph = get_graph()
    workers = _clone_record_list(get_workers_at_time_step(time_step, fallback="none"))
    gas_sensors = _clone_record_list(get_gas_sensors(time_step, fallback="last_lte"))
    environmental_risk = _clone_record_list(get_environmental_risks(time_step, fallback="last_lte"))
    risks = get_segment_risks(
        time_step=time_step,
        workers_override=workers,
        sensor_fallback="last_lte",
    )
    risks = _clone_record_list(risks)

    scenario_result = {
        "scenario_id": scenario_id,
        "label": scenario_id,
        "blocked_segment": None,
        "message": "Normal state.",
    }

    if scenario_id == "methane_spike":
        scenario_result = _apply_methane_spike(segments, risks, gas_sensors)
    elif scenario_id in {"collapse_s004", "collapse"}:
        scenario_result = _apply_collapse(workers, segments, risks)
        scenario_id = "collapse_s004"
    elif scenario_id == "worker_at_risk":
        scenario_result = _apply_worker_at_risk(workers, risks, worker_id=worker_id)
    elif scenario_id == "show_route":
        route_worker = _select_worker(workers, worker_id)
        route_preview = get_emergency_route(
            start_segment=route_worker.get("current_segment") if route_worker else "S001",
            blocked_segment=None,
            worker_id=route_worker.get("worker_id") if route_worker else None,
            time_step=time_step,
        )
        scenario_result = {
            "scenario_id": "show_route",
            "label": "Show Route",
            "blocked_segment": None,
            "route_preview": route_preview,
            "message": "Route preview mode.",
        }

    enriched_segments = _enrich_segments(segments, risks, workers, gas_sensors)
    trapped = get_trapped_analysis(time_step=time_step, blocked_segment=scenario_result.get("blocked_segment"))
    worker_steps = get_worker_time_steps()
    gas_steps = get_gas_time_steps()

    return {
        "scenario_id": scenario_id,
        "scenario": scenario_result,
        "time_step": time_step,
        "available_time_steps": _source_time_bounds(worker_steps, gas_steps),
        "counts": {
            "segments": len(enriched_segments),
            "graph_nodes": len(graph.get("nodes", [])),
            "graph_edges": len(graph.get("edges", [])),
            "workers": len(workers),
            "gas_sensors": len(gas_sensors),
            "risks": len(risks),
        },
        "risk_summary": _risk_summary(risks),
        "trapped_summary": trapped["summary"],
        "trapped_workers": trapped["trapped_workers"],
        "segments": enriched_segments,
        "graph": graph,
        "workers": workers,
        "gas_sensors": gas_sensors,
        "environmental_risk": environmental_risk,
        "risks": risks,
        "trapped": trapped,
        "source_contract": {
            "segment_source": "haki_lidar",
            "worker_source": "uwb_worker_timeline",
            "gas_source": "methane_sensor_timeline",
            "join_key": "segment_id",
        },
    }


def get_scenario_state(scenario_id: str, time_step: int = 0, worker_id: str | None = None) -> dict[str, Any]:
    return build_scenario_state(scenario_id, time_step=time_step, worker_id=worker_id)


def get_integration_status(time_step: int = 0, scenario_id: str | None = None, worker_id: str | None = None) -> dict[str, Any]:
    state = get_scenario_state(scenario_id, time_step=time_step, worker_id=worker_id) if scenario_id else get_simulation_state(time_step)
    worker_steps = get_worker_time_steps()
    gas_steps = get_gas_time_steps()
    shared_steps = sorted(set(worker_steps) & set(gas_steps))

    segments = state.get("segments", [])
    workers = state.get("workers", [])
    gas_sensors = state.get("gas_sensors", [])
    risks = state.get("risks", [])

    checks = {
        "segment_contract_ok": all(str(segment.get("segment_id", "")).startswith("S") for segment in segments),
        "worker_contract_ok": all(worker.get("current_segment") for worker in workers),
        "gas_contract_ok": all(sensor.get("segment_id") for sensor in gas_sensors),
        "risk_contract_ok": all("risk_breakdown" in risk for risk in risks),
        "join_key_contract_ok": state.get("source_contract", {}).get("join_key") == "segment_id",
        "time_step_contract_ok": state.get("time_step") == time_step,
    }

    warnings = []
    if not shared_steps:
        warnings.append("No shared worker/gas time steps available.")
    if not checks["segment_contract_ok"]:
        warnings.append("One or more segments do not use the canonical SXXX prefix.")
    if not checks["join_key_contract_ok"]:
        warnings.append("Source contract join key drift detected.")

    return {
        "time_step": time_step,
        "scenario_id": scenario_id or "normal",
        "shared_time_steps": {
            "count": len(shared_steps),
            "min": shared_steps[0] if shared_steps else None,
            "max": shared_steps[-1] if shared_steps else None,
            "sample": shared_steps[:5],
        },
        "source_contract": state.get("source_contract", {}),
        "counts": state.get("counts", {}),
        "checks": {
            **checks,
            "all_passed": all(checks.values()),
        },
        "warnings": warnings,
        "scenario": state.get("scenario"),
        "trapped_summary": state.get("trapped_summary"),
        "risk_summary": state.get("risk_summary"),
    }


def get_trapped_analysis(time_step: int = 0, blocked_segment: str | None = None) -> dict[str, Any]:
    collapse = get_collapse_result()
    scenario_blocked_segment = normalize_segment_id(blocked_segment or collapse.get("blocked_segment"))
    workers = get_workers_at_time_step(time_step, fallback="none")

    worker_records = []
    for worker in workers:
        worker_id = worker.get("worker_id")
        route = get_emergency_route(
            start_segment=worker.get("current_segment"),
            blocked_segment=scenario_blocked_segment,
            worker_id=worker_id,
            time_step=time_step,
        )
        trapped = bool(route.get("trapped"))
        worker_records.append(
            {
                "worker_id": worker_id,
                "tag_id": worker.get("tag_id"),
                "time_step": time_step,
                "current_segment": worker.get("current_segment"),
                "blocked_segment": scenario_blocked_segment,
                "trapped": trapped,
                "trapped_reason": route.get("reason"),
                "emergency_status": route.get("emergency_status"),
                "exit_reachable": route.get("exit_reachable", route.get("reachable", False)),
                "alternative_route_available": route.get("alternative_route_available", False),
                "route_segments": route.get("route_segments", []),
                "route_nodes": route.get("route_nodes", []),
                "total_cost": route.get("total_cost"),
                "message": route.get("message"),
                "tracking_status": worker.get("tracking_status"),
                "position_reliability": worker.get("position_reliability"),
            }
        )

    return {
        "time_step": time_step,
        "blocked_segment": scenario_blocked_segment,
        "scenario": collapse,
        "summary": _trapped_summary(worker_records),
        "workers": worker_records,
        "trapped_workers": [item for item in worker_records if item.get("trapped")],
    }


def get_simulation_state(time_step: int = 0) -> dict[str, Any]:
    segments = get_segments()
    graph = get_graph()
    workers = get_workers_at_time_step(time_step, fallback="none")
    gas_sensors = get_gas_sensors(time_step, fallback="last_lte")
    environmental_risk = get_environmental_risks(time_step, fallback="last_lte")
    risks = get_segment_risks(
        time_step=time_step,
        workers_override=workers,
        sensor_fallback="last_lte",
    )
    enriched_segments = _enrich_segments(segments, risks, workers, gas_sensors)
    trapped = get_trapped_analysis(time_step=time_step)

    worker_steps = get_worker_time_steps()
    gas_steps = get_gas_time_steps()

    return {
        "time_step": time_step,
        "available_time_steps": _source_time_bounds(worker_steps, gas_steps),
        "counts": {
            "segments": len(enriched_segments),
            "graph_nodes": len(graph.get("nodes", [])),
            "graph_edges": len(graph.get("edges", [])),
            "workers": len(workers),
            "gas_sensors": len(gas_sensors),
            "risks": len(risks),
        },
        "risk_summary": _risk_summary(risks),
        "trapped_summary": trapped["summary"],
        "trapped_workers": trapped["trapped_workers"],
        "segments": enriched_segments,
        "graph": graph,
        "workers": workers,
        "gas_sensors": gas_sensors,
        "environmental_risk": environmental_risk,
        "risks": risks,
        "trapped": trapped,
        "source_contract": {
            "segment_source": "haki_lidar",
            "worker_source": "uwb_worker_timeline",
            "gas_source": "methane_sensor_timeline",
            "join_key": "segment_id",
        },
    }
