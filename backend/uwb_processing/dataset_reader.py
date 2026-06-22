"""Discover and read configured UTIL UWB flight CSV trials.

UTIL UWB pose_x, pose_y and pose_z values are motion-capture ground-truth proxy positions, not real UWB-estimated miner positions. In this MVP they are used only as worker movement proxies.

Raw UTIL CSV files remain outside the repository. This module streams or reads configured files from the external dataset path and never copies raw dataset files into backend/data_processed.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any, Iterable

try:
    from .config_loader import load_config
    from .core import Point3D, ensure_finite_number
except ImportError:  # Supports ``python backend/uwb_processing/dataset_reader.py``.
    from config_loader import load_config  # type: ignore
    from core import Point3D, ensure_finite_number  # type: ignore


REQUIRED_POSE_COLUMNS = ("t_pose", "pose_x", "pose_y", "pose_z")
OPTIONAL_TDOA_COLUMNS = ("t_tdoa", "idA", "idB", "tdoa_meas")
IMPORTANT_TOKEN_PATTERN = re.compile(r"(?:const|trial|tdoa|traj|manual)\d+")


@dataclass(frozen=True)
class PoseSample:
    row_index: int
    timestamp_s: float
    position: Point3D
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TDoASample:
    row_index: int
    timestamp_s: float
    anchor_a: str
    anchor_b: str
    tdoa_meas: float
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TrialData:
    trial_hint: str
    csv_path: str
    pose_samples: tuple[PoseSample, ...]
    tdoa_samples: tuple[TDoASample, ...] = field(default_factory=tuple)
    rejected_pose_rows: int = 0
    rejected_tdoa_rows: int = 0
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_summary(self) -> dict[str, Any]:
        timestamps = [sample.timestamp_s for sample in self.pose_samples]
        xs = [sample.position.x for sample in self.pose_samples]
        ys = [sample.position.y for sample in self.pose_samples]
        zs = [sample.position.z for sample in self.pose_samples]
        time_min = min(timestamps) if timestamps else None
        time_max = max(timestamps) if timestamps else None
        return {
            "trial_hint": self.trial_hint,
            "csv_path": self.csv_path,
            "pose_sample_count": len(self.pose_samples),
            "tdoa_sample_count": len(self.tdoa_samples),
            "rejected_pose_rows": self.rejected_pose_rows,
            "rejected_tdoa_rows": self.rejected_tdoa_rows,
            "time_min_s": time_min,
            "time_max_s": time_max,
            "duration_s": (time_max - time_min) if timestamps else None,
            "pose_x_min": min(xs) if xs else None,
            "pose_x_max": max(xs) if xs else None,
            "pose_y_min": min(ys) if ys else None,
            "pose_y_max": max(ys) if ys else None,
            "pose_z_min": min(zs) if zs else None,
            "pose_z_max": max(zs) if zs else None,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class DatasetReadResult:
    dataset_root: str
    matched_trials: dict[str, TrialData]
    unmatched_hints: tuple[str, ...]
    discovered_csv_count: int
    summary: dict[str, Any]

    def get_trial(self, trial_hint: str) -> TrialData:
        if trial_hint in self.matched_trials:
            return self.matched_trials[trial_hint]
        normalized = normalize_hint(trial_hint)
        for hint, trial in self.matched_trials.items():
            if normalize_hint(hint) == normalized:
                return trial
        raise KeyError(f"Unmatched trial hint: {trial_hint}")

    def to_summary(self) -> dict[str, Any]:
        return dict(self.summary)


def normalize_hint(value: str) -> str:
    """Normalize a trial hint or path for deterministic fuzzy matching."""
    if not isinstance(value, str):
        raise ValueError("trial hint must be a string")
    text = value.strip().lower().replace("\\", "/")
    name = text.rsplit("/", 1)[-1]
    if "." in name:
        suffix = name.rsplit(".", 1)[-1]
        if suffix in {"csv", "txt", "bag"}:
            text = text[: -(len(suffix) + 1)]
    return "".join(character for character in text if character.isalnum())


def discover_csv_files(dataset_root: str | Path) -> list[Path]:
    root = Path(dataset_root).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"UTIL dataset root does not exist: {root}")
    return sorted(
        (path.resolve() for path in root.rglob("*.csv") if path.is_file()),
        key=lambda path: str(path).lower(),
    )


def score_file_match(trial_hint: str, csv_path: Path) -> int:
    normalized_hint = normalize_hint(trial_hint)
    if not normalized_hint:
        return 0
    normalized_stem = normalize_hint(csv_path.stem)
    normalized_path = normalize_hint(str(csv_path))
    score = 0
    if normalized_hint == normalized_stem:
        score += 10_000
    elif normalized_hint in normalized_stem:
        score += 8_000
    elif normalized_hint in normalized_path:
        score += 6_000
    hint_tokens = set(IMPORTANT_TOKEN_PATTERN.findall(normalized_hint))
    path_tokens = set(IMPORTANT_TOKEN_PATTERN.findall(normalized_path))
    matching_tokens = hint_tokens & path_tokens
    score += len(matching_tokens) * 250
    if hint_tokens and matching_tokens == hint_tokens:
        score += 1_000
    return score


def match_trial_files(
    trial_hints: Iterable[str],
    csv_files: list[Path],
    allow_reuse: bool = False,
) -> tuple[dict[str, Path], tuple[str, ...]]:
    matches: dict[str, Path] = {}
    unmatched: list[str] = []
    used: set[Path] = set()
    for hint in trial_hints:
        ranked = sorted(
            (
                (score_file_match(hint, path), str(path).lower(), path)
                for path in csv_files
                if allow_reuse or path not in used
            ),
            key=lambda item: (-item[0], item[1]),
        )
        if not ranked or ranked[0][0] <= 0:
            unmatched.append(hint)
            continue
        selected = ranked[0][2]
        matches[hint] = selected
        used.add(selected)
    return matches, tuple(unmatched)


def read_csv_header(csv_path: str | Path) -> tuple[str, ...]:
    path = Path(csv_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"CSV file does not exist: {path}")
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            row = next(csv.reader(handle), None)
    except (OSError, csv.Error, UnicodeError) as exc:
        raise ValueError(f"Could not read CSV header from {path}: {exc}") from exc
    if not row or not any(column.strip() for column in row):
        raise ValueError(f"CSV file has an empty or invalid header: {path}")
    return tuple(column.strip() for column in row)


def has_required_pose_columns(header: Iterable[str]) -> bool:
    return set(REQUIRED_POSE_COLUMNS).issubset(set(header))


def has_optional_tdoa_columns(header: Iterable[str]) -> bool:
    return set(OPTIONAL_TDOA_COLUMNS).issubset(set(header))


def parse_pose_sample(row: dict[str, str], row_index: int) -> PoseSample | None:
    if any(not row.get(column, "").strip() for column in REQUIRED_POSE_COLUMNS):
        return None
    try:
        timestamp = ensure_finite_number(row["t_pose"], "t_pose")
        position = Point3D(
            ensure_finite_number(row["pose_x"], "pose_x"),
            ensure_finite_number(row["pose_y"], "pose_y"),
            ensure_finite_number(row["pose_z"], "pose_z"),
        )
    except (TypeError, ValueError):
        return None
    return PoseSample(
        row_index=row_index,
        timestamp_s=timestamp,
        position=position,
        raw={column: row.get(column, "") for column in REQUIRED_POSE_COLUMNS},
    )


def parse_tdoa_sample(row: dict[str, str], row_index: int) -> TDoASample | None:
    if any(not row.get(column, "").strip() for column in OPTIONAL_TDOA_COLUMNS):
        return None
    try:
        timestamp = ensure_finite_number(row["t_tdoa"], "t_tdoa")
        measurement = ensure_finite_number(row["tdoa_meas"], "tdoa_meas")
    except (TypeError, ValueError):
        return None
    return TDoASample(
        row_index=row_index,
        timestamp_s=timestamp,
        anchor_a=str(row["idA"]).strip(),
        anchor_b=str(row["idB"]).strip(),
        tdoa_meas=measurement,
        raw={column: row.get(column, "") for column in OPTIONAL_TDOA_COLUMNS},
    )


def read_trial_csv(csv_path: str | Path, trial_hint: str) -> TrialData:
    path = Path(csv_path).expanduser().resolve()
    header = read_csv_header(path)
    if not has_required_pose_columns(header):
        missing = sorted(set(REQUIRED_POSE_COLUMNS) - set(header))
        raise ValueError(f"CSV {path} is missing required pose columns: {missing}")
    tdoa_available = has_optional_tdoa_columns(header)
    pose_samples: list[PoseSample] = []
    tdoa_samples: list[TDoASample] = []
    rejected_pose = 0
    rejected_tdoa = 0
    source_pose_timestamps: list[float] = []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row_index, row in enumerate(reader, start=2):
                pose = parse_pose_sample(row, row_index)
                if pose is None:
                    rejected_pose += 1
                else:
                    pose_samples.append(pose)
                    source_pose_timestamps.append(pose.timestamp_s)
                if tdoa_available:
                    tdoa = parse_tdoa_sample(row, row_index)
                    if tdoa is None:
                        rejected_tdoa += 1
                    else:
                        tdoa_samples.append(tdoa)
    except (OSError, csv.Error, UnicodeError) as exc:
        raise ValueError(f"Could not read trial CSV {path}: {exc}") from exc
    if not pose_samples:
        raise ValueError(f"CSV contains no valid pose samples: {path}")

    warnings: list[str] = []
    if any(
        later < earlier
        for earlier, later in zip(source_pose_timestamps, source_pose_timestamps[1:])
    ):
        warnings.append("pose timestamps were not monotonic in source order; samples were sorted")
    if len(set(source_pose_timestamps)) != len(source_pose_timestamps):
        warnings.append("duplicate pose timestamps were retained")
    if not tdoa_available:
        warnings.append("optional TDoA columns were not available")
    if rejected_pose:
        warnings.append(f"{rejected_pose} malformed pose row(s) were rejected")
    if rejected_tdoa:
        warnings.append(f"{rejected_tdoa} malformed TDoA row(s) were rejected")

    pose_samples.sort(key=lambda sample: (sample.timestamp_s, sample.row_index))
    tdoa_samples.sort(key=lambda sample: (sample.timestamp_s, sample.row_index))
    return TrialData(
        trial_hint=trial_hint,
        csv_path=str(path),
        pose_samples=tuple(pose_samples),
        tdoa_samples=tuple(tdoa_samples),
        rejected_pose_rows=rejected_pose,
        rejected_tdoa_rows=rejected_tdoa,
        warnings=tuple(warnings),
    )


def build_dataset_summary(
    dataset_root: str | Path,
    csv_files: list[Path],
    matched_trials: dict[str, TrialData],
    unmatched_hints: tuple[str, ...],
) -> dict[str, Any]:
    summaries = [matched_trials[hint].to_summary() for hint in sorted(matched_trials)]
    warnings = [f"unmatched trial hint: {hint}" for hint in unmatched_hints]
    return {
        "dataset_root": str(Path(dataset_root).expanduser().resolve()),
        "discovered_csv_count": len(csv_files),
        "matched_trial_count": len(matched_trials),
        "unmatched_hint_count": len(unmatched_hints),
        "unmatched_hints": list(unmatched_hints),
        "total_pose_samples": sum(len(trial.pose_samples) for trial in matched_trials.values()),
        "total_tdoa_samples": sum(len(trial.tdoa_samples) for trial in matched_trials.values()),
        "total_rejected_pose_rows": sum(
            trial.rejected_pose_rows for trial in matched_trials.values()
        ),
        "total_rejected_tdoa_rows": sum(
            trial.rejected_tdoa_rows for trial in matched_trials.values()
        ),
        "trial_summaries": summaries,
        "warnings": warnings,
    }


def read_configured_dataset(config: dict[str, Any] | None = None) -> DatasetReadResult:
    normalized_config = load_config() if config is None else config
    dataset_root = normalized_config["dataset_root"]
    csv_files = discover_csv_files(dataset_root)
    trial_hints = [worker["source_trial_hint"] for worker in normalized_config["workers"]]
    matches, unmatched = match_trial_files(
        trial_hints,
        csv_files,
        bool(normalized_config.get("allow_trial_reuse", False)),
    )
    if not matches:
        raise ValueError("none of the configured source_trial_hint values matched a CSV file")
    trials = {
        hint: read_trial_csv(path, hint)
        for hint, path in sorted(matches.items())
    }
    summary = build_dataset_summary(dataset_root, csv_files, trials, unmatched)
    return DatasetReadResult(
        dataset_root=str(Path(dataset_root).resolve()),
        matched_trials=trials,
        unmatched_hints=unmatched,
        discovered_csv_count=len(csv_files),
        summary=summary,
    )


def _self_check() -> None:
    config = load_config()
    result = read_configured_dataset(config)
    assert result.discovered_csv_count > 0
    assert result.matched_trials
    assert all(trial.pose_samples for trial in result.matched_trials.values())
    print(json.dumps(result.to_summary(), ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    _self_check()
    print("dataset_reader.py self-check passed")
