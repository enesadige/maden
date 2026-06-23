"""Experimental UWB TDoA position solver extension.

Mode distinction:

* ``mocap_proxy`` keeps the existing MVP behavior. UTIL ``pose_x/y/z`` values
  are used as worker movement proxy positions.
* ``tdoa_solver`` estimates worker position from UWB measurements. In
  tdoa_solver mode, worker position is estimated from UWB measurements. The
  UTIL pose_x/y/z values are used only as motion-capture ground-truth proxy
  references for validation metrics, not as the primary position source.

This module is intentionally independent from Django and uses only the Python
standard library plus the local UWB processing dataclasses.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any
import json
import math
import sys

try:
    from backend.uwb_processing.config_loader import load_config, resolve_path
    from backend.uwb_processing.core import (
        Point3D,
        clamp,
        distance_3d,
        ensure_finite_number,
        normalize_anchor_id,
        normalize_tag_id,
        normalize_worker_id,
        to_jsonable,
    )
    from backend.uwb_processing.dataset_reader import DatasetReadResult, TrialData, read_configured_dataset
    from backend.uwb_processing.position_extractor import PositionExtractionResult, extract_positions
except ModuleNotFoundError:
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from backend.uwb_processing.config_loader import load_config, resolve_path
    from backend.uwb_processing.core import (
        Point3D,
        clamp,
        distance_3d,
        ensure_finite_number,
        normalize_anchor_id,
        normalize_tag_id,
        normalize_worker_id,
        to_jsonable,
    )
    from backend.uwb_processing.dataset_reader import DatasetReadResult, TrialData, read_configured_dataset
    from backend.uwb_processing.position_extractor import PositionExtractionResult, extract_positions


ALLOWED_SOLVER_STATUSES = {
    "solved",
    "fallback_mocap_proxy",
    "insufficient_anchors",
    "missing_calibration",
    "no_measurements",
    "failed_to_converge",
}


@dataclass(frozen=True)
class CalibratedAnchor:
    anchor_id: str
    segment_id: str | None
    position: Point3D
    status: str = "active"
    calibrated: bool = False
    clock_bias_ns: float = 0.0


@dataclass(frozen=True)
class UWBMeasurement:
    tag_id: str
    timestamp_s: float
    anchor_id_a: str
    anchor_id_b: str | None
    measurement_type: str
    value: float
    raw_value: float
    source_trial: str


@dataclass(frozen=True)
class PositionEstimate:
    worker_id: str
    tag_id: str
    timestamp_s: float
    time_step: int
    estimated_position: Point3D | None
    ground_truth_position: Point3D | None
    source_trial: str
    solver_mode: str
    measurement_type: str
    used_measurement_count: int
    used_anchor_count: int
    used_anchor_ids: tuple[str, ...]
    residual_rmse_m: float | None
    error_to_ground_truth_m: float | None
    solver_status: str
    confidence: float
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class SolverValidationSummary:
    estimate_count: int
    solved_count: int
    fallback_count: int
    failed_count: int
    mean_error_m: float | None
    median_error_m: float | None
    rmse_error_m: float | None
    p95_error_m: float | None
    max_error_m: float | None
    mean_residual_rmse_m: float | None
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class UWBPositionSolverResult:
    estimates: tuple[PositionEstimate, ...]
    validation_summary: SolverValidationSummary
    summary: dict[str, Any]


def _solver_config(config: dict[str, Any]) -> dict[str, Any]:
    return dict(config.get("uwb_position_solver") or {})


def _repo_root(config: dict[str, Any]) -> Path:
    return Path(str(config.get("repo_root") or Path(__file__).resolve().parents[2])).resolve()


def load_anchor_calibration(config: dict) -> dict[str, CalibratedAnchor]:
    solver = _solver_config(config)
    raw_path = solver.get("anchor_calibration_path")
    if not raw_path:
        return {}
    path = resolve_path(str(raw_path), _repo_root(config))
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    anchors: dict[str, CalibratedAnchor] = {}
    for item in payload.get("anchors", []):
        try:
            anchor_id = normalize_anchor_id(item.get("anchor_id"))
            position = Point3D.from_any(item.get("position"))
            segment_id = item.get("segment_id")
            status = str(item.get("status", "active")).strip().lower() or "active"
            calibrated = bool(item.get("calibrated", False))
            clock_bias_ns = ensure_finite_number(item.get("clock_bias_ns", 0.0), "clock_bias_ns")
        except (TypeError, ValueError):
            continue
        if status != "active":
            continue
        anchors[anchor_id] = CalibratedAnchor(
            anchor_id=anchor_id,
            segment_id=str(segment_id).strip() if segment_id else None,
            position=position,
            status=status,
            calibrated=calibrated,
            clock_bias_ns=clock_bias_ns,
        )
    return anchors


def convert_tdoa_to_distance_difference_m(tdoa_value: float, speed_of_light_m_s: float) -> float:
    """Convert a TDoA time delta to a distance difference in meters.

    The UTIL parser exposes ``tdoa_meas`` without unit metadata. For this
    experimental path we assume the value is seconds and multiply by the
    configured propagation speed. If later dataset documentation proves the
    value is already meters or nanoseconds, this should become a config unit
    switch before field use.
    """
    return ensure_finite_number(tdoa_value, "tdoa_value") * ensure_finite_number(speed_of_light_m_s, "speed_of_light_m_s")


def build_uwb_measurements_from_trial(trial_data: Any, worker_config: dict, config: dict) -> tuple[UWBMeasurement, ...]:
    solver = _solver_config(config)
    speed = ensure_finite_number(solver.get("speed_of_light_m_s", 299702547.0), "speed_of_light_m_s")
    measurement_type = str(solver.get("measurement_type", "tdoa")).lower()
    tag_id = normalize_tag_id(worker_config["tag_id"])
    source_trial = str(worker_config.get("source_trial_hint") or getattr(trial_data, "trial_hint", ""))
    measurements: list[UWBMeasurement] = []
    if measurement_type != "tdoa":
        return ()
    for sample in getattr(trial_data, "tdoa_samples", ()):
        try:
            anchor_a = normalize_anchor_id(sample.anchor_a)
            anchor_b = normalize_anchor_id(sample.anchor_b)
            raw = ensure_finite_number(sample.tdoa_meas, "tdoa_meas")
            value = convert_tdoa_to_distance_difference_m(raw, speed)
            timestamp = ensure_finite_number(sample.timestamp_s, "timestamp_s")
        except (TypeError, ValueError):
            continue
        measurements.append(UWBMeasurement(tag_id, timestamp, anchor_a, anchor_b, "tdoa", value, raw, source_trial))
    return tuple(sorted(measurements, key=lambda item: (item.timestamp_s, item.anchor_id_a, item.anchor_id_b or "")))


def group_measurements_by_time_window(measurements: tuple[UWBMeasurement, ...], target_timestamp_s: float, max_age_s: float) -> tuple[UWBMeasurement, ...]:
    target = ensure_finite_number(target_timestamp_s, "target_timestamp_s")
    max_age = ensure_finite_number(max_age_s, "max_age_s")
    return tuple(
        item
        for item in sorted(measurements, key=lambda value: (abs(value.timestamp_s - target), value.timestamp_s, value.anchor_id_a, value.anchor_id_b or ""))
        if abs(item.timestamp_s - target) <= max_age
    )


def unique_anchor_ids_from_measurements(measurements: tuple[UWBMeasurement, ...]) -> tuple[str, ...]:
    values = {item.anchor_id_a for item in measurements if item.anchor_id_a}
    values.update(item.anchor_id_b for item in measurements if item.anchor_id_b)
    return tuple(sorted(values))


def residuals_for_tdoa_position(position: Point3D, measurements: tuple[UWBMeasurement, ...], anchors: dict[str, CalibratedAnchor]) -> tuple[float, ...]:
    residuals: list[float] = []
    for measurement in measurements:
        if not measurement.anchor_id_b:
            continue
        anchor_a = anchors.get(measurement.anchor_id_a)
        anchor_b = anchors.get(measurement.anchor_id_b)
        if anchor_a is None or anchor_b is None:
            continue
        predicted = distance_3d(position, anchor_a.position) - distance_3d(position, anchor_b.position)
        residuals.append(predicted - measurement.value)
    return tuple(residuals)


def rmse(values: tuple[float, ...]) -> float | None:
    if not values:
        return None
    return math.sqrt(sum(value * value for value in values) / len(values))


def solve_tdoa_position_gradient_descent(measurements: tuple[UWBMeasurement, ...], anchors: dict[str, CalibratedAnchor], initial_position: Point3D, config: dict) -> tuple[Point3D | None, float | None, str, tuple[str, ...]]:
    solver = _solver_config(config)
    min_unique = int(solver.get("min_unique_anchors", 3))
    used_anchor_ids = unique_anchor_ids_from_measurements(measurements)
    if len(used_anchor_ids) < min_unique:
        return None, None, "insufficient_anchors", ("insufficient calibrated anchors for TDoA solve",)
    solve_dimension = str(solver.get("solve_dimension", "2d")).lower()
    max_iterations = int(solver.get("max_iterations", 200))
    learning_rate = ensure_finite_number(solver.get("learning_rate", 0.02), "learning_rate")
    tolerance = ensure_finite_number(solver.get("convergence_tolerance_m", 0.001), "convergence_tolerance_m")
    max_jump = ensure_finite_number(solver.get("max_position_jump_m", 10.0), "max_position_jump_m")
    axes = ("x", "y", "z") if solve_dimension == "3d" else ("x", "y")
    coords = {"x": initial_position.x, "y": initial_position.y, "z": initial_position.z}
    previous_rmse: float | None = None
    epsilon = 0.05

    def current_point() -> Point3D:
        return Point3D(coords["x"], coords["y"], coords["z"])

    def objective(point: Point3D) -> float:
        residual_values = residuals_for_tdoa_position(point, measurements, anchors)
        if not residual_values:
            return float("inf")
        return sum(value * value for value in residual_values) / len(residual_values)

    for _ in range(max_iterations):
        base = current_point()
        base_rmse = rmse(residuals_for_tdoa_position(base, measurements, anchors))
        if base_rmse is None:
            return None, None, "insufficient_anchors", ("no residuals could be computed from calibrated anchors",)
        if previous_rmse is not None and abs(previous_rmse - base_rmse) < tolerance:
            return base, base_rmse, "solved", ()
        previous_rmse = base_rmse
        gradients: dict[str, float] = {}
        for axis in axes:
            plus = dict(coords)
            minus = dict(coords)
            plus[axis] += epsilon
            minus[axis] -= epsilon
            gradients[axis] = (objective(Point3D(**plus)) - objective(Point3D(**minus))) / (2.0 * epsilon)
        for axis in axes:
            step = clamp(learning_rate * gradients[axis], -max_jump, max_jump)
            coords[axis] -= step
        if distance_3d(initial_position, current_point()) > max_jump:
            direction = (coords["x"] - initial_position.x, coords["y"] - initial_position.y, coords["z"] - initial_position.z)
            length = math.sqrt(sum(value * value for value in direction)) or 1.0
            coords["x"] = initial_position.x + direction[0] / length * max_jump
            coords["y"] = initial_position.y + direction[1] / length * max_jump
            coords["z"] = initial_position.z + direction[2] / length * max_jump
    final = current_point()
    final_rmse = rmse(residuals_for_tdoa_position(final, measurements, anchors))
    return final, final_rmse, "failed_to_converge", ("maximum solver iterations reached",)


def estimate_confidence_from_solution(residual_rmse_m: float | None, used_anchor_count: int, used_measurement_count: int, solver_status: str, config: dict) -> float:
    if solver_status == "solved":
        residual = residual_rmse_m if residual_rmse_m is not None else 10.0
        residual_score = 1.0 / (1.0 + max(residual, 0.0) / 5.0)
        anchor_score = min(max(used_anchor_count, 0) / max(int(_solver_config(config).get("min_unique_anchors", 3)), 1), 1.0)
        measurement_score = min(max(used_measurement_count, 0) / max(int(_solver_config(config).get("min_anchor_pairs", 3)), 1), 1.0)
        return round(clamp(0.60 * residual_score + 0.25 * anchor_score + 0.15 * measurement_score), 4)
    if solver_status == "fallback_mocap_proxy":
        return 0.35
    return 0.0


def compare_to_ground_truth(estimated: Point3D | None, ground_truth: Point3D | None) -> float | None:
    if estimated is None or ground_truth is None:
        return None
    return distance_3d(estimated, ground_truth)


def _average_anchor_position(anchors: dict[str, CalibratedAnchor]) -> Point3D:
    active = list(anchors.values())
    if not active:
        return Point3D(0.0, 0.0, 0.0)
    return Point3D(
        sum(anchor.position.x for anchor in active) / len(active),
        sum(anchor.position.y for anchor in active) / len(active),
        sum(anchor.position.z for anchor in active) / len(active),
    )


def _make_estimate(worker_id: str, tag_id: str, raw_pose: Any, estimated: Point3D | None, status: str, config: dict, used_measurements: tuple[UWBMeasurement, ...] = (), used_anchor_ids: tuple[str, ...] = (), residual_rmse_m: float | None = None, warnings: tuple[str, ...] = ()) -> PositionEstimate:
    ground_truth = getattr(raw_pose, "source_pose", None)
    error = compare_to_ground_truth(estimated, ground_truth)
    return PositionEstimate(
        worker_id=worker_id,
        tag_id=tag_id,
        timestamp_s=raw_pose.timestamp_s,
        time_step=raw_pose.time_step,
        estimated_position=estimated,
        ground_truth_position=ground_truth,
        source_trial=raw_pose.source_trial,
        solver_mode=str(_solver_config(config).get("position_source_mode", "mocap_proxy")),
        measurement_type=str(_solver_config(config).get("measurement_type", "tdoa")),
        used_measurement_count=len(used_measurements),
        used_anchor_count=len(used_anchor_ids),
        used_anchor_ids=used_anchor_ids,
        residual_rmse_m=residual_rmse_m,
        error_to_ground_truth_m=error,
        solver_status=status,
        confidence=estimate_confidence_from_solution(residual_rmse_m, len(used_anchor_ids), len(used_measurements), status, config),
        warnings=warnings,
    )


def solve_worker_positions_from_tdoa(config: dict | None = None, dataset_result: Any | None = None, extraction_result: Any | None = None) -> UWBPositionSolverResult:
    config = load_config() if config is None else config
    solver = _solver_config(config)
    enabled = bool(solver.get("enabled", False))
    mode = str(solver.get("position_source_mode", "mocap_proxy"))
    warnings: list[str] = []
    if not enabled or mode != "tdoa_solver":
        summary = {"enabled": enabled, "position_source_mode": mode, "estimate_count": 0, "warnings": ["UWB position solver disabled; existing mocap_proxy pipeline remains primary."]}
        validation = SolverValidationSummary(0, 0, 0, 0, None, None, None, None, None, None, tuple(summary["warnings"]))
        return UWBPositionSolverResult((), validation, summary)

    dataset = read_configured_dataset(config) if dataset_result is None else dataset_result
    extraction = extract_positions(config, dataset) if extraction_result is None else extraction_result
    anchors = load_anchor_calibration(config)
    fallback = bool(solver.get("fallback_to_mocap_proxy", True))
    if not anchors:
        warnings.append("missing calibration: no active calibrated anchors loaded")
    max_age = ensure_finite_number(solver.get("max_measurement_age_s", 0.5), "max_measurement_age_s")
    min_pairs = int(solver.get("min_anchor_pairs", 3))
    min_unique = int(solver.get("min_unique_anchors", 3))
    estimates: list[PositionEstimate] = []

    for worker in config.get("workers", []):
        worker_id = normalize_worker_id(worker["worker_id"])
        tag_id = normalize_tag_id(worker["tag_id"])
        worker_result = extraction.workers.get(worker_id)
        if worker_result is None:
            continue
        try:
            trial: TrialData = dataset.get_trial(worker["source_trial_hint"])
        except KeyError:
            continue
        measurements = build_uwb_measurements_from_trial(trial, worker, config)
        previous: Point3D | None = None
        for raw_pose in worker_result.raw_poses:
            if not anchors:
                if fallback:
                    estimates.append(_make_estimate(worker_id, tag_id, raw_pose, raw_pose.source_pose, "fallback_mocap_proxy", config, warnings=("fallback used because anchor calibration is missing",)))
                else:
                    estimates.append(_make_estimate(worker_id, tag_id, raw_pose, None, "missing_calibration", config, warnings=("anchor calibration is missing",)))
                continue
            nearby = group_measurements_by_time_window(measurements, raw_pose.timestamp_s - worker.get("time_offset_s", 0.0), max_age)
            if not nearby:
                estimates.append(_make_estimate(worker_id, tag_id, raw_pose, None, "no_measurements", config, warnings=("no TDoA measurements in configured time window",)))
                continue
            calibrated_nearby = tuple(
                item for item in nearby if item.anchor_id_a in anchors and item.anchor_id_b in anchors
            )
            used_anchor_ids = unique_anchor_ids_from_measurements(calibrated_nearby)
            if len(calibrated_nearby) < min_pairs or len(used_anchor_ids) < min_unique:
                estimates.append(_make_estimate(worker_id, tag_id, raw_pose, None, "insufficient_anchors", config, calibrated_nearby, used_anchor_ids, warnings=("insufficient calibrated anchor pairs for solve",)))
                continue
            initial = previous or raw_pose.source_pose or _average_anchor_position(anchors)
            estimate, residual_rmse_m, status, solve_warnings = solve_tdoa_position_gradient_descent(calibrated_nearby, anchors, initial, config)
            if status == "solved" and estimate is not None:
                previous = estimate
            estimates.append(_make_estimate(worker_id, tag_id, raw_pose, estimate, status, config, calibrated_nearby, used_anchor_ids, residual_rmse_m, solve_warnings))

    estimate_tuple = tuple(estimates)
    validation = build_solver_validation_summary(estimate_tuple)
    all_warnings = tuple(dict.fromkeys((*warnings, *validation.warnings)))
    summary = {
        "enabled": enabled,
        "position_source_mode": mode,
        "measurement_type": solver.get("measurement_type", "tdoa"),
        "estimate_count": len(estimate_tuple),
        "solved_count": validation.solved_count,
        "fallback_count": validation.fallback_count,
        "failed_count": validation.failed_count,
        "mean_error_m": validation.mean_error_m,
        "rmse_error_m": validation.rmse_error_m,
        "mean_residual_rmse_m": validation.mean_residual_rmse_m,
        "calibrated_anchor_count": len(anchors),
        "warnings": list(all_warnings),
    }
    return UWBPositionSolverResult(estimate_tuple, validation, summary)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


def build_solver_validation_summary(estimates: tuple[PositionEstimate, ...]) -> SolverValidationSummary:
    errors = [item.error_to_ground_truth_m for item in estimates if item.error_to_ground_truth_m is not None and item.solver_status == "solved"]
    residuals = [item.residual_rmse_m for item in estimates if item.residual_rmse_m is not None]
    solved_count = sum(item.solver_status == "solved" for item in estimates)
    fallback_count = sum(item.solver_status == "fallback_mocap_proxy" for item in estimates)
    failed_count = len(estimates) - solved_count - fallback_count
    warnings: list[str] = []
    statuses = {item.solver_status for item in estimates}
    if not estimates:
        warnings.append("solver produced no estimates")
    if fallback_count:
        warnings.append("fallback to mocap proxy was used")
    if "missing_calibration" in statuses or any("calibration" in warning for item in estimates for warning in item.warnings):
        warnings.append("missing calibration")
    if "insufficient_anchors" in statuses:
        warnings.append("insufficient anchors")
    if solved_count == 0 and estimates:
        warnings.append("no solved positions")
    mean_residual = (sum(residuals) / len(residuals)) if residuals else None
    if mean_residual is not None and mean_residual > 15.0:
        warnings.append("high RMSE")
    return SolverValidationSummary(
        estimate_count=len(estimates),
        solved_count=solved_count,
        fallback_count=fallback_count,
        failed_count=failed_count,
        mean_error_m=(sum(errors) / len(errors)) if errors else None,
        median_error_m=median(errors) if errors else None,
        rmse_error_m=math.sqrt(sum(value * value for value in errors) / len(errors)) if errors else None,
        p95_error_m=_percentile(errors, 0.95),
        max_error_m=max(errors) if errors else None,
        mean_residual_rmse_m=mean_residual,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def validate_solver_result(result: UWBPositionSolverResult) -> None:
    if not result.estimates:
        return
    for estimate in result.estimates:
        if not estimate.worker_id or not estimate.tag_id:
            raise ValueError("solver estimate worker_id/tag_id must be non-empty")
        normalize_worker_id(estimate.worker_id)
        normalize_tag_id(estimate.tag_id)
        if estimate.solver_status not in ALLOWED_SOLVER_STATUSES:
            raise ValueError(f"invalid solver status: {estimate.solver_status}")
        if not 0.0 <= estimate.confidence <= 1.0:
            raise ValueError("solver confidence must be in [0,1]")
        for point_name in ("estimated_position", "ground_truth_position"):
            point = getattr(estimate, point_name)
            if point is not None and not all(math.isfinite(value) for value in point.to_dict().values()):
                raise ValueError(f"{point_name} must be finite when present")
        if estimate.error_to_ground_truth_m is not None and estimate.error_to_ground_truth_m < 0:
            raise ValueError("solver error must be non-negative")
    json.dumps(to_jsonable(result), allow_nan=False)


def _self_check() -> None:
    config = load_config()
    result = solve_worker_positions_from_tdoa(config=config)
    validate_solver_result(result)
    print(json.dumps(result.summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _self_check()
    print("uwb_position_solver.py self-check passed")
