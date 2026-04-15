from ..runtime import get_activity_function

def score_leg_action(*args, **kwargs):
    return get_activity_function('6-9', 'score_leg_action')(*args, **kwargs)
