from ..runtime import get_activity_function

def arm_leg(*args, **kwargs):
    return get_activity_function('6-9', 'arm_leg')(*args, **kwargs)
