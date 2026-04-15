from ..runtime import get_activity_function

def rhythm(*args, **kwargs):
    return get_activity_function('10-13', 'rhythm')(*args, **kwargs)
