from ..runtime import get_activity_function

def partial_lap(*args, **kwargs):
    return get_activity_function('10-13', 'partial_lap')(*args, **kwargs)
