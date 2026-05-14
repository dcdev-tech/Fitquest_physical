from __future__ import annotations

from running.ages_2_5.running import run_running


def calculate_running(**kwargs):
    if kwargs.get("age_group") != "2.5-5":
        raise ValueError(f"Unsupported age group '{kwargs.get('age_group')}' for running")
    return run_running(**kwargs)
