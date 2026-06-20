from __future__ import annotations

from _env import bootstrap

bootstrap()

from madenguard.config import ensure_project_dirs, load_config, project_path
from madenguard.graph_utils import adjacency_from_segments, reachable_nodes
from madenguard.io_utils import normalize, read_json, write_csv, write_json


def risk_level(score: float) -> str:
    if score >= 80:
        return "CRITICAL"
    if score >= 60:
        return "HIGH"
    if score >= 30:
        return "MEDIUM"
    return "LOW"


def main() -> None:
    ensure_project_dirs()
    config = load_config()
    exit_node = str(config["runtime"].get("exit_node", "3"))
    segments = read_json(project_path("processed", "features", "segments.json"))
    nodes = sorted({str(seg["from_node"]) for seg in segments} | {str(seg["to_node"]) for seg in segments})
    lengths = [float(seg.get("length", 0.0) or 0.0) for seg in segments]
    min_len, max_len = min(lengths or [0.0]), max(lengths or [1.0])
    rows = []
    for seg in segments:
        graph = adjacency_from_segments(segments, blocked_segment_id=seg["segment_id"])
        reachable = reachable_nodes(graph, exit_node)
        disconnected = len(set(nodes) - reachable)
        graph_blocking_score = disconnected / max(1, len(nodes)) * 100.0
        chokepoint_score = 100.0 if seg.get("is_chokepoint") else 0.0
        length_score = normalize(float(seg.get("length", 0.0) or 0.0), min_len, max_len)
        score = 0.60 * graph_blocking_score + 0.25 * chokepoint_score + 0.15 * length_score
        rows.append({
            "segment_id": seg["segment_id"],
            "from_node": seg["from_node"],
            "to_node": seg["to_node"],
            "length": seg["length"],
            "is_chokepoint": seg["is_chokepoint"],
            "disconnected_node_count": disconnected,
            "total_node_count": len(nodes),
            "graph_blocking_score": round(graph_blocking_score, 3),
            "chokepoint_score": round(chokepoint_score, 3),
            "length_score": round(length_score, 3),
            "graph_risk_score": round(score, 3),
            "risk_level": risk_level(score),
        })

    write_csv(project_path("processed", "features", "graph_risk_scores.csv"), rows)
    write_json(project_path("processed", "features", "graph_risk_scores.json"), rows)
    write_json(project_path("simulation_ready", "graph_risk_scores.json"), rows)

    top = sorted(rows, key=lambda item: item["graph_risk_score"], reverse=True)[:10]
    report = ["# Graph Risk Analysis", "", f"- Exit node: `{exit_node}`", f"- Segments: {len(segments)}", f"- Nodes: {len(nodes)}", "", "## Top Graph Risk Segments"]
    for item in top:
        report.append(
            f"- {item['segment_id']} ({item['from_node']}->{item['to_node']}): risk={item['graph_risk_score']}, "
            f"disconnected={item['disconnected_node_count']}, chokepoint={item['is_chokepoint']}, length={item['length']}"
        )
    project_path("reports", "graph_risk_analysis.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"Computed graph risk for {len(rows)} segments")


if __name__ == "__main__":
    main()

