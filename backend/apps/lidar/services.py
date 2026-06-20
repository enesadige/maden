from __future__ import annotations

from typing import Any

from apps.common.ids import normalize_record_ids, normalize_segment_id
from apps.common.json_store import load_json


def get_segments() -> list[dict[str, Any]]:
    records = load_json("digital_twin/segments.json", default=[])
    segments = []
    for item in records:
        segment = normalize_record_ids(item)
        segment.setdefault("is_blocked", False)
        segment.setdefault("source", "sample")
        segments.append(segment)
    return segments


def get_graph() -> dict[str, Any]:
    segments = get_segments()
    node_ids = sorted({str(item["from_node"]) for item in segments} | {str(item["to_node"]) for item in segments})
    nodes = [{"node_id": node_id, "is_exit": node_id == "3"} for node_id in node_ids]
    edges = [
        {
            "segment_id": normalize_segment_id(item["segment_id"]),
            "from_node": str(item["from_node"]),
            "to_node": str(item["to_node"]),
            "length": item.get("length", 1.0),
            "is_chokepoint": bool(item.get("is_chokepoint", False)),
        }
        for item in segments
    ]
    return {"nodes": nodes, "edges": edges}
