from activity_common.school_motor import agility_test


def run_agility_test(**kwargs):
    return agility_test(kwargs["video_path"])
