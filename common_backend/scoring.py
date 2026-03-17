from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import sys

import cv2
import numpy as np

from .config import ACTIVITY_DURATION_SECONDS, DEFAULT_MAX_SCORE
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

logger = get_activity_logger()

@dataclass
class ScoreResult:
    score: float
    max_score: float
    category: str
    duration_seconds: float


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


def _fallback_score_activity_video(activity: str, video_path: Path) -> ScoreResult:
    if activity not in ACTIVITY_DURATION_SECONDS:
        raise ValueError(f"Unsupported activity '{activity}'.")

    target_duration = float(ACTIVITY_DURATION_SECONDS[activity])
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
    progress_request_id: str | None = None,
) -> ScoreResult:
    activity_calculators = {
        "high_knee_jump": calculate_high_knee_jump,
        "shuttle_run": calculate_shuttle_run,
        "sprint_run_20m": calculate_sprint_run_20m,
        "long_jump": calculate_long_jump,
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
                )
            raw_score = float(calculation.score)
            if not math.isfinite(raw_score):
                raise ValueError("Evaluator returned non-finite score")
            score = max(0.0, min(float(DEFAULT_MAX_SCORE), raw_score))
            duration = _read_video_duration_seconds(video_path)
            complete_progress(progress_request_id, "Analysis complete")
            if activity == "shuttle_run":
                logger.info(
                    "CONE_DETECTION_STAGE_DONE | activity=shuttle_run | score=%.2f | category=%s | candidate_id=%s",
                    score,
                    calculation.category,
                    candidate_id,
                )
            logger.info(
                "SCORING_PIPELINE_DONE | activity=%s | score=%.2f | category=%s | duration=%.2f | candidate_id=%s",
                activity,
                score,
                calculation.category,
                duration,
                candidate_id,
            )
            return ScoreResult(
                score=round(score, 2),
                max_score=float(DEFAULT_MAX_SCORE),
                category=calculation.category,
                duration_seconds=round(duration, 2),
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
            return _fallback_score_activity_video(activity=activity, video_path=video_path)

    # Fallback for activities without existing evaluator code in ages_* folders.
    return _fallback_score_activity_video(activity=activity, video_path=video_path)
