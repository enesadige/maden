"""Assign and resample configured UTIL movement-proxy positions per worker.

UTIL UWB pose_x, pose_y and pose_z values are motion-capture ground-truth proxy positions, not real UWB-estimated miner positions. In this MVP they are used only as worker movement proxies.

Worker count is entirely configuration-driven. This module does not transform
coordinates, map segments, write outputs, or duplicate trajectories silently.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
import json
import math
from typing import Any

try:
    from .config_loader import load_config
    from .core import (
        RawPose,
        clamp,
        ensure_finite_number,
        normalize_tag_id,
        normalize_worker_id,
    )
    from .dataset_reader import (
        DatasetReadResult,
        PoseSample,
        TDoASample,
        TrialData,
        read_configured_dataset,
    )
except ImportError:  # Supports ``python backend/uwb_processing/position_extractor.py``.
    from config_loader import load_config  # type: ignore
    from core import (  # type: ignore
        RawPose,
        clamp,
        ensure_finite_number,
        normalize_tag_id,
        normalize_worker_id,
    )
    from dataset_reader import (  # type: ignore
        DatasetReadResult,
        PoseSample,
        TDoASample,
        TrialData,
        read_configured_dataset,
    )


@dataclass(frozen=True)
class WorkerExtractionResult:
    worker_id: str
    tag_id: str
    source_trial_hint: str
    source_csv_path: str
    raw_poses: tuple[RawPose, ...]
    sample_rate_hz: float
    time_offset_s: float
    rejected_time_steps: int = 0
    warnings: tuple[str, ...] = field(default_factory=tuple)
    flight_signal_reliabilities: tuple[float, ...] = field(default_factory=tuple)

    def to_summary(self) -> dict[str, Any]:
        timestamps = [pose.timestamp_s for pose in self.raw_poses]
        time_min = min(timestamps) if timestamps else None
        time_max = max(timestamps) if timestamps else None
        reliabilities = self.flight_signal_reliabilities
        return {
            "worker_id": self.worker_id,
            "tag_id": self.tag_id,
            "source_trial_hint": self.source_trial_hint,
            "source_csv_path": self.source_csv_path,
            "raw_pose_count": len(self.raw_poses),
            "sample_rate_hz": self.sample_rate_hz,
            "time_offset_s": self.time_offset_s,
            "time_min_s": time_min,
            "time_max_s": time_max,
            "duration_s": (time_max - time_min) if timestamps else None,
            "rejected_time_steps": self.rejected_time_steps,
            "average_flight_signal_reliability": (
                round(sum(reliabilities) / len(reliabilities), 4)
                if reliabilities
                else None
            ),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class PositionExtractionResult:
    workers: dict[str, WorkerExtractionResult]
    summary: dict[str, Any]

    def all_raw_poses(self) -> tuple[RawPose, ...]:
        return tuple(
            sorted(
                (
                    pose
                    for worker_result in self.workers.values()
                    for pose in worker_result.raw_poses
                ),
                key=lambda pose: (pose.time_step, pose.worker_id),
            )
        )

    def to_summary(self) -> dict[str, Any]:
        return dict(self.summary)


def get_worker_config_map(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    workers = config.get("workers")
    if not isinstance(workers, list) or not workers:
        raise ValueError("config.workers must be a non-empty list")
    result: dict[str, dict[str, Any]] = {}
    for index, raw_worker in enumerate(workers):
        if not isinstance(raw_worker, dict):
            raise ValueError(f"config.workers[{index}] must be an object")
        worker = dict(raw_worker)
        if "worker_id" not in worker or "tag_id" not in worker:
            raise ValueError(f"config.workers[{index}] requires worker_id and tag_id")
        hint = worker.get("source_trial_hint")
        if not isinstance(hint, str) or not hint.strip():
            raise ValueError(f"config.workers[{index}].source_trial_hint must be non-empty")
        worker_id = normalize_worker_id(worker["worker_id"])
        if worker_id in result:
            raise ValueError(f"duplicate worker_id: {worker_id}")
        worker["worker_id"] = worker_id
        worker["tag_id"] = normalize_tag_id(worker["tag_id"])
        worker["source_trial_hint"] = hint.strip()
        worker["time_offset_s"] = ensure_finite_number(
            worker.get("time_offset_s", 0.0), f"{worker_id}.time_offset_s"
        )
        result[worker_id] = worker
    return result


def nearest_pose_sample(
    trial: TrialData, target_time_s: float, tolerance_s: float
) -> PoseSample | None:
    target = ensure_finite_number(target_time_s, "target_time_s")
    tolerance = ensure_finite_number(tolerance_s, "tolerance_s")
    if tolerance < 0.0:
        raise ValueError("tolerance_s must be non-negative")
    if not trial.pose_samples:
        return None
    timestamps = [sample.timestamp_s for sample in trial.pose_samples]
    insertion = bisect_left(timestamps, target)
    indices = [index for index in (insertion - 1, insertion) if 0 <= index < len(timestamps)]
    nearest = min(
        (trial.pose_samples[index] for index in indices),
        key=lambda sample: (abs(sample.timestamp_s - target), sample.row_index),
    )
    return nearest if abs(nearest.timestamp_s - target) <= tolerance else None


def tdoa_samples_near_time(
    trial: TrialData, target_time_s: float, window_s: float
) -> tuple[TDoASample, ...]:
    target = ensure_finite_number(target_time_s, "target_time_s")
    window = ensure_finite_number(window_s, "window_s")
    if window < 0.0:
        raise ValueError("window_s must be non-negative")
    timestamps = [sample.timestamp_s for sample in trial.tdoa_samples]
    left = bisect_left(timestamps, target - window)
    right = bisect_right(timestamps, target + window)
    return trial.tdoa_samples[left:right]


def estimate_flight_signal_reliability(
    trial: TrialData,
    target_time_s: float,
    tdoa_window_s: float = 0.5,
) -> tuple[float, int, int]:
    nearby = tdoa_samples_near_time(trial, target_time_s, tdoa_window_s)
    sample_count = len(nearby)
    pair_count = len({(sample.anchor_a, sample.anchor_b) for sample in nearby})
    if not nearby:
        return 0.5, 0, 0
    density_score = min(sample_count / 8.0, 1.0)
    pair_score = min(pair_count / 4.0, 1.0)
    reliability = clamp(0.6 * density_score + 0.4 * pair_score)
    return round(reliability, 4), sample_count, pair_count


def build_resample_time_grid(
    trial: TrialData,
    sample_rate_hz: float,
    time_offset_s: float = 0.0,
) -> tuple[float, ...]:
    rate = ensure_finite_number(sample_rate_hz, "sample_rate_hz")
    ensure_finite_number(time_offset_s, "time_offset_s")
    if rate <= 0.0:
        raise ValueError("sample_rate_hz must be greater than zero")
    if not trial.pose_samples:
        return ()
    first = trial.pose_samples[0].timestamp_s
    last = trial.pose_samples[-1].timestamp_s
    step = 1.0 / rate
    estimated_count = int(math.floor((last - first) / step)) + 1
    if estimated_count > 1_000_000:
        raise ValueError("resample grid exceeds the one-million-step safety limit")
    return tuple(first + index * step for index in range(max(estimated_count, 1)))


def extract_worker_positions(
    worker_config: dict[str, Any],
    trial: TrialData,
    sample_rate_hz: float,
    tolerance_s: float = 0.5,
    tdoa_window_s: float = 0.5,
) -> WorkerExtractionResult:
    worker_id = normalize_worker_id(worker_config["worker_id"])
    tag_id = normalize_tag_id(worker_config["tag_id"])
    hint = worker_config.get("source_trial_hint")
    if not isinstance(hint, str) or not hint.strip():
        raise ValueError(f"{worker_id}.source_trial_hint must be non-empty")
    offset = ensure_finite_number(worker_config.get("time_offset_s", 0.0), "time_offset_s")
    rate = ensure_finite_number(sample_rate_hz, "sample_rate_hz")
    grid = build_resample_time_grid(trial, rate, offset)
    raw_poses: list[RawPose] = []
    reliabilities: list[float] = []
    rejected = 0
    for time_step, source_time in enumerate(grid):
        sample = nearest_pose_sample(trial, source_time, tolerance_s)
        if sample is None:
            rejected += 1
            continue
        reliability, tdoa_count, pair_count = estimate_flight_signal_reliability(
            trial, source_time, tdoa_window_s
        )
        raw_poses.append(
            RawPose(
                worker_id=worker_id,
                tag_id=tag_id,
                time_step=time_step,
                timestamp_s=source_time + offset,
                source_trial=hint.strip(),
                source_pose=sample.position,
                tdoa_sample_count=tdoa_count,
                anchor_pair_count=pair_count,
                source_position_type="mocap_ground_truth",
            )
        )
        reliabilities.append(reliability)
    if not raw_poses:
        raise ValueError(f"no resampled pose records were extracted for {worker_id}")
    warnings = list(trial.warnings)
    if rejected:
        warnings.append(f"{rejected} resample time step(s) had no nearby pose")
    return WorkerExtractionResult(
        worker_id=worker_id,
        tag_id=tag_id,
        source_trial_hint=hint.strip(),
        source_csv_path=trial.csv_path,
        raw_poses=tuple(raw_poses),
        sample_rate_hz=rate,
        time_offset_s=offset,
        rejected_time_steps=rejected,
        warnings=tuple(warnings),
        flight_signal_reliabilities=tuple(reliabilities),
    )


def build_extraction_summary(
    worker_results: dict[str, WorkerExtractionResult],
    dataset_result: DatasetReadResult,
    config: dict[str, Any],
) -> dict[str, Any]:
    summaries = [worker_results[worker_id].to_summary() for worker_id in sorted(worker_results)]
    all_reliabilities = [
        reliability
        for worker in worker_results.values()
        for reliability in worker.flight_signal_reliabilities
    ]
    all_timestamps = [
        pose.timestamp_s
        for worker in worker_results.values()
        for pose in worker.raw_poses
    ]
    missing_workers = len(config["workers"]) - len(worker_results)
    warnings = [f"{missing_workers} configured worker(s) were skipped"] if missing_workers else []
    return {
        "worker_count_configured": len(config["workers"]),
        "worker_count_extracted": len(worker_results),
        "sample_rate_hz": ensure_finite_number(config["sample_rate_hz"], "sample_rate_hz"),
        "source_position_type": "mocap_ground_truth",
        "total_raw_pose_records": sum(len(worker.raw_poses) for worker in worker_results.values()),
        "total_rejected_time_steps": sum(
            worker.rejected_time_steps for worker in worker_results.values()
        ),
        "matched_trial_count": len(dataset_result.matched_trials),
        "unmatched_hints": list(dataset_result.unmatched_hints),
        "time_min_s": min(all_timestamps) if all_timestamps else None,
        "time_max_s": max(all_timestamps) if all_timestamps else None,
        "average_flight_signal_reliability": (
            round(sum(all_reliabilities) / len(all_reliabilities), 4)
            if all_reliabilities
            else None
        ),
        "worker_summaries": summaries,
        "warnings": warnings,
        "limitation": (
            "UTIL UWB pose_x, pose_y and pose_z values are motion-capture "
            "ground-truth proxy positions, not real UWB-estimated miner positions. "
            "In this MVP they are used only as worker movement proxies."
        ),
    }


def extract_positions(
    config: dict[str, Any] | None = None,
    dataset_result: DatasetReadResult | None = None,
) -> PositionExtractionResult:
    normalized_config = load_config() if config is None else config
    dataset = (
        read_configured_dataset(normalized_config)
        if dataset_result is None
        else dataset_result
    )
    worker_map = get_worker_config_map(normalized_config)
    results: dict[str, WorkerExtractionResult] = {}
    for worker in normalized_config["workers"]:
        worker_id = normalize_worker_id(worker["worker_id"])
        normalized_worker = worker_map[worker_id]
        hint = normalized_worker["source_trial_hint"]
        try:
            trial = dataset.get_trial(hint)
        except KeyError:
            continue
        results[worker_id] = extract_worker_positions(
            normalized_worker,
            trial,
            normalized_config["sample_rate_hz"],
        )
    if not results:
        raise ValueError("no configured workers could be extracted from matched trials")
    return PositionExtractionResult(
        workers=results,
        summary=build_extraction_summary(results, dataset, normalized_config),
    )


def _self_check() -> None:
    config = load_config()
    dataset_result = read_configured_dataset(config)
    result = extract_positions(config, dataset_result)
    assert result.workers
    assert len(result.workers) <= len(config["workers"])
    assert all(worker.raw_poses for worker in result.workers.values())
    assert all(
        pose.source_position_type == "mocap_ground_truth"
        and all(
            math.isfinite(value)
            for value in (pose.source_pose.x, pose.source_pose.y, pose.source_pose.z)
        )
        for worker in result.workers.values()
        for pose in worker.raw_poses
    )
    print(json.dumps(result.to_summary(), ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    _self_check()
    print("position_extractor.py self-check passed")
