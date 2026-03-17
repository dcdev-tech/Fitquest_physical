"""Shared activity configuration for all age groups."""

from typing import Dict, List

AGE_GROUPS: Dict[str, Dict[str, object]] = {
    "2-5": {
        "min_age": 2,
        "max_age": 5,
        "activities": ["loco_motor", "gross_motor", "fine_motor"],
    },
    "6-9": {
        "min_age": 6,
        "max_age": 9,
        "activities": ["high_knee_jump", "shuttle_run", "sprint_run_20m", "visual_integration"],
    },
    "10-13": {
        "min_age": 10,
        "max_age": 13,
        "activities": ["high_knee_jump", "shuttle_run", "sprint_run_20m", "long_jump"],
    },
    "14-18": {
        "min_age": 14,
        "max_age": 18,
        "activities": ["high_knee_jump", "shuttle_run", "sprint_run_20m", "long_jump"],
    },
}

ACTIVITY_LABELS: Dict[str, str] = {
    "loco_motor": "Loco Motor",
    "gross_motor": "Gross Motor",
    "fine_motor": "Fine Motor",
    "high_knee_jump": "High Knee Jump",
    "shuttle_run": "Shuttle Run",
    "sprint_run_20m": "Sprint Run 20 Meter",
    "visual_integration": "Visual Integration",
    "long_jump": "Long Jump",
}

ACTIVITY_DURATION_SECONDS: Dict[str, int] = {
    "high_knee_jump": 180,
    "shuttle_run": 15,
    "sprint_run_20m": 15,
    "long_jump": 10,
    "loco_motor": 20,
    "gross_motor": 20,
    "fine_motor": 20,
    "visual_integration": 20,
}

DEFAULT_MAX_SCORE = 20


def age_group_for_age(age: int) -> str:
    for group, spec in AGE_GROUPS.items():
        if int(spec["min_age"]) <= age <= int(spec["max_age"]):
            return group
    raise ValueError(f"Age {age} is outside supported ranges.")


def activities_for_group(age_group: str) -> List[str]:
    if age_group not in AGE_GROUPS:
        raise ValueError(f"Unsupported age group: {age_group}")
    return list(AGE_GROUPS[age_group]["activities"])


def validate_activity_for_group(age_group: str, activity: str) -> None:
    if activity not in activities_for_group(age_group):
        raise ValueError(f"Activity '{activity}' is not allowed for age group '{age_group}'.")


def validate_age_in_group(age_group: str, age: int) -> None:
    if age_group not in AGE_GROUPS:
        raise ValueError(f"Unsupported age group: {age_group}")
    spec = AGE_GROUPS[age_group]
    min_age = int(spec["min_age"])
    max_age = int(spec["max_age"])
    if not (min_age <= age <= max_age):
        raise ValueError(
            f"Age {age} is outside selected group '{age_group}' range ({min_age}-{max_age})."
        )
