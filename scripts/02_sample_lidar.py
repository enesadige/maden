from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from _env import bootstrap

bootstrap()

from madenguard.config import ensure_project_dirs, load_config, project_path
from madenguard.io_utils import file_size, human_size, write_json
from madenguard.las_utils import point_bounds, systematic_las_sample, write_points_npz


def main() -> None:
    ensure_project_dirs()
    config = load_config()
    las_path = Path(config["paths"]["mediumres_las"])
    targets = [int(value) for value in config["runtime"].get("lidar_sample_targets", [50000])]
    metadata = {
        "source_file": str(las_path),
        "source_size_bytes": file_size(las_path),
        "source_size": human_size(file_size(las_path)),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "samples": [],
        "safety": "Uses direct record seeking; never calls las.read() or loads full LAS into memory.",
    }
    for target in targets:
        points, meta = systematic_las_sample(las_path, target)
        sample_path = project_path("processed", "lidar_samples", f"mediumres_sample_{target//1000}k.npz")
        write_points_npz(sample_path, points)
        bounds = point_bounds(points)
        sample_meta = {
            "target_point_count": target,
            "sampled_point_count": len(points),
            "output": str(sample_path),
            "output_size": human_size(file_size(sample_path)),
            "bounds": bounds,
            "las_header": meta,
        }
        metadata["samples"].append(sample_meta)
        print(f"Wrote {sample_path} ({sample_meta['output_size']})")
    write_json(project_path("processed", "lidar_samples", "mediumres_sample_metadata.json"), metadata)


if __name__ == "__main__":
    main()

