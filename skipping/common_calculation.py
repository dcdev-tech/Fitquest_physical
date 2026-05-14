from __future__ import annotations

from skipping.ages_2_5.skipping import run_skipping


def calculate_skipping(**kwargs):
    if kwargs.get("age_group") != "2.5-5":
        raise ValueError(f"Unsupported age group '{kwargs.get('age_group')}' for skipping")
    return run_skipping(**kwargs)
