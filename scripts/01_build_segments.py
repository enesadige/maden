from __future__ import annotations

import csv
from pathlib import Path

from _env import bootstrap

bootstrap()

from madenguard.config import ensure_project_dirs, load_config, project_path
from madenguard.io_utils import write_json


def load_edges(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    ensure_project_dirs()
    config = load_config()
    edge_path = Path(config["paths"]["graph_ex_edgelist"])
    rows = load_edges(edge_path)
    segments = []
    for index, row in enumerate(rows, start=1):
        notes = (row.get("NOTES") or "").strip()
        segment = {
            "segment_id": f"SEG_ {index:03d}".replace(" ", ""),
            "from_node": str(row.get("FROM", "")).strip(),
            "to_node": str(row.get("TO", "")).strip(),
            "length": float(row.get("LENGTH") or 0.0),
            "notes": notes,
            "is_chokepoint": "chokepoint" in notes.lower(),
        }
        segments.append(segment)

    nodes = sorted({s["from_node"] for s in segments} | {s["to_node"] for s in segments}, key=lambda x: (len(x), x))
    anchors = []
    exit_node = str(config["runtime"].get("exit_node", "3"))
    degree: dict[str, int] = {node: 0 for node in nodes}
    for seg in segments:
        degree[seg["from_node"]] += 1
        degree[seg["to_node"]] += 1
    for node in nodes:
        reason = None
        if node == exit_node:
            reason = "exit_node"
        elif degree[node] >= 3:
            reason = "junction"
        if reason:
            anchors.append({"anchor_id": f"ANCHOR_{len(anchors)+1:02d}", "node_id": node, "placement_reason": reason})
    for seg in segments:
        if seg["is_chokepoint"]:
            anchors.append({
                "anchor_id": f"ANCHOR_{len(anchors)+1:02d}",
                "node_id": seg["from_node"],
                "segment_id": seg["segment_id"],
                "placement_reason": "chokepoint_segment",
            })

    write_json(project_path("processed", "features", "segments.json"), segments)
    write_json(project_path("simulation_ready", "segments.json"), segments)
    write_json(project_path("simulation_ready", "uwb_anchors.json"), anchors)
    print(f"Built {len(segments)} segments from {edge_path}")


if __name__ == "__main__":
    main()

