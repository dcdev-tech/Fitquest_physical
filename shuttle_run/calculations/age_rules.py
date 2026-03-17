from __future__ import annotations


def apply_shuttle_run_age_rules(score: float, age_group: str, duration_seconds: float) -> float:
    # Activity-specific age conditions are centralized here.
    if age_group == "6-9":
        factor = 1.0
    elif age_group == "10-13":
        factor = 1.0
    elif age_group == "14-18":
        factor = 1.0
    else:
        raise ValueError(f"Unsupported age group '{age_group}' for shuttle run")

    adjusted = score * factor
    return max(0.0, min(20.0, adjusted))
