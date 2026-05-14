from activity_common.school_motor import visual_integration_test


def run_visual_integration(**kwargs):
    return visual_integration_test(kwargs["video_path"], age=kwargs.get("age"))
