from ..runtime import get_activity_function

def score_arm_movement(*args, **kwargs):
    return get_activity_function('10-13', 'score_arm_movement')(*args, **kwargs)
