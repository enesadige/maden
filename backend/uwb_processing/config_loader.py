"""Load, normalize, and validate configuration for the UWB MVP.

This module performs no writes. Haki inputs are restricted to their read-only
handoff directory, while generated UWB paths target sibling sample folders.
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

try:
    from .core import (
        clamp,
        ensure_finite_number,
        normalize_segment_id,
        normalize_tag_id,
        normalize_worker_id,
    )
except ImportError:  # Supports ``python backend/uwb_processing/config_loader.py``.
    from core import (  # type: ignore
        clamp,
        ensure_finite_number,
        normalize_segment_id,
        normalize_tag_id,
        normalize_worker_id,
    )


REQUIRED_TOP_LEVEL_KEYS = (
    "dataset_root",
    "output_root",
    "segment_source",
    "anchor_placement",
    "cable_topology",
    "workers",
    "sample_rate_hz",
    "source_position_type",
    "coordinate_transform",
    "segment_mapping",
    "reliability",
)

SEGMENT_SOURCE_KEYS = (
    "map_segments_path",
    "segment_metadata_path",
    "mine_graph_path",
    "geometry_risk_path",
)


def find_repo_root(start_path: str | Path | None = None) -> Path:
    """Find the resolved repository root from a file or directory location."""
    start = Path(start_path).expanduser() if start_path is not None else Path(__file__)
    current = start.resolve()
    if current.is_file():
        current = current.parent
    candidates = (current, *current.parents)
    for candidate in candidates:
        if (candidate / ".git").exists():
            return candidate.resolve()
    for candidate in candidates:
        if (candidate / "backend").is_dir():
            return candidate.resolve()
    raise FileNotFoundError(f"Could not locate repository root from {current}")


def resolve_path(path_value: str, repo_root: Path) -> Path:
    """Resolve an absolute or repository-relative path without requiring it."""
    if not isinstance(path_value, str) or not path_value.strip():
        raise ValueError("path value must be a non-empty string")
    path = Path(path_value.strip()).expanduser()
    if not path.is_absolute():
        path = Path(repo_root) / path
    return path.resolve()


def load_json_file(path: str | Path) -> dict[str, Any]:
    """Read a UTF-8 JSON object with clear path and format errors."""
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Configuration file does not exist: {resolved}")
    try:
        with resolved.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON in {resolved} at line {exc.lineno}, column {exc.colno}"
        ) from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {resolved}")
    return value


def is_relative_to(path: Path, parent: Path) -> bool:
    """Return whether *path* is equal to or below *parent*."""
    try:
        Path(path).resolve().relative_to(Path(parent).resolve())
    except ValueError:
        return False
    return True


def _require_mapping(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")
    return value


def _require_keys(mapping: dict[str, Any], keys: tuple[str, ...], field_name: str) -> None:
    missing = [key for key in keys if key not in mapping]
    if missing:
        raise ValueError(f"{field_name} is missing required keys: {', '.join(missing)}")


def _require_bool(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a boolean")
    return value


def _require_int(value: Any, field_name: str, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{field_name} must be at least {minimum}")
    return value


def _positive_number(value: Any, field_name: str) -> float:
    number = ensure_finite_number(value, field_name)
    if number <= 0.0:
        raise ValueError(f"{field_name} must be greater than zero")
    return number


def _validate_output_root(config: dict[str, Any], repo_root: Path) -> None:
    output_root = resolve_path(config["output_root"], repo_root)
    expected_root = resolve_path("backend/data_processed/sample", repo_root)
    if output_root != expected_root:
        raise ValueError(
            "output_root must resolve to backend/data_processed/sample for local API testing"
        )
    if not is_relative_to(output_root, repo_root):
        raise ValueError("output_root must be inside the repository")

    protected = (
        resolve_path("backend/data_processed/sample/haki_lidar", repo_root),
        resolve_path("docs/haki_lidar_handoff.md", repo_root),
        resolve_path("pipelines/colab_lidar_pipeline.py", repo_root),
        resolve_path("pipelines/colab_lidar_pipeline.ipynb", repo_root),
        resolve_path("dashboards", repo_root),
        resolve_path("backend/apps/risk", repo_root),
        resolve_path("backend/apps/routing", repo_root),
        resolve_path("backend/apps/sensors", repo_root),
    )
    output_dirs = {
        "output_root": output_root,
        "workers_output_dir": output_root / "workers",
        "anchors_output_dir": output_root / "anchors",
        "risk_output_dir": output_root / "risk",
    }
    for name, path in output_dirs.items():
        for protected_path in protected:
            if is_relative_to(path, protected_path):
                raise ValueError(f"{name} targets protected path: {protected_path}")
    config.update({name: str(path.resolve()) for name, path in output_dirs.items()})


def _validate_segment_sources(config: dict[str, Any], repo_root: Path) -> None:
    sources = _require_mapping(config["segment_source"], "segment_source")
    _require_keys(sources, SEGMENT_SOURCE_KEYS, "segment_source")
    haki_root = resolve_path("backend/data_processed/sample/haki_lidar", repo_root)
    normalized: dict[str, str] = {}
    for key in SEGMENT_SOURCE_KEYS:
        path = resolve_path(sources[key], repo_root)
        if not path.is_file():
            raise FileNotFoundError(f"segment_source.{key} does not exist: {path}")
        if not is_relative_to(path, haki_root):
            raise ValueError(f"segment_source.{key} must be under {haki_root}")
        normalized[key] = str(path)
    config["segment_source"] = normalized


def _normalize_prefix(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    prefix = value.strip().upper().replace("_", "")
    if not prefix.isalnum():
        raise ValueError(f"{field_name} must contain only letters and numbers")
    return prefix


def generate_default_workers(
    count: int,
    worker_prefix: str = "WORKER",
    tag_prefix: str = "TAG",
) -> list[dict[str, str]]:
    """Generate canonical worker/tag identities without pipeline-specific trial fields."""
    total = _require_int(count, "worker_defaults.default_worker_count", 1)
    worker_base = _normalize_prefix(worker_prefix, "worker_defaults.worker_id_prefix")
    tag_base = _normalize_prefix(tag_prefix, "worker_defaults.tag_id_prefix")
    return [
        {
            "worker_id": f"{worker_base}_{index:02d}",
            "tag_id": f"{tag_base}_{index:03d}",
        }
        for index in range(1, total + 1)
    ]


def _validate_worker_defaults(config: dict[str, Any]) -> dict[str, Any]:
    defaults = deepcopy(config.get("worker_defaults", {}))
    if defaults is None:
        defaults = {}
    defaults = _require_mapping(defaults, "worker_defaults")
    defaults.setdefault("default_worker_count", 10)
    defaults.setdefault("worker_id_prefix", "WORKER")
    defaults.setdefault("tag_id_prefix", "TAG")
    defaults.setdefault("allow_auto_generate_workers", False)
    defaults["default_worker_count"] = _require_int(
        defaults["default_worker_count"], "worker_defaults.default_worker_count", 1
    )
    defaults["worker_id_prefix"] = _normalize_prefix(
        defaults["worker_id_prefix"], "worker_defaults.worker_id_prefix"
    )
    defaults["tag_id_prefix"] = _normalize_prefix(
        defaults["tag_id_prefix"], "worker_defaults.tag_id_prefix"
    )
    defaults["allow_auto_generate_workers"] = _require_bool(
        defaults["allow_auto_generate_workers"],
        "worker_defaults.allow_auto_generate_workers",
    )
    config["worker_defaults"] = defaults
    return defaults


def _workers_are_explicit(workers: Any) -> bool:
    return isinstance(workers, list) and bool(workers)


def _validate_workers(config: dict[str, Any]) -> None:
    defaults = _validate_worker_defaults(config)
    workers = config.get("workers")
    generated = False
    if _workers_are_explicit(workers):
        source_workers = workers
    elif workers in (None, []):
        if not defaults["allow_auto_generate_workers"]:
            raise ValueError(
                "workers must be non-empty unless worker_defaults.allow_auto_generate_workers is true"
            )
        source_workers = generate_default_workers(
            defaults["default_worker_count"],
            defaults["worker_id_prefix"],
            defaults["tag_id_prefix"],
        )
        generated = True
    else:
        raise ValueError("workers must be a list when provided")

    allow_reuse = _require_bool(config.get("allow_trial_reuse", False), "allow_trial_reuse")
    normalized: list[dict[str, Any]] = []
    worker_ids: set[str] = set()
    tag_ids: set[str] = set()
    trial_hints: set[str] = set()
    explicit_required = ("worker_id", "tag_id", "source_trial_hint", "time_offset_s", "start_segment")
    generated_required = ("worker_id", "tag_id")
    required = generated_required if generated else explicit_required
    for index, item in enumerate(source_workers):
        worker = deepcopy(_require_mapping(item, f"workers[{index}]"))
        _require_keys(worker, required, f"workers[{index}]")
        worker["worker_id"] = normalize_worker_id(worker["worker_id"])
        worker["tag_id"] = normalize_tag_id(worker["tag_id"])
        if not generated:
            worker["start_segment"] = normalize_segment_id(worker["start_segment"])
            trial_hint = worker["source_trial_hint"]
            if not isinstance(trial_hint, str) or not trial_hint.strip():
                raise ValueError(f"workers[{index}].source_trial_hint must be non-empty")
            worker["source_trial_hint"] = trial_hint.strip()
            worker["time_offset_s"] = ensure_finite_number(
                worker["time_offset_s"], f"workers[{index}].time_offset_s"
            )
        if worker["worker_id"] in worker_ids:
            raise ValueError(f"duplicate worker_id: {worker['worker_id']}")
        if worker["tag_id"] in tag_ids:
            raise ValueError(f"duplicate tag_id: {worker['tag_id']}")
        if not generated:
            if not allow_reuse and worker["source_trial_hint"] in trial_hints:
                raise ValueError(f"duplicate source_trial_hint: {worker['source_trial_hint']}")
            trial_hints.add(worker["source_trial_hint"])
        worker_ids.add(worker["worker_id"])
        tag_ids.add(worker["tag_id"])
        normalized.append(worker)
    config["workers"] = normalized
    config["worker_count"] = len(normalized)
    config["worker_generation_mode"] = "auto_generated" if generated else "explicit"
    config["allow_trial_reuse"] = allow_reuse


def _validate_anchor_placement(config: dict[str, Any]) -> None:
    anchor = deepcopy(_require_mapping(config["anchor_placement"], "anchor_placement"))
    required = (
        "geometry_mode", "coverage_radius_m", "anchor_spacing_m", "sample_spacing_m",
        "min_visible_anchors_2d", "redundancy", "anchor_height_m",
        "junction_extra_anchor", "dead_end_extra_anchor", "exit_extra_anchor",
        "risk_zone_extra_anchor", "curve_extra_anchor", "turn_angle_threshold_deg",
        "long_edge_threshold_m", "max_anchor_count",
    )
    _require_keys(anchor, required, "anchor_placement")
    if anchor["geometry_mode"] not in {"bounds_center", "center_only", "graph_only"}:
        raise ValueError("anchor_placement.geometry_mode is not supported")
    for key in ("coverage_radius_m", "anchor_spacing_m", "sample_spacing_m", "long_edge_threshold_m"):
        anchor[key] = _positive_number(anchor[key], f"anchor_placement.{key}")
    anchor["min_visible_anchors_2d"] = _require_int(
        anchor["min_visible_anchors_2d"], "anchor_placement.min_visible_anchors_2d", 1
    )
    anchor["redundancy"] = _require_int(anchor["redundancy"], "anchor_placement.redundancy", 0)
    anchor["anchor_height_m"] = ensure_finite_number(
        anchor["anchor_height_m"], "anchor_placement.anchor_height_m"
    )
    for key in (
        "junction_extra_anchor", "dead_end_extra_anchor", "exit_extra_anchor",
        "risk_zone_extra_anchor", "curve_extra_anchor",
    ):
        anchor[key] = _require_bool(anchor[key], f"anchor_placement.{key}")
    angle = ensure_finite_number(
        anchor["turn_angle_threshold_deg"], "anchor_placement.turn_angle_threshold_deg"
    )
    if not 0.0 <= angle <= 180.0:
        raise ValueError("anchor_placement.turn_angle_threshold_deg must be in [0, 180]")
    anchor["turn_angle_threshold_deg"] = angle
    maximum = anchor["max_anchor_count"]
    if maximum is not None:
        anchor["max_anchor_count"] = _require_int(
            maximum, "anchor_placement.max_anchor_count", 1
        )
    config["anchor_placement"] = anchor


def _validate_cable_topology(config: dict[str, Any]) -> None:
    cable = deepcopy(_require_mapping(config["cable_topology"], "cable_topology"))
    required = (
        "mode", "enable_cross_links", "max_cross_link_distance_m",
        "head_end_selection", "wall_offset_m",
    )
    _require_keys(cable, required, "cable_topology")
    if cable["mode"] != "graph_based":
        raise ValueError("cable_topology.mode must be graph_based")
    cable["enable_cross_links"] = _require_bool(
        cable["enable_cross_links"], "cable_topology.enable_cross_links"
    )
    cable["max_cross_link_distance_m"] = _positive_number(
        cable["max_cross_link_distance_m"], "cable_topology.max_cross_link_distance_m"
    )
    if not isinstance(cable["head_end_selection"], str) or not cable["head_end_selection"].strip():
        raise ValueError("cable_topology.head_end_selection must be non-empty")
    cable["head_end_selection"] = cable["head_end_selection"].strip()
    cable["wall_offset_m"] = ensure_finite_number(
        cable["wall_offset_m"], "cable_topology.wall_offset_m"
    )
    config["cable_topology"] = cable


def _validate_coordinate_transform(config: dict[str, Any]) -> None:
    transform = deepcopy(
        _require_mapping(config["coordinate_transform"], "coordinate_transform")
    )
    required = ("mode", "axis_mapping", "scale", "rotation_deg_z", "translation")
    _require_keys(transform, required, "coordinate_transform")
    if transform["mode"] not in {"bounds_fit", "manual", "identity"}:
        raise ValueError("coordinate_transform.mode is not supported")
    axis = _require_mapping(transform["axis_mapping"], "coordinate_transform.axis_mapping")
    _require_keys(axis, ("source_x", "source_y", "source_z"), "coordinate_transform.axis_mapping")
    allowed_axes = {"x", "y", "z", "-x", "-y", "-z"}
    if any(axis[key] not in allowed_axes for key in ("source_x", "source_y", "source_z")):
        raise ValueError("coordinate_transform.axis_mapping contains an invalid axis")
    transform["axis_mapping"] = dict(axis)
    scale = _require_mapping(transform["scale"], "coordinate_transform.scale")
    translation = _require_mapping(transform["translation"], "coordinate_transform.translation")
    _require_keys(scale, ("x", "y", "z"), "coordinate_transform.scale")
    _require_keys(translation, ("x", "y", "z"), "coordinate_transform.translation")
    normalized_scale: dict[str, float] = {}
    normalized_translation: dict[str, float] = {}
    for axis_name in ("x", "y", "z"):
        normalized_scale[axis_name] = ensure_finite_number(
            scale[axis_name], f"coordinate_transform.scale.{axis_name}"
        )
        if normalized_scale[axis_name] == 0.0:
            raise ValueError(f"coordinate_transform.scale.{axis_name} must be non-zero")
        normalized_translation[axis_name] = ensure_finite_number(
            translation[axis_name], f"coordinate_transform.translation.{axis_name}"
        )
    transform["scale"] = normalized_scale
    transform["translation"] = normalized_translation
    transform["rotation_deg_z"] = ensure_finite_number(
        transform["rotation_deg_z"], "coordinate_transform.rotation_deg_z"
    )
    config["coordinate_transform"] = transform


def _validate_segment_mapping(config: dict[str, Any]) -> None:
    mapping = deepcopy(_require_mapping(config["segment_mapping"], "segment_mapping"))
    required = (
        "method", "max_nearest_segment_distance_m", "graph_jump_penalty",
        "hysteresis_margin_m",
    )
    _require_keys(mapping, required, "segment_mapping")
    if mapping["method"] != "bounds_center":
        raise ValueError("segment_mapping.method must be bounds_center")
    mapping["max_nearest_segment_distance_m"] = _positive_number(
        mapping["max_nearest_segment_distance_m"],
        "segment_mapping.max_nearest_segment_distance_m",
    )
    penalty = ensure_finite_number(mapping["graph_jump_penalty"], "segment_mapping.graph_jump_penalty")
    if not 0.0 <= penalty <= 1.0:
        raise ValueError("segment_mapping.graph_jump_penalty must be in [0, 1]")
    mapping["graph_jump_penalty"] = clamp(penalty)
    margin = ensure_finite_number(mapping["hysteresis_margin_m"], "segment_mapping.hysteresis_margin_m")
    if margin < 0.0:
        raise ValueError("segment_mapping.hysteresis_margin_m must be non-negative")
    mapping["hysteresis_margin_m"] = margin
    config["segment_mapping"] = mapping


def _validate_reliability(config: dict[str, Any]) -> None:
    reliability = deepcopy(_require_mapping(config["reliability"], "reliability"))
    source_keys = (
        "flight_signal_weight", "visible_anchor_weight", "signal_quality_weight",
        "mapping_confidence_weight", "continuity_weight",
    )
    _require_keys(reliability, source_keys, "reliability")
    values: dict[str, float] = {}
    for key in source_keys:
        value = ensure_finite_number(reliability[key], f"reliability.{key}")
        if value < 0.0:
            raise ValueError(f"reliability.{key} must be non-negative")
        values[key] = value
    total = sum(values.values())
    if total == 0.0:
        raise ValueError("reliability weights must not sum to zero")
    if abs(total - 1.0) > 0.05:
        raise ValueError("reliability weights must sum approximately to 1.0")
    normalized = {key: value / total for key, value in values.items()}
    reliability.update(normalized)
    config["reliability"] = reliability
    config["reliability_weights"] = {
        "flight_signal": normalized["flight_signal_weight"],
        "visible_anchor": normalized["visible_anchor_weight"],
        "signal_quality": normalized["signal_quality_weight"],
        "mapping_confidence": normalized["mapping_confidence_weight"],
        "continuity": normalized["continuity_weight"],
    }


def validate_config(config: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    """Return a normalized, JSON-serializable copy of a UWB configuration."""
    if not isinstance(config, dict):
        raise ValueError("config must be an object")
    normalized = deepcopy(config)
    _require_keys(normalized, REQUIRED_TOP_LEVEL_KEYS, "config")
    root = Path(repo_root).resolve()
    normalized["repo_root"] = str(root)

    dataset_root = resolve_path(normalized["dataset_root"], root)
    normalized["dataset_root"] = str(dataset_root)
    normalized["dataset_root_exists"] = dataset_root.exists()
    warnings: list[str] = list(normalized.get("warnings", []))
    if not normalized["dataset_root_exists"]:
        warnings.append(f"dataset_root does not exist: {dataset_root}")
    normalized["warnings"] = warnings

    _validate_output_root(normalized, root)
    _validate_segment_sources(normalized, root)
    _validate_workers(normalized)
    _validate_anchor_placement(normalized)
    _validate_cable_topology(normalized)
    _validate_coordinate_transform(normalized)
    _validate_segment_mapping(normalized)
    _validate_reliability(normalized)

    normalized["sample_rate_hz"] = _positive_number(
        normalized["sample_rate_hz"], "sample_rate_hz"
    )
    if (
        not isinstance(normalized["source_position_type"], str)
        or not normalized["source_position_type"].strip()
    ):
        raise ValueError("source_position_type must be a non-empty string")
    normalized["source_position_type"] = normalized["source_position_type"].strip()
    return normalized


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Load the default or supplied configuration and return its normalized form."""
    repo_root = find_repo_root()
    if config_path is None:
        path = resolve_path("backend/uwb_processing/uwb_config.example.json", repo_root)
    else:
        path = resolve_path(str(config_path), repo_root)
    return validate_config(load_json_file(path), repo_root)


