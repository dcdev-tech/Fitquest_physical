from __future__ import annotations

from jumping.ages_2_5.jumping import run_jumping


def calculate_jumping(**kwargs):
    if kwargs.get("age_group") != "2.5-5":
        raise ValueError(f"Unsupported age group '{kwargs.get('age_group')}' for jumping")
    return run_jumping(**kwargs)
