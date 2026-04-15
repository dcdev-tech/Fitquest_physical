from ..runtime import get_activity_function

def predict_category(*args, **kwargs):
    return get_activity_function('6-9', 'predict_category')(*args, **kwargs)
