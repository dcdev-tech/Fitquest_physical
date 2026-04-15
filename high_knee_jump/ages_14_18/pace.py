from ..runtime import get_activity_function

def pace(*args, **kwargs):
    return get_activity_function('14-18', 'pace')(*args, **kwargs)
