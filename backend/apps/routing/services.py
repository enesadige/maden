from __future__ import annotations

from collections import defaultdict
from typing import Any
import heapq
import math

from apps.common.ids import normalize_segment_id
from apps.lidar.services import get_segments
from apps.risk.services import risk_by_segment


def _edge_weight(segment: dict[str, Any], risks: dict[str, dict[str, Any]]) -> float:
    base = float(segment.get("length") or 1.0)
    risk = float(risks.get(segment["segment_id"], {}).get("final_risk_score") or 0.0)
    return base + (risk * 0.20)


def _build_adjacency(blocked_segment: str | None, risks: dict[str, dict[str, Any]]):
    adjacency = defaultdict(list)
    segment_lookup = {}
    for segment in get_segments():
        segment_id = normalize_segment_id(segment["segment_id"])
        segment["segment_id"] = segment_id
        segment_lookup[segment_id] = segment
        if blocked_segment and segment_id == blocked_segment:
            continue
        left = str(segment["from_node"])
        right = str(segment["to_node"])
        weight = _edge_weight(segment, risks)
        adjacency[left].append((right, weight, segment_id))
        adjacency[right].append((left, weight, segment_id))
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
    time_step: int | None = 0,
) -> dict[str, Any]:
    start_segment = normalize_segment_id(start_segment)
    blocked_segment = normalize_segment_id(blocked_segment) if blocked_segment else None
    risks = risk_by_segment(time_step)

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
            "trapped": True,
            "reason": "worker_segment_blocked",
            "start_segment": start_segment,
            "blocked_segment": blocked_segment,
            "exit_node": exit_node,
            "route_segments": [],
            "route_nodes": [],
        }

    candidates = []
    for node in (str(start["from_node"]), str(start["to_node"])):
        candidates.append(_shortest_path(node, str(exit_node), adjacency))

    cost, route_segments, route_nodes = min(candidates, key=lambda item: item[0])
    if math.isinf(cost):
        return {
            "reachable": False,
            "trapped": True,
            "reason": "no_route_to_exit",
            "start_segment": start_segment,
            "blocked_segment": blocked_segment,
            "exit_node": exit_node,
            "route_segments": [],
            "route_nodes": [],
        }

    return {
        "reachable": True,
        "trapped": False,
        "reason": "route_found",
        "start_segment": start_segment,
        "blocked_segment": blocked_segment,
        "exit_node": str(exit_node),
        "route_segments": route_segments,
        "route_nodes": route_nodes,
        "total_cost": round(cost, 3),
        "cost_policy": "length + final_risk_score * 0.20",
    }
