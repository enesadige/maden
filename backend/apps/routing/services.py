from __future__ import annotations

from collections import defaultdict
from typing import Any
import heapq
import math

from apps.common.ids import normalize_segment_id
from apps.lidar.services import get_graph, get_segments
from apps.risk.services import risk_by_segment
from apps.workers.services import get_workers


def _segment_traversal_cost(segment_id: str, risks: dict[str, dict[str, Any]]) -> float:
    risk = risks.get(segment_id, {})
    geometry_risk = float(risk.get("geometry_risk", 0.0) or 0.0)
    environmental_risk = float(risk.get("environmental_risk", 0.0) or 0.0)
    worker_risk = float(risk.get("worker_exposure_risk", 0.0) or 0.0)
    tracking_risk = float(risk.get("tracking_risk_score", 0.0) or 0.0)
    occupied_workers = len(risk.get("active_worker_ids", []) or [])
    risk_level = str(risk.get("risk_level") or "low").lower()

    cost = (
        geometry_risk * 0.15
        + environmental_risk * 0.45
        + worker_risk * 0.12
        + tracking_risk * 0.05
    )
    if occupied_workers > 0:
        cost += 8.0 + ((occupied_workers - 1) * 4.0)
    if risk_level == "critical":
        cost += 60.0
    elif risk_level == "high":
        cost += 25.0
    elif risk_level == "medium":
        cost += 8.0
    return cost


def _edge_weight(source_segment: str, target_segment: str, graph_edge: dict[str, Any], risks: dict[str, dict[str, Any]]) -> float:
    base = float(graph_edge.get("weight", graph_edge.get("length", 1.0)) or 1.0)
    source_cost = _segment_traversal_cost(source_segment, risks)
    target_cost = _segment_traversal_cost(target_segment, risks)
    return base + ((source_cost + target_cost) / 2.0)


def _build_adjacency(blocked_segment: str | None, risks: dict[str, dict[str, Any]]):
    adjacency = defaultdict(list)
    graph = get_graph()
    segment_lookup = {segment["segment_id"]: segment for segment in get_segments()}
    for edge in graph.get("edges", []):
        left = normalize_segment_id(edge.get("source") or edge.get("from_segment") or edge.get("from_node"))
        right = normalize_segment_id(edge.get("target") or edge.get("to_segment") or edge.get("to_node"))
        if not left or not right:
            continue
        if blocked_segment and (left == blocked_segment or right == blocked_segment):
            continue
        weight = _edge_weight(left, right, edge, risks)
        adjacency[left].append((right, weight, right))
        adjacency[right].append((left, weight, left))
    return adjacency, segment_lookup


def _shortest_path(start_node: str, exit_node: str, adjacency):
    queue = [(0.0, start_node, [], [start_node])]
    best = {start_node: 0.0}

    while queue:
        cost, node, segment_path, node_path = heapq.heappop(queue)
        if node == exit_node:
            return cost, segment_path, node_path
        if cost > best.get(node, math.inf):
            continue
        for next_node, weight, segment_id in adjacency.get(node, []):
            next_cost = cost + weight
            if next_cost >= best.get(next_node, math.inf):
                continue
            best[next_node] = next_cost
            heapq.heappush(
                queue,
                (next_cost, next_node, segment_path + [segment_id], node_path + [next_node]),
            )
    return math.inf, [], []


def get_emergency_route(
    start_segment: str,
    exit_node: str = "3",
    blocked_segment: str | None = None,
    worker_id: str | None = None,
    time_step: int | None = 0,
) -> dict[str, Any]:
    start_segment = normalize_segment_id(start_segment)
    blocked_segment = normalize_segment_id(blocked_segment) if blocked_segment else None
    risks = risk_by_segment(time_step)
    workers = [item for item in get_workers(time_step) if item.get("worker_id") != worker_id]

    adjacency, segment_lookup = _build_adjacency(blocked_segment, risks)
    start = segment_lookup.get(start_segment)
    if not start:
        return {
            "reachable": False,
            "trapped": True,
            "reason": "start_segment_not_found",
            "start_segment": start_segment,
        }

    if blocked_segment == start_segment:
        return {
            "reachable": False,
            "exit_reachable": False,
            "trapped": True,
            "reason": "worker_segment_blocked",
            "start_segment": start_segment,
            "blocked_segment": blocked_segment,
            "exit_node": exit_node,
            "exit_segment": None,
            "route_segments": [],
            "route": [],
            "route_nodes": [],
            "alternative_route_available": False,
            "emergency_status": "WORKER_TRAPPED",
            "message": "Worker segment is blocked; no safe route is available.",
        }

    if worker_id:
        worker_segments = sorted({normalize_segment_id(item.get("current_segment")) for item in workers if item.get("current_segment")})
    else:
        worker_segments = sorted({normalize_segment_id(item.get("current_segment")) for item in workers if item.get("current_segment")})

    exit_segment = normalize_segment_id(exit_node)
    exit_segments = [exit_segment] if exit_segment in segment_lookup else []
    if not exit_segments:
        exit_segments = [item["segment_id"] for item in segment_lookup.values() if item.get("is_exit")]
    if not exit_segments:
        exit_segments = [start_segment]

    candidates = [_shortest_path(start_segment, candidate, adjacency) + (candidate,) for candidate in exit_segments]

    cost, route_segments, route_nodes, selected_exit = min(candidates, key=lambda item: item[0])
    if math.isinf(cost):
        return {
            "reachable": False,
            "exit_reachable": False,
            "trapped": True,
            "reason": "no_route_to_exit",
            "start_segment": start_segment,
            "blocked_segment": blocked_segment,
            "exit_node": exit_node,
            "exit_segment": selected_exit,
            "route_segments": [],
            "route": [],
            "route_nodes": [],
            "alternative_route_available": False,
            "emergency_status": "NO_ROUTE_TO_EXIT",
            "message": "No reachable exit segment was found after blockage constraints.",
        }

    route_segments = [start_segment] + route_segments
    worker_overlap_segments = [segment_id for segment_id in route_segments if segment_id in worker_segments and segment_id != start_segment]
    return {
        "reachable": True,
        "exit_reachable": True,
        "trapped": False,
        "reason": "route_found",
        "start_segment": start_segment,
        "blocked_segment": blocked_segment,
        "exit_node": str(exit_node),
        "exit_segment": selected_exit,
        "route_segments": route_segments,
        "route": route_segments,
        "route_nodes": route_nodes,
        "alternative_route_available": True,
        "emergency_status": "ROUTE_AVAILABLE",
        "message": "Risk-aware route to an exit segment is available.",
        "total_cost": round(cost, 3),
        "worker_overlap_segments": worker_overlap_segments,
        "cost_policy": "length + geometry*0.15 + environmental*0.45 + worker*0.12 + tracking*0.05 + occupancy penalty",
    }
