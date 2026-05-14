from __future__ import annotations

from visual_integration.ages_6_9.visual_integration import run_visual_integration


def calculate_visual_integration(**kwargs):
    if kwargs.get("age_group") != "6-9":
        raise ValueError(f"Unsupported age group '{kwargs.get('age_group')}' for visual integration")
    return run_visual_integration(**kwargs)
