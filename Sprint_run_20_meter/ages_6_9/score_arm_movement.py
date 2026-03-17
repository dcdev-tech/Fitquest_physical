from ..runtime import get_activity_function

def score_arm_movement(*args, **kwargs):
    return get_activity_function('6-9', 'score_arm_movement')(*args, **kwargs)
