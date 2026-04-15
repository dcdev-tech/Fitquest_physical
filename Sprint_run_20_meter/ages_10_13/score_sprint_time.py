from ..runtime import get_activity_function

def score_sprint_time(*args, **kwargs):
    return get_activity_function('10-13', 'score_sprint_time')(*args, **kwargs)
