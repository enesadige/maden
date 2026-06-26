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
