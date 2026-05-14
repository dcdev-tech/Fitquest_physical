from __future__ import annotations

from galloping.ages_2_5.galloping import run_galloping


def calculate_galloping(**kwargs):
    if kwargs.get("age_group") != "2.5-5":
        raise ValueError(f"Unsupported age group '{kwargs.get('age_group')}' for galloping")
    return run_galloping(**kwargs)
