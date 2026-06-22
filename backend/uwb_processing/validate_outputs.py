"""Validate all in-memory UWB handoff contracts before file writing.

Validation distinguishes between MVP limitations and structural errors.
Approximate mapping, fallback mapping and no_tracking records are warnings;
invalid IDs, non-finite coordinates and broken backend contracts are failures.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json
import math
import re
import sys

try:
    from backend.uwb_processing.core import to_jsonable
    from backend.uwb_processing.config_loader import load_config
    from backend.uwb_processing.segment_loader import SegmentDataset, load_segment_dataset
    from backend.uwb_processing.anchor_planner import AnchorPlanResult, plan_anchors
    from backend.uwb_processing.cable_planner import CablePlanResult, plan_cables
    from backend.uwb_processing.timeline_builder import TimelineBuildResult, build_timeline
    from backend.uwb_processing.distance_matrix import DistanceMatrixResult, compute_distance_matrix
    from backend.uwb_processing.timeline_enricher import TimelineEnrichmentResult, enrich_timeline
    from backend.uwb_processing.exposure_builder import ExposureBuildResult, build_exposure
except ModuleNotFoundError:
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from backend.uwb_processing.core import to_jsonable
    from backend.uwb_processing.config_loader import load_config
    from backend.uwb_processing.segment_loader import SegmentDataset, load_segment_dataset
    from backend.uwb_processing.anchor_planner import AnchorPlanResult, plan_anchors
    from backend.uwb_processing.cable_planner import CablePlanResult, plan_cables
    from backend.uwb_processing.timeline_builder import TimelineBuildResult, build_timeline
    from backend.uwb_processing.distance_matrix import DistanceMatrixResult, compute_distance_matrix
    from backend.uwb_processing.timeline_enricher import TimelineEnrichmentResult, enrich_timeline
    from backend.uwb_processing.exposure_builder import ExposureBuildResult, build_exposure


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    code: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.severity not in {"error", "warning", "info"}:
            raise ValueError(f"invalid validation severity: {self.severity}")

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class OutputValidationResult:
    ok: bool
    error_count: int
    warning_count: int
    info_count: int
    issues: tuple[ValidationIssue, ...]
    summary: dict[str, Any]

    def errors(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "error")

    def warnings(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "warning")

    def to_summary(self) -> dict[str, Any]:
        return to_jsonable(self.summary)


def is_finite_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(float(value))


def point_is_finite(point: Any) -> bool:
    try:
        values = point.to_dict() if hasattr(point, "to_dict") else point
        return all(is_finite_number(values[name]) for name in ("x", "y", "z"))
    except (KeyError, TypeError, AttributeError):
        return False


def add_issue(issues: list[ValidationIssue], severity: str, code: str, message: str, **context: Any) -> None:
    issues.append(ValidationIssue(severity, code, message, context))


def assert_json_serializable(name: str, obj: Any, issues: list[ValidationIssue]) -> None:
    try:
        json.dumps(to_jsonable(obj), allow_nan=False)
    except (TypeError, ValueError, OverflowError) as exc:
        add_issue(issues, "error", "json_serialization_failed", f"{name} is not JSON serializable", error=str(exc))


def count_by(items: Any, key_func: Any) -> dict[str, int]:
    return dict(sorted(Counter(str(key_func(item)) for item in items).items()))


def validate_anchor_plan_contract(anchor_plan: AnchorPlanResult, dataset: SegmentDataset, issues: list[ValidationIssue]) -> None:
    anchors = anchor_plan.anchors
    if not anchors:
        add_issue(issues, "error", "anchors_empty", "anchor plan contains no anchors")
    ids = [anchor.anchor_id for anchor in anchors]
    if len(ids) != len(set(ids)):
        add_issue(issues, "error", "anchor_ids_duplicate", "anchor IDs are not unique")
    for anchor in anchors:
        if not re.fullmatch(r"A\d{3}", anchor.anchor_id):
            add_issue(issues, "error", "anchor_id_invalid", "invalid anchor ID", anchor_id=anchor.anchor_id)
        if not dataset.has_segment(anchor.segment_id):
            add_issue(issues, "error", "anchor_segment_invalid", "anchor references unknown segment", anchor_id=anchor.anchor_id)
        if not point_is_finite(anchor.position) or not is_finite_number(anchor.coverage_radius_m) or anchor.coverage_radius_m <= 0:
            add_issue(issues, "error", "anchor_geometry_invalid", "anchor position or coverage is invalid", anchor_id=anchor.anchor_id)
        if not anchor.status:
            add_issue(issues, "error", "anchor_status_missing", "anchor status is missing", anchor_id=anchor.anchor_id)
    undercovered = int(anchor_plan.coverage_report.get("undercovered_segment_count", 0))
    if undercovered:
        add_issue(issues, "warning", "segments_undercovered", "some segments are below target anchor coverage", count=undercovered)
    assert_json_serializable("anchor_plan", anchor_plan, issues)


def validate_cable_plan_contract(cable_plan: CablePlanResult, anchor_plan: AnchorPlanResult, dataset: SegmentDataset, issues: list[ValidationIssue]) -> None:
    cables = cable_plan.cables
    if not cables:
        add_issue(issues, "error", "cables_empty", "cable plan contains no links")
    cable_ids = [getattr(cable, "cable_id", "") for cable in cables]
    if len(cable_ids) != len(set(cable_ids)):
        add_issue(issues, "error", "cable_ids_duplicate", "cable IDs are not unique")
    anchor_ids = {anchor.anchor_id for anchor in anchor_plan.anchors}
    for cable in cables:
        if cable.from_anchor not in anchor_ids or cable.to_anchor not in anchor_ids:
            add_issue(issues, "error", "cable_anchor_invalid", "cable references unknown anchor", cable_id=cable.cable_id)
        for segment_id in cable.segment_path:
            if not dataset.has_segment(segment_id):
                add_issue(issues, "error", "cable_segment_invalid", "cable references unknown segment", cable_id=cable.cable_id, segment_id=segment_id)
        length = getattr(cable, "length_m", None)
        if length is not None and (not is_finite_number(length) or length < 0):
            add_issue(issues, "error", "cable_length_invalid", "cable length is invalid", cable_id=cable.cable_id)
    add_issue(issues, "info", "cable_routing_approximate", "cable routing uses the bounds-based tunnel wall approximation", routing_surface=cable_plan.cable_report.get("routing_surface"))
    assert_json_serializable("cable_plan", cable_plan, issues)


def validate_timeline_contract(timeline_result: TimelineBuildResult, dataset: SegmentDataset, issues: list[ValidationIssue]) -> None:
    if not timeline_result.timeline:
        add_issue(issues, "error", "timeline_empty", "base timeline is empty")
    if not timeline_result.latest_workers:
        add_issue(issues, "error", "latest_workers_empty", "base latest worker list is empty")
    for record in timeline_result.timeline:
        if not record.worker_id or not record.tag_id:
            add_issue(issues, "error", "timeline_identity_missing", "timeline worker or tag ID is missing")
        if not point_is_finite(record.position) or record.time_step < 0:
            add_issue(issues, "error", "timeline_position_invalid", "timeline position or time step is invalid", worker_id=record.worker_id)
        if record.current_segment is not None and not dataset.has_segment(record.current_segment):
            add_issue(issues, "error", "timeline_segment_invalid", "timeline references unknown segment", segment_id=record.current_segment)
        for name, value in (("position_reliability", record.position_reliability), ("mapping_confidence", record.mapping_confidence), ("continuity_score", record.continuity_score)):
            if not is_finite_number(value) or not 0 <= value <= 1:
                add_issue(issues, "error", "timeline_score_invalid", f"{name} is outside [0,1]", worker_id=record.worker_id)
        if record.source_position_type != "mocap_ground_truth":
            add_issue(issues, "error", "source_position_type_invalid", "unexpected timeline source position type")
    required = {"mapped_segment_id", "uwb_pose", "motion_status", "current_segment", "position", "position_reliability", "status"}
    for latest in timeline_result.latest_workers:
        payload = latest.to_dict()
        if not required.issubset(payload):
            add_issue(issues, "error", "latest_worker_contract_missing", "base latest worker lacks compatibility fields", worker_id=latest.worker_id)
        elif payload["mapped_segment_id"] != payload["current_segment"] or payload["uwb_pose"] != payload["position"] or payload["motion_status"] != payload["status"]:
            add_issue(issues, "error", "latest_worker_contract_mismatch", "base latest worker compatibility aliases differ", worker_id=latest.worker_id)
    assert_json_serializable("timeline_result", timeline_result, issues)


def validate_distance_matrix_contract(distance_result: DistanceMatrixResult, timeline_result: TimelineBuildResult, anchor_plan: AnchorPlanResult, issues: list[ValidationIssue]) -> None:
    expected = len(timeline_result.timeline) * len(anchor_plan.anchors)
    if len(distance_result.observations) != expected:
        add_issue(issues, "error", "distance_count_mismatch", "distance observation count is inconsistent", expected=expected, actual=len(distance_result.observations))
    anchor_ids = {anchor.anchor_id for anchor in anchor_plan.anchors}
    for observation in distance_result.observations:
        if not observation.worker_id or not observation.tag_id or observation.anchor_id not in anchor_ids:
            add_issue(issues, "error", "distance_identity_invalid", "distance observation references invalid IDs")
        if any(not is_finite_number(value) or value < 0 for value in (observation.distance_2d_m, observation.distance_3d_m)):
            add_issue(issues, "error", "distance_value_invalid", "distance is non-finite or negative")
        if observation.coverage_radius_m <= 0 or not 0 <= observation.signal_quality_est <= 1:
            add_issue(issues, "error", "distance_signal_invalid", "coverage or signal quality is invalid")
        if not isinstance(observation.visible, bool) or not isinstance(observation.within_range, bool):
            add_issue(issues, "error", "distance_flag_invalid", "distance visibility flags are not boolean")
    for record in timeline_result.timeline:
        visibility = distance_result.visibility_for_worker_time(record.worker_id, record.time_step)
        if visibility is None:
            add_issue(issues, "error", "visibility_entry_missing", "worker/time visibility entry is missing", worker_id=record.worker_id, time_step=record.time_step)
        elif visibility.visible_anchor_count < 0:
            add_issue(issues, "error", "visibility_count_invalid", "visible anchor count is negative")
    no_visible = int(distance_result.summary.get("records_with_no_visible_anchors", 0))
    if no_visible:
        add_issue(issues, "warning", "no_visible_anchors", "some worker-time records have no visible anchors", count=no_visible)
    # The tuple-keyed visibility mapping is an internal lookup. Validate the
    # JSON output shape as a list so worker/time keys remain explicit fields.
    assert_json_serializable(
        "distance_result",
        {
            "observations": distance_result.observations,
            "visibility_by_worker_time": tuple(
                distance_result.visibility_by_worker_time.values()
            ),
            "summary": distance_result.summary,
        },
        issues,
    )


def validate_enriched_timeline_contract(enrichment_result: TimelineEnrichmentResult, timeline_result: TimelineBuildResult, distance_result: DistanceMatrixResult, dataset: SegmentDataset, issues: list[ValidationIssue]) -> None:
    del distance_result
    if len(enrichment_result.enriched_timeline) != len(timeline_result.timeline):
        add_issue(issues, "error", "enriched_count_mismatch", "enriched and base timeline counts differ")
    unique_workers = {record.worker_id for record in enrichment_result.enriched_timeline}
    if len(enrichment_result.latest_workers) != len(unique_workers):
        add_issue(issues, "error", "latest_worker_count_mismatch", "latest worker count differs from dynamic worker count")
    tracking_allowed = {"full_tracking", "degraded_tracking", "weak_tracking", "no_tracking"}
    status_allowed = {"safe", "tracking_lost", "low_confidence", "unknown"}
    reliability_allowed = {"good", "degraded", "poor"}
    for record in enrichment_result.enriched_timeline:
        if record.tracking_status not in tracking_allowed or record.status not in status_allowed or record.reliability_status not in reliability_allowed:
            add_issue(issues, "error", "enriched_status_invalid", "enriched status value is invalid", worker_id=record.worker_id)
        if record.visible_anchor_count < 0 or len(record.visible_anchors) != record.visible_anchor_count:
            add_issue(issues, "error", "enriched_visibility_invalid", "visible anchor list and count differ", worker_id=record.worker_id)
        if not 0 <= record.position_reliability <= 1 or not point_is_finite(record.position):
            add_issue(issues, "error", "enriched_position_invalid", "enriched position or reliability is invalid")
        if record.current_segment is not None and not dataset.has_segment(record.current_segment):
            add_issue(issues, "error", "enriched_segment_invalid", "enriched record references unknown segment")
    required = {"mapped_segment_id", "uwb_pose", "motion_status", "tracking_status", "visible_anchor_count"}
    for latest in enrichment_result.latest_workers:
        payload = latest.to_dict()
        if not required.issubset(payload):
            add_issue(issues, "error", "enriched_latest_contract_missing", "enriched latest worker lacks backend fields", worker_id=latest.worker_id)
        risk = payload.get("tracking_risk_score")
        if risk is not None and (not is_finite_number(risk) or not 0 <= risk <= 100):
            add_issue(issues, "error", "tracking_risk_invalid", "tracking risk is outside [0,100]", worker_id=latest.worker_id)
    no_tracking = sum(record.tracking_status == "no_tracking" for record in enrichment_result.enriched_timeline)
    fallback = sum(record.mapping_method in {"continuity_fallback", "start_segment_seed"} for record in enrichment_result.enriched_timeline)
    if no_tracking:
        add_issue(issues, "warning", "no_tracking_records", "no_tracking records are retained for safety debugging", count=no_tracking)
    if fallback:
        add_issue(issues, "warning", "fallback_mapping_records", "fallback segment mapping is present", count=fallback)
    assert_json_serializable("enrichment_result", enrichment_result, issues)


def validate_exposure_contract(exposure_result: ExposureBuildResult, enrichment_result: TimelineEnrichmentResult, dataset: SegmentDataset, issues: list[ValidationIssue]) -> None:
    if len(exposure_result.exposure_records) != len(enrichment_result.enriched_timeline):
        add_issue(issues, "error", "exposure_count_mismatch", "exposure and enriched timeline counts differ")
    for record in exposure_result.exposure_records:
        if not record.worker_id or not record.tag_id or record.time_step < 0 or not point_is_finite(record.position):
            add_issue(issues, "error", "exposure_record_invalid", "exposure identity, time, or position is invalid")
        if not 0 <= record.position_reliability <= 1 or not 0 <= record.tracking_risk_score <= 100 or not 0 <= record.worker_exposure_risk <= 100:
            add_issue(issues, "error", "exposure_score_invalid", "exposure score is out of range")
        if record.segment_id is not None:
            if not dataset.has_segment(record.segment_id) or record.worker_exposure_risk != 100.0 or record.risk_level != "critical":
                add_issue(issues, "error", "exposure_rule_violated", "mapped worker exposure must be 100 and critical", worker_id=record.worker_id)
        elif record.worker_exposure_risk != 0.0:
            add_issue(issues, "error", "exposure_rule_violated", "unmapped worker exposure must be zero", worker_id=record.worker_id)
    for summary in exposure_result.segment_summaries:
        if not dataset.has_segment(summary.segment_id):
            add_issue(issues, "error", "exposure_summary_segment_invalid", "exposure summary references unknown segment")
    add_issue(issues, "warning", "exposure_not_fused_risk", "worker exposure is occupancy contribution only and not fused risk")
    assert_json_serializable("exposure_result", exposure_result, issues)


def validate_cross_consistency(anchor_plan: AnchorPlanResult, cable_plan: CablePlanResult, timeline_result: TimelineBuildResult, distance_result: DistanceMatrixResult, enrichment_result: TimelineEnrichmentResult, exposure_result: ExposureBuildResult, dataset: SegmentDataset, issues: list[ValidationIssue]) -> None:
    del cable_plan
    counts = (len(timeline_result.timeline), len(enrichment_result.enriched_timeline), len(exposure_result.exposure_records))
    if len(set(counts)) != 1:
        add_issue(issues, "error", "cross_timeline_count_mismatch", "timeline, enrichment and exposure counts differ", counts=counts)
    if len(distance_result.observations) != counts[0] * len(anchor_plan.anchors):
        add_issue(issues, "error", "cross_distance_count_mismatch", "distance matrix does not equal timeline × anchors")
    enriched_workers = {record.worker_id for record in enrichment_result.enriched_timeline}
    exposure_workers = {record.worker_id for record in exposure_result.exposure_records}
    if len(enrichment_result.latest_workers) != len(enriched_workers) or exposure_workers != enriched_workers:
        add_issue(issues, "error", "cross_worker_mismatch", "worker sets are inconsistent")
    if any(record.current_segment is not None and not dataset.has_segment(record.current_segment) for record in enrichment_result.enriched_timeline):
        add_issue(issues, "error", "cross_segment_invalid", "visited worker segment is not in Haki dataset")
    if all(record.segment_id is not None for record in exposure_result.exposure_records) and any(latest.current_segment is None for latest in enrichment_result.latest_workers):
        add_issue(issues, "error", "cross_latest_segment_missing", "latest worker lacks segment despite complete exposure mapping")
    count = max(counts[0], 1)
    fallback_ratio = sum(record.mapping_method in {"continuity_fallback", "start_segment_seed"} for record in enrichment_result.enriched_timeline) / count
    no_tracking_ratio = sum(record.tracking_status == "no_tracking" for record in enrichment_result.enriched_timeline) / count
    mean_mapping = sum(record.mapping_confidence for record in enrichment_result.enriched_timeline) / count
    mean_reliability = sum(record.position_reliability for record in enrichment_result.enriched_timeline) / count
    if fallback_ratio >= 0.25:
        add_issue(issues, "warning", "fallback_ratio_high", "fallback mapping ratio is high", ratio=round(fallback_ratio, 4))
    if no_tracking_ratio >= 0.25:
        add_issue(issues, "warning", "no_tracking_ratio_high", "no_tracking ratio is high", ratio=round(no_tracking_ratio, 4))
    if mean_mapping < 0.5:
        add_issue(issues, "warning", "mean_mapping_confidence_low", "mean mapping confidence is low", value=round(mean_mapping, 4))
    if mean_reliability < 0.6:
        add_issue(issues, "warning", "mean_reliability_low", "mean enriched position reliability is low", value=round(mean_reliability, 4))


def build_validation_summary(issues: tuple[ValidationIssue, ...], anchor_plan: AnchorPlanResult, cable_plan: CablePlanResult, timeline_result: TimelineBuildResult, distance_result: DistanceMatrixResult, enrichment_result: TimelineEnrichmentResult, exposure_result: ExposureBuildResult, dataset: SegmentDataset) -> dict[str, Any]:
    error_count = sum(issue.severity == "error" for issue in issues)
    warning_messages = [issue.message for issue in issues if issue.severity == "warning"]
    return {
        "ok": error_count == 0,
        "error_count": error_count,
        "warning_count": sum(issue.severity == "warning" for issue in issues),
        "info_count": sum(issue.severity == "info" for issue in issues),
        "segment_count": len(dataset.segments), "anchor_count": len(anchor_plan.anchors),
        "cable_link_count": len(cable_plan.cables), "timeline_record_count": len(timeline_result.timeline),
        "distance_observation_count": len(distance_result.observations),
        "enriched_timeline_record_count": len(enrichment_result.enriched_timeline),
        "exposure_record_count": len(exposure_result.exposure_records),
        "latest_worker_count": len(enrichment_result.latest_workers),
        "segments_with_worker_exposure": len(exposure_result.segment_summaries),
        "records_with_no_tracking": sum(record.tracking_status == "no_tracking" for record in enrichment_result.enriched_timeline),
        "fallback_record_count": sum(record.mapping_method in {"continuity_fallback", "start_segment_seed"} for record in enrichment_result.enriched_timeline),
        "ready_for_pipeline_write": error_count == 0,
        "warnings": warning_messages,
    }


def validate_all_outputs(config: dict | None = None, dataset: SegmentDataset | None = None, anchor_plan: AnchorPlanResult | None = None, cable_plan: CablePlanResult | None = None, timeline_result: TimelineBuildResult | None = None, distance_result: DistanceMatrixResult | None = None, enrichment_result: TimelineEnrichmentResult | None = None, exposure_result: ExposureBuildResult | None = None) -> OutputValidationResult:
    config = load_config() if config is None else config
    dataset = load_segment_dataset(config) if dataset is None else dataset
    anchor_plan = plan_anchors(dataset=dataset, config=config) if anchor_plan is None else anchor_plan
    cable_plan = plan_cables(dataset=dataset, anchor_plan=anchor_plan, config=config) if cable_plan is None else cable_plan
    timeline_result = build_timeline(config=config) if timeline_result is None else timeline_result
    distance_result = compute_distance_matrix(timeline_result=timeline_result, anchor_plan=anchor_plan, dataset=dataset, config=config) if distance_result is None else distance_result
    enrichment_result = enrich_timeline(timeline_result=timeline_result, distance_result=distance_result, config=config) if enrichment_result is None else enrichment_result
    exposure_result = build_exposure(enrichment_result=enrichment_result, dataset=dataset, config=config) if exposure_result is None else exposure_result
    issues: list[ValidationIssue] = []
    validate_anchor_plan_contract(anchor_plan, dataset, issues)
    validate_cable_plan_contract(cable_plan, anchor_plan, dataset, issues)
    validate_timeline_contract(timeline_result, dataset, issues)
    validate_distance_matrix_contract(distance_result, timeline_result, anchor_plan, issues)
    validate_enriched_timeline_contract(enrichment_result, timeline_result, distance_result, dataset, issues)
    validate_exposure_contract(exposure_result, enrichment_result, dataset, issues)
    validate_cross_consistency(anchor_plan, cable_plan, timeline_result, distance_result, enrichment_result, exposure_result, dataset, issues)
    issue_tuple = tuple(issues)
    summary = build_validation_summary(issue_tuple, anchor_plan, cable_plan, timeline_result, distance_result, enrichment_result, exposure_result, dataset)
    return OutputValidationResult(summary["ok"], summary["error_count"], summary["warning_count"], summary["info_count"], issue_tuple, summary)


def _self_check() -> None:
    result = validate_all_outputs(load_config())
    print(json.dumps(result.to_summary(), separators=(",", ":"), sort_keys=True))
    if not result.ok:
        print(json.dumps([issue.to_dict() for issue in result.errors()], separators=(",", ":")))
        raise AssertionError("in-memory output validation failed")
    assert result.summary["ready_for_pipeline_write"] is True
    assert result.summary["timeline_record_count"] == result.summary["enriched_timeline_record_count"] == result.summary["exposure_record_count"]
    assert result.summary["distance_observation_count"] == result.summary["timeline_record_count"] * result.summary["anchor_count"]


if __name__ == "__main__":
    _self_check()
    print("validate_outputs.py self-check passed")
