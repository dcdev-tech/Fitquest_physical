from activity_common.school_motor import agility_ladder_test


def run_agility_ladder(**kwargs):
    return agility_ladder_test(
        kwargs["video_path"],
        ladder_box_count=kwargs.get("ladder_box_count") or 0,
    )
