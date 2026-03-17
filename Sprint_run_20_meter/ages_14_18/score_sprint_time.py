from ..runtime import get_activity_function

def score_sprint_time(*args, **kwargs):
    return get_activity_function('14-18', 'score_sprint_time')(*args, **kwargs)
