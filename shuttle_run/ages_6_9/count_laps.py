from ..runtime import get_activity_function

def count_laps(*args, **kwargs):
    return get_activity_function('6-9', 'count_laps')(*args, **kwargs)
