from ..runtime import get_activity_function

def score_leg_action(*args, **kwargs):
    return get_activity_function('14-18', 'score_leg_action')(*args, **kwargs)
