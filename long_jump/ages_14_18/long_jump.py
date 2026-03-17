from ..runtime import get_activity_function

def long_jump(*args, **kwargs):
    return get_activity_function('14-18', 'long_jump')(*args, **kwargs)
