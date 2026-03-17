from ..runtime import get_activity_function

def pace(*args, **kwargs):
    return get_activity_function('10-13', 'pace')(*args, **kwargs)
