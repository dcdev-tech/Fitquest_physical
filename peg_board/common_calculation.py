from __future__ import annotations

from peg_board.ages_10_13.peg_board import run_peg_board as run_10_13
from peg_board.ages_14_18.peg_board import run_peg_board as run_14_18
from peg_board.ages_6_9.peg_board import run_peg_board as run_6_9


def calculate_peg_board(**kwargs):
    age_group = kwargs.get("age_group")
    if age_group == "6-9":
        return run_6_9(**kwargs)
    if age_group == "10-13":
        return run_10_13(**kwargs)
    if age_group == "14-18":
        return run_14_18(**kwargs)
    raise ValueError(f"Unsupported age group '{age_group}' for peg board")
