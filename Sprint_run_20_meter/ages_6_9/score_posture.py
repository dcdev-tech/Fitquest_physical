from ..runtime import get_activity_function

def score_posture(*args, **kwargs):
    return get_activity_function('6-9', 'score_posture')(*args, **kwargs)
