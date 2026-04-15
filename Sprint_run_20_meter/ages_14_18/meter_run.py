from ..runtime import get_activity_function

def meter_run(*args, **kwargs):
    return get_activity_function('14-18', 'meter_run')(*args, **kwargs)
