from ..runtime import get_activity_function

def endurance_score(*args, **kwargs):
    return get_activity_function('6-9', 'endurance_score')(*args, **kwargs)
