from __future__ import annotations

from beads_fm.ages_10_13.beads_fm import run_beads_fm as run_10_13
from beads_fm.ages_14_18.beads_fm import run_beads_fm as run_14_18


def calculate_beads_fm(**kwargs):
    age_group = kwargs.get("age_group")
    if age_group == "10-13":
        return run_10_13(**kwargs)
    if age_group == "14-18":
        return run_14_18(**kwargs)
    raise ValueError(f"Unsupported age group '{age_group}' for beads FM")
