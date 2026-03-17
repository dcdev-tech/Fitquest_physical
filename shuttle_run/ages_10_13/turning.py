from ..runtime import get_activity_function

def turning(*args, **kwargs):
    return get_activity_function('10-13', 'turning')(*args, **kwargs)
