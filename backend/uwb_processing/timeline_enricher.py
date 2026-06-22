"""Enrich worker timelines with anchor-derived tracking estimates.

Tracking status and reliability are estimated using anchor distance, approximate
graph visibility, mapping confidence and continuity. This is not certified safety
localization and not calibrated RF positioning.

No-visible-anchor records are retained instead of being removed. They represent
no_tracking states and must remain visible in the output for safety debugging.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from math import isfinite
from pathlib import Path
from typing import Any
import json
import sys

try:
    from backend.uwb_processing.core import (
        WorkerTimelineRecord, compute_position_reliability,
        tracking_status_from_visible_count, tracking_risk_score_from_reliability,
        reliability_status, clamp, to_jsonable,
    )
    from backend.uwb_processing.config_loader import load_config
    from backend.uwb_processing.timeline_builder import TimelineBuildResult, build_timeline
    from backend.uwb_processing.distance_matrix import (
        DistanceMatrixResult, WorkerAnchorVisibility, compute_distance_matrix,
    )
except ModuleNotFoundError:
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from backend.uwb_processing.core import (
        WorkerTimelineRecord, compute_position_reliability,
        tracking_status_from_visible_count, tracking_risk_score_from_reliability,
        reliability_status, clamp, to_jsonable,
    )
    from backend.uwb_processing.config_loader import load_config
    from backend.uwb_processing.timeline_builder import TimelineBuildResult, build_timeline
    from backend.uwb_processing.distance_matrix import (
        DistanceMatrixResult, WorkerAnchorVisibility, compute_distance_matrix,
    )


@dataclass(frozen=True)
class EnrichedWorkerLatestSnapshot:
    worker_id: str
    tag_id: str
    time_step: int
    timestamp_s: float
    current_segment: str | None
    position: Any
    position_reliability: float
    reliability_status: str
    status: str
    visible_anchor_count: int
    visible_anchors: tuple[str, ...]
    tracking_status: str
    tracking_risk_score: float
    mean_signal_quality_est: float
    nearest_anchor_id: str | None
    nearest_anchor_distance_3d_m: float | None
    mapping_method: str
    mapping_confidence: float
    continuity_score: float
    flight_signal_reliability: float
    source_trial: str
    source_position_type: str = "mocap_ground_truth"

    def to_dict(self) -> dict[str, Any]:
        position = self.position.to_dict() if hasattr(self.position, "to_dict") else to_jsonable(self.position)
        return {
            "worker_id": self.worker_id, "tag_id": self.tag_id,
            "time_step": self.time_step, "timestamp_s": self.timestamp_s,
            "current_segment": self.current_segment, "position": position,
            "position_reliability": self.position_reliability,
            "reliability_status": self.reliability_status, "status": self.status,
            "mapped_segment_id": self.current_segment, "uwb_pose": dict(position),
            "motion_status": self.status,
            "visible_anchor_count": self.visible_anchor_count,
            "visible_anchors": list(self.visible_anchors),
            "tracking_status": self.tracking_status,
            "tracking_risk_score": self.tracking_risk_score,
            "mean_signal_quality_est": self.mean_signal_quality_est,
            "nearest_anchor_id": self.nearest_anchor_id,
            "nearest_anchor_distance_3d_m": self.nearest_anchor_distance_3d_m,
            "mapping_method": self.mapping_method,
            "mapping_confidence": self.mapping_confidence,
            "continuity_score": self.continuity_score,
            "flight_signal_reliability": self.flight_signal_reliability,
            "source_trial": self.source_trial,
            "source_position_type": self.source_position_type,
            "source": "uwb_tracking",
        }


@dataclass(frozen=True)
class TimelineEnrichmentResult:
    enriched_timeline: tuple[WorkerTimelineRecord, ...]
    latest_workers: tuple[EnrichedWorkerLatestSnapshot, ...]
    summary: dict[str, Any]

    def by_worker(self) -> dict[str, tuple[WorkerTimelineRecord, ...]]:
        grouped: dict[str, list[WorkerTimelineRecord]] = {}
        for record in self.enriched_timeline:
            grouped.setdefault(record.worker_id, []).append(record)
        return {
            worker_id: tuple(sorted(records, key=lambda item: (item.time_step, item.timestamp_s)))
            for worker_id, records in sorted(grouped.items())
        }

    def to_summary(self) -> dict[str, Any]:
        return to_jsonable(self.summary)


def status_from_tracking(tracking_status: str, position_reliability: float, current_segment: str | None) -> str:
    if current_segment is None:
        return "unknown"
    if tracking_status == "no_tracking":
        return "tracking_lost"
    if position_reliability < 0.30:
        return "low_confidence"
    return "safe"


def mean_quality_from_visibility(visibility: WorkerAnchorVisibility | None) -> float:
    return 0.0 if visibility is None else clamp(visibility.mean_signal_quality_est)


def enrich_timeline_record(record: WorkerTimelineRecord, visibility: WorkerAnchorVisibility | None, config: dict) -> WorkerTimelineRecord:
    visible_count = visibility.visible_anchor_count if visibility else 0
    visible_anchors = visibility.visible_anchors if visibility else ()
    minimum = int(config.get("anchor_placement", {}).get("min_visible_anchors_2d", 3))
    tracking_status = tracking_status_from_visible_count(visible_count, minimum)
    position_reliability = compute_position_reliability(
        flight_signal_reliability=record.flight_signal_reliability,
        visible_anchor_count=visible_count, min_visible_anchors=minimum,
        mean_signal_quality_est=mean_quality_from_visibility(visibility),
        mapping_confidence=record.mapping_confidence,
        continuity_score=record.continuity_score,
        weights=config.get("reliability_weights"),
    )
    if record.mapping_method == "continuity_fallback":
        position_reliability = min(position_reliability, 0.45)
    elif record.mapping_method == "start_segment_seed":
        position_reliability = min(position_reliability, 0.40)
    if record.current_segment is None:
        position_reliability = min(position_reliability, 0.25)
    position_reliability = round(clamp(position_reliability), 4)
    return replace(
        record, visible_anchor_count=visible_count, visible_anchors=tuple(visible_anchors),
        tracking_status=tracking_status, position_reliability=position_reliability,
        reliability_status=reliability_status(position_reliability),
        status=status_from_tracking(tracking_status, position_reliability, record.current_segment),
    )


def enrich_timeline_records(timeline_result: TimelineBuildResult, distance_result: DistanceMatrixResult, config: dict) -> tuple[WorkerTimelineRecord, ...]:
    enriched = (
        enrich_timeline_record(
            record,
            distance_result.visibility_for_worker_time(record.worker_id, record.time_step),
            config,
        )
        for record in timeline_result.timeline
    )
    return tuple(sorted(enriched, key=lambda item: (item.time_step, item.worker_id)))


def build_latest_enriched_snapshots(enriched_timeline: tuple[WorkerTimelineRecord, ...], distance_result: DistanceMatrixResult) -> tuple[EnrichedWorkerLatestSnapshot, ...]:
    grouped: dict[str, list[WorkerTimelineRecord]] = {}
    for record in enriched_timeline:
        grouped.setdefault(record.worker_id, []).append(record)
    snapshots = []
    for worker_id in sorted(grouped):
        record = max(grouped[worker_id], key=lambda item: (item.time_step, item.timestamp_s))
        visibility = distance_result.visibility_for_worker_time(record.worker_id, record.time_step)
        snapshots.append(EnrichedWorkerLatestSnapshot(
            worker_id=record.worker_id, tag_id=record.tag_id, time_step=record.time_step,
            timestamp_s=record.timestamp_s, current_segment=record.current_segment,
            position=record.position, position_reliability=record.position_reliability,
            reliability_status=record.reliability_status, status=record.status,
            visible_anchor_count=record.visible_anchor_count,
            visible_anchors=record.visible_anchors, tracking_status=record.tracking_status,
            tracking_risk_score=round(tracking_risk_score_from_reliability(record.position_reliability), 4),
            mean_signal_quality_est=mean_quality_from_visibility(visibility),
            nearest_anchor_id=visibility.nearest_anchor_id if visibility else None,
            nearest_anchor_distance_3d_m=visibility.nearest_anchor_distance_3d_m if visibility else None,
            mapping_method=record.mapping_method, mapping_confidence=record.mapping_confidence,
            continuity_score=record.continuity_score,
            flight_signal_reliability=record.flight_signal_reliability,
            source_trial=record.source_trial, source_position_type=record.source_position_type,
        ))
    return tuple(snapshots)


def build_enrichment_summary(enriched_timeline: tuple[WorkerTimelineRecord, ...], timeline_result: TimelineBuildResult, distance_result: DistanceMatrixResult, config: dict) -> dict[str, Any]:
    del timeline_result, config
    count = len(enriched_timeline)
    tracking_counts = Counter(item.tracking_status for item in enriched_timeline)
    status_counts = Counter(item.status for item in enriched_timeline)
    reliability_counts = Counter(item.reliability_status for item in enriched_timeline)
    reliabilities = [item.position_reliability for item in enriched_timeline]
    visible_counts = [item.visible_anchor_count for item in enriched_timeline]
    fallback_count = sum(item.mapping_method in {"continuity_fallback", "start_segment_seed"} for item in enriched_timeline)
    no_visible = tracking_counts.get("no_tracking", 0)
    warnings = [
        "Tracking status and reliability are estimated using anchor distance, approximate graph visibility, mapping confidence and continuity. This is not certified safety localization and not calibrated RF positioning.",
        "anchor visibility uses an approximate RF/graph visibility model",
    ]
    if no_visible:
        warnings.append(f"{no_visible} no-visible-anchor records are retained as no_tracking")
    if fallback_count:
        warnings.append("fallback segment assignments remain low-confidence in enriched records")
    return {
        "timeline_record_count": count,
        "worker_count": len({item.worker_id for item in enriched_timeline}),
        "latest_worker_count": len({item.worker_id for item in enriched_timeline}),
        "tracking_status_counts": {name: tracking_counts.get(name, 0) for name in ("full_tracking", "degraded_tracking", "weak_tracking", "no_tracking")},
        "status_counts": {name: status_counts.get(name, 0) for name in ("safe", "tracking_lost", "low_confidence", "unknown")},
        "reliability_status_counts": {name: reliability_counts.get(name, 0) for name in ("good", "degraded", "poor")},
        "min_position_reliability": min(reliabilities) if reliabilities else 0.0,
        "mean_position_reliability": round(sum(reliabilities) / count, 4) if count else 0.0,
        "max_position_reliability": max(reliabilities) if reliabilities else 0.0,
        "min_visible_anchor_count": min(visible_counts) if visible_counts else 0,
        "mean_visible_anchor_count": round(sum(visible_counts) / count, 4) if count else 0.0,
        "max_visible_anchor_count": max(visible_counts) if visible_counts else 0,
        "records_with_no_visible_anchors": no_visible,
        "records_with_full_tracking": tracking_counts.get("full_tracking", 0),
        "fallback_record_count": fallback_count,
        "distance_observation_count": distance_result.summary.get("observation_count", 0),
        "warnings": warnings,
    }


def validate_enrichment_result(result: TimelineEnrichmentResult, timeline_result: TimelineBuildResult) -> None:
    if len(result.enriched_timeline) != len(timeline_result.timeline):
        raise ValueError("enriched timeline count does not match base timeline")
    if not result.latest_workers:
        raise ValueError("no latest enriched worker snapshots")
    tracking_allowed = {"full_tracking", "degraded_tracking", "weak_tracking", "no_tracking"}
    reliability_allowed = {"good", "degraded", "poor"}
    status_allowed = {"safe", "tracking_lost", "low_confidence", "unknown"}
    for record in result.enriched_timeline:
        if not all(isfinite(value) for value in record.position.to_dict().values()):
            raise ValueError("enriched position must be finite")
        if record.visible_anchor_count < 0 or not 0.0 <= record.position_reliability <= 1.0:
            raise ValueError("invalid visibility count or reliability")
        if record.tracking_status not in tracking_allowed or record.reliability_status not in reliability_allowed or record.status not in status_allowed:
            raise ValueError("invalid enriched status")
        if record.source_position_type != "mocap_ground_truth":
            raise ValueError("unexpected source position type")
    required = {"mapped_segment_id", "uwb_pose", "motion_status", "current_segment", "position", "position_reliability", "tracking_status", "visible_anchor_count"}
    for snapshot in result.latest_workers:
        if not required.issubset(snapshot.to_dict()):
            raise ValueError("latest snapshot lacks compatibility fields")
    if result.summary.get("timeline_record_count") != len(result.enriched_timeline):
        raise ValueError("enrichment summary count mismatch")


def enrich_timeline(timeline_result: TimelineBuildResult | None = None, distance_result: DistanceMatrixResult | None = None, config: dict | None = None) -> TimelineEnrichmentResult:
    config = load_config() if config is None else config
    timeline_result = build_timeline(config=config) if timeline_result is None else timeline_result
    distance_result = compute_distance_matrix(timeline_result=timeline_result, config=config) if distance_result is None else distance_result
    enriched = enrich_timeline_records(timeline_result, distance_result, config)
    latest = build_latest_enriched_snapshots(enriched, distance_result)
    result = TimelineEnrichmentResult(enriched, latest, build_enrichment_summary(enriched, timeline_result, distance_result, config))
    validate_enrichment_result(result, timeline_result)
    return result


def _self_check() -> None:
    config = load_config()
    timeline_result = build_timeline(config=config)
    distance_result = compute_distance_matrix(timeline_result=timeline_result, config=config)
    result = enrich_timeline(timeline_result, distance_result, config)
    validate_enrichment_result(result, timeline_result)
    assert len(result.enriched_timeline) == len(timeline_result.timeline)
    assert result.latest_workers
    assert all(record.tracking_status != "pending_anchor_enrichment" for record in result.enriched_timeline)
    if distance_result.summary["records_with_full_tracking_candidate"]:
        assert any(record.tracking_status == "full_tracking" for record in result.enriched_timeline)
    for snapshot in result.latest_workers:
        payload = snapshot.to_dict()
        for field_name in ("mapped_segment_id", "uwb_pose", "motion_status"):
            assert field_name in payload
        assert payload["mapped_segment_id"] == payload["current_segment"]
        assert payload["uwb_pose"] == payload["position"]
        assert payload["motion_status"] == payload["status"]
    print(json.dumps(result.to_summary(), separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    _self_check()
    print("timeline_enricher.py self-check passed")
