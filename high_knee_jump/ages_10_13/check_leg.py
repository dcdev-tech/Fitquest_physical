from ..runtime import get_activity_function

def check_leg(*args, **kwargs):
    return get_activity_function('10-13', 'check_leg')(*args, **kwargs)
