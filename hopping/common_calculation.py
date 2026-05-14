from __future__ import annotations

from hopping.ages_2_5.hopping import run_hopping


def calculate_hopping(**kwargs):
    if kwargs.get("age_group") != "2.5-5":
        raise ValueError(f"Unsupported age group '{kwargs.get('age_group')}' for hopping")
    return run_hopping(**kwargs)
