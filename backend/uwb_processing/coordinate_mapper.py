"""Transform UTIL movement proxies into the Haki coordinate frame.

UTIL UWB pose_x, pose_y and pose_z values are motion-capture ground-truth proxy positions, not real UWB-estimated miner positions. In this MVP they are transformed into the Haki coordinate frame only as worker movement proxies.

The default bounds_fit transform is an MVP spatial placement strategy. It aligns the UTIL trajectory bounding box into the available Haki segment bounds. It is not a calibrated UWB-to-mine coordinate registration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from math import cos, radians, sin
from typing import Any

try:
    from .config_loader import load_config
    from .core import Point3D, RawPose, clamp, ensure_finite_number, to_jsonable
    from .position_extractor import PositionExtractionResult, extract_positions
    from .segment_loader import SegmentDataset, load_segment_dataset
except ImportError:  # Supports ``python backend/uwb_processing/coordinate_mapper.py``.
    from config_loader import load_config  # type: ignore
    from core import Point3D, RawPose, clamp, ensure_finite_number, to_jsonable  # type: ignore
    from position_extractor import PositionExtractionResult, extract_positions  # type: ignore
    from segment_loader import SegmentDataset, load_segment_dataset  # type: ignore


SUPPORTED_TRANSFORM_MODES = {"bounds_fit", "manual", "identity"}


@dataclass(frozen=True)
class TransformParameters:
    mode: str
    axis_mapping: dict[str, str]
    scale: dict[str, float]
    rotation_deg_z: float
    translation: Point3D
    derived_from_bounds_fit: bool = False
    source_bounds: dict[str, float] = field(default_factory=dict)
    target_bounds: dict[str, float] = field(default_factory=dict)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class TransformedPose:
    worker_id: str
    tag_id: str
    time_step: int
    timestamp_s: float
    source_position: Point3D
    transformed_position: Point3D
    source_trial: str
    flight_signal_reliability: float
    tdoa_sample_count: int = 0
    anchor_pair_count: int = 0
    source_position_type: str = "mocap_ground_truth"
    transform_mode: str = "bounds_fit"

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class CoordinateMappingResult:
    transformed_poses: tuple[TransformedPose, ...]
    transform_parameters: TransformParameters
    summary: dict[str, Any]

    def by_worker(self) -> dict[str, tuple[TransformedPose, ...]]:
        grouped: dict[str, list[TransformedPose]] = {}
        for pose in self.transformed_poses:
            grouped.setdefault(pose.worker_id, []).append(pose)
        return {
            worker_id: tuple(
                sorted(poses, key=lambda pose: (pose.time_step, pose.timestamp_s))
            )
            for worker_id, poses in sorted(grouped.items())
        }

    def to_summary(self) -> dict[str, Any]:
        return dict(self.summary)


def compute_point_bounds(points: tuple[Point3D, ...]) -> dict[str, float]:
    if not points:
        raise ValueError("at least one point is required to compute bounds")
    return {
        "min_x": min(point.x for point in points),
        "max_x": max(point.x for point in points),
        "min_y": min(point.y for point in points),
        "max_y": max(point.y for point in points),
        "min_z": min(point.z for point in points),
        "max_z": max(point.z for point in points),
    }


def compute_dataset_bounds(dataset: SegmentDataset) -> dict[str, float]:
    points: list[Point3D] = []
    for segment in dataset.segments.values():
        if segment.bounds is not None:
            points.extend(
                (
                    Point3D(segment.bounds.min_x, segment.bounds.min_y, segment.bounds.min_z),
                    Point3D(segment.bounds.max_x, segment.bounds.max_y, segment.bounds.max_z),
                )
            )
        elif segment.center is not None:
            points.append(segment.center)
    if not points:
        raise ValueError("segment dataset has no usable bounds or center geometry")
    return compute_point_bounds(tuple(points))


def safe_range(min_value: float, max_value: float, fallback: float = 1.0) -> float:
    minimum = ensure_finite_number(min_value, "min_value")
    maximum = ensure_finite_number(max_value, "max_value")
    safe_fallback = ensure_finite_number(fallback, "fallback")
    value = maximum - minimum
    return value if value > 0.0 and math.isfinite(value) else safe_fallback


def _mapped_component(point: Point3D, selector: str) -> float:
    sign = -1.0 if selector.startswith("-") else 1.0
    axis = selector.lstrip("-")
    if axis not in {"x", "y", "z"}:
        raise ValueError(f"unsupported axis selector: {selector}")
    return sign * getattr(point, axis)


def apply_axis_mapping(point: Point3D, axis_mapping: dict[str, str]) -> Point3D:
    required = ("source_x", "source_y", "source_z")
    if any(key not in axis_mapping for key in required):
        raise ValueError("axis_mapping requires source_x, source_y, and source_z")
    return Point3D(
        _mapped_component(point, axis_mapping["source_x"]),
        _mapped_component(point, axis_mapping["source_y"]),
        _mapped_component(point, axis_mapping["source_z"]),
    )


def apply_scale(point: Point3D, scale: dict[str, float]) -> Point3D:
    return Point3D(
        point.x * ensure_finite_number(scale["x"], "scale.x"),
        point.y * ensure_finite_number(scale["y"], "scale.y"),
        point.z * ensure_finite_number(scale["z"], "scale.z"),
    )


def apply_rotation_z(point: Point3D, rotation_deg_z: float) -> Point3D:
    angle = radians(ensure_finite_number(rotation_deg_z, "rotation_deg_z"))
    cosine, sine = cos(angle), sin(angle)
    return Point3D(
        point.x * cosine - point.y * sine,
        point.x * sine + point.y * cosine,
        point.z,
    )


def apply_translation(point: Point3D, translation: Point3D) -> Point3D:
    return Point3D(
        point.x + translation.x,
        point.y + translation.y,
        point.z + translation.z,
    )


def apply_transform(point: Point3D, transform: TransformParameters) -> Point3D:
    mapped = apply_axis_mapping(point, transform.axis_mapping)
    scaled = apply_scale(mapped, transform.scale)
    rotated = apply_rotation_z(scaled, transform.rotation_deg_z)
    return apply_translation(rotated, transform.translation)


def _bounds_center(bounds: dict[str, float]) -> Point3D:
    return Point3D(
        (bounds["min_x"] + bounds["max_x"]) / 2.0,
        (bounds["min_y"] + bounds["max_y"]) / 2.0,
        (bounds["min_z"] + bounds["max_z"]) / 2.0,
    )


def derive_bounds_fit_transform(
    raw_poses: tuple[RawPose, ...],
    dataset: SegmentDataset,
    config: dict[str, Any],
) -> TransformParameters:
    if not raw_poses:
        raise ValueError("bounds_fit requires at least one RawPose")
    settings = config["coordinate_transform"]
    axis_mapping = dict(settings["axis_mapping"])
    source_points = tuple(pose.source_pose for pose in raw_poses)
    source_bounds = compute_point_bounds(source_points)
    mapped_points = tuple(apply_axis_mapping(point, axis_mapping) for point in source_points)
    mapped_bounds = compute_point_bounds(mapped_points)
    target_bounds = compute_dataset_bounds(dataset)

    source_x_range = safe_range(mapped_bounds["min_x"], mapped_bounds["max_x"])
    source_y_range = safe_range(mapped_bounds["min_y"], mapped_bounds["max_y"])
    source_z_range = safe_range(mapped_bounds["min_z"], mapped_bounds["max_z"])
    target_x_range = safe_range(target_bounds["min_x"], target_bounds["max_x"])
    target_y_range = safe_range(target_bounds["min_y"], target_bounds["max_y"])
    target_z_range = safe_range(target_bounds["min_z"], target_bounds["max_z"])
    padding_factor = 0.90
    scale_xy = min(
        target_x_range * padding_factor / source_x_range,
        target_y_range * padding_factor / source_y_range,
    )
    scale_z = min(1.0, target_z_range * padding_factor / source_z_range)
    scale = {"x": scale_xy, "y": scale_xy, "z": scale_z}
    rotation = ensure_finite_number(settings["rotation_deg_z"], "rotation_deg_z")

    mapped_center = _bounds_center(mapped_bounds)
    centered_after_scale_rotation = apply_rotation_z(
        apply_scale(mapped_center, scale), rotation
    )
    target_center = _bounds_center(target_bounds)
    configured_translation = Point3D.from_any(settings["translation"])
    translation = Point3D(
        target_center.x - centered_after_scale_rotation.x + configured_translation.x,
        target_center.y - centered_after_scale_rotation.y + configured_translation.y,
        target_center.z - centered_after_scale_rotation.z + configured_translation.z,
    )
    return TransformParameters(
        mode="bounds_fit",
        axis_mapping=axis_mapping,
        scale=scale,
        rotation_deg_z=rotation,
        translation=translation,
        derived_from_bounds_fit=True,
        source_bounds=source_bounds,
        target_bounds=target_bounds,
        warnings=("bounds_fit is approximate and not calibrated UWB-to-mine registration",),
    )


def build_transform_parameters(
    raw_poses: tuple[RawPose, ...],
    dataset: SegmentDataset,
    config: dict[str, Any],
) -> TransformParameters:
    settings = config["coordinate_transform"]
    mode = settings["mode"]
    if mode not in SUPPORTED_TRANSFORM_MODES:
        raise ValueError(f"unsupported coordinate transform mode: {mode}")
    if mode == "bounds_fit":
        return derive_bounds_fit_transform(raw_poses, dataset, config)
    source_bounds = compute_point_bounds(tuple(pose.source_pose for pose in raw_poses))
    target_bounds = compute_dataset_bounds(dataset)
    if mode == "identity":
        return TransformParameters(
            mode="identity",
            axis_mapping={"source_x": "x", "source_y": "y", "source_z": "z"},
            scale={"x": 1.0, "y": 1.0, "z": 1.0},
            rotation_deg_z=0.0,
            translation=Point3D(0.0, 0.0, 0.0),
            source_bounds=source_bounds,
            target_bounds=target_bounds,
        )
    return TransformParameters(
        mode="manual",
        axis_mapping=dict(settings["axis_mapping"]),
        scale={
            axis: ensure_finite_number(settings["scale"][axis], f"scale.{axis}")
            for axis in ("x", "y", "z")
        },
        rotation_deg_z=ensure_finite_number(settings["rotation_deg_z"], "rotation_deg_z"),
        translation=Point3D.from_any(settings["translation"]),
        source_bounds=source_bounds,
        target_bounds=target_bounds,
    )


def _reliability_from_raw_pose(raw_pose: RawPose) -> float:
    if raw_pose.tdoa_sample_count <= 0:
        return 0.5
    density = min(raw_pose.tdoa_sample_count / 8.0, 1.0)
    pairs = min(raw_pose.anchor_pair_count / 4.0, 1.0)
    return round(clamp(0.6 * density + 0.4 * pairs), 4)


def transform_raw_pose(
    raw_pose: RawPose, transform: TransformParameters
) -> TransformedPose:
    return TransformedPose(
        worker_id=raw_pose.worker_id,
        tag_id=raw_pose.tag_id,
        time_step=raw_pose.time_step,
        timestamp_s=raw_pose.timestamp_s,
        source_position=raw_pose.source_pose,
        transformed_position=apply_transform(raw_pose.source_pose, transform),
        source_trial=raw_pose.source_trial,
        flight_signal_reliability=_reliability_from_raw_pose(raw_pose),
        tdoa_sample_count=raw_pose.tdoa_sample_count,
        anchor_pair_count=raw_pose.anchor_pair_count,
        source_position_type=raw_pose.source_position_type,
        transform_mode=transform.mode,
    )


def build_coordinate_summary(
    transformed_poses: tuple[TransformedPose, ...],
    transform: TransformParameters,
    extraction_result: PositionExtractionResult,
    dataset: SegmentDataset,
) -> dict[str, Any]:
    transformed_bounds = compute_point_bounds(
        tuple(pose.transformed_position for pose in transformed_poses)
    )
    warnings = list(transform.warnings)
    if transform.mode == "bounds_fit" and (
        "The default bounds_fit transform is an MVP spatial placement strategy. "
        "It aligns the UTIL trajectory bounding box into the available Haki segment "
        "bounds. It is not a calibrated UWB-to-mine coordinate registration."
    ) not in warnings:
        warnings.append(
            "The default bounds_fit transform is an MVP spatial placement strategy. "
            "It aligns the UTIL trajectory bounding box into the available Haki segment "
            "bounds. It is not a calibrated UWB-to-mine coordinate registration."
        )
    return {
        "transformed_pose_count": len(transformed_poses),
        "worker_count": len({pose.worker_id for pose in transformed_poses}),
        "transform_mode": transform.mode,
        "source_position_type": "mocap_ground_truth",
        "derived_from_bounds_fit": transform.derived_from_bounds_fit,
        "source_bounds": dict(transform.source_bounds),
        "target_bounds": dict(transform.target_bounds),
        "transformed_bounds": transformed_bounds,
        "warnings": warnings,
    }


def map_coordinates(
    extraction_result: PositionExtractionResult | None = None,
    dataset: SegmentDataset | None = None,
    config: dict[str, Any] | None = None,
) -> CoordinateMappingResult:
    normalized_config = load_config() if config is None else config
    segment_dataset = (
        load_segment_dataset(normalized_config) if dataset is None else dataset
    )
    extraction = (
        extract_positions(normalized_config)
        if extraction_result is None
        else extraction_result
    )
    raw_poses = extraction.all_raw_poses()
    transform = build_transform_parameters(raw_poses, segment_dataset, normalized_config)
    transformed = tuple(
        sorted(
            (transform_raw_pose(pose, transform) for pose in raw_poses),
            key=lambda pose: (pose.time_step, pose.worker_id),
        )
    )
    result = CoordinateMappingResult(
        transformed_poses=transformed,
        transform_parameters=transform,
        summary=build_coordinate_summary(
            transformed, transform, extraction, segment_dataset
        ),
    )
    validate_coordinate_mapping(result)
    return result


def validate_coordinate_mapping(result: CoordinateMappingResult) -> None:
    if not result.transformed_poses:
        raise ValueError("coordinate mapping must contain at least one transformed pose")
    if result.transform_parameters.mode not in SUPPORTED_TRANSFORM_MODES:
        raise ValueError("coordinate mapping has an unsupported transform mode")
    for pose in result.transformed_poses:
        if not pose.worker_id or not pose.tag_id:
            raise ValueError("transformed pose requires worker_id and tag_id")
        if pose.time_step < 0:
            raise ValueError("transformed pose time_step must be non-negative")
        if pose.source_position_type != "mocap_ground_truth":
            raise ValueError("transformed pose source_position_type is invalid")
        if not all(
            math.isfinite(value)
            for value in (
                pose.transformed_position.x,
                pose.transformed_position.y,
                pose.transformed_position.z,
            )
        ):
            raise ValueError("transformed pose contains NaN or Infinity")
    if result.summary.get("transformed_pose_count") != len(result.transformed_poses):
        raise ValueError("coordinate summary count does not match transformed poses")


def _self_check() -> None:
    config = load_config()
    dataset = load_segment_dataset(config)
    extraction_result = extract_positions(config)
    result = map_coordinates(extraction_result, dataset, config)
    validate_coordinate_mapping(result)
    assert result.transformed_poses
    assert len(result.by_worker()) == len(extraction_result.workers)
    assert all(
        pose.source_position_type == "mocap_ground_truth"
        and all(
            math.isfinite(value)
            for value in (
                pose.transformed_position.x,
                pose.transformed_position.y,
                pose.transformed_position.z,
            )
        )
        for pose in result.transformed_poses
    )
    print(json.dumps(result.to_summary(), ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    _self_check()
    print("coordinate_mapper.py self-check passed")