def _self_check() -> None:
    config = load_config()
    assert config["output_root"].replace("\\", "/").endswith(
        "backend/data_processed/sample"
    )
    haki_root = resolve_path(
        "backend/data_processed/sample/haki_lidar", Path(config["repo_root"])
    )
    for path in config["segment_source"].values():
        resolved = Path(path)
        assert resolved.exists()
        assert is_relative_to(resolved, haki_root)
    assert config["worker_generation_mode"] == "explicit"
    assert config["worker_count"] == len(config["workers"])
    assert config["workers"][0]["worker_id"] == "WORKER_01"
    assert config["workers"][0]["tag_id"] == "TAG_001"
    assert config["workers"][0]["start_segment"] == "S001"
    assert abs(sum(config["reliability_weights"].values()) - 1.0) < 1e-9
    assert not is_relative_to(Path(config["output_root"]), haki_root)

    base = deepcopy(config)
    base["workers"] = []
    base["worker_defaults"]["allow_auto_generate_workers"] = True
    for count in (10, 2, 20):
        candidate = deepcopy(base)
        candidate["worker_defaults"]["default_worker_count"] = count
        checked = validate_config(candidate, Path(config["repo_root"]))
        assert checked["worker_generation_mode"] == "auto_generated"
        assert checked["worker_count"] == count
        assert checked["workers"][0] == {"worker_id": "WORKER_01", "tag_id": "TAG_001"}
        assert checked["workers"][-1] == {
            "worker_id": f"WORKER_{count:02d}",
            "tag_id": f"TAG_{count:03d}",
        }


if __name__ == "__main__":
    _self_check()
    print("config_loader.py self-check passed")
