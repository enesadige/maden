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
    from backend.uwb_processing.behavior_anomaly_builder import (
        ALLOWED_EVENT_TYPES, ALLOWED_SEVERITIES, BehaviorAnomalyBuildResult,
        build_behavior_anomalies, validate_behavior_anomaly_result,
    )
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
    from backend.uwb_processing.behavior_anomaly_builder import (
        ALLOWED_EVENT_TYPES, ALLOWED_SEVERITIES, BehaviorAnomalyBuildResult,
        build_behavior_anomalies, validate_behavior_anomaly_result,
    )


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


def _behavior_anomaly_config(config: dict[str, Any]) -> dict[str, Any]:
    raw = config.get("behavior_anomaly") or {}
    if not isinstance(raw, dict):
        raise ValueError("behavior_anomaly must be an object when provided")
    return raw


def behavior_anomaly_enabled(config: dict[str, Any]) -> bool:
    return bool(_behavior_anomaly_config(config).get("enabled", True))


def _empty_anomaly_summary(enabled: bool = False) -> dict[str, Any]:
    return {
        "anomaly_event_count": 0,
        "anomaly_event_count_by_type": {event_type: 0 for event_type in sorted(ALLOWED_EVENT_TYPES)},
        "anomaly_warning_count": 0,
        "anomaly_validation_ok": True,
        "anomaly_enabled": enabled,
    }


def _event_record(event: Any) -> dict[str, Any]:
    if hasattr(event, "to_dict"):
        return dict(event.to_dict())
    if isinstance(event, dict):
        return dict(event)
    return dict(to_jsonable(event))


def _validate_behavior_anomaly_records(
    events: list[dict[str, Any]],
    summary: dict[str, Any] | None,
    dataset: SegmentDataset,
    enrichment_result: TimelineEnrichmentResult,
    issues: list[ValidationIssue],
) -> dict[str, Any]:
    before_errors = sum(issue.severity == "error" for issue in issues)
    before_warnings = sum(issue.severity == "warning" for issue in issues)
    event_ids: set[str] = set()
    known_workers = {record.worker_id for record in enrichment_result.enriched_timeline}
    type_counts: Counter[str] = Counter()
    if not events:
        add_issue(issues, "warning", "anomaly_events_empty", "behavior anomaly validation found zero events")
    if not dataset.blocked_segments:
        add_issue(issues, "warning", "anomaly_no_blocked_segments", "no blocked segments exist; near_blocked_segment may be absent")
    if not dataset.risky_segments and not dataset.geometry_risk_by_segment:
        add_issue(issues, "warning", "anomaly_no_high_risk_segments", "no high risk segment data exists; high-risk anomaly rules may be absent")
    for index, event in enumerate(events):
        event_id = event.get("event_id")
        if not isinstance(event_id, str) or not event_id.strip():
            add_issue(issues, "error", "anomaly_event_id_missing", "behavior anomaly event_id is missing", index=index)
        elif event_id in event_ids:
            add_issue(issues, "error", "anomaly_event_id_duplicate", "behavior anomaly event_id is not unique", event_id=event_id)
        else:
            event_ids.add(event_id)
        worker_id = event.get("worker_id")
        if not isinstance(worker_id, str) or not worker_id.strip():
            add_issue(issues, "error", "anomaly_worker_id_missing", "behavior anomaly worker_id is missing", event_id=event_id)
        elif worker_id not in known_workers:
            add_issue(issues, "error", "anomaly_worker_id_unknown", "behavior anomaly worker_id is not in enriched timeline", event_id=event_id, worker_id=worker_id)
        event_type = event.get("event_type")
        if event_type not in ALLOWED_EVENT_TYPES:
            add_issue(issues, "error", "anomaly_event_type_invalid", "behavior anomaly event_type is invalid", event_id=event_id, event_type=event_type)
        else:
            type_counts[str(event_type)] += 1
        severity = event.get("severity")
        if severity not in ALLOWED_SEVERITIES:
            add_issue(issues, "error", "anomaly_severity_invalid", "behavior anomaly severity is invalid", event_id=event_id, severity=severity)
        score = event.get("score")
        if not is_finite_number(score) or not 0 <= float(score) <= 100:
            add_issue(issues, "error", "anomaly_score_invalid", "behavior anomaly score is outside [0,100]", event_id=event_id)
        time_step = event.get("time_step")
        if isinstance(time_step, bool) or not isinstance(time_step, int) or time_step < 0:
            add_issue(issues, "error", "anomaly_time_step_invalid", "behavior anomaly time_step is invalid", event_id=event_id)
        timestamp_s = event.get("timestamp_s")
        if timestamp_s is not None and not is_finite_number(timestamp_s):
            add_issue(issues, "error", "anomaly_timestamp_invalid", "behavior anomaly timestamp_s is invalid", event_id=event_id)
        segment_id = event.get("segment_id")
        if segment_id is not None and not dataset.has_segment(segment_id):
            add_issue(issues, "error", "anomaly_segment_invalid", "behavior anomaly segment_id is unknown", event_id=event_id, segment_id=segment_id)
    if summary is not None:
        summary_count = summary.get("event_count")
        if summary_count is not None and summary_count != len(events):
            add_issue(issues, "error", "anomaly_summary_event_count_mismatch", "behavior anomaly summary event_count does not match events", expected=len(events), actual=summary_count)
        summary_by_type = summary.get("event_count_by_type")
        if summary_by_type is not None:
            if not isinstance(summary_by_type, dict):
                add_issue(issues, "error", "anomaly_summary_type_counts_invalid", "behavior anomaly summary event_count_by_type must be an object")
            else:
                for event_type in ALLOWED_EVENT_TYPES:
                    if summary_by_type.get(event_type, 0) != type_counts.get(event_type, 0):
                        add_issue(issues, "error", "anomaly_summary_type_count_mismatch", "behavior anomaly summary type count does not match events", event_type=event_type)
    assert_json_serializable("behavior_anomaly_events", events, issues)
    if summary is not None:
        assert_json_serializable("behavior_anomaly_summary", summary, issues)
    return {
        "anomaly_event_count": len(events),
        "anomaly_event_count_by_type": {event_type: type_counts.get(event_type, 0) for event_type in sorted(ALLOWED_EVENT_TYPES)},
        "anomaly_warning_count": sum(issue.severity == "warning" for issue in issues) - before_warnings,
        "anomaly_validation_ok": sum(issue.severity == "error" for issue in issues) == before_errors,
        "anomaly_enabled": True,
    }


