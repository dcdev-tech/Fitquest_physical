from ..runtime import get_activity_function

def shuttle_run(*args, **kwargs):
    return get_activity_function('14-18', 'shuttle_run')(*args, **kwargs)
