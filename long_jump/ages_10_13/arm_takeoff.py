from ..runtime import get_activity_function

def arm_takeoff(*args, **kwargs):
    return get_activity_function('10-13', 'arm_takeoff')(*args, **kwargs)
