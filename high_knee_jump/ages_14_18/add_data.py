from ..runtime import get_activity_function

def add_data(*args, **kwargs):
    return get_activity_function('14-18', 'add_data')(*args, **kwargs)
