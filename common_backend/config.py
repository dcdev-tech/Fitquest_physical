"""Shared activity configuration for all age groups."""

from typing import Dict, List

AGE_GROUP_ALIASES = {
    "9-14": "10-13",
    "2-5": "2.5-5",
}

AGE_GROUPS: Dict[str, Dict[str, object]] = {
    "2.5-5": {
        "min_age": 2.5,
        "max_age": 5,
        "activities": [
            "running",
            "galloping",
            "hopping",
            "skipping",
            "jumping",
            "bead_threading",
            "block_stacking",
        ],
    },
    "6-9": {
        "min_age": 6,
        "max_age": 9,
        "activities": [
            "high_knee_jump",
            "shuttle_run",
            "sprint_run_20m",
            "visual_integration",
            "ball_catch",
            "peg_board",
        ],
    },
    "10-13": {
        "min_age": 10,
        "max_age": 13,
        "activities": [
            "high_knee_jump",
            "shuttle_run",
            "sprint_run_20m",
            "long_jump",
            "peg_board",
            "beads_fm",
            "agility_ladder",
            "agility_test",
        ],
    },
    "14-18": {
        "min_age": 14,
        "max_age": 18,
        "activities": [
            "high_knee_jump",
            "shuttle_run",
            "sprint_run_20m",
            "long_jump",
            "peg_board",
            "beads_fm",
        ],
    },
}

ACTIVITY_LABELS: Dict[str, str] = {
    "loco_motor": "Loco Motor",
    "gross_motor": "Gross Motor",
    "fine_motor": "Fine Motor",
    "running": "Running",
    "galloping": "Galloping",
    "hopping": "Hopping",
    "skipping": "Skipping",
    "jumping": "Jumping",
    "bead_threading": "Bead Threading",
    "block_stacking": "Block Stacking",
    "high_knee_jump": "High Knee Jump",
    "shuttle_run": "Shuttle Run",
    "sprint_run_20m": "Sprint Run 20 Meter",
    "visual_integration": "Visual Integration",
    "long_jump": "Long Jump",
    "ball_catch": "Ball Catch",
    "peg_board": "Peg Board",
    "beads_fm": "Beads FM",
    "agility_ladder": "Agility Ladder",
    "agility_test": "Agility Test",
}

ACTIVITY_LABELS_BY_GROUP: Dict[str, Dict[str, str]] = {
    "6-9": {
        "sprint_run_20m": "Sprint Run 10 m",
    },
}

ACTIVITY_DURATION_SECONDS: Dict[str, int] = {
    "high_knee_jump": 180,
    "shuttle_run": 15,
    "sprint_run_20m": 15,
    "long_jump": 10,
    "loco_motor": 20,
    "gross_motor": 20,
    "fine_motor": 20,
    "running": 20,
    "galloping": 20,
    "hopping": 20,
    "skipping": 20,
    "jumping": 20,
    "bead_threading": 20,
    "block_stacking": 20,
    "visual_integration": 20,
    "ball_catch": 20,
    "peg_board": 20,
    "beads_fm": 60,
    "agility_ladder": 20,
    "agility_test": 20,
}

ACTIVITY_DURATION_SECONDS_BY_GROUP: Dict[str, Dict[str, int]] = {
    "6-9": {
        "high_knee_jump": 75,
    },
}

DEFAULT_MAX_SCORE = 20


def canonical_age_group(age_group: str) -> str:
    return AGE_GROUP_ALIASES.get(age_group, age_group)


def age_group_for_age(age: float) -> str:
    for group, spec in AGE_GROUPS.items():
        if float(spec["min_age"]) <= age <= float(spec["max_age"]):
            return group
    raise ValueError(f"Age {age} is outside supported ranges.")


def activities_for_group(age_group: str) -> List[str]:
    age_group = canonical_age_group(age_group)
    if age_group not in AGE_GROUPS:
        raise ValueError(f"Unsupported age group: {age_group}")
    return list(AGE_GROUPS[age_group]["activities"])


def validate_activity_for_group(age_group: str, activity: str) -> None:
    age_group = canonical_age_group(age_group)
    if activity not in activities_for_group(age_group):
        raise ValueError(f"Activity '{activity}' is not allowed for age group '{age_group}'.")


def validate_age_in_group(age_group: str, age: float) -> None:
    age_group = canonical_age_group(age_group)
    if age_group not in AGE_GROUPS:
        raise ValueError(f"Unsupported age group: {age_group}")
    spec = AGE_GROUPS[age_group]
    min_age = float(spec["min_age"])
    max_age = float(spec["max_age"])
    if not (min_age <= age <= max_age):
        raise ValueError(
            f"Age {age} is outside selected group '{age_group}' range ({min_age}-{max_age})."
        )
