from ..runtime import get_activity_function

def score_flight_phase(*args, **kwargs):
    return get_activity_function('14-18', 'score_flight_phase')(*args, **kwargs)