def validate_behavior_anomaly_contract(
    config: dict[str, Any],
    dataset: SegmentDataset,
    enrichment_result: TimelineEnrichmentResult,
    issues: list[ValidationIssue],
    anomaly_result: BehaviorAnomalyBuildResult | None = None,
) -> dict[str, Any]:
    if not behavior_anomaly_enabled(config):
        add_issue(issues, "warning", "anomaly_disabled", "behavior anomaly outputs are disabled; missing outputs are not a baseline blocker")
        summary = _empty_anomaly_summary(False)
        summary["anomaly_warning_count"] = 1
        return summary
    result = anomaly_result or build_behavior_anomalies(config=config, dataset=dataset, enrichment_result=enrichment_result)
    try:
        validate_behavior_anomaly_result(result, enrichment_result, dataset)
    except ValueError as exc:
        add_issue(issues, "error", "anomaly_result_invalid", "behavior anomaly builder result failed validation", error=str(exc))
    events = [_event_record(event) for event in result.events]
    return _validate_behavior_anomaly_records(events, result.summary, dataset, enrichment_result, issues)


def validate_existing_behavior_anomaly_outputs(
    config: dict[str, Any],
    dataset: SegmentDataset,
    enrichment_result: TimelineEnrichmentResult,
    issues: list[ValidationIssue],
) -> dict[str, Any] | None:
    output_root = Path(str(config.get("output_root", "")))
    if not output_root:
        return None
    events_path = output_root / "workers" / "behavior_anomaly_events.json"
    summary_path = output_root / "workers" / "behavior_anomaly_summary.json"
    if not events_path.exists() and not summary_path.exists():
        return None
    if not events_path.exists() or not summary_path.exists():
        add_issue(issues, "error", "anomaly_output_pair_missing", "behavior anomaly output files must be present as a pair", events_path=str(events_path), summary_path=str(summary_path))
        return _empty_anomaly_summary(behavior_anomaly_enabled(config))
    try:
        events_payload = json.loads(events_path.read_text(encoding="utf-8"))
        summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
        json.dumps(events_payload, allow_nan=False)
        json.dumps(summary_payload, allow_nan=False)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        add_issue(issues, "error", "anomaly_json_invalid", "behavior anomaly output JSON is malformed", error=str(exc))
        return _empty_anomaly_summary(behavior_anomaly_enabled(config))
    events = events_payload.get("events", events_payload)
    if not isinstance(events, list):
        add_issue(issues, "error", "anomaly_events_shape_invalid", "behavior anomaly events payload must be a list or contain an events list")
        events = []
    summary = summary_payload.get("summary", summary_payload)
    if not isinstance(summary, dict):
        add_issue(issues, "error", "anomaly_summary_shape_invalid", "behavior anomaly summary payload must be an object or contain a summary object")
        summary = None
    return _validate_behavior_anomaly_records(events, summary, dataset, enrichment_result, issues)

