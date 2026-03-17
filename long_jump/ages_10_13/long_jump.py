from ..runtime import get_activity_function

def long_jump(*args, **kwargs):
    return get_activity_function('10-13', 'long_jump')(*args, **kwargs)
