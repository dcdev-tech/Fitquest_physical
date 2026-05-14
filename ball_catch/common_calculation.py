from __future__ import annotations

from ball_catch.ages_6_9.ball_catch import run_ball_catch


def calculate_ball_catch(**kwargs):
    if kwargs.get("age_group") != "6-9":
        raise ValueError(f"Unsupported age group '{kwargs.get('age_group')}' for ball catch")
    return run_ball_catch(**kwargs)
