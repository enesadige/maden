from __future__ import annotations

import argparse
import csv
import json
import math
import struct
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT / "backend" / "data_processed"
GROUND_TRUTH_ROOT = PROJECT_ROOT / "systems_tunnel_ground_truth-master"

GRID_SIZE_M = 1.0
FLOOR_PERCENTILE = 0.10
FLOOR_BAND_M = 0.75
MIN_CELL_POINTS = 3
MAX_FLOOR_POINTS = 650_000

ARTIFACT_COLORS = {
    "backpack": (252, 211, 77),
    "fire_extinguisher": (248, 113, 113),
    "drill": (96, 165, 250),
    "survivor": (74, 222, 128),
    "cell_phone": (216, 180, 254),
}


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def read_binary_xyz_ply(path: Path):
    with path.open("rb") as handle:
        header_lines = []
        while True:
            line = handle.readline()
            if not line:
                raise ValueError(f"Invalid PLY header: {path}")
            decoded = line.decode("ascii", errors="replace").strip()
            header_lines.append(decoded)
            if decoded == "end_header":
                break

        if "format binary_little_endian 1.0" not in header_lines:
            raise ValueError("Expected binary_little_endian PLY.")

        vertex_count = None
        for line in header_lines:
            if line.startswith("element vertex "):
                vertex_count = int(line.split()[-1])
                break
        if vertex_count is None:
            raise ValueError("PLY vertex count not found.")

        data_offset = handle.tell()

    def iterator():
        with path.open("rb") as reader:
            reader.seek(data_offset)
            unpack = struct.Struct("<fff").unpack
            for _index in range(vertex_count):
                raw = reader.read(12)
                if len(raw) < 12:
                    break
                yield unpack(raw)

    return vertex_count, iterator


def grid_key(x: float, y: float) -> tuple[int, int]:
    return math.floor(x / GRID_SIZE_M), math.floor(y / GRID_SIZE_M)


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values.sort()
    index = int(round((len(values) - 1) * p))
    return values[index]


def compute_floor_cells(points_iter) -> dict[tuple[int, int], dict]:
    z_by_cell: dict[tuple[int, int], list[float]] = {}
    for x, y, z in points_iter():
        key = grid_key(x, y)
        z_by_cell.setdefault(key, []).append(z)

    floor_cells = {}
    for key, z_values in z_by_cell.items():
        if len(z_values) < MIN_CELL_POINTS:
            continue
        floor_z = percentile(z_values, FLOOR_PERCENTILE)
        floor_cells[key] = {
            "floor_z": floor_z,
            "point_count": len(z_values),
            "floor_count": 0,
        }
    return floor_cells


def select_floor_points(points_iter, floor_cells: dict[tuple[int, int], dict]) -> list[tuple[float, float, float, int, int, int]]:
    selected = []
    stride = 1
    accepted_index = 0

    for x, y, z in points_iter():
        key = grid_key(x, y)
        cell = floor_cells.get(key)
        if not cell:
            continue
        floor_z = cell["floor_z"]
        if floor_z - 0.05 <= z <= floor_z + FLOOR_BAND_M:
            cell["floor_count"] += 1
            if accepted_index % stride == 0:
                density = min(1.0, cell["point_count"] / 80.0)
                red = 255
                green = int(150 + 90 * density)
                blue = int(40 + 80 * density)
                selected.append((x, y, z + 0.08, red, green, blue))
                if len(selected) > MAX_FLOOR_POINTS:
                    stride += 1
                    selected = selected[::2]
            accepted_index += 1

    return selected


