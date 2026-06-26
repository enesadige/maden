from __future__ import annotations

from typing import Any

from apps.common.ids import normalize_record_ids, normalize_segment_id
from apps.common.json_store import load_first_json, load_json


HAKI_SEGMENTS = "haki_lidar/segments/map_segments.json"
HAKI_METADATA = "haki_lidar/segments/segment_metadata.json"
HAKI_GRAPH = "haki_lidar/graph/mine_graph.json"
HAKI_GEOMETRY_RISK = "haki_lidar/risk/geometry_risk.json"
LEGACY_SEGMENTS = "digital_twin/segments.json"


def get_segments() -> list[dict[str, Any]]:
    records = load_first_json([HAKI_SEGMENTS, LEGACY_SEGMENTS], default=[])
    metadata = {
        normalize_segment_id(item.get("segment_id")): normalize_record_ids(item)
        for item in load_json(HAKI_METADATA, default=[])
    }
    geometry = {
        normalize_segment_id(item.get("segment_id")): normalize_record_ids(item)
        for item in load_json(HAKI_GEOMETRY_RISK, default=[])
    }
    segments = []
    for item in records:
        segment = normalize_record_ids(item)
        segment_id = segment.get("segment_id")
        meta = metadata.get(segment_id, {})
        geo = geometry.get(segment_id, {})

        center = segment.get("center") or meta.get("center_position") or [0.0, 0.0, 0.0]
        length = segment.get("length_m", segment.get("length", meta.get("length_m", 1.0)))

        segment["center"] = center
        segment["length_m"] = length
        segment["length"] = length
        segment["name"] = segment.get("name") or meta.get("segment_name") or segment_id
        segment["type"] = segment.get("type") or meta.get("segment_type") or "unknown"
        segment["role"] = segment.get("role") or meta.get("role") or "unknown"
        segment["connected_segments"] = [
            normalize_segment_id(connected)
            for connected in segment.get("connected_segments", meta.get("connected_segments", []))
        ]
        segment["is_exit"] = bool(meta.get("is_exit", segment.get("is_exit_candidate", False)))
        segment["is_blocked"] = bool(meta.get("is_blocked", segment.get("is_blocked", False)))
        segment["geometry_risk"] = geo.get("geometry_risk", segment.get("geometry_risk", meta.get("base_geometry_risk", 0.0)))
        segment["risk_level"] = geo.get("risk_level", segment.get("risk_level", "low"))
        segment["risk_reasons"] = geo.get("reasons", [])
        segment["source"] = "haki_lidar" if metadata else "legacy_sample"
        segment.setdefault("is_blocked", False)
        segments.append(segment)
    return segments


def get_graph() -> dict[str, Any]:
    graph = load_json(HAKI_GRAPH, default=None)
    segments = {item["segment_id"]: item for item in get_segments()}

    if graph:
        nodes = []
        for node in graph.get("nodes", []):
            segment_id = normalize_segment_id(node.get("id"))
            segment = segments.get(segment_id, {})
            nodes.append(
                {
                    **node,
                    "id": segment_id,
                    "segment_id": segment_id,
                    "center": node.get("center") or segment.get("center"),
                    "is_exit": bool(segment.get("is_exit", False)),
                    "risk_level": segment.get("risk_level", "low"),
                }
            )

        edges = []
        for index, edge in enumerate(graph.get("edges", []), start=1):
            source = normalize_segment_id(edge.get("source"))
            target = normalize_segment_id(edge.get("target"))
            edges.append(
                {
                    **edge,
                    "edge_id": edge.get("edge_id", f"E{index:03d}"),
                    "source": source,
                    "target": target,
                    "from_segment": source,
                    "to_segment": target,
                    "weight": edge.get("weight", edge.get("length", 1.0)),
                }
            )
        return {"nodes": nodes, "edges": edges}

    legacy_segments = get_segments()
    node_ids = sorted({str(item["from_node"]) for item in legacy_segments} | {str(item["to_node"]) for item in legacy_segments})
    nodes = [{"node_id": node_id, "is_exit": node_id == "3"} for node_id in node_ids]
    edges = [
        {
            "segment_id": normalize_segment_id(item["segment_id"]),
            "from_node": str(item["from_node"]),
            "to_node": str(item["to_node"]),
            "length": item.get("length", 1.0),
            "is_chokepoint": bool(item.get("is_chokepoint", False)),
        }
        for item in legacy_segments
    ]
    return {"nodes": nodes, "edges": edges}


def get_pointcloud_metadata() -> dict[str, Any]:
    return {
        "source": "haki_lidar",
        "preview_url": "/models/tunnel_preview_500k.ply",
        "downsampled_url": "/models/tunnel_downsampled.ply",
        "global_shift": load_json("haki_lidar/pointcloud/global_shift.json", default={}),
        "note": "PLY files are served by the frontend public/models directory in local development.",
    }


def get_geometry_risks() -> list[dict[str, Any]]:
    records = load_json(HAKI_GEOMETRY_RISK, default=[])
    return [normalize_record_ids(item) for item in records]
