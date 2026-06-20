from __future__ import annotations

from collections import deque
from typing import Any


def adjacency_from_segments(segments: list[dict[str, Any]], blocked_segment_id: str | None = None) -> dict[str, list[tuple[str, str, float]]]:
    graph: dict[str, list[tuple[str, str, float]]] = {}
    for seg in segments:
        if blocked_segment_id and seg["segment_id"] == blocked_segment_id:
            continue
        a = str(seg["from_node"])
        b = str(seg["to_node"])
        length = float(seg.get("length", 1.0) or 1.0)
        graph.setdefault(a, []).append((b, seg["segment_id"], length))
        graph.setdefault(b, []).append((a, seg["segment_id"], length))
    return graph


def reachable_nodes(graph: dict[str, list[tuple[str, str, float]]], start: str) -> set[str]:
    seen = {start}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        for nxt, _, _ in graph.get(node, []):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen


def shortest_path(graph: dict[str, list[tuple[str, str, float]]], start: str, goal: str) -> list[str] | None:
    queue = deque([(start, [start])])
    seen = {start}
    while queue:
        node, path = queue.popleft()
        if node == goal:
            return path
        for nxt, _, _ in graph.get(node, []):
            if nxt not in seen:
                seen.add(nxt)
                queue.append((nxt, path + [nxt]))
    return None


def segment_by_id(segments: list[dict[str, Any]], segment_id: str) -> dict[str, Any] | None:
    for seg in segments:
        if seg["segment_id"] == segment_id:
            return seg
    return None