def write_point_ply(path: Path, points: list[tuple[float, float, float, int, int, int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii", newline="\n") as handle:
        handle.write("ply\n")
        handle.write("format ascii 1.0\n")
        handle.write(f"element vertex {len(points)}\n")
        handle.write("property float x\n")
        handle.write("property float y\n")
        handle.write("property float z\n")
        handle.write("property uchar red\n")
        handle.write("property uchar green\n")
        handle.write("property uchar blue\n")
        handle.write("end_header\n")
        for x, y, z, red, green, blue in points:
            handle.write(f"{x:.4f} {y:.4f} {z:.4f} {red} {green} {blue}\n")


def parse_artifacts_yaml(path: Path) -> list[dict]:
    artifacts = []
    current_type = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("- type:"):
            current_type = line.split(":", 1)[1].strip()
        elif line.startswith("position:") and current_type:
            values = line.split("[", 1)[1].split("]", 1)[0]
            position = [float(value.strip()) for value in values.split(",")]
            artifacts.append({"type": current_type, "position": position})
            current_type = None
    return artifacts


def localize_artifacts(artifacts: list[dict], global_shift: dict) -> list[dict]:
    origin = global_shift["origin"]
    localized = []
    for index, artifact in enumerate(artifacts, start=1):
        x, y, z = artifact["position"]
        local = [x - origin["x"], y - origin["y"], z - origin["z"]]
        localized.append(
            {
                "artifact_id": f"A{index:03d}",
                "type": artifact["type"],
                "position_ex_frame": [round(x, 3), round(y, 3), round(z, 3)],
                "position_local_shifted": [round(local[0], 3), round(local[1], 3), round(local[2], 3)],
            }
        )
    return localized


def marker_points(center: list[float], color: tuple[int, int, int], radius: float = 1.4):
    points = []
    samples = 28
    x, y, z = center
    for axis_pair in [(0, 1), (0, 2), (1, 2)]:
        for i in range(samples):
            angle = 2.0 * math.pi * i / samples
            coords = [x, y, z + 0.35]
            coords[axis_pair[0]] += math.cos(angle) * radius
            coords[axis_pair[1]] += math.sin(angle) * radius
            points.append((coords[0], coords[1], coords[2], *color))
    return points


def write_artifact_marker_ply(path: Path, artifacts: list[dict]) -> int:
    points = []
    for artifact in artifacts:
        color = ARTIFACT_COLORS.get(artifact["type"], (255, 255, 255))
        points.extend(marker_points(artifact["position_local_shifted"], color))
    write_point_ply(path, points)
    return len(points)


def read_ex_topology(path: Path) -> dict:
    nodes = set()
    edges = []
    chokepoints = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            source = f"GT{int(row['FROM']):03d}"
            target = f"GT{int(row['TO']):03d}"
            length = float(row["LENGTH"])
            notes = (row.get("NOTES") or "").strip()
            nodes.add(source)
            nodes.add(target)
            edge = {"source": source, "target": target, "length_m": length, "notes": notes}
            edges.append(edge)
            if notes:
                chokepoints.append(edge)
    return {
        "course": "ex",
        "coordinate_status": "topology_only_no_node_coordinates",
        "note": "Use this graph for route logic. Do not draw it directly over LiDAR without manual node coordinate registration.",
        "nodes": [{"id": node} for node in sorted(nodes)],
        "edges": edges,
        "chokepoints": chokepoints,
    }


def write_floor_density_svg(path: Path, floor_cells: dict[tuple[int, int], dict], artifacts: list[dict]) -> None:
    drawable_cells = {
        key: cell for key, cell in floor_cells.items() if cell["floor_count"] >= MIN_CELL_POINTS
    }
    xs = [key[0] * GRID_SIZE_M for key in drawable_cells]
    ys = [key[1] * GRID_SIZE_M for key in drawable_cells]
    for artifact in artifacts:
        xs.append(artifact["position_local_shifted"][0])
        ys.append(artifact["position_local_shifted"][1])

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    width_m = max(max_x - min_x, 1.0)
    height_m = max(max_y - min_y, 1.0)
    padding = 36
    canvas_w = 1400
    canvas_h = max(760, int(canvas_w * height_m / width_m))
    scale = min((canvas_w - 2 * padding) / width_m, (canvas_h - 2 * padding) / height_m)

    def project(x: float, y: float) -> tuple[float, float]:
        return padding + (x - min_x) * scale, canvas_h - padding - (y - min_y) * scale

    max_floor_count = max((cell["floor_count"] for cell in drawable_cells.values()), default=1)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii", newline="\n") as handle:
        handle.write(f'<svg xmlns="http://www.w3.org/2000/svg" width="{canvas_w}" height="{canvas_h}" viewBox="0 0 {canvas_w} {canvas_h}">\n')
        handle.write('<rect width="100%" height="100%" fill="#0f1317"/>\n')
        handle.write('<g opacity="0.85">\n')
        for (gx, gy), cell in drawable_cells.items():
            x, y = project(gx * GRID_SIZE_M, gy * GRID_SIZE_M)
            intensity = min(1.0, cell["floor_count"] / max_floor_count)
            green = int(130 + 100 * intensity)
            size = max(1.2, GRID_SIZE_M * scale)
            handle.write(
                f'<rect x="{x:.2f}" y="{y:.2f}" width="{size:.2f}" height="{size:.2f}" '
                f'fill="rgb(255,{green},45)" opacity="{0.28 + 0.55 * intensity:.3f}"/>\n'
            )
        handle.write("</g>\n")
        for artifact in artifacts:
            x, y = project(artifact["position_local_shifted"][0], artifact["position_local_shifted"][1])
            red, green, blue = ARTIFACT_COLORS.get(artifact["type"], (255, 255, 255))
            handle.write(
                f'<circle cx="{x:.2f}" cy="{y:.2f}" r="5.5" fill="rgb({red},{green},{blue})" '
                'stroke="#0f1317" stroke-width="1.2">\n'
            )
            handle.write(f'<title>{artifact["artifact_id"]} {artifact["type"]}</title></circle>\n')
        handle.write('<g font-family="Arial, sans-serif" fill="#e7edf3">\n')
        handle.write('<text x="24" y="30" font-size="20" font-weight="700">EX LiDAR Floor / Road Visibility Map</text>\n')
        handle.write(f'<text x="24" y="55" font-size="14">Actual floor-like LiDAR points, shifted local frame. Cells: {len(drawable_cells)} | Artifacts: {len(artifacts)}</text>\n')
        handle.write("</g>\n")
        handle.write("</svg>\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate LiDAR-based road visibility layers using EX ground truth references.")
    parser.add_argument("--data-root", type=Path, default=DATA_ROOT)
    parser.add_argument("--ground-truth-root", type=Path, default=GROUND_TRUTH_ROOT)
    parser.add_argument("--artifact-config", choices=["a", "b"], default="a")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data_root = args.data_root
    gt_root = args.ground_truth_root
    viewer_dir = data_root / "viewer_ground_truth"
    source_ply = data_root / "pointcloud" / "tunnel_downsampled.ply"
    global_shift = read_json(data_root / "pointcloud" / "global_shift.json")

    vertex_count, points_iter = read_binary_xyz_ply(source_ply)
    floor_cells = compute_floor_cells(points_iter)
    _vertex_count, points_iter_second = read_binary_xyz_ply(source_ply)
    floor_points = select_floor_points(points_iter_second, floor_cells)

    artifact_path = gt_root / "config" / f"ex_artifacts_{args.artifact_config}.yaml"
    artifacts = localize_artifacts(parse_artifacts_yaml(artifact_path), global_shift)
    topology = read_ex_topology(gt_root / "network" / "data" / "ex_edgelist.csv")

    walkable_ply = viewer_dir / "walkable_floor_highlight.ply"
    artifact_ply = viewer_dir / "artifact_markers.ply"
    artifact_json = viewer_dir / "ground_truth_artifacts_local.json"
    topology_json = viewer_dir / "ex_topology_graph.json"
    floor_svg = viewer_dir / "floor_density_topdown.svg"
    layers_json = viewer_dir / "road_visibility_layers.json"
    summary_json = viewer_dir / "road_visibility_summary.json"

    write_point_ply(walkable_ply, floor_points)
    artifact_point_count = write_artifact_marker_ply(artifact_ply, artifacts)
    write_json(artifact_json, {"course": "ex", "config": args.artifact_config, "artifacts": artifacts})
    write_json(topology_json, topology)
    write_floor_density_svg(floor_svg, floor_cells, artifacts)

    layer_config = {
        "coordinate_system": "local_shifted",
        "ground_truth_course": "ex",
        "important_warning": "EX topology CSV has edge lengths and connectivity, but no node coordinates. 3D road visibility layer is extracted from actual LiDAR floor-like points.",
        "layers": [
            {
                "id": "tunnel_downsampled_1m",
                "path": "../pointcloud/tunnel_downsampled.ply",
                "type": "pointcloud",
                "recommended_point_size": 0.018,
                "visible_by_default": True,
            },
            {
                "id": "walkable_floor_highlight",
                "path": "walkable_floor_highlight.ply",
                "type": "actual_lidar_floor_points",
                "recommended_point_size": 0.08,
                "visible_by_default": True,
            },
            {
                "id": "artifact_markers",
                "path": "artifact_markers.ply",
                "type": "ground_truth_artifact_markers",
                "recommended_point_size": 0.11,
                "visible_by_default": True,
            },
            {
                "id": "floor_density_topdown",
                "path": "floor_density_topdown.svg",
                "type": "static_topdown_svg",
                "visible_by_default": False,
            },
            {
                "id": "ex_topology_graph",
                "path": "ex_topology_graph.json",
                "type": "topology_only_graph",
                "visible_by_default": False,
            },
        ],
    }
    write_json(layers_json, layer_config)

    summary = {
        "source_ply": str(source_ply),
        "source_vertex_count": vertex_count,
        "floor_cell_count": len(floor_cells),
        "selected_floor_point_count": len(floor_points),
        "artifact_count": len(artifacts),
        "artifact_marker_point_count": artifact_point_count,
        "topology_node_count": len(topology["nodes"]),
        "topology_edge_count": len(topology["edges"]),
        "chokepoint_count": len(topology["chokepoints"]),
        "outputs": {
            "walkable_floor_highlight": str(walkable_ply),
            "artifact_markers": str(artifact_ply),
            "ground_truth_artifacts_local": str(artifact_json),
            "ex_topology_graph": str(topology_json),
            "floor_density_topdown": str(floor_svg),
            "road_visibility_layers": str(layers_json),
        },
    }
    write_json(summary_json, summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
