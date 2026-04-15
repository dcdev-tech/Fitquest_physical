from __future__ import annotations

from activity_common.base import ActivityCalculationResult
from activity_common.result_utils import normalize_legacy_result
from common_backend.logging_utils import get_activity_logger
from shuttle_run.base_input import read_shuttle_run_input
from shuttle_run.calculations.age_rules import apply_shuttle_run_age_rules
from shuttle_run.runtime import SOURCES, run_shuttle_run

logger = get_activity_logger()


def calculate_shuttle_run(
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
        raise ValueError(f"Unsupported age group '{age_group}' for shuttle run")

    logger.info(
        "SHUTTLE_RUN_INPUT_READ_START | candidate_id=%s | age_group=%s | video_path=%s",
        candidate_id,
        age_group,
        video_path,
    )
    stats = read_shuttle_run_input(video_path)
    logger.info(
        "SHUTTLE_RUN_INPUT_READ_DONE | candidate_id=%s | duration=%.2f",
        candidate_id,
        stats.duration_seconds,
    )
    logger.info(
        "SHUTTLE_RUN_CONE_DETECTION_EXECUTE | candidate_id=%s | age_group=%s",
        candidate_id,
        age_group,
    )
    raw = run_shuttle_run(
        age_group=age_group,
        candidate_id=candidate_id,
        candidate_name=candidate_name,
        video_path=video_path,
        age=age,
        gender=gender,
        jumped_length=jumped_length,
    )
    normalized = normalize_legacy_result(raw)
    adjusted_score = apply_shuttle_run_age_rules(normalized.score, age_group, stats.duration_seconds)
    logger.info(
        "SHUTTLE_RUN_SCORE_COMPUTED | candidate_id=%s | raw_score=%.2f | adjusted_score=%.2f | category=%s",
        candidate_id,
        normalized.score,
        adjusted_score,
        normalized.category,
    )
    return ActivityCalculationResult(score=adjusted_score, category=normalized.category)
