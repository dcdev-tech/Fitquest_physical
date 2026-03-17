from __future__ import annotations


def apply_high_knee_age_rules(score: float, age_group: str, duration_seconds: float) -> float:
    # High knee duration expectation can differ by age band; keep unified surface.
    if age_group == "6-9":
        factor = 1.0
    elif age_group == "10-13":
        factor = 1.0
    elif age_group == "14-18":
        factor = 1.0
    else:
        raise ValueError(f"Unsupported age group '{age_group}' for high knee")

    adjusted = score * factor
    return max(0.0, min(20.0, adjusted))
