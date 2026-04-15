from ..runtime import get_activity_function

def pace(*args, **kwargs):
    return get_activity_function('6-9', 'pace')(*args, **kwargs)