def validate_optional_solver_generated_outputs(config: dict[str, Any], issues: list[ValidationIssue]) -> None:
    output_root = Path(str(config.get("output_root", "")))
    if not output_root:
        return
    estimates_path = output_root / "uwb" / "uwb_position_estimates.json"
    validation_path = output_root / "uwb" / "uwb_solver_validation.json"
    for path in (estimates_path, validation_path):
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            json.dumps(payload, allow_nan=False)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            add_issue(issues, "error", "solver_json_invalid", "optional solver output JSON is malformed", path=str(path), error=str(exc))
            continue
        warnings = payload.get("warnings", [])
        if isinstance(warnings, list):
            for warning in warnings:
                text = str(warning)
                if "missing calibration" in text:
                    add_issue(issues, "warning", "solver_missing_calibration", "optional solver output reports missing calibration")
                if "fallback" in text:
                    add_issue(issues, "warning", "solver_fallback_mocap_proxy", "optional solver output reports fallback to mocap proxy")
                if "insufficient anchor" in text:
                    add_issue(issues, "warning", "solver_insufficient_anchors", "optional solver output reports insufficient anchors")
                if "high RMSE" in text:
                    add_issue(issues, "warning", "solver_high_rmse", "optional solver output reports high RMSE")
                if "no solved positions" in text:
                    add_issue(issues, "warning", "solver_no_solved_positions", "optional solver output reports no solved positions")
        if path == estimates_path:
            records = payload.get("estimates", [])
            if not isinstance(records, list):
                add_issue(issues, "error", "solver_estimates_invalid", "solver estimates must be a list", path=str(path))
                continue
            for index, record in enumerate(records):
                if not isinstance(record, dict):
                    add_issue(issues, "error", "solver_estimate_invalid", "solver estimate must be an object", index=index)
                    continue
                confidence = record.get("confidence")
                if not is_finite_number(confidence) or not 0 <= float(confidence) <= 1:
                    add_issue(issues, "error", "solver_confidence_invalid", "solver confidence is outside [0,1]", index=index)
                for key in ("estimated_position", "ground_truth_position"):
                    point = record.get(key)
                    if point is not None and not point_is_finite(point):
                        add_issue(issues, "error", "solver_position_invalid", "solver position is non-finite", index=index, field=key)


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
        add_issue(issues, "error", "cross_distance_count_mismatch", "distance matrix does not equal timeline times anchors")
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


def build_validation_summary(issues: tuple[ValidationIssue, ...], anchor_plan: AnchorPlanResult, cable_plan: CablePlanResult, timeline_result: TimelineBuildResult, distance_result: DistanceMatrixResult, enrichment_result: TimelineEnrichmentResult, exposure_result: ExposureBuildResult, dataset: SegmentDataset, anomaly_summary: dict[str, Any] | None = None) -> dict[str, Any]:
    error_count = sum(issue.severity == "error" for issue in issues)
    warning_messages = [issue.message for issue in issues if issue.severity == "warning"]
    anomaly_summary = _empty_anomaly_summary(False) if anomaly_summary is None else anomaly_summary
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
        **anomaly_summary,
        "ready_for_pipeline_write": error_count == 0,
        "warnings": warning_messages,
    }


def validate_all_outputs(config: dict | None = None, dataset: SegmentDataset | None = None, anchor_plan: AnchorPlanResult | None = None, cable_plan: CablePlanResult | None = None, timeline_result: TimelineBuildResult | None = None, distance_result: DistanceMatrixResult | None = None, enrichment_result: TimelineEnrichmentResult | None = None, exposure_result: ExposureBuildResult | None = None, anomaly_result: BehaviorAnomalyBuildResult | None = None) -> OutputValidationResult:
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
    anomaly_summary = validate_behavior_anomaly_contract(config, dataset, enrichment_result, issues, anomaly_result)
    file_anomaly_summary = validate_existing_behavior_anomaly_outputs(config, dataset, enrichment_result, issues)
    if file_anomaly_summary is not None:
        anomaly_summary = file_anomaly_summary
    validate_optional_solver_generated_outputs(config, issues)
    issue_tuple = tuple(issues)
    summary = build_validation_summary(issue_tuple, anchor_plan, cable_plan, timeline_result, distance_result, enrichment_result, exposure_result, dataset, anomaly_summary)
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
    assert "anomaly_validation_ok" in result.summary


if __name__ == "__main__":
    _self_check()
    print("validate_outputs.py self-check passed")
