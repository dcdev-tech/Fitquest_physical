from ..runtime import get_activity_function

def predict_category(*args, **kwargs):
    return get_activity_function('10-13', 'predict_category')(*args, **kwargs)
