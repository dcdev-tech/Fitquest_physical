from __future__ import annotations

from block_stacking.ages_2_5.block_stacking import run_block_stacking


def calculate_block_stacking(**kwargs):
    if kwargs.get("age_group") != "2.5-5":
        raise ValueError(f"Unsupported age group '{kwargs.get('age_group')}' for block stacking")
    return run_block_stacking(**kwargs)
