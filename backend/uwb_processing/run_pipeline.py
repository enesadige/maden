"""Final file writer for the UWB worker-tracking MVP pipeline.

Default execution is a dry run. Repository outputs are written only when
``--write`` is passed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import argparse
import csv
import json
import sys
import time

try:
    from backend.uwb_processing.core import to_jsonable
    from backend.uwb_processing.config_loader import load_config
    from backend.uwb_processing.segment_loader import load_segment_dataset
    from backend.uwb_processing.anchor_planner import plan_anchors
    from backend.uwb_processing.cable_planner import plan_cables
    from backend.uwb_processing.timeline_builder import build_timeline
    from backend.uwb_processing.distance_matrix import compute_distance_matrix
    from backend.uwb_processing.timeline_enricher import enrich_timeline
    from backend.uwb_processing.exposure_builder import build_exposure
    from backend.uwb_processing.behavior_anomaly_builder import build_behavior_anomalies
    from backend.uwb_processing.validate_outputs import validate_all_outputs
    from backend.uwb_processing.uwb_position_solver import solve_worker_positions_from_tdoa
except ModuleNotFoundError:
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from backend.uwb_processing.core import to_jsonable
    from backend.uwb_processing.config_loader import load_config
    from backend.uwb_processing.segment_loader import load_segment_dataset
    from backend.uwb_processing.anchor_planner import plan_anchors
    from backend.uwb_processing.cable_planner import plan_cables
    from backend.uwb_processing.timeline_builder import build_timeline
    from backend.uwb_processing.distance_matrix import compute_distance_matrix
    from backend.uwb_processing.timeline_enricher import enrich_timeline
    from backend.uwb_processing.exposure_builder import build_exposure
    from backend.uwb_processing.behavior_anomaly_builder import build_behavior_anomalies
    from backend.uwb_processing.validate_outputs import validate_all_outputs
    from backend.uwb_processing.uwb_position_solver import solve_worker_positions_from_tdoa


LIMITATIONS = [
    "UTIL pose_x/y/z values are motion-capture ground-truth proxy positions, not real UWB-estimated miner positions.",
    "bounds_fit transform is approximate and not calibrated UWB-to-mine registration.",
    "segment mapping uses bounds-center graph geometry and fallback continuity.",
    "anchor visibility is approximate distance/graph visibility, not calibrated RF propagation.",
    "worker exposure risk is occupancy contribution only and does not include gas/geometric risk fusion.",
    "final fused segment risk and emergency routing are owned by backend risk/routing modules.",
    "workers.json is a backend-compatible latest snapshot. Its time_step is normalized to 0 for the existing API filter; latest_time_step preserves the original per-worker timeline step.",
]

CSV_FIELDS = [
    "worker_id",
    "tag_id",
    "time_step",
    "timestamp_s",
    "x",
    "y",
    "z",
    "current_segment",
    "position_reliability",
    "reliability_status",
    "status",
    "tracking_status",
    "visible_anchor_count",
    "tracking_risk_score",
    "mapping_method",
    "mapping_confidence",
    "continuity_score",
    "flight_signal_reliability",
    "source_trial",
    "source_position_type",
]


@dataclass(frozen=True)
class PipelineArtifacts:
    config: dict[str, Any]
    dataset: Any
    anchor_plan: Any
    cable_plan: Any
    timeline_result: Any
    distance_result: Any
    enrichment_result: Any
    exposure_result: Any
    anomaly_result: Any | None
    validation_result: Any


@dataclass(frozen=True)
class PipelineWriteResult:
    dry_run: bool
    output_root: str
    written_files: tuple[str, ...]
    skipped_files: tuple[str, ...]
    summary: dict[str, Any]

    def to_summary(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "output_root": self.output_root,
            "written_file_count": len(self.written_files),
            "skipped_file_count": len(self.skipped_files),
            "written_files": list(self.written_files),
            "skipped_files": list(self.skipped_files),
            **to_jsonable(self.summary),
        }


def repo_root_from_file() -> Path:
    return Path(__file__).resolve().parents[2]


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def resolve_output_root(config: dict[str, Any]) -> Path:
    raw_output_root = config.get("output_root")
    if not raw_output_root:
        raise ValueError("config output_root is required")
    output_root = Path(str(raw_output_root))
    if not output_root.is_absolute():
        output_root = repo_root_from_file() / output_root
    output_root = output_root.resolve()
    expected_suffix = Path("backend") / "data_processed" / "sample"
    if output_root.parts[-len(expected_suffix.parts):] != expected_suffix.parts:
        raise ValueError(f"output_root must end with {expected_suffix.as_posix()}: {output_root}")
    if "haki_lidar" in output_root.parts:
        raise ValueError("output_root must not point inside haki_lidar")
    return output_root


def solver_outputs_enabled(config: dict[str, Any]) -> bool:
    solver = config.get("uwb_position_solver") or {}
    return bool(solver.get("enabled", False) and solver.get("write_solver_outputs", False))


def behavior_anomaly_enabled(config: dict[str, Any]) -> bool:
    anomaly = config.get("behavior_anomaly") or {}
    if not isinstance(anomaly, dict):
        raise ValueError("behavior_anomaly must be an object when provided")
    return bool(anomaly.get("enabled", True))


def behavior_anomaly_outputs_enabled(config: dict[str, Any]) -> bool:
    anomaly = config.get("behavior_anomaly") or {}
    if not isinstance(anomaly, dict):
        raise ValueError("behavior_anomaly must be an object when provided")
    return behavior_anomaly_enabled(config) and bool(anomaly.get("write_outputs", True))


def approved_output_paths(output_root: Path, config: dict[str, Any] | None = None) -> dict[str, Path]:
    paths = {
        "workers_json": output_root / "workers" / "workers.json",
        "worker_positions_clean_csv": output_root / "workers" / "worker_positions_clean.csv",
        "worker_positions_demo_json": output_root / "workers" / "worker_positions_demo.json",
        "worker_segment_timeline_json": output_root / "workers" / "worker_segment_timeline.json",
        "worker_segment_timeline_summary_json": output_root / "workers" / "worker_segment_timeline_summary.json",
        "uwb_extraction_summary_json": output_root / "workers" / "uwb_extraction_summary.json",
        "anchor_positions_json": output_root / "anchors" / "anchor_positions.json",
        "anchor_cables_json": output_root / "anchors" / "anchor_cables.json",
        "anchor_coverage_report_json": output_root / "anchors" / "anchor_coverage_report.json",
        "anchor_tag_distances_json": output_root / "anchors" / "anchor_tag_distances.json",
        "anchor_tag_distance_summary_json": output_root / "anchors" / "anchor_tag_distance_summary.json",
        "worker_exposure_risk_json": output_root / "risk" / "worker_exposure_risk.json",
        "uwb_pipeline_manifest_json": output_root / "uwb" / "uwb_pipeline_manifest.json",
        "uwb_validation_summary_json": output_root / "uwb" / "uwb_validation_summary.json",
    }
    if config is not None and behavior_anomaly_outputs_enabled(config):
        paths.update({
            "behavior_anomaly_events_json": output_root / "workers" / "behavior_anomaly_events.json",
            "behavior_anomaly_summary_json": output_root / "workers" / "behavior_anomaly_summary.json",
        })
    if config is not None and solver_outputs_enabled(config):
        paths.update({
            "uwb_position_estimates_json": output_root / "uwb" / "uwb_position_estimates.json",
            "uwb_solver_validation_json": output_root / "uwb" / "uwb_solver_validation.json",
        })
    return paths


def ensure_safe_output_path(path: Path, output_root: Path) -> None:
    resolved_root = output_root.resolve()
    resolved_path = path.resolve()
    if not _is_relative_to(resolved_path, resolved_root):
        raise ValueError(f"output path is outside output_root: {resolved_path}")
    if "haki_lidar" in resolved_path.parts:
        raise ValueError(f"output path must not touch haki_lidar: {resolved_path}")
    approved = {item.resolve() for item in approved_output_paths(resolved_root).values()}
    approved.update({
        (resolved_root / "uwb" / "uwb_position_estimates.json").resolve(),
        (resolved_root / "uwb" / "uwb_solver_validation.json").resolve(),
        (resolved_root / "workers" / "behavior_anomaly_events.json").resolve(),
        (resolved_root / "workers" / "behavior_anomaly_summary.json").resolve(),
    })
    if resolved_path not in approved:
        raise ValueError(f"output path is not approved: {resolved_path}")


def write_json(path: Path, data: Any, output_root: Path) -> None:
    ensure_safe_output_path(path, output_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(to_jsonable(data), handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    tmp_path.replace(path)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str], output_root: Path) -> None:
    ensure_safe_output_path(path, output_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    with tmp_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})
    tmp_path.replace(path)


def build_pipeline_artifacts() -> PipelineArtifacts:
    config = load_config()
    dataset = load_segment_dataset(config)
    anchor_plan = plan_anchors(dataset=dataset, config=config)
    cable_plan = plan_cables(dataset=dataset, anchor_plan=anchor_plan, config=config)
    timeline_result = build_timeline(config=config)
    distance_result = compute_distance_matrix(
        timeline_result=timeline_result,
        anchor_plan=anchor_plan,
        dataset=dataset,
        config=config,
    )
    enrichment_result = enrich_timeline(
        timeline_result=timeline_result,
        distance_result=distance_result,
        config=config,
    )
    anomaly_result = (
        build_behavior_anomalies(
            config=config,
            dataset=dataset,
            enrichment_result=enrichment_result,
        )
        if behavior_anomaly_enabled(config)
        else None
    )
    exposure_result = build_exposure(
        enrichment_result=enrichment_result,
        dataset=dataset,
        config=config,
    )
    validation_result = validate_all_outputs(
        config=config,
        dataset=dataset,
        anchor_plan=anchor_plan,
        cable_plan=cable_plan,
        timeline_result=timeline_result,
        distance_result=distance_result,
        enrichment_result=enrichment_result,
        exposure_result=exposure_result,
    )
    return PipelineArtifacts(
        config=config,
        dataset=dataset,
        anchor_plan=anchor_plan,
        cable_plan=cable_plan,
        timeline_result=timeline_result,
        distance_result=distance_result,
        enrichment_result=enrichment_result,
        exposure_result=exposure_result,
        anomaly_result=anomaly_result,
        validation_result=validation_result,
    )


def _record_dict(record: Any) -> dict[str, Any]:
    if hasattr(record, "to_dict"):
        return dict(record.to_dict())
    return dict(to_jsonable(record))


def _position_dict(value: Any) -> dict[str, Any]:
    return value.to_dict() if hasattr(value, "to_dict") else to_jsonable(value)


def build_workers_json(enrichment_result: Any) -> list[dict[str, Any]]:
    workers = []
    for snapshot in enrichment_result.latest_workers:
        item = snapshot.to_dict() if hasattr(snapshot, "to_dict") else _record_dict(snapshot)
        original_time_step = item.get("time_step")
        original_timestamp_s = item.get("timestamp_s")
        item["latest_time_step"] = original_time_step
        item["latest_timestamp_s"] = original_timestamp_s
        item["time_step"] = 0
        item["snapshot_type"] = "latest_worker_snapshot"
        assert item.get("mapped_segment_id") == item.get("current_segment")
        assert item.get("uwb_pose") == item.get("position")
        assert item.get("motion_status") == item.get("status")
        workers.append(item)
    workers = sorted(workers, key=lambda item: item.get("worker_id", ""))
    assert all(item.get("time_step") == 0 for item in workers)
    assert all(item.get("latest_time_step") is not None for item in workers)
    return workers


def build_worker_positions_clean_rows(enrichment_result: Any) -> list[dict[str, Any]]:
    rows = []
    for record in enrichment_result.enriched_timeline:
        position = _position_dict(record.position)
        rows.append({
            "worker_id": record.worker_id,
            "tag_id": record.tag_id,
            "time_step": record.time_step,
            "timestamp_s": record.timestamp_s,
            "x": position["x"],
            "y": position["y"],
            "z": position["z"],
            "current_segment": record.current_segment,
            "position_reliability": record.position_reliability,
            "reliability_status": record.reliability_status,
            "status": record.status,
            "tracking_status": record.tracking_status,
            "visible_anchor_count": record.visible_anchor_count,
            "tracking_risk_score": round((1.0 - record.position_reliability) * 100.0, 4),
            "mapping_method": record.mapping_method,
            "mapping_confidence": record.mapping_confidence,
            "continuity_score": record.continuity_score,
            "flight_signal_reliability": record.flight_signal_reliability,
            "source_trial": record.source_trial,
            "source_position_type": record.source_position_type,
        })
    return sorted(rows, key=lambda item: (item["time_step"], item["worker_id"]))


def build_worker_positions_demo(enrichment_result: Any) -> dict[str, Any]:
    return {
        "source": "uwb_tracking",
        "source_position_type": "mocap_ground_truth",
        "latest_workers": build_workers_json(enrichment_result),
        "timeline_preview": build_worker_segment_timeline(enrichment_result),
        "summary": enrichment_result.to_summary(),
        "warnings": list(enrichment_result.summary.get("warnings", [])) + LIMITATIONS,
    }


def build_worker_segment_timeline(enrichment_result: Any) -> list[dict[str, Any]]:
    records = []
    for record in enrichment_result.enriched_timeline:
        records.append({
            "worker_id": record.worker_id,
            "tag_id": record.tag_id,
            "time_step": record.time_step,
            "timestamp_s": record.timestamp_s,
            "current_segment": record.current_segment,
            "position": _position_dict(record.position),
            "position_reliability": record.position_reliability,
            "reliability_status": record.reliability_status,
            "status": record.status,
            "tracking_status": record.tracking_status,
            "visible_anchor_count": record.visible_anchor_count,
            "visible_anchors": list(record.visible_anchors),
            "tracking_risk_score": round((1.0 - record.position_reliability) * 100.0, 4),
            "mapping_method": record.mapping_method,
            "mapping_confidence": record.mapping_confidence,
            "continuity_score": record.continuity_score,
            "source_trial": record.source_trial,
            "source_position_type": record.source_position_type,
        })
    return sorted(records, key=lambda item: (item["time_step"], item["worker_id"]))


def build_anchor_positions(anchor_plan: Any) -> list[dict[str, Any]]:
    return sorted(
        (_record_dict(anchor) for anchor in anchor_plan.anchors),
        key=lambda item: item.get("anchor_id", ""),
    )


def build_anchor_cables(cable_plan: Any) -> dict[str, Any]:
    return {
        "source": "uwb_anchor_planner",
        "routing_surface": "tunnel_wall_approximation",
        "links": sorted((_record_dict(cable) for cable in cable_plan.cables), key=lambda item: item.get("cable_id", "")),
        "summary": cable_plan.to_summary(),
        "warnings": list(cable_plan.cable_report.get("warnings", [])),
    }


def build_anchor_coverage_report(anchor_plan: Any, distance_result: Any) -> dict[str, Any]:
    return {
        "source": "uwb_anchor_planner",
        "anchor_plan_summary": anchor_plan.to_summary(),
        "coverage_report": anchor_plan.coverage_report,
        "distance_visibility_summary": distance_result.to_summary(),
        "undercovered_segments": anchor_plan.coverage_report.get("undercovered_segments", []),
        "warnings": list(anchor_plan.coverage_report.get("warnings", []))
        + list(distance_result.summary.get("warnings", [])),
    }


def build_anchor_tag_distances(distance_result: Any) -> list[dict[str, Any]]:
    return sorted(
        (_record_dict(item) for item in distance_result.observations),
        key=lambda item: (item.get("time_step", 0), item.get("worker_id", ""), item.get("anchor_id", "")),
    )


def build_anchor_tag_distance_summary(distance_result: Any) -> dict[str, Any]:
    visibility = sorted(
        (_record_dict(item) for item in distance_result.visibility_by_worker_time.values()),
        key=lambda item: (item.get("time_step", 0), item.get("worker_id", "")),
    )
    return {
        "source": "uwb_tracking",
        "summary": distance_result.to_summary(),
        "visibility_by_worker_time": visibility,
        "warnings": list(distance_result.summary.get("warnings", [])),
    }


def build_worker_exposure_risk(exposure_result: Any) -> dict[str, Any]:
    return {
        "source": "uwb_tracking",
        "description": "Worker exposure is occupancy contribution only; not fused risk.",
        "records": sorted((_record_dict(item) for item in exposure_result.exposure_records), key=lambda item: (item.get("time_step", 0), item.get("worker_id", ""))),
        "segment_summaries": sorted((_record_dict(item) for item in exposure_result.segment_summaries), key=lambda item: item.get("segment_id", "")),
        "summary": exposure_result.to_summary(),
        "warnings": list(exposure_result.summary.get("warnings", [])) + [LIMITATIONS[4], LIMITATIONS[5]],
    }


def build_uwb_extraction_summary(artifacts: PipelineArtifacts) -> dict[str, Any]:
    return {
        "source": "uwb_tracking",
        "source_position_type": "mocap_ground_truth",
        "timeline": artifacts.timeline_result.to_summary(),
        "distance": artifacts.distance_result.to_summary(),
        "enrichment": artifacts.enrichment_result.to_summary(),
        "exposure": artifacts.exposure_result.to_summary(),
        "behavior_anomaly": artifacts.anomaly_result.to_summary() if artifacts.anomaly_result else {"enabled": False},
        "validation": artifacts.validation_result.to_summary(),
        "limitations": LIMITATIONS,
    }


def build_pipeline_manifest(artifacts: PipelineArtifacts, written_files: list[str], dry_run: bool) -> dict[str, Any]:
    return {
        "generated_at_unix": int(time.time()),
        "dry_run": dry_run,
        "source": "uwb_tracking",
        "source_position_type": "mocap_ground_truth",
        "output_root": str(resolve_output_root(artifacts.config)),
        "written_files": written_files,
        "counts": {
            "segment_count": len(artifacts.dataset.segments),
            "anchor_count": len(artifacts.anchor_plan.anchors),
            "cable_link_count": len(artifacts.cable_plan.cables),
            "timeline_record_count": len(artifacts.timeline_result.timeline),
            "distance_observation_count": len(artifacts.distance_result.observations),
            "exposure_record_count": len(artifacts.exposure_result.exposure_records),
            "latest_worker_count": len(artifacts.enrichment_result.latest_workers),
            "anomaly_event_count": len(artifacts.anomaly_result.events) if artifacts.anomaly_result else 0,
            "anomaly_event_count_by_type": artifacts.anomaly_result.summary.get("event_count_by_type", {}) if artifacts.anomaly_result else {},
            "anomaly_warning_count": len(artifacts.anomaly_result.warnings) if artifacts.anomaly_result else 0,
        },
        "limitations": LIMITATIONS,
        "validation": artifacts.validation_result.to_summary(),
        "warnings": artifacts.validation_result.summary.get("warnings", []),
    }


def build_solver_payloads(artifacts: PipelineArtifacts) -> dict[str, Any]:
    result = solve_worker_positions_from_tdoa(config=artifacts.config)
    return {
        "uwb_position_estimates_json": {
            "source": "uwb_position_solver",
            "mode_note": (
                "In tdoa_solver mode, worker position is estimated from UWB measurements. "
                "The UTIL pose_x/y/z values are used only as motion-capture ground-truth "
                "proxy references for validation metrics, not as the primary position source."
            ),
            "estimates": result.estimates,
            "summary": result.summary,
            "warnings": result.summary.get("warnings", []),
        },
        "uwb_solver_validation_json": {
            "source": "uwb_position_solver",
            "validation_summary": result.validation_summary,
            "summary": result.summary,
            "warnings": result.summary.get("warnings", []),
        },
    }


def build_output_payloads(artifacts: PipelineArtifacts, output_root: Path) -> dict[str, Any]:
    del output_root
    return {
        "workers_json": build_workers_json(artifacts.enrichment_result),
        "worker_positions_clean_csv": build_worker_positions_clean_rows(artifacts.enrichment_result),
        "worker_positions_demo_json": build_worker_positions_demo(artifacts.enrichment_result),
        "worker_segment_timeline_json": build_worker_segment_timeline(artifacts.enrichment_result),
        "worker_segment_timeline_summary_json": artifacts.enrichment_result.to_summary(),
        "uwb_extraction_summary_json": build_uwb_extraction_summary(artifacts),
        "anchor_positions_json": build_anchor_positions(artifacts.anchor_plan),
        "anchor_cables_json": build_anchor_cables(artifacts.cable_plan),
        "anchor_coverage_report_json": build_anchor_coverage_report(artifacts.anchor_plan, artifacts.distance_result),
        "anchor_tag_distances_json": build_anchor_tag_distances(artifacts.distance_result),
        "anchor_tag_distance_summary_json": build_anchor_tag_distance_summary(artifacts.distance_result),
        "worker_exposure_risk_json": build_worker_exposure_risk(artifacts.exposure_result),
        **({
            "behavior_anomaly_events_json": artifacts.anomaly_result.to_events_payload(),
            "behavior_anomaly_summary_json": artifacts.anomaly_result.to_summary_payload(),
        } if artifacts.anomaly_result and behavior_anomaly_outputs_enabled(artifacts.config) else {}),
        "uwb_pipeline_manifest_json": build_pipeline_manifest(artifacts, [], True),
        "uwb_validation_summary_json": artifacts.validation_result.to_summary(),
    }


def write_pipeline_outputs(artifacts: PipelineArtifacts, output_root: Path, dry_run: bool) -> PipelineWriteResult:
    paths = approved_output_paths(output_root, artifacts.config)
    payloads = build_output_payloads(artifacts, output_root)
    if solver_outputs_enabled(artifacts.config):
        payloads.update(build_solver_payloads(artifacts))
    all_files = [str(paths[name]) for name in paths]
    if dry_run:
        summary = build_pipeline_manifest(artifacts, [], True)
        summary["ready"] = artifacts.validation_result.ok
        return PipelineWriteResult(True, str(output_root), (), tuple(all_files), summary)
    if not artifacts.validation_result.ok:
        raise ValueError("validation failed; refusing to write UWB outputs")

    written: list[str] = []
    json_payloads = dict(payloads)
    json_payloads["uwb_pipeline_manifest_json"] = build_pipeline_manifest(artifacts, all_files, False)
    for logical_name, path in paths.items():
        payload = json_payloads[logical_name]
        if logical_name == "worker_positions_clean_csv":
            write_csv(path, payload, CSV_FIELDS, output_root)
        else:
            write_json(path, payload, output_root)
        written.append(str(path))
    summary = build_pipeline_manifest(artifacts, written, False)
    summary["ready"] = artifacts.validation_result.ok
    return PipelineWriteResult(False, str(output_root), tuple(written), (), summary)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and optionally write UWB MVP outputs.")
    parser.add_argument("--dry-run", action="store_true", help="Build and validate, but write nothing.")
    parser.add_argument("--write", action="store_true", help="Write approved UWB outputs.")
    parser.add_argument("--summary-only", action="store_true", help="Print compact summary JSON.")
    args = parser.parse_args(argv)
    if args.dry_run and args.write:
        parser.error("--dry-run and --write cannot be used together")
    args.dry_run = not args.write
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    artifacts = build_pipeline_artifacts()
    if not artifacts.validation_result.ok:
        print(json.dumps(artifacts.validation_result.to_summary(), separators=(",", ":"), sort_keys=True))
        print(json.dumps([issue.to_dict() for issue in artifacts.validation_result.errors()], separators=(",", ":"), sort_keys=True))
        return 2
    output_root = resolve_output_root(artifacts.config)
    result = write_pipeline_outputs(artifacts, output_root, dry_run=args.dry_run)
    summary = result.to_summary()
    if args.summary_only:
        summary = {
            "dry_run": summary["dry_run"],
            "ready": summary["ready"],
            "written_file_count": summary["written_file_count"],
            "skipped_file_count": summary["skipped_file_count"],
            "counts": summary["counts"],
            "validation": summary["validation"],
        }
    print(json.dumps(summary, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
