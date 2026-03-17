from ..runtime import get_activity_function

def count_laps(*args, **kwargs):
    return get_activity_function('10-13', 'count_laps')(*args, **kwargs)
