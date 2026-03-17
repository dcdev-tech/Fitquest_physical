from ..runtime import get_activity_function

def cal_arm_movement(*args, **kwargs):
    return get_activity_function('14-18', 'cal_arm_movement')(*args, **kwargs)
