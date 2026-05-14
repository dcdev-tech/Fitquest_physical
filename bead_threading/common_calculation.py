from __future__ import annotations

from bead_threading.ages_2_5.bead_threading import run_bead_threading


def calculate_bead_threading(**kwargs):
    if kwargs.get("age_group") != "2.5-5":
        raise ValueError(f"Unsupported age group '{kwargs.get('age_group')}' for bead threading")
    return run_bead_threading(**kwargs)
