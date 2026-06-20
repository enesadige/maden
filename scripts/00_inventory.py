from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from _env import bootstrap

bootstrap()

from madenguard.config import ensure_project_dirs, load_config, project_path
from madenguard.io_utils import file_size, human_size, iter_files, write_json
from madenguard.las_utils import read_las_header


TRACKED_EXTS = {".las", ".laz", ".csv", ".dat", ".json", ".npz", ".png", ".jpg", ".jpeg", ".html", ".bag"}
EXPECTED = {
    "mediumres_las": "DARPA MediumRes LAS",
    "graph_ex_edgelist": "DARPA EX graph",
    "graph_sr_edgelist": "DARPA SR graph",
    "methane_csv": "Methane CSV",
    "uci_gas_drift_dir": "UCI Gas Drift directory",
    "uwb_csv": "UTIL UWB selected CSV",
    "tunnel_map_png": "DARPA tunnel map image",
}


def main() -> None:
    ensure_project_dirs()
    config = load_config()
    files_by_ext: dict[str, list[dict[str, object]]] = defaultdict(list)
    large_files: list[dict[str, object]] = []

    for root_value in config["source_roots"]:
        root = Path(root_value)
        if not root.exists():
            continue
        for path in iter_files(root):
            ext = path.suffix.lower()
            size = file_size(path)
            if ext in TRACKED_EXTS:
                files_by_ext[ext].append({"path": str(path), "size_bytes": size, "size": human_size(size)})
            if size >= 100 * 1024 * 1024:
                large_files.append({"path": str(path), "size_bytes": size, "size": human_size(size)})

    expected_status: dict[str, dict[str, object]] = {}
    for key, label in EXPECTED.items():
        raw = config["paths"].get(key)
        path = Path(raw) if raw else None
        exists = bool(path and path.exists())
        expected_status[key] = {
            "label": label,
            "path": str(path) if path else None,
            "exists": exists,
            "size": human_size(file_size(path)) if exists and path.is_file() else None,
        }

    las_headers = []
    for item in files_by_ext.get(".las", []):
        path = Path(str(item["path"]))
        try:
            header = read_las_header(path)
            header["path"] = str(path)
            header["size"] = item["size"]
            las_headers.append(header)
        except Exception as exc:
            las_headers.append({"path": str(path), "error": str(exc), "size": item["size"]})

    inventory = {
        "source_roots": config["source_roots"],
        "expected_status": expected_status,
        "files_by_extension": files_by_ext,
        "large_files": sorted(large_files, key=lambda row: int(row["size_bytes"]), reverse=True),
        "las_headers": las_headers,
        "notes": [
            "External flash disk is used as raw data source; raw data is not copied into project.",
            "FullRes LAS is intentionally absent; MediumRes LAS is the active point cloud source.",
            "Downloads pointcloud directory is not used because the real LAS file is on the flash disk.",
        ],
    }
    json_path = project_path("reports", "data_inventory.json")
    write_json(json_path, inventory)
    for header in las_headers:
        if str(header.get("path")) == config["paths"].get("mediumres_las") and "error" not in header:
            write_json(project_path("reports", "mediumres_las_summary.json"), header)
            break

    md = ["# MadenGuard Data Inventory", ""]
    md.append("## Expected Data")
    for key, status in expected_status.items():
        mark = "OK" if status["exists"] else "MISSING"
        size = f" ({status['size']})" if status.get("size") else ""
        md.append(f"- {mark}: {status['label']}: `{status['path']}`{size}")
    md.extend(["", "## LAS Header Summary"])
    for header in las_headers:
        if "error" in header:
            md.append(f"- `{header['path']}`: {header['error']}")
        else:
            md.append(
                f"- `{header['path']}`: {header['size']}, LAS {header['version']}, "
                f"point_format={header['point_format']}, point_count={header['point_count']}, "
                f"mins={header['mins']}, maxs={header['maxs']}"
            )
    md.extend(["", "## Large Files"])
    for item in inventory["large_files"][:20]:
        md.append(f"- {item['size']}: `{item['path']}`")
    md.extend(["", "## Files By Extension"])
    for ext in sorted(files_by_ext):
        md.append(f"- `{ext}`: {len(files_by_ext[ext])} file(s)")
    md.extend(["", "## Notes"])
    for note in inventory["notes"]:
        md.append(f"- {note}")

    md_path = project_path("reports", "data_inventory.md")
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")


if __name__ == "__main__":
    main()
