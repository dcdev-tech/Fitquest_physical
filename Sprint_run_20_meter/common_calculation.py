from __future__ import annotations

from Sprint_run_20_meter.base_input import read_sprint_input
from Sprint_run_20_meter.calculations.age_rules import apply_sprint_age_rules
from Sprint_run_20_meter.runtime import SOURCES, run_sprint_run_20m
from activity_common.base import ActivityCalculationResult
from activity_common.result_utils import normalize_legacy_result


def calculate_sprint_run_20m(
    *,
    age_group: str,
    candidate_id: str,
    candidate_name: str,
    video_path: str,
    age: int | None = None,
    gender: str | None = None,
    jumped_length: float | None = None,
) -> ActivityCalculationResult:
    if age_group not in SOURCES:
        raise ValueError(f"Unsupported age group '{age_group}' for sprint run")

    stats = read_sprint_input(video_path)
    raw = run_sprint_run_20m(
        age_group=age_group,
        candidate_id=candidate_id,
        candidate_name=candidate_name,
        video_path=video_path,
        age=age,
        gender=gender,
        jumped_length=jumped_length,
    )
    normalized = normalize_legacy_result(raw)
    adjusted_score = apply_sprint_age_rules(normalized.score, age_group, stats.duration_seconds)
    return ActivityCalculationResult(score=adjusted_score, category=normalized.category)
