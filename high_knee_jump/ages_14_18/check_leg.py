from ..runtime import get_activity_function

def check_leg(*args, **kwargs):
    return get_activity_function('14-18', 'check_leg')(*args, **kwargs)
