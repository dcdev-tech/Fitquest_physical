from activity_common.school_motor import peg_board_test


def run_peg_board(**kwargs):
    return peg_board_test(
        kwargs["video_path"],
        peg_count=kwargs.get("peg_count") or 0,
        peg_drop_count=kwargs.get("peg_drop_count") or 0,
        age_group=kwargs.get("age_group") or "6-9",
    )
