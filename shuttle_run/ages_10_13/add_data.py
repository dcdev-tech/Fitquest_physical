from ..runtime import get_activity_function

def add_data(*args, **kwargs):
    return get_activity_function('10-13', 'add_data')(*args, **kwargs)
