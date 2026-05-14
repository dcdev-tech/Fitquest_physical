from activity_common.preschool import block_stacking_test


def run_block_stacking(**kwargs):
    return block_stacking_test(
        kwargs["video_path"],
        age=kwargs.get("age"),
        blocks_stood=kwargs.get("blocks_stood") or 0,
        blocks_dropped=kwargs.get("blocks_dropped") or 0,
    )
