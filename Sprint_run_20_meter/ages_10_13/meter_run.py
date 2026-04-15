from ..runtime import get_activity_function

def meter_run(*args, **kwargs):
    return get_activity_function('10-13', 'meter_run')(*args, **kwargs)
