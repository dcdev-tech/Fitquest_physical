from __future__ import annotations

from activity_common.base import ActivityCalculationResult
from activity_common.result_utils import normalize_legacy_result
from long_jump.base_input import read_long_jump_input
from long_jump.calculations.age_rules import apply_long_jump_age_rules
from long_jump.runtime import SOURCES, run_long_jump


def calculate_long_jump(
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
        raise ValueError(f"Unsupported age group '{age_group}' for long jump")

    stats = read_long_jump_input(video_path)
    raw = run_long_jump(
        age_group=age_group,
        candidate_id=candidate_id,
        candidate_name=candidate_name,
        video_path=video_path,
        age=age,
        gender=gender,
        jumped_length=jumped_length,
    )
    normalized = normalize_legacy_result(raw)
    adjusted_score = apply_long_jump_age_rules(normalized.score, age_group, stats.duration_seconds)
    return ActivityCalculationResult(score=adjusted_score, category=normalized.category)
