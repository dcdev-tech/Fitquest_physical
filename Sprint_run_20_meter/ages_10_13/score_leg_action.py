from ..runtime import get_activity_function

def score_leg_action(*args, **kwargs):
    return get_activity_function('10-13', 'score_leg_action')(*args, **kwargs)
