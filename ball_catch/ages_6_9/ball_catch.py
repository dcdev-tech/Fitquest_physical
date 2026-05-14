from activity_common.school_motor import ball_catch_test


def run_ball_catch(**kwargs):
    return ball_catch_test(
        kwargs["video_path"],
        age=kwargs.get("age"),
        ball_catches=kwargs.get("ball_catches") or 0,
        ball_drops=kwargs.get("ball_drops") or 0,
    )
