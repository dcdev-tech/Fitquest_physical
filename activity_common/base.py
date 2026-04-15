from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class ActivityCalculationResult:
    score: float
    category: str


def resolve_age_group(age_group: str, aliases: dict[str, str], supported: set[str]) -> str:
    resolved = aliases.get(age_group, age_group)
    if resolved not in supported:
        raise ValueError(f"Unsupported age group '{age_group}'.")
    return resolved


def run_activity_calculation(
    *,
    runner: Callable[..., object],
    age_group: str,
    aliases: dict[str, str],
    supported: set[str],
    candidate_id: str,
    candidate_name: str,
    video_path: str,
    age: int | None = None,
    gender: str | None = None,
    data_print: str = "N",
    jumped_length: float | None = None,
    max_score: float = 20.0,
) -> ActivityCalculationResult:
    resolved_group = resolve_age_group(age_group=age_group, aliases=aliases, supported=supported)

    raw_result = runner(
        age_group=resolved_group,
        candidate_id=candidate_id,
        candidate_name=candidate_name,
        video_path=video_path,
        age=age,
        gender=gender,
        data_print=data_print,
        jumped_length=jumped_length,
    )

    if isinstance(raw_result, tuple) and len(raw_result) >= 2:
        return ActivityCalculationResult(score=float(raw_result[0]), category=str(raw_result[1]))

    if isinstance(raw_result, (int, float)):
        score = float(raw_result)
        ratio = max(0.0, min(1.0, score / max_score))
        if ratio >= 0.85:
            category = "Excellent"
        elif ratio >= 0.65:
            category = "Above Average"
        elif ratio >= 0.45:
            category = "Average"
        elif ratio >= 0.25:
            category = "Below Average"
        else:
            category = "Poor"
        return ActivityCalculationResult(score=score, category=category)

    raise ValueError("Activity evaluator returned unsupported result format.")
