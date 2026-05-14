from __future__ import annotations

from agility_test.ages_10_13.agility_test import run_agility_test


def calculate_agility_test(**kwargs):
    if kwargs.get("age_group") != "10-13":
        raise ValueError(f"Unsupported age group '{kwargs.get('age_group')}' for agility test")
    return run_agility_test(**kwargs)
