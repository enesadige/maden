"""
Colab LiDAR pipeline template for MadenGuard AI.

Purpose:
    LAS / chunked LAS files
    -> chunked point reading
    -> downsampled PLY
    -> X-Y grid segments
    -> geometry risk
    -> mine graph JSON

Important:
    Do not use laspy.read() for large files. This script reads LAS data in chunks.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

import laspy
import networkx as nx
import numpy as np


# In Colab, change BASE_DIR to your mounted Drive project directory.
BASE_DIR = Path("/content/drive/MyDrive/MadenGuardAI")

# Default input is the single MediumRes LAS file uploaded to Google Drive.
SINGLE_LAS_PATH = BASE_DIR / "data_raw" / "subt_las" / "Tunnel_Circuit_MediumRes_Scan_EX_Frame.las"

# Alternative: set SINGLE_LAS_PATH = None and provide a folder of LAS chunks.
INPUT_DIR = None

OUTPUT_DIR = BASE_DIR / "backend" / "data_processed"
POINTCLOUD_DIR = OUTPUT_DIR / "pointcloud"
SEGMENT_DIR = OUTPUT_DIR / "segments"
GRAPH_DIR = OUTPUT_DIR / "graph"
RISK_DIR = OUTPUT_DIR / "risk"
SUMMARY_DIR = BASE_DIR / "outputs"

CHUNK_SIZE = 500_000
QUALITY_LEVELS = {
    "preview_500k": 500_000,
    "frontend_1m": 1_000_000,
}
PLY_OUTPUT_FILENAMES = {
    "preview_500k": "tunnel_preview_500k.ply",
    "frontend_1m": "tunnel_downsampled.ply",
}
GRID_SIZE_METERS = 25.0
NARROW_PASSAGE_WIDTH_M = 8.0


@dataclass
class Bounds:
    min_x: float = math.inf
    max_x: float = -math.inf
    min_y: float = math.inf
    max_y: float = -math.inf
    min_z: float = math.inf
    max_z: float = -math.inf
    point_count: int = 0

    def update(self, x: np.ndarray, y: np.ndarray, z: np.ndarray) -> None:
        if x.size == 0:
            return
        self.min_x = min(self.min_x, float(np.min(x)))
        self.max_x = max(self.max_x, float(np.max(x)))
        self.min_y = min(self.min_y, float(np.min(y)))
        self.max_y = max(self.max_y, float(np.max(y)))
        self.min_z = min(self.min_z, float(np.min(z)))
        self.max_z = max(self.max_z, float(np.max(z)))
        self.point_count += int(x.size)


@dataclass
class SegmentStats:
    segment_id: str
    grid_x: int
    grid_y: int
    min_x: float
    max_x: float
    min_y: float
    max_y: float
    min_z: float
    max_z: float
    center_x: float
    center_y: float
    center_z: float
    point_count: int
    density: float
    height_range: float


def iter_las_paths(input_dir: Path) -> list[Path]:
    if SINGLE_LAS_PATH is not None:
        if not SINGLE_LAS_PATH.exists():
            raise FileNotFoundError(f"Single LAS file not found: {SINGLE_LAS_PATH}")
        return [SINGLE_LAS_PATH]

    if input_dir is None:
        raise ValueError("Set SINGLE_LAS_PATH or INPUT_DIR before running the pipeline.")

    paths = sorted(input_dir.glob("*.las"))
    if not paths:
        raise FileNotFoundError(f"No LAS files found under {input_dir}")
    return paths


def iter_las_chunks(paths: Iterable[Path], chunk_size: int = CHUNK_SIZE):
    for path in paths:
        with laspy.open(path) as reader:
            for points in reader.chunk_iterator(chunk_size):
                yield path, points


def compute_bounds(paths: list[Path]) -> Bounds:
    bounds = Bounds()
    for _, points in iter_las_chunks(paths):
        bounds.update(np.asarray(points.x), np.asarray(points.y), np.asarray(points.z))
    return bounds


def compute_sample_stride(total_points: int, target_points: int) -> int:
    if target_points <= 0:
        raise ValueError("target_points must be positive")
    return max(1, math.ceil(total_points / target_points))


def collect_downsample(paths: list[Path], origin: dict[str, float], stride: int) -> np.ndarray:
    samples: list[np.ndarray] = []
    global_index = 0

    for _, points in iter_las_chunks(paths):
        x = np.asarray(points.x)
        y = np.asarray(points.y)
        z = np.asarray(points.z)
        n = x.size

        first = (-global_index) % stride
        if first < n:
            xyz = np.column_stack(
                [
                    x[first::stride] - origin["x"],
                    y[first::stride] - origin["y"],
                    z[first::stride] - origin["z"],
                ]
            ).astype(np.float32)
            samples.append(xyz)

        global_index += n

    if not samples:
        return np.empty((0, 3), dtype=np.float32)
    return np.vstack(samples)


def write_ascii_ply(path: Path, points: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii") as f:
        f.write("ply\n")
        f.write("format ascii 1.0\n")
        f.write(f"element vertex {len(points)}\n")
        f.write("property float x\n")
        f.write("property float y\n")
        f.write("property float z\n")
        f.write("end_header\n")
        np.savetxt(f, points, fmt="%.4f %.4f %.4f")


def build_xy_segments(paths: list[Path], origin: dict[str, float]) -> dict[tuple[int, int], dict[str, float]]:
    segments: dict[tuple[int, int], dict[str, float]] = {}

    for _, points in iter_las_chunks(paths):
        x = np.asarray(points.x) - origin["x"]
        y = np.asarray(points.y) - origin["y"]
        z = np.asarray(points.z) - origin["z"]

        gx = np.floor(x / GRID_SIZE_METERS).astype(np.int64)
        gy = np.floor(y / GRID_SIZE_METERS).astype(np.int64)

        for key in np.unique(np.column_stack([gx, gy]), axis=0):
            ix, iy = int(key[0]), int(key[1])
            mask = (gx == ix) & (gy == iy)
            xs = x[mask]
            ys = y[mask]
            zs = z[mask]

            seg = segments.setdefault(
                (ix, iy),
                {
                    "point_count": 0,
                    "min_x": math.inf,
                    "max_x": -math.inf,
                    "min_y": math.inf,
                    "max_y": -math.inf,
                    "min_z": math.inf,
                    "max_z": -math.inf,
                },
            )
            seg["point_count"] += int(xs.size)
            seg["min_x"] = min(seg["min_x"], float(np.min(xs)))
            seg["max_x"] = max(seg["max_x"], float(np.max(xs)))
            seg["min_y"] = min(seg["min_y"], float(np.min(ys)))
            seg["max_y"] = max(seg["max_y"], float(np.max(ys)))
            seg["min_z"] = min(seg["min_z"], float(np.min(zs)))
            seg["max_z"] = max(seg["max_z"], float(np.max(zs)))

    return segments


def finalize_segments(raw_segments: dict[tuple[int, int], dict[str, float]]) -> list[SegmentStats]:
    finalized: list[SegmentStats] = []
    area = GRID_SIZE_METERS * GRID_SIZE_METERS

    for index, ((gx, gy), seg) in enumerate(sorted(raw_segments.items()), start=1):
        min_z = seg["min_z"]
        max_z = seg["max_z"]
        center_x = (seg["min_x"] + seg["max_x"]) / 2
        center_y = (seg["min_y"] + seg["max_y"]) / 2
        center_z = (min_z + max_z) / 2
        point_count = int(seg["point_count"])
        finalized.append(
            SegmentStats(
                segment_id=f"S{index:03d}",
                grid_x=gx,
                grid_y=gy,
                min_x=seg["min_x"],
                max_x=seg["max_x"],
                min_y=seg["min_y"],
                max_y=seg["max_y"],
                min_z=min_z,
                max_z=max_z,
                center_x=center_x,
                center_y=center_y,
                center_z=center_z,
                point_count=point_count,
                density=point_count / area,
                height_range=max_z - min_z,
            )
        )

    return finalized


def build_graph_object(segments: list[SegmentStats]) -> nx.Graph:
    by_grid = {(s.grid_x, s.grid_y): s for s in segments}
    graph = nx.Graph()

    for segment in segments:
        graph.add_node(
            segment.segment_id,
            center=[segment.center_x, segment.center_y, segment.center_z],
            grid=[segment.grid_x, segment.grid_y],
            point_count=segment.point_count,
        )

    for segment in segments:
        for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
            neighbor = by_grid.get((segment.grid_x + dx, segment.grid_y + dy))
            if not neighbor:
                continue
            distance = math.dist(
                [segment.center_x, segment.center_y, segment.center_z],
                [neighbor.center_x, neighbor.center_y, neighbor.center_z],
            )
            graph.add_edge(segment.segment_id, neighbor.segment_id, weight=round(distance, 3))

    return graph


def risk_level(score: int) -> str:
    if score >= 85:
        return "critical"
    if score >= 65:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def graph_exit_distances(graph: nx.Graph) -> tuple[dict[str, float], float]:
    exit_nodes = [node for node in graph.nodes if graph.degree(node) <= 1]
    if not exit_nodes:
        return {}, 0.0

    distances = nx.multi_source_dijkstra_path_length(graph, exit_nodes, weight="weight")
    max_distance = max(distances.values(), default=0.0)
    return distances, max_distance


def graph_cycle_nodes(graph: nx.Graph) -> set[str]:
    nodes: set[str] = set()
    for cycle in nx.cycle_basis(graph):
        nodes.update(cycle)
    return nodes


def geometry_risk_scores(segments: list[SegmentStats], graph: nx.Graph) -> list[dict]:
    density_max = max((segment.density for segment in segments), default=1.0)
    exit_distances, max_exit_distance = graph_exit_distances(graph)
    articulation_nodes = set(nx.articulation_points(graph)) if graph.number_of_nodes() else set()
    cycle_nodes = graph_cycle_nodes(graph)
    risks: list[dict] = []

    for segment in segments:
        degree = graph.degree(segment.segment_id)
        x_span = segment.max_x - segment.min_x
        y_span = segment.max_y - segment.min_y
        width_m = min(x_span, y_span)
        length_m = max(x_span, y_span)

        narrow_passage_risk = 1.0 - min(1.0, width_m / NARROW_PASSAGE_WIDTH_M) if width_m > 0 else 1.0
        distance = exit_distances.get(segment.segment_id)
        exit_distance_risk = (distance / max_exit_distance) if distance is not None and max_exit_distance > 0 else 0.5
        single_connection_risk = 1.0 if degree <= 1 else 0.0
        limited_alternative_route_risk = 1.0 if segment.segment_id not in cycle_nodes and degree <= 2 else 0.0
        critical_passage_risk = 1.0 if segment.segment_id in articulation_nodes else 0.0
        sparse_geometry_risk = 1.0 - min(1.0, segment.density / density_max) if density_max > 0 else 1.0

        weighted = (
            0.20 * narrow_passage_risk
            + 0.20 * exit_distance_risk
            + 0.15 * single_connection_risk
            + 0.20 * limited_alternative_route_risk
            + 0.20 * critical_passage_risk
            + 0.05 * sparse_geometry_risk
        )
        score = int(round(100 * weighted))

        reasons: list[str] = []
        if narrow_passage_risk >= 0.55:
            reasons.append("Dar gecit olasiligi yuksek")
        elif narrow_passage_risk >= 0.25:
            reasons.append("Gecit genisligi sinirli")
        if exit_distance_risk >= 0.65:
            reasons.append("Cikisa uzak bolge")
        if single_connection_risk == 1.0:
            reasons.append("Tek baglantili segment")
        elif limited_alternative_route_risk == 1.0:
            reasons.append("Alternatif rotasi az olan segment")
        if critical_passage_risk == 1.0:
            reasons.append("Gocuk senaryosunda kritik gecis noktasi")
        if sparse_geometry_risk >= 0.60:
            reasons.append("Nokta yogunlugu dusuk / seyrek geometri")
        if not reasons:
            reasons.append("Geometri ve baglanti acisindan dusuk risk")

        risks.append(
            {
                "segment_id": segment.segment_id,
                "geometry_risk": score,
                "risk_level": risk_level(score),
                "reasons": reasons,
                "components": {
                    "narrow_passage_risk": round(float(narrow_passage_risk), 4),
                    "exit_distance_risk": round(float(exit_distance_risk), 4),
                    "single_connection_risk": round(float(single_connection_risk), 4),
                    "limited_alternative_route_risk": round(float(limited_alternative_route_risk), 4),
                    "critical_passage_risk": round(float(critical_passage_risk), 4),
                    "sparse_geometry_risk": round(float(sparse_geometry_risk), 4),
                },
                "metrics": {
                    "degree": int(degree),
                    "length_m": round(float(length_m), 3),
                    "width_m": round(float(width_m), 3),
                    "height_m": round(float(segment.height_range), 3),
                    "distance_to_nearest_exit_m": round(float(distance), 3) if distance is not None else None,
                    "point_density": round(float(segment.density), 4),
                },
            }
        )

    return risks


def serialize_graph(graph: nx.Graph) -> dict:
    return {
        "nodes": [
            {"id": node, **attrs}
            for node, attrs in graph.nodes(data=True)
        ],
        "edges": [
            {"source": u, "target": v, **attrs}
            for u, v, attrs in graph.edges(data=True)
        ],
    }


def approximate_main_path(graph: nx.Graph) -> set[str]:
    if graph.number_of_nodes() == 0:
        return set()

    largest_component = max(nx.connected_components(graph), key=len)
    subgraph = graph.subgraph(largest_component)
    candidates = [node for node in subgraph.nodes if subgraph.degree(node) <= 1]
    if not candidates:
        candidates = list(subgraph.nodes)

    start = candidates[0]
    lengths = nx.single_source_dijkstra_path_length(subgraph, start, weight="weight")
    farthest = max(lengths, key=lengths.get)
    lengths = nx.single_source_dijkstra_path_length(subgraph, farthest, weight="weight")
    other = max(lengths, key=lengths.get)
    return set(nx.shortest_path(subgraph, farthest, other, weight="weight"))


def semantic_segments(
    segments: list[SegmentStats],
    graph: nx.Graph,
    geometry_risks: list[dict],
) -> list[dict]:
    risk_by_id = {item["segment_id"]: item for item in geometry_risks}
    main_path = approximate_main_path(graph)
    semantic: list[dict] = []

    for segment in segments:
        risk_item = risk_by_id[segment.segment_id]
        risk_value = risk_item["geometry_risk"]
        neighbors = sorted(graph.neighbors(segment.segment_id))
        degree = len(neighbors)
        is_exit_candidate = degree <= 1
        is_risky = risk_value >= 65

        if is_exit_candidate:
            segment_type = "exit_point"
            role = "exit_or_dead_end_candidate"
        elif segment.segment_id in main_path:
            segment_type = "main_tunnel"
            role = "main_route"
        elif degree >= 3:
            segment_type = "junction"
            role = "gallery_connection"
        else:
            segment_type = "side_gallery"
            role = "secondary_route"

        length_m = max(segment.max_x - segment.min_x, segment.max_y - segment.min_y)
        semantic.append(
            {
                "segment_id": segment.segment_id,
                "name": f"{segment_type.replace('_', ' ').title()} {segment.segment_id}",
                "type": segment_type,
                "role": role,
                "center": [
                    round(segment.center_x, 3),
                    round(segment.center_y, 3),
                    round(segment.center_z, 3),
                ],
                "length_m": round(float(length_m), 3),
                "connected_segments": neighbors,
                "approx_position": {
                    "grid_x": segment.grid_x,
                    "grid_y": segment.grid_y,
                },
                "bounds": {
                    "min_x": round(segment.min_x, 3),
                    "max_x": round(segment.max_x, 3),
                    "min_y": round(segment.min_y, 3),
                    "max_y": round(segment.max_y, 3),
                    "min_z": round(segment.min_z, 3),
                    "max_z": round(segment.max_z, 3),
                },
                "point_count": segment.point_count,
                "density": round(float(segment.density), 4),
                "height_range": round(float(segment.height_range), 4),
                "geometry_risk": risk_value,
                "is_risky": is_risky,
                "is_exit_candidate": is_exit_candidate,
                "classification_source": "auto_xy_grid_graph",
            }
        )

    return semantic


def build_segment_metadata(map_segments: list[dict]) -> list[dict]:
    metadata: list[dict] = []

    for segment in map_segments:
        bounds = segment["bounds"]
        x_span = bounds["max_x"] - bounds["min_x"]
        y_span = bounds["max_y"] - bounds["min_y"]
        length_m = max(x_span, y_span)
        width_m = min(x_span, y_span)
        height_m = bounds["max_z"] - bounds["min_z"]

        metadata.append(
            {
                "segment_id": segment["segment_id"],
                "segment_name": segment["name"],
                "segment_type": segment["type"],
                "center_position": segment["center"],
                "length_m": round(float(length_m), 3),
                "width_m": round(float(width_m), 3),
                "height_m": round(float(height_m), 3),
                "connected_segments": segment["connected_segments"],
                "is_exit": bool(segment["is_exit_candidate"]),
                "is_blocked": False,
                "base_geometry_risk": segment["geometry_risk"],
            }
        )

    return metadata


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main() -> None:
    POINTCLOUD_DIR.mkdir(parents=True, exist_ok=True)
    SEGMENT_DIR.mkdir(parents=True, exist_ok=True)
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    RISK_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)

    paths = iter_las_paths(INPUT_DIR)
    print(f"LAS files: {len(paths)}")

    bounds = compute_bounds(paths)
    origin = {
        "x": (bounds.min_x + bounds.max_x) / 2,
        "y": (bounds.min_y + bounds.max_y) / 2,
        "z": (bounds.min_z + bounds.max_z) / 2,
    }
    save_json(POINTCLOUD_DIR / "global_shift.json", {"origin": origin, "bounds": asdict(bounds)})

    ply_outputs = {}
    for quality_name, target_points in QUALITY_LEVELS.items():
        stride = compute_sample_stride(bounds.point_count, target_points)
        print(f"{quality_name}: total={bounds.point_count:,}; target={target_points:,}; stride={stride}")
        sampled_points = collect_downsample(paths, origin, stride)
        output_path = POINTCLOUD_DIR / PLY_OUTPUT_FILENAMES[quality_name]
        write_ascii_ply(output_path, sampled_points)
        ply_outputs[quality_name] = {
            "target_points": target_points,
            "actual_points": int(len(sampled_points)),
            "stride": stride,
            "output_path": str(output_path),
        }
        print(f"{quality_name} PLY points: {len(sampled_points):,}")

    raw_segments = build_xy_segments(paths, origin)
    segments = finalize_segments(raw_segments)
    graph = build_graph_object(segments)
    graph_json = serialize_graph(graph)
    geometry_risks = geometry_risk_scores(segments, graph)
    map_segments = semantic_segments(segments, graph, geometry_risks)
    segment_metadata = build_segment_metadata(map_segments)

    save_json(SEGMENT_DIR / "map_segments.json", map_segments)
    save_json(SEGMENT_DIR / "segment_metadata.json", segment_metadata)
    save_json(RISK_DIR / "geometry_risk.json", geometry_risks)
    save_json(GRAPH_DIR / "mine_graph.json", graph_json)

    summary = {
        "input_files": [str(p) for p in paths],
        "total_points_processed": bounds.point_count,
        "quality_levels": ply_outputs,
        "grid_size_meters": GRID_SIZE_METERS,
        "segment_count": len(segments),
        "graph_node_count": len(graph_json["nodes"]),
        "graph_edge_count": len(graph_json["edges"]),
        "outputs": {
            "preview_500k_ply": str(POINTCLOUD_DIR / "tunnel_preview_500k.ply"),
            "downsampled_ply": str(POINTCLOUD_DIR / "tunnel_downsampled.ply"),
            "global_shift": str(POINTCLOUD_DIR / "global_shift.json"),
            "map_segments": str(SEGMENT_DIR / "map_segments.json"),
            "segment_metadata": str(SEGMENT_DIR / "segment_metadata.json"),
            "geometry_risk": str(RISK_DIR / "geometry_risk.json"),
            "mine_graph": str(GRAPH_DIR / "mine_graph.json"),
        },
    }
    save_json(SUMMARY_DIR / "digital_twin_lidar_pipeline_summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
