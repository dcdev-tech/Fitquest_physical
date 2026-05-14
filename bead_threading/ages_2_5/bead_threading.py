from activity_common.preschool import bead_threading_test


def run_bead_threading(**kwargs):
    return bead_threading_test(
        kwargs["video_path"],
        age=kwargs.get("age"),
        beads_threaded=kwargs.get("beads_threaded") or 0,
        beads_dropped=kwargs.get("beads_dropped") or 0,
    )
