from activity_common.school_motor import beads_fm_test


def run_beads_fm(**kwargs):
    return beads_fm_test(
        kwargs["video_path"],
        beads_threaded=kwargs.get("beads_threaded") or 0,
        bead_drop_count=kwargs.get("bead_drop_count") or kwargs.get("beads_dropped") or 0,
        age_group=kwargs.get("age_group") or "10-13",
    )
