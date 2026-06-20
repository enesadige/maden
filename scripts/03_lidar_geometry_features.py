from __future__ import annotations

from pathlib import Path

from _env import bootstrap

bootstrap()

from madenguard.config import ensure_project_dirs, load_config, project_path
from madenguard.io_utils import clamp, normalize, normalize_inverse, percentile, read_json, stdev, write_csv, write_json
from madenguard.las_utils import read_points_npz


def score_level(score: float) -> str:
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
    sample_targets = [int(value) for value in config["runtime"].get("lidar_sample_targets", [50000])]
    sample_path = project_path("processed", "lidar_samples", f"mediumres_sample_{sample_targets[0]//1000}k.npz")
    if not sample_path.exists():
        raise SystemExit(f"Missing sample file: {sample_path}. Run scripts/02_sample_lidar.py first.")
    points = read_points_npz(sample_path)
    segments = read_json(project_path("processed", "features", "segments.json"))
    slice_count = int(config["runtime"].get("geometry_slice_count", 32))
    xs = [p[0] for p in points]
    min_x, max_x = min(xs), max(xs)
    width = (max_x - min_x) / slice_count if slice_count else 1.0
    bins: list[list[tuple[float, float, float]]] = [[] for _ in range(slice_count)]
    for point in points:
        idx = min(slice_count - 1, max(0, int((point[0] - min_x) / width))) if width > 0 else 0
        bins[idx].append(point)

    raw_rows = []
    for idx, bucket in enumerate(bins):
        xs_bucket = [p[0] for p in bucket]
        ys = [p[1] for p in bucket]
        zs = [p[2] for p in bucket]
        top_cut = percentile(zs, 75) if zs else 0.0
        top_zs = [z for z in zs if z >= top_cut]
        width_proxy = percentile(ys, 95) - percentile(ys, 5) if ys else 0.0
        height_proxy = percentile(zs, 95) - percentile(zs, 5) if zs else 0.0
        ceiling_roughness = stdev(top_zs)
        raw_rows.append({
            "slice_index": idx,
            "point_count": len(bucket),
            "bbox_width_x": width,
            "bbox_width_y": (max(ys) - min(ys)) if ys else 0.0,
            "bbox_height_z": (max(zs) - min(zs)) if zs else 0.0,
            "centroid_x": (sum(xs_bucket) / len(xs_bucket)) if xs_bucket else 0.0,
            "centroid_y": (sum(ys) / len(ys)) if ys else 0.0,
            "centroid_z": (sum(zs) / len(zs)) if zs else 0.0,
            "width_proxy": width_proxy,
            "height_proxy": height_proxy,
            "ceiling_z_p95": percentile(zs, 95),
            "floor_z_p05": percentile(zs, 5),
            "ceiling_roughness": ceiling_roughness,
        })

    widths = [row["width_proxy"] for row in raw_rows if row["point_count"] > 0]
    heights = [row["height_proxy"] for row in raw_rows if row["point_count"] > 0]
    roughness = [row["ceiling_roughness"] for row in raw_rows if row["point_count"] > 0]
    min_w, max_w = min(widths or [0.0]), max(widths or [1.0])
    min_h, max_h = min(heights or [0.0]), max(heights or [1.0])
    min_r, max_r = min(roughness or [0.0]), max(roughness or [1.0])

    rows = []
    for idx, row in enumerate(raw_rows):
        prev = raw_rows[idx - 1] if idx > 0 else row
        width_change = abs(row["width_proxy"] - prev["width_proxy"])
        height_change = abs(row["height_proxy"] - prev["height_proxy"])
        geometry_change_score = clamp(normalize(width_change + height_change, 0.0, (max_w - min_w) + (max_h - min_h) or 1.0))
        narrowness_score = clamp(normalize_inverse(row["width_proxy"], min_w, max_w))
        low_ceiling_score = clamp(normalize_inverse(row["height_proxy"], min_h, max_h))
        ceiling_roughness_score = clamp(normalize(row["ceiling_roughness"], min_r, max_r))
        risk = (
            0.30 * narrowness_score
            + 0.25 * low_ceiling_score
            + 0.25 * ceiling_roughness_score
            + 0.20 * geometry_change_score
        )
        segment = segments[idx % len(segments)] if segments else {"segment_id": f"SLICE_{idx:03d}"}
        rows.append({
            "segment_id": segment["segment_id"],
            "slice_index": idx,
            **row,
            "narrowness_score": round(narrowness_score, 3),
            "low_ceiling_score": round(low_ceiling_score, 3),
            "ceiling_roughness_score": round(ceiling_roughness_score, 3),
            "geometry_change_score": round(geometry_change_score, 3),
            "lidar_geometry_risk": round(risk, 3),
            "risk_level": score_level(risk),
        })

    write_csv(project_path("processed", "features", "lidar_geometry_features.csv"), rows)
    write_json(project_path("processed", "features", "lidar_geometry_features.json"), rows)
    write_json(project_path("simulation_ready", "lidar_geometry_risk.json"), rows)

    top = sorted(rows, key=lambda item: item["lidar_geometry_risk"], reverse=True)[:10]
    report = ["# LiDAR Geometry Analysis", ""]
    report.append(f"- Source sample: `{sample_path}`")
    report.append(f"- Points used: {len(points)}")
    report.append(f"- Slice count: {slice_count}")
    report.append("- Graph-segment matching is approximate in this MVP: ordered LiDAR X slices are mapped onto EX graph segment IDs.")
    report.extend(["", "## Top Risk Slices"])
    for item in top:
        report.append(
            f"- {item['segment_id']} / slice {item['slice_index']}: risk={item['lidar_geometry_risk']} "
            f"({item['risk_level']}), width={item['width_proxy']:.2f}, height={item['height_proxy']:.2f}, "
            f"ceiling_roughness={item['ceiling_roughness']:.3f}"
        )
    project_path("reports", "lidar_geometry_analysis.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"Computed geometry features from {len(points)} sampled LAS points")


if __name__ == "__main__":
    main()
