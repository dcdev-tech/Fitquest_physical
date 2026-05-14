from __future__ import annotations

from agility_ladder.ages_10_13.agility_ladder import run_agility_ladder


def calculate_agility_ladder(**kwargs):
    if kwargs.get("age_group") != "10-13":
        raise ValueError(f"Unsupported age group '{kwargs.get('age_group')}' for agility ladder")
    return run_agility_ladder(**kwargs)
