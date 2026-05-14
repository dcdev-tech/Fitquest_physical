from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import sys

import cv2
import numpy as np

from .config import ACTIVITY_DURATION_SECONDS, ACTIVITY_DURATION_SECONDS_BY_GROUP, DEFAULT_MAX_SCORE
from .logging_utils import get_activity_logger
from .progress import (
    complete_progress,
    fail_progress,
    set_progress_message,
    track_request_progress,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from high_knee_jump.common_calculation import calculate_high_knee_jump
from long_jump.common_calculation import calculate_long_jump
from shuttle_run.common_calculation import calculate_shuttle_run
from Sprint_run_20_meter.common_calculation import calculate_sprint_run_20m
from agility_ladder.common_calculation import calculate_agility_ladder
from agility_test.common_calculation import calculate_agility_test
from ball_catch.common_calculation import calculate_ball_catch
from bead_threading.common_calculation import calculate_bead_threading
from beads_fm.common_calculation import calculate_beads_fm
from block_stacking.common_calculation import calculate_block_stacking
from galloping.common_calculation import calculate_galloping
from hopping.common_calculation import calculate_hopping
from jumping.common_calculation import calculate_jumping
from peg_board.common_calculation import calculate_peg_board
from running.common_calculation import calculate_running
from skipping.common_calculation import calculate_skipping
from visual_integration.common_calculation import calculate_visual_integration

logger = get_activity_logger()
PRESCHOOL_ACTIVITIES = {
    "running",
    "galloping",
    "hopping",
    "skipping",
    "jumping",
    "bead_threading",
    "block_stacking",
    "ball_catch",
    "peg_board",
    "visual_integration",
    "beads_fm",
    "agility_ladder",
    "agility_test",
}

@dataclass
class ScoreResult:
    score: float
    max_score: float
    category: str
    duration_seconds: float
    activity_metrics: dict | None = None


def _category_from_ratio(ratio: float) -> str:
    if ratio >= 0.85:
        return "Excellent"
    if ratio >= 0.65:
        return "Above Average"
    if ratio >= 0.45:
        return "Average"
    if ratio >= 0.25:
        return "Below Average"
    return "Poor"


def _category_from_score(score: float, max_score: float) -> str:
    ratio = max(0.0, min(1.0, float(score) / max(1.0, float(max_score))))
    return _category_from_ratio(ratio)


def _read_video_duration_seconds(video_path: Path) -> float:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError("Unable to open uploaded video.")

    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
    cap.release()

    if fps <= 0:
        raise ValueError("Invalid FPS detected in video.")
    return float(frame_count / fps)


def _estimate_motion_factor(video_path: Path, sample_step: int = 5) -> float:
    """Simple reusable motion estimator to keep scoring consistent across activities."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError("Unable to read video for motion analysis.")

    prev_gray = None
    diffs = []
    idx = 0

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        idx += 1
        if idx % sample_step != 0:
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if prev_gray is not None:
            diff = cv2.absdiff(gray, prev_gray)
            diffs.append(float(np.mean(diff)))
        prev_gray = gray

    cap.release()

    if not diffs:
        return 0.0

    mean_diff = float(np.mean(diffs))
    # Normalize roughly into [0,1].
    return float(min(1.0, mean_diff / 35.0))


def _target_duration_seconds(activity: str, age_group: str | None = None) -> float:
    if age_group:
        group_durations = ACTIVITY_DURATION_SECONDS_BY_GROUP.get(age_group, {})
        if activity in group_durations:
            return float(group_durations[activity])
    return float(ACTIVITY_DURATION_SECONDS[activity])


def _fallback_score_activity_video(activity: str, video_path: Path, age_group: str | None = None) -> ScoreResult:
    if activity not in ACTIVITY_DURATION_SECONDS:
        raise ValueError(f"Unsupported activity '{activity}'.")

    target_duration = _target_duration_seconds(activity, age_group)
    duration = _read_video_duration_seconds(video_path)

    # Existing concept retained: score should be duration-aware.
    duration_ratio = min(1.0, duration / target_duration) if target_duration > 0 else 0.0
    motion_ratio = _estimate_motion_factor(video_path)

    # Reusable weighted score across all activities.
    composite_ratio = (0.7 * duration_ratio) + (0.3 * motion_ratio)
    score = round(DEFAULT_MAX_SCORE * composite_ratio, 2)
    category = _category_from_ratio(composite_ratio)
    logger.info(
        "SCORING_FALLBACK_USED | activity=%s | duration=%.2f | motion_ratio=%.4f | score=%.2f | category=%s",
        activity,
        duration,
        motion_ratio,
        score,
        category,
    )

    return ScoreResult(
        score=score,
        max_score=float(DEFAULT_MAX_SCORE),
        category=category,
        duration_seconds=round(duration, 2),
        activity_metrics={
            "Duration Seconds": round(duration, 2),
            "Motion Ratio": round(motion_ratio, 4),
            "Duration Completion": {"score": round(duration_ratio, 4), "maxValue": 1},
            "Motion Quality": {"score": round(motion_ratio, 4), "maxValue": 1},
            "Final Score": {"score": score, "maxValue": float(DEFAULT_MAX_SCORE)},
            "Final Marking": category,
        },
    )


def score_activity_video(
    activity: str,
    video_path: Path,
    age_group: str,
    candidate_id: str,
    candidate_name: str,
    age: int | None = None,
    gender: str | None = None,
    jumped_length: float | None = None,
    blocks_stood: int | None = None,
    blocks_dropped: int | None = None,
    beads_threaded: int | None = None,
    beads_dropped: int | None = None,
    ball_catches: int | None = None,
    ball_drops: int | None = None,
    peg_count: int | None = None,
    peg_drop_count: int | None = None,
    bead_drop_count: int | None = None,
    ladder_box_count: int | None = None,
    progress_request_id: str | None = None,
) -> ScoreResult:
    activity_calculators = {
        "high_knee_jump": calculate_high_knee_jump,
        "shuttle_run": calculate_shuttle_run,
        "sprint_run_20m": calculate_sprint_run_20m,
        "long_jump": calculate_long_jump,
        "running": calculate_running,
        "galloping": calculate_galloping,
        "hopping": calculate_hopping,
        "skipping": calculate_skipping,
        "jumping": calculate_jumping,
        "bead_threading": calculate_bead_threading,
        "block_stacking": calculate_block_stacking,
        "ball_catch": calculate_ball_catch,
        "peg_board": calculate_peg_board,
        "visual_integration": calculate_visual_integration,
        "beads_fm": calculate_beads_fm,
        "agility_ladder": calculate_agility_ladder,
        "agility_test": calculate_agility_test,
    }

    if activity in activity_calculators:
        calculator = activity_calculators[activity]
        logger.info(
            "SCORING_PIPELINE_START | activity=%s | age_group=%s | candidate_id=%s",
            activity,
            age_group,
            candidate_id,
        )
        if activity == "shuttle_run":
            logger.info(
                "CONE_DETECTION_STAGE_START | activity=shuttle_run | age_group=%s | candidate_id=%s",
                age_group,
                candidate_id,
            )
        try:
            set_progress_message(progress_request_id, "Processing video frames", status="processing")
            with track_request_progress(progress_request_id):
                calculation = calculator(
                    age_group=age_group,
                    candidate_id=candidate_id,
                    candidate_name=candidate_name,
                    video_path=str(video_path),
                    age=age,
                    gender=gender,
                    jumped_length=jumped_length,
                    blocks_stood=blocks_stood,
                    blocks_dropped=blocks_dropped,
                    beads_threaded=beads_threaded,
                    beads_dropped=beads_dropped,
                    ball_catches=ball_catches,
                    ball_drops=ball_drops,
                    peg_count=peg_count,
                    peg_drop_count=peg_drop_count,
                    bead_drop_count=bead_drop_count,
                    ladder_box_count=ladder_box_count,
                )
            raw_score = float(calculation.score)
            if not math.isfinite(raw_score):
                raise ValueError("Evaluator returned non-finite score")
            max_score = 5.0 if activity in PRESCHOOL_ACTIVITIES else float(DEFAULT_MAX_SCORE)
            score = max(0.0, min(max_score, raw_score))
            category = str(calculation.category or "").strip()
            if not category or category.lower() == "unknown":
                category = _category_from_score(score, max_score)
            duration = 0.0 if activity == "visual_integration" else _read_video_duration_seconds(video_path)
            complete_progress(progress_request_id, "Analysis complete")
            if activity == "shuttle_run":
                logger.info(
                    "CONE_DETECTION_STAGE_DONE | activity=shuttle_run | score=%.2f | category=%s | candidate_id=%s",
                    score,
                    category,
                    candidate_id,
                )
            logger.info(
                "SCORING_PIPELINE_DONE | activity=%s | score=%.2f | category=%s | duration=%.2f | candidate_id=%s",
                activity,
                score,
                category,
                duration,
                candidate_id,
            )
            return ScoreResult(
                score=round(score, 2),
                max_score=max_score,
                category=category,
                duration_seconds=round(duration, 2),
                activity_metrics=getattr(calculation, "metrics", None),
            )
        except Exception as exc:
            fail_progress(progress_request_id, str(exc))
            # Keep API stable even when legacy notebook evaluators fail on edge videos.
            logger.exception(
                "SCORING_PIPELINE_FAIL | activity=%s | age_group=%s | candidate_id=%s | error=%s",
                activity,
                age_group,
                candidate_id,
                exc,
            )
            return _fallback_score_activity_video(activity=activity, video_path=video_path, age_group=age_group)

    # Fallback for activities without existing evaluator code in ages_* folders.
    return _fallback_score_activity_video(activity=activity, video_path=video_path, age_group=age_group)
