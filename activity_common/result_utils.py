from __future__ import annotations

from activity_common.base import ActivityCalculationResult


def normalize_legacy_result(result: object) -> ActivityCalculationResult:
    if isinstance(result, tuple) and len(result) >= 2:
        return ActivityCalculationResult(score=float(result[0]), category=str(result[1]))
    if isinstance(result, (int, float)):
        return ActivityCalculationResult(score=float(result), category="Unknown")
    raise ValueError("Unsupported evaluator result format")


def clamp_score(score: float, max_score: float = 20.0) -> float:
    return max(0.0, min(max_score, float(score)))


def normalize_age_group(age_group: str) -> str:
    # Source folders now use the same labels exposed in the UI.
    if age_group == "9-14":
        return "10-13"
    if age_group == "9-13":
        return "10-13"
    return age_group
