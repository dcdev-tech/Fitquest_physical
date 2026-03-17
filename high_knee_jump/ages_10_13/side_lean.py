from ..runtime import get_activity_function

def side_lean(*args, **kwargs):
    return get_activity_function('10-13', 'side_lean')(*args, **kwargs)
