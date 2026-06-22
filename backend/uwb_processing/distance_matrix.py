"""Compute the in-memory UWB anchor-tag distance matrix.

Anchor visibility is estimated using distance, coverage radius and graph/segment
constraints. This is not a calibrated RF propagation or exact line-of-sight model.
Cable topology is infrastructure connectivity only. Anchor visibility for tracking
is calculated separately from cable links.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Any
import json
import sys

try:
    from backend.uwb_processing.core import (
        Anchor, DistanceObservation, WorkerTimelineRecord, distance_2d, distance_3d,
        signal_quality_from_distance, normalize_anchor_id, to_jsonable,
    )
    from backend.uwb_processing.config_loader import load_config
    from backend.uwb_processing.segment_loader import SegmentDataset, load_segment_dataset
    from backend.uwb_processing.anchor_planner import AnchorPlanResult, plan_anchors
    from backend.uwb_processing.timeline_builder import TimelineBuildResult, build_timeline
except ModuleNotFoundError:
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from backend.uwb_processing.core import (
        Anchor, DistanceObservation, WorkerTimelineRecord, distance_2d, distance_3d,
        signal_quality_from_distance, normalize_anchor_id, to_jsonable,
    )
    from backend.uwb_processing.config_loader import load_config
    from backend.uwb_processing.segment_loader import SegmentDataset, load_segment_dataset
    from backend.uwb_processing.anchor_planner import AnchorPlanResult, plan_anchors
    from backend.uwb_processing.timeline_builder import TimelineBuildResult, build_timeline


@dataclass(frozen=True)
class WorkerAnchorVisibility:
    worker_id: str
    tag_id: str
    time_step: int
    timestamp_s: float
    current_segment: str | None
    visible_anchor_count: int
    visible_anchors: tuple[str, ...]
    mean_signal_quality_est: float
    nearest_anchor_id: str | None
    nearest_anchor_distance_3d_m: float | None

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class DistanceMatrixResult:
    observations: tuple[DistanceObservation, ...]
    visibility_by_worker_time: dict[tuple[str, int], WorkerAnchorVisibility]
    summary: dict[str, Any]

    def observations_for_worker_time(self, worker_id: str, time_step: int) -> tuple[DistanceObservation, ...]:
        return tuple(item for item in self.observations if item.worker_id == worker_id and item.time_step == time_step)

    def visibility_for_worker_time(self, worker_id: str, time_step: int) -> WorkerAnchorVisibility | None:
        return self.visibility_by_worker_time.get((worker_id, time_step))

    def to_summary(self) -> dict[str, Any]:
        return to_jsonable(self.summary)


def anchor_lookup(anchors: tuple[Anchor, ...]) -> dict[str, Anchor]:
    lookup: dict[str, Anchor] = {}
    for anchor in anchors:
        anchor_id = normalize_anchor_id(anchor.anchor_id)
        if anchor_id in lookup:
            raise ValueError(f"duplicate anchor ID: {anchor_id}")
        lookup[anchor_id] = anchor
    return lookup


def graph_distance_steps(dataset: SegmentDataset, start_segment: str | None, end_segment: str | None, max_depth: int = 3) -> int | None:
    if start_segment is None or end_segment is None:
        return None
    if start_segment == end_segment:
        return 0
    queue = deque([(start_segment, 0)])
    visited = {start_segment}
    while queue:
        current, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for neighbor in dataset.neighbors(current):
            if neighbor == end_segment:
                return depth + 1
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, depth + 1))
    return None


def graph_visibility_allowed(dataset: SegmentDataset, worker_segment: str | None, anchor_segment: str, max_graph_steps: int = 2) -> tuple[bool, str]:
    if worker_segment is None:
        return False, "worker_segment_unknown"
    steps = graph_distance_steps(dataset, worker_segment, anchor_segment, max_graph_steps)
    if steps == 0:
        return True, "same_segment"
    if steps == 1:
        return True, "graph_adjacent"
    if steps is not None:
        return True, "nearby_graph_segment"
    return False, "graph_too_far"


def compute_distance_observation(record: WorkerTimelineRecord, anchor: Anchor, dataset: SegmentDataset, config: dict) -> DistanceObservation:
    distance_2d_m = distance_2d(record.position, anchor.position)
    distance_3d_m = distance_3d(record.position, anchor.position)
    within_range = distance_3d_m <= anchor.coverage_radius_m
    max_steps = int(config.get("anchor_placement", {}).get("max_visibility_graph_steps", 2))
    graph_allowed, graph_reason = graph_visibility_allowed(dataset, record.current_segment, anchor.segment_id, max_steps)
    visible = anchor.status == "active" and within_range and graph_allowed
    if anchor.status != "active":
        reason = "inactive_anchor"
    elif not within_range:
        reason = "out_of_range"
    elif not graph_allowed:
        reason = graph_reason
    else:
        reason = "visible"
    return DistanceObservation(
        time_step=record.time_step, worker_id=record.worker_id, tag_id=record.tag_id,
        current_segment=record.current_segment, worker_position=record.position,
        anchor_id=anchor.anchor_id, anchor_segment=anchor.segment_id,
        anchor_position=anchor.position, distance_2d_m=round(distance_2d_m, 4),
        distance_3d_m=round(distance_3d_m, 4), coverage_radius_m=anchor.coverage_radius_m,
        within_range=within_range, anchor_status=anchor.status, visible=visible,
        signal_quality_est=round(signal_quality_from_distance(distance_3d_m, anchor.coverage_radius_m), 4),
        visibility_reason=reason,
    )


def compute_observations_for_record(record: WorkerTimelineRecord, anchors: tuple[Anchor, ...], dataset: SegmentDataset, config: dict) -> tuple[DistanceObservation, ...]:
    return tuple(sorted((compute_distance_observation(record, anchor, dataset, config) for anchor in anchors), key=lambda item: item.anchor_id))


def build_worker_anchor_visibility(record: WorkerTimelineRecord, observations: tuple[DistanceObservation, ...]) -> WorkerAnchorVisibility:
    visible = sorted((item for item in observations if item.visible), key=lambda item: item.anchor_id)
    nearest = min(observations, key=lambda item: (item.distance_3d_m, item.anchor_id)) if observations else None
    return WorkerAnchorVisibility(
        worker_id=record.worker_id, tag_id=record.tag_id, time_step=record.time_step,
        timestamp_s=record.timestamp_s, current_segment=record.current_segment,
        visible_anchor_count=len(visible), visible_anchors=tuple(item.anchor_id for item in visible),
        mean_signal_quality_est=round(sum(item.signal_quality_est for item in visible) / len(visible), 4) if visible else 0.0,
        nearest_anchor_id=nearest.anchor_id if nearest else None,
        nearest_anchor_distance_3d_m=nearest.distance_3d_m if nearest else None,
    )


def build_distance_summary(observations: tuple[DistanceObservation, ...], visibility_by_worker_time: dict[tuple[str, int], WorkerAnchorVisibility], timeline_result: TimelineBuildResult, anchor_plan: AnchorPlanResult) -> dict[str, Any]:
    visibility = list(visibility_by_worker_time.values())
    counts = [item.visible_anchor_count for item in visibility]
    qualities = [item.mean_signal_quality_est for item in visibility]
    minimum_required = int(anchor_plan.coverage_report.get("min_visible_anchors_2d", 3))
    no_visible = sum(count == 0 for count in counts)
    warnings = ["Anchor visibility is estimated using distance, coverage radius and graph/segment constraints. This is not a calibrated RF propagation or exact line-of-sight model."]
    if no_visible:
        warnings.append(f"{no_visible} worker-time records have no visible anchors")
    return {
        "observation_count": len(observations), "timeline_record_count": len(timeline_result.timeline),
        "anchor_count": len(anchor_plan.anchors), "worker_time_count": len(visibility),
        "worker_count": len({item.worker_id for item in visibility}),
        "min_visible_anchor_count": min(counts) if counts else 0,
        "mean_visible_anchor_count": round(sum(counts) / len(counts), 4) if counts else 0.0,
        "max_visible_anchor_count": max(counts) if counts else 0,
        "records_with_full_tracking_candidate": sum(count >= minimum_required for count in counts),
        "records_with_no_visible_anchors": no_visible,
        "mean_signal_quality_est": round(sum(qualities) / len(qualities), 4) if qualities else 0.0,
        "warnings": warnings,
    }


def validate_distance_matrix(result: DistanceMatrixResult, timeline_result: TimelineBuildResult, anchor_plan: AnchorPlanResult) -> None:
    expected = len(timeline_result.timeline) * len(anchor_plan.anchors)
    if not result.observations:
        raise ValueError("distance matrix contains no observations")
    if len(result.observations) != expected:
        raise ValueError(f"distance matrix size mismatch: expected {expected}, got {len(result.observations)}")
    for item in result.observations:
        if not item.worker_id or not item.tag_id or not item.anchor_id:
            raise ValueError("distance observation IDs must be non-empty")
        if not isfinite(item.distance_2d_m) or not isfinite(item.distance_3d_m) or item.distance_2d_m < 0 or item.distance_3d_m < 0:
            raise ValueError("distances must be finite and non-negative")
        if not 0.0 <= item.signal_quality_est <= 1.0 or item.coverage_radius_m <= 0:
            raise ValueError("invalid signal quality or coverage radius")
        if not isinstance(item.within_range, bool) or not isinstance(item.visible, bool):
            raise ValueError("range and visibility flags must be bool")
    for record in timeline_result.timeline:
        key = (record.worker_id, record.time_step)
        visibility = result.visibility_by_worker_time.get(key)
        if visibility is None:
            raise ValueError(f"missing visibility record: {key}")
        actual = sum(item.visible for item in result.observations_for_worker_time(*key))
        if visibility.visible_anchor_count != actual:
            raise ValueError(f"visible anchor count mismatch: {key}")
    if result.summary.get("observation_count") != len(result.observations):
        raise ValueError("distance summary count mismatch")


def compute_distance_matrix(timeline_result: TimelineBuildResult | None = None, anchor_plan: AnchorPlanResult | None = None, dataset: SegmentDataset | None = None, config: dict | None = None) -> DistanceMatrixResult:
    config = load_config() if config is None else config
    dataset = load_segment_dataset(config) if dataset is None else dataset
    anchor_plan = plan_anchors(dataset=dataset, config=config) if anchor_plan is None else anchor_plan
    timeline_result = build_timeline(config=config) if timeline_result is None else timeline_result
    anchor_lookup(anchor_plan.anchors)
    observations: list[DistanceObservation] = []
    visibility: dict[tuple[str, int], WorkerAnchorVisibility] = {}
    for record in timeline_result.timeline:
        record_observations = compute_observations_for_record(record, anchor_plan.anchors, dataset, config)
        observations.extend(record_observations)
        key = (record.worker_id, record.time_step)
        if key in visibility:
            raise ValueError(f"duplicate worker/time key: {key}")
        visibility[key] = build_worker_anchor_visibility(record, record_observations)
    observations_tuple = tuple(observations)
    result = DistanceMatrixResult(observations_tuple, visibility, build_distance_summary(observations_tuple, visibility, timeline_result, anchor_plan))
    validate_distance_matrix(result, timeline_result, anchor_plan)
    return result


def _self_check() -> None:
    config = load_config()
    dataset = load_segment_dataset(config)
    anchor_plan = plan_anchors(dataset=dataset, config=config)
    timeline_result = build_timeline(config=config)
    result = compute_distance_matrix(timeline_result, anchor_plan, dataset, config)
    validate_distance_matrix(result, timeline_result, anchor_plan)
    assert result.summary["observation_count"] == len(timeline_result.timeline) * len(anchor_plan.anchors)
    assert result.summary["worker_time_count"] == len(timeline_result.timeline)
    assert any(item.visible_anchor_count > 0 for item in result.visibility_by_worker_time.values())
    print(json.dumps(result.to_summary(), separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    _self_check()
    print("distance_matrix.py self-check passed")
