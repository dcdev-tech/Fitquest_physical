from ..runtime import get_activity_function

def flight_phase(*args, **kwargs):
    return get_activity_function('14-18', 'flight_phase')(*args, **kwargs)
