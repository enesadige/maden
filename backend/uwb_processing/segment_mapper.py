"""Map Haki-frame worker positions to canonical Haki segment IDs.

Segment mapping uses Haki bounds-center graph geometry. It is an MVP
approximation because exact tunnel centerline and calibrated UWB-to-mine
registration are not available.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from math import isfinite
from pathlib import Path
from typing import Any
import json
import sys

try:
    from backend.uwb_processing.core import (
        MappedPosition,
        Point3D,
        Segment,
        clamp,
        distance_3d,
        normalize_segment_id,
        normalize_worker_id,
        to_jsonable,
    )
    from backend.uwb_processing.config_loader import load_config
    from backend.uwb_processing.segment_loader import SegmentDataset, load_segment_dataset
    from backend.uwb_processing.coordinate_mapper import (
        CoordinateMappingResult,
        TransformedPose,
        map_coordinates,
    )
except ModuleNotFoundError:
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from backend.uwb_processing.core import (
        MappedPosition,
        Point3D,
        Segment,
        clamp,
        distance_3d,
        normalize_segment_id,
        normalize_worker_id,
        to_jsonable,
    )
    from backend.uwb_processing.config_loader import load_config
    from backend.uwb_processing.segment_loader import SegmentDataset, load_segment_dataset
    from backend.uwb_processing.coordinate_mapper import (
        CoordinateMappingResult,
        TransformedPose,
        map_coordinates,
    )


@dataclass(frozen=True)
class SegmentMatch:
    segment_id: str | None
    mapping_method: str
    mapping_confidence: float
    distance_m: float | None = None
    continuity_score: float = 1.0
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class SegmentMappingResult:
    mapped_positions: tuple[MappedPosition, ...]
    summary: dict[str, Any]

    def by_worker(self) -> dict[str, tuple[MappedPosition, ...]]:
        grouped: dict[str, list[MappedPosition]] = {}
        for position in self.mapped_positions:
            grouped.setdefault(position.worker_id, []).append(position)
        return {
            worker_id: tuple(sorted(items, key=lambda item: item.time_step))
            for worker_id, items in sorted(grouped.items())
        }

    def to_summary(self) -> dict[str, Any]:
        return to_jsonable(self.summary)


def segment_representative_point(segment: Segment) -> Point3D | None:
    if segment.center is not None:
        return segment.center
    if segment.bounds is not None:
        return segment.bounds.center()
    return None


def point_inside_segment_bounds(
    point: Point3D, segment: Segment, margin_m: float = 0.0
) -> bool:
    return segment.bounds is not None and segment.bounds.contains(point, margin=margin_m)


def distance_to_segment_representative(
    point: Point3D, segment: Segment
) -> float | None:
    representative = segment_representative_point(segment)
    return None if representative is None else distance_3d(point, representative)


def find_bounds_containing_segments(
    point: Point3D, dataset: SegmentDataset, margin_m: float = 0.0
) -> list[tuple[str, float]]:
    candidates: list[tuple[str, float]] = []
    for segment_id, segment in dataset.segments.items():
        if point_inside_segment_bounds(point, segment, margin_m):
            distance = distance_to_segment_representative(point, segment)
            candidates.append((segment_id, distance if distance is not None else 1.0e308))
    return sorted(candidates, key=lambda item: (item[1], item[0]))


def find_nearest_segments(
    point: Point3D, dataset: SegmentDataset, max_distance_m: float
) -> list[tuple[str, float]]:
    candidates = []
    for segment_id, segment in dataset.segments.items():
        distance = distance_to_segment_representative(point, segment)
        if distance is not None and distance <= max_distance_m:
            candidates.append((segment_id, distance))
    return sorted(candidates, key=lambda item: (item[1], item[0]))


def graph_distance_steps(
    dataset: SegmentDataset,
    start_segment: str,
    end_segment: str,
    max_depth: int = 5,
) -> int | None:
    start = normalize_segment_id(start_segment)
    end = normalize_segment_id(end_segment)
    if start == end:
        return 0
    if not dataset.has_segment(start) or not dataset.has_segment(end) or max_depth < 1:
        return None
    queue = deque([(start, 0)])
    visited = {start}
    while queue:
        current, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for neighbor in dataset.neighbors(current):
            if neighbor == end:
                return depth + 1
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, depth + 1))
    return None


def continuity_score_for_candidate(
    dataset: SegmentDataset,
    previous_segment: str | None,
    candidate_segment: str | None,
    config: dict,
) -> float:
    if candidate_segment is None:
        return 0.0
    if previous_segment is None:
        return 1.0
    previous = normalize_segment_id(previous_segment)
    candidate = normalize_segment_id(candidate_segment)
    if previous == candidate:
        return 1.0
    if dataset.is_graph_adjacent(previous, candidate):
        return 0.9
    steps = graph_distance_steps(dataset, previous, candidate, max_depth=5)
    if steps is not None and steps <= 2:
        return 0.7
    if steps is not None:
        return 0.4
    penalty = float(config["segment_mapping"]["graph_jump_penalty"])
    return clamp(1.0 - penalty)


def _rank_candidates(
    candidates: list[tuple[str, float]],
    dataset: SegmentDataset,
    previous_segment: str | None,
    config: dict,
    base_confidence_for_distance,
) -> tuple[str, float, float, float]:
    ranked = []
    for segment_id, distance in candidates:
        continuity = continuity_score_for_candidate(
            dataset, previous_segment, segment_id, config
        )
        base_confidence = base_confidence_for_distance(distance)
        final_confidence = clamp(base_confidence * continuity)
        ranked.append((segment_id, distance, continuity, final_confidence))
    return sorted(ranked, key=lambda item: (-item[3], item[1], item[0]))[0]


def choose_best_segment_candidate(
    point: Point3D,
    dataset: SegmentDataset,
    previous_segment: str | None,
    config: dict,
    start_segment: str | None = None,
) -> SegmentMatch:
    containing = find_bounds_containing_segments(point, dataset)
    if containing:
        segment_id, distance, continuity, confidence = _rank_candidates(
            containing, dataset, previous_segment, config, lambda _distance: 0.95
        )
        return SegmentMatch(
            segment_id, "bounds_contains", confidence, distance, continuity
        )

    maximum = float(config["segment_mapping"]["max_nearest_segment_distance_m"])
    soft_maximum = max(maximum, 60.0)
    nearest = find_nearest_segments(point, dataset, soft_maximum)
    if nearest:
        def nearest_confidence(distance: float) -> float:
            if distance <= maximum:
                return max(0.2, 1.0 - distance / maximum)
            soft_span = max(soft_maximum - maximum, 1.0)
            soft_fraction = (distance - maximum) / soft_span
            return clamp(0.35 - 0.25 * soft_fraction, 0.10, 0.35)

        segment_id, distance, continuity, confidence = _rank_candidates(
            nearest,
            dataset,
            previous_segment,
            config,
            nearest_confidence,
        )
        warnings = (
            ("soft nearest-center fallback used",) if distance > maximum else ()
        )
        if distance > maximum:
            confidence = clamp(confidence, 0.10, 0.35)
        return SegmentMatch(
            segment_id,
            "nearest_center",
            confidence,
            distance,
            continuity,
            warnings,
        )
    if previous_segment is not None:
        return SegmentMatch(
            normalize_segment_id(previous_segment),
            "continuity_fallback",
            0.20,
            None,
            0.4,
            ("approximate continuity fallback",),
        )
    if start_segment is not None:
        normalized_start = normalize_segment_id(start_segment)
        if dataset.has_segment(normalized_start):
            return SegmentMatch(
                normalized_start,
                "start_segment_seed",
                0.20,
                None,
                0.5,
                ("start segment seed used",),
            )
    return SegmentMatch(None, "unknown", 0.0, None, 0.0)


def map_single_transformed_pose(
    pose: TransformedPose,
    dataset: SegmentDataset,
    previous_segment: str | None,
    config: dict,
    start_segment: str | None = None,
) -> MappedPosition:
    match = choose_best_segment_candidate(
        pose.transformed_position,
        dataset,
        previous_segment,
        config,
        start_segment,
    )
    return MappedPosition(
        worker_id=pose.worker_id,
        tag_id=pose.tag_id,
        time_step=pose.time_step,
        timestamp_s=pose.timestamp_s,
        position=pose.transformed_position,
        current_segment=match.segment_id,
        mapping_method=match.mapping_method,
        mapping_confidence=match.mapping_confidence,
        continuity_score=match.continuity_score,
        flight_signal_reliability=pose.flight_signal_reliability,
        source_trial=pose.source_trial,
        source_position_type=pose.source_position_type,
    )


def map_worker_positions(
    poses: tuple[TransformedPose, ...], dataset: SegmentDataset, config: dict
) -> tuple[MappedPosition, ...]:
    grouped: dict[str, list[TransformedPose]] = {}
    for pose in poses:
        grouped.setdefault(pose.worker_id, []).append(pose)
    worker_start_segments = {
        normalize_worker_id(worker["worker_id"]): normalize_segment_id(
            worker["start_segment"]
        )
        for worker in config["workers"]
        if worker.get("start_segment") is not None
    }
    mapped = []
    for worker_id in sorted(grouped):
        previous_segment = None
        for pose in sorted(grouped[worker_id], key=lambda item: (item.time_step, item.timestamp_s)):
            position = map_single_transformed_pose(
                pose,
                dataset,
                previous_segment,
                config,
                worker_start_segments.get(worker_id),
            )
            mapped.append(position)
            if position.current_segment is not None:
                previous_segment = position.current_segment
    return tuple(sorted(mapped, key=lambda item: (item.time_step, item.worker_id)))


def build_mapping_summary(
    mapped_positions: tuple[MappedPosition, ...],
    coordinate_result: CoordinateMappingResult,
    dataset: SegmentDataset,
    config: dict,
) -> dict[str, Any]:
    del coordinate_result, dataset, config
    count = len(mapped_positions)
    known = sum(item.current_segment is not None for item in mapped_positions)
    unknown = count - known
    visited = sorted(
        {item.current_segment for item in mapped_positions if item.current_segment is not None}
    )
    method_counts = Counter(item.mapping_method for item in mapped_positions)
    fallback_count = (
        method_counts.get("continuity_fallback", 0)
        + method_counts.get("start_segment_seed", 0)
    )
    confidences = [item.mapping_confidence for item in mapped_positions]
    continuity = [item.continuity_score for item in mapped_positions]
    warnings = [
        "segment mapping uses bounds-center graph geometry and approximate bounds-fit coordinates"
    ]
    if fallback_count:
        warnings.append(
            "fallback segment assignment was used; confidence values should be interpreted carefully"
        )
    if unknown:
        warnings.append("some positions remain unmapped")
    nearest_count = method_counts.get("nearest_center", 0)
    if count and nearest_count > count / 2:
        warnings.append(
            "many positions required nearest-center fallback; coordinate transform may need calibration"
        )
    return {
        "mapped_position_count": count,
        "worker_count": len({item.worker_id for item in mapped_positions}),
        "known_segment_count": known,
        "unknown_segment_count": unknown,
        "unique_segments_visited": visited,
        "unique_segments_visited_count": len(visited),
        "mapping_methods": {
            name: method_counts.get(name, 0)
            for name in (
                "bounds_contains",
                "nearest_center",
                "continuity_fallback",
                "start_segment_seed",
                "unknown",
            )
        },
        "known_ratio": round(known / count, 4) if count else 0.0,
        "unknown_ratio": round(unknown / count, 4) if count else 0.0,
        "fallback_count": fallback_count,
        "fallback_ratio": round(fallback_count / count, 4) if count else 0.0,
        "mean_mapping_confidence": round(sum(confidences) / count, 4) if count else 0.0,
        "min_mapping_confidence": round(min(confidences), 4) if confidences else 0.0,
        "mean_continuity_score": round(sum(continuity) / count, 4) if count else 0.0,
        "warnings": warnings,
    }


def validate_segment_mapping(
    result: SegmentMappingResult, dataset: SegmentDataset
) -> None:
    if not result.mapped_positions:
        raise ValueError("segment mapping contains no positions")
    allowed_methods = {
        "bounds_contains",
        "nearest_center",
        "continuity_fallback",
        "start_segment_seed",
        "unknown",
    }
    for position in result.mapped_positions:
        if position.current_segment is not None and not dataset.has_segment(
            position.current_segment
        ):
            raise ValueError(f"unknown mapped segment: {position.current_segment}")
        if not position.worker_id or not position.tag_id:
            raise ValueError("mapped worker_id and tag_id must be non-empty")
        if position.time_step < 0:
            raise ValueError("mapped time_step must be non-negative")
        coordinates = (position.position.x, position.position.y, position.position.z)
        if not all(isfinite(value) for value in coordinates):
            raise ValueError("mapped position must have finite coordinates")
        if not 0.0 <= position.mapping_confidence <= 1.0:
            raise ValueError("mapping_confidence must be in [0, 1]")
        if not 0.0 <= position.continuity_score <= 1.0:
            raise ValueError("continuity_score must be in [0, 1]")
        if position.mapping_method not in allowed_methods:
            raise ValueError(f"unsupported mapping method: {position.mapping_method}")
    if result.summary.get("mapped_position_count") != len(result.mapped_positions):
        raise ValueError("mapping summary count does not match mapped positions")


def map_segments(
    coordinate_result: CoordinateMappingResult | None = None,
    dataset: SegmentDataset | None = None,
    config: dict | None = None,
) -> SegmentMappingResult:
    config = load_config() if config is None else config
    dataset = load_segment_dataset(config) if dataset is None else dataset
    coordinate_result = (
        map_coordinates(config=config, dataset=dataset)
        if coordinate_result is None
        else coordinate_result
    )
    mapped_positions = map_worker_positions(
        coordinate_result.transformed_poses, dataset, config
    )
    summary = build_mapping_summary(
        mapped_positions, coordinate_result, dataset, config
    )
    result = SegmentMappingResult(mapped_positions, summary)
    validate_segment_mapping(result, dataset)
    return result


def _self_check() -> None:
    config = load_config()
    dataset = load_segment_dataset(config)
    coordinate_result = map_coordinates(dataset=dataset, config=config)
    result = map_segments(coordinate_result=coordinate_result, dataset=dataset, config=config)
    validate_segment_mapping(result, dataset)
    assert result.mapped_positions
    assert result.summary["known_segment_count"] > 0
    assert all(
        item.current_segment is None or dataset.has_segment(item.current_segment)
        for item in result.mapped_positions
    )
    assert result.summary["worker_count"] == coordinate_result.summary["worker_count"]
    assert result.summary["fallback_count"] > 0
    assert result.summary["known_ratio"] > 0.9
    assert result.summary["mapping_methods"]["continuity_fallback"] > 0
    print(json.dumps(result.to_summary(), separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    _self_check()
    print("segment_mapper.py self-check passed")
