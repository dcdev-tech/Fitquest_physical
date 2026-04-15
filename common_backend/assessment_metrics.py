from __future__ import annotations

import ast
from typing import Any


DUAL_TRIAL_ACTIVITIES = {"sprint_run_20m", "shuttle_run", "long_jump"}


def _parse_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return text
    if text.startswith("[") and text.endswith("]"):
        try:
            return ast.literal_eval(text)
        except Exception:
            return text
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return text


def _row_value(row: dict[str, Any] | None, key: str, default: Any = 0) -> Any:
    if not isinstance(row, dict):
        return default
    return _parse_value(row.get(key, default))


def _round_score(value: float, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(round(float(value)))))


def _bounded_round(value: float, minimum: int, maximum: int) -> int:
    rounded = int(round(float(value)))
    return max(minimum, min(maximum, rounded))


def _gender_bucket(gender: str | None) -> str:
    normalized = str(gender or "").strip().lower()
    if normalized in {"male", "boy", "m"}:
        return "boy"
    if normalized in {"female", "girl", "f"}:
        return "girl"
    return normalized


def _score_with_max(score: float | int, maximum: int) -> str:
    rounded = int(round(float(score)))
    return f"{rounded} / {maximum}"


def _sprint_posture_score(trunk_angle: float, shoulder_y_diff: float) -> int:
    if trunk_angle <= 10 and shoulder_y_diff <= 0.01:
        return 6
    if trunk_angle <= 15 and shoulder_y_diff <= 0.02:
        return 5
    if trunk_angle <= 20 and shoulder_y_diff <= 0.03:
        return 4
    if trunk_angle <= 30 and shoulder_y_diff <= 0.05:
        return 3
    if trunk_angle <= 40:
        return 2
    return 1


def _sprint_arm_score(avg_elbow_angle: float, cross_amount: float) -> int:
    if 70 <= avg_elbow_angle <= 110 and cross_amount < 0.01:
        return 6
    if 60 <= avg_elbow_angle <= 120 and cross_amount < 0.02:
        return 5
    if 50 <= avg_elbow_angle <= 130 and cross_amount < 0.03:
        return 4
    if 40 <= avg_elbow_angle <= 140 and cross_amount < 0.05:
        return 3
    if 30 <= avg_elbow_angle <= 150:
        return 2
    return 1


def _sprint_leg_score(knee_lift: float, avg_knee_angle: float) -> int:
    if knee_lift >= 0.10 and 150 <= avg_knee_angle <= 180:
        return 6
    if knee_lift >= 0.08 and 140 <= avg_knee_angle <= 180:
        return 5
    if knee_lift >= 0.06 and 130 <= avg_knee_angle <= 180:
        return 4
    if knee_lift >= 0.04 and 120 <= avg_knee_angle <= 180:
        return 3
    if knee_lift >= 0.02:
        return 2
    return 1


def _sprint_time_score(time_sec: float) -> int:
    if time_sec <= 0:
        return 0
    if time_sec <= 4.1:
        return 5
    if time_sec <= 4.5:
        return 4
    if time_sec <= 4.9:
        return 3
    if time_sec <= 5.3:
        return 2
    return 1


def _sprint_final_marking(final_score: int) -> str:
    if final_score >= 9:
        return "Outstanding"
    if final_score >= 7:
        return "Strong"
    if final_score >= 5:
        return "Adequate"
    if final_score >= 3:
        return "Improve"
    return "Major dev."


def _high_knee_complete_laps_score(age_group: str, age: int | None, laps: float) -> int:
    if laps <= 0:
        return 0
    if age_group == "6-9":
        age_value = float(age or 0)
        if 6 <= age_value <= 7.5:
            if laps >= 80:
                return 5
            if laps >= 65:
                return 4
            if laps >= 50:
                return 3
            if laps >= 35:
                return 2
            return 1
        if 7.5 < age_value <= 9:
            if laps >= 100:
                return 5
            if laps >= 80:
                return 4
            if laps >= 60:
                return 3
            if laps >= 40:
                return 2
            return 1
        return 0
    if laps >= 300:
        return 5
    if laps >= 240:
        return 4
    if laps >= 180:
        return 3
    if laps >= 120:
        return 2
    return 1


def _high_knee_postural_maintenance(avg_side_lean: float, avg_vertical_angle: float) -> int:
    side_score = 0
    if avg_side_lean < 2:
        side_score = 4
    elif avg_side_lean < 4:
        side_score = 3
    elif avg_side_lean < 6:
        side_score = 2
    elif avg_side_lean < 8:
        side_score = 1

    vertical_score = 0
    if avg_vertical_angle < 8:
        vertical_score = 4
    elif avg_vertical_angle < 15:
        vertical_score = 3
    elif avg_vertical_angle < 25:
        vertical_score = 2
    elif avg_vertical_angle < 30:
        vertical_score = 1

    return side_score + vertical_score


def _high_knee_consistency(left_data: Any, right_data: Any) -> int:
    left = list(left_data) if isinstance(left_data, list) else []
    right = list(right_data) if isinstance(right_data, list) else []
    combined = [(left[i] if i < len(left) else 0) + (right[i] if i < len(right) else 0) for i in range(5)]
    total_steps = sum(combined)
    if total_steps <= 0:
        return 0
    weighted_avg = sum((index + 1) * count for index, count in enumerate(combined)) / total_steps
    if weighted_avg >= 4.5:
        return 5
    if weighted_avg >= 3.5:
        return 4
    if weighted_avg >= 2.5:
        return 3
    if weighted_avg >= 1.5:
        return 2
    return 1


def _high_knee_coordination_score(age_group: str, age: int | None, coordinate_count: float) -> int:
    if coordinate_count <= 0:
        return 0
    if age_group == "6-9":
        age_value = float(age or 0)
        if 6 <= age_value <= 7.5:
            if coordinate_count >= 80:
                return 4
            if coordinate_count >= 60:
                return 3
            if coordinate_count >= 40:
                return 2
            if coordinate_count >= 20:
                return 1
            return 0
        if 7.5 < age_value <= 9:
            if coordinate_count >= 100:
                return 4
            if coordinate_count >= 80:
                return 3
            if coordinate_count >= 60:
                return 2
            if coordinate_count >= 40:
                return 1
            return 0
        return 0
    if coordinate_count >= 250:
        return 4
    if coordinate_count >= 180:
        return 3
    if coordinate_count >= 120:
        return 2
    if coordinate_count >= 60:
        return 1
    return 0


def _high_knee_pace_rhythm_score(age_group: str, pace: float, rhythm: float) -> float:
    if age_group == "6-9":
        if pace >= 100:
            pace_score = 1.5
        elif pace >= 70:
            pace_score = 1.0
        elif pace >= 40:
            pace_score = 0.5
        else:
            pace_score = 0.0

        if rhythm <= 0.10:
            rhythm_score = 1.5
        elif rhythm <= 0.15:
            rhythm_score = 1.0
        elif rhythm <= 0.20:
            rhythm_score = 0.5
        else:
            rhythm_score = 0.0
        return pace_score + rhythm_score

    if pace >= 120:
        pace_score = 1.5
    elif pace >= 100:
        pace_score = 1.0
    elif pace >= 60:
        pace_score = 0.5
    else:
        pace_score = 0.0

    if rhythm <= 0.05:
        rhythm_score = 1.5
    elif rhythm <= 0.10:
        rhythm_score = 1.0
    elif rhythm <= 0.15:
        rhythm_score = 0.5
    else:
        rhythm_score = 0.0
    return pace_score + rhythm_score


def _high_knee_task_completion_level(duration_seconds: float) -> int:
    if duration_seconds >= 180:
        return 1
    if duration_seconds >= 120:
        return 2
    if duration_seconds >= 60:
        return 3
    return 4


def _high_knee_quality_band(total: float) -> int:
    if total >= 18:
        return 4
    if total >= 14:
        return 3
    if total >= 10:
        return 2
    return 1


def _high_knee_base_score(id1: int, id7: float) -> int:
    if id7 <= 5:
        return 1
    if id7 <= 9:
        return 2
    if id7 >= 18:
        if id1 >= 4:
            return 5
        if id1 >= 1:
            return 4
        return 3
    if id7 >= 14:
        if id1 >= 4:
            return 4
        if id1 >= 3:
            return 4
        return 3
    if id1 >= 3:
        return 3
    return 2


def _high_knee_apply_completion_adjustment(base_score: int, completion_level: int, id1: int, id7: float) -> int:
    if id1 == 0 or id7 == 0:
        return 1
    if completion_level == 1:
        return base_score
    if completion_level == 2:
        return max(1, base_score - 1)
    if completion_level == 3:
        return min(base_score, 2)
    return min(base_score, 1)


def _high_knee_marking(final_score: int) -> str:
    if final_score >= 5:
        return "Excellent"
    if final_score >= 4:
        return "Above Average"
    if final_score >= 3:
        return "Average"
    if final_score >= 2:
        return "Below Average"
    return "Poor"


def _long_jump_distance_score(distance_cm: float) -> int:
    if distance_cm <= 0:
        return 0
    if distance_cm >= 160:
        return 5
    if distance_cm >= 140:
        return 4
    if distance_cm >= 120:
        return 3
    if distance_cm >= 100:
        return 2
    return 1


def _long_jump_arm_score(avg_angle: float) -> int:
    if 70 <= avg_angle <= 110:
        return 5
    if 60 <= avg_angle <= 120:
        return 4
    if 50 <= avg_angle <= 130:
        return 3
    if 40 <= avg_angle <= 140:
        return 2
    return 1


def _long_jump_flight_score(knee_lift: float) -> int:
    if knee_lift > 0.10:
        return 5
    if knee_lift > 0.08:
        return 4
    if knee_lift > 0.06:
        return 3
    if knee_lift > 0.04:
        return 2
    return 1


def _long_jump_landing_score(ankle_diff: float) -> int:
    if ankle_diff < 0.02:
        return 5
    if ankle_diff < 0.04:
        return 4
    if ankle_diff < 0.06:
        return 3
    if ankle_diff < 0.10:
        return 2
    return 1


def _long_jump_composite(score_2: int, score_3: int, score_4: int) -> int:
    total = score_2 + score_3 + score_4
    if total >= 13:
        return 5
    if total >= 10:
        return 4
    if total >= 7:
        return 3
    if total >= 4:
        return 2
    return 1


def _long_jump_marking(final_score: int) -> str:
    if final_score >= 9:
        return "Excellent"
    if final_score >= 7:
        return "Above Average"
    if final_score >= 5:
        return "Average"
    if final_score >= 3:
        return "Below Average"
    return "Poor"


def _shuttle_time_score(age_group: str, time_seconds: float, age: int | None, gender: str | None) -> int:
    if time_seconds <= 0:
        return 0
    if age_group != "14-18":
        if time_seconds <= 13.5:
            return 6
        if time_seconds <= 14.2:
            return 5
        if time_seconds <= 14.9:
            return 4
        if time_seconds <= 15.6:
            return 3
        if time_seconds <= 16.3:
            return 2
        return 1

    age_value = float(age or 0)
    gender_value = _gender_bucket(gender)
    limits: list[float] | None = None
    if 14 <= age_value <= 16:
        if gender_value == "boy":
            limits = [13.0, 13.8, 14.6, 15.4, 16.2]
        elif gender_value == "girl":
            limits = [13.5, 14.3, 15.1, 15.9, 16.7]
    elif 16 < age_value <= 18:
        if gender_value == "boy":
            limits = [12.8, 13.6, 14.4, 15.2, 16.0]
        elif gender_value == "girl":
            limits = [13.8, 14.6, 15.4, 16.2, 17.0]
    if not limits:
        return 0
    if time_seconds < limits[0]:
        return 6
    if time_seconds < limits[1]:
        return 5
    if time_seconds < limits[2]:
        return 4
    if time_seconds < limits[3]:
        return 3
    if time_seconds < limits[4]:
        return 2
    return 1


def _shuttle_line_touch_score(correct_touches: float) -> int:
    if correct_touches <= 0:
        return 0
    if correct_touches >= 6:
        return 6
    if correct_touches >= 5:
        return 5
    if correct_touches >= 4:
        return 4
    if correct_touches >= 3:
        return 3
    if correct_touches >= 2:
        return 2
    return 1


def _shuttle_turning_score(avg_turn_angle: float, avg_turn_time: float) -> int:
    if avg_turn_angle <= 0 and avg_turn_time <= 0:
        return 0
    if avg_turn_angle < 20 and avg_turn_time < 0.25:
        return 6
    if avg_turn_angle < 25:
        return 5
    if avg_turn_angle < 35:
        return 4
    if avg_turn_angle < 45:
        return 3
    if avg_turn_angle < 60 or avg_turn_time < 0.6:
        return 2
    return 1


def _shuttle_movement_score(speed_var: float, sway: float, accel_var: float) -> int:
    if speed_var == 0 and sway == 0 and accel_var == 0:
        return 0
    if speed_var < 0.05 and sway < 0.02 and accel_var < 0.04:
        return 6
    if speed_var < 0.07:
        return 5
    if speed_var < 0.09:
        return 4
    if sway < 0.05:
        return 3
    if sway < 0.08:
        return 2
    return 1


def _shuttle_composite(score_2: int, score_3: int, score_4: int) -> int:
    total = score_2 + score_3 + score_4
    if total >= 16:
        return 6
    if total >= 13:
        return 5
    if total >= 10:
        return 4
    if total >= 7:
        return 3
    if total >= 4:
        return 2
    return 1


def _shuttle_marking(final_score: int) -> str:
    if final_score >= 9:
        return "Outstanding"
    if final_score >= 7:
        return "Strong"
    if final_score >= 5:
        return "Adequate"
    if final_score >= 3:
        return "Improve"
    return "Major dev."


def build_assessment_metrics(
    *,
    activity: str,
    age_group: str,
    candidate_name: str | None,
    age: int | None,
    gender: str | None,
    trial_rows: list[dict[str, Any]],
    trial_durations: list[float] | None = None,
    jumped_lengths: list[float | None] | None = None,
    landing_stabilities: list[int | None] | None = None,
) -> tuple[dict[str, Any], int, int, str]:
    if activity == "sprint_run_20m":
        times = [float(_row_value(row, "Sprint_time", 0.0) or 0.0) for row in trial_rows]
        postures = [
            _sprint_posture_score(
                float(_row_value(row, "Trunk_angle_avg", 0.0) or 0.0),
                float(_row_value(row, "Shoulder_y_diff_avg", 0.0) or 0.0),
            )
            for row in trial_rows
        ]
        arms = [
            _sprint_arm_score(
                float(_row_value(row, "Avg_elbow_angle_avg", 0.0) or 0.0),
                float(_row_value(row, "Cross_amount_avg", 0.0) or 0.0),
            )
            for row in trial_rows
        ]
        legs = [
            _sprint_leg_score(
                float(_row_value(row, "Knee_lift_avg", 0.0) or 0.0),
                float(_row_value(row, "Avg_knee_angle_avg", 0.0) or 0.0),
            )
            for row in trial_rows
        ]
        avg_time = round(sum(times) / max(1, len(times)), 2)
        id1 = _sprint_time_score(avg_time)
        id2 = _round_score(sum(postures) / max(1, len(postures)), 1, 6)
        id3 = _round_score(sum(arms) / max(1, len(arms)), 1, 6)
        id4 = _round_score(sum(legs) / max(1, len(legs)), 1, 6)
        id5 = _shuttle_composite(id2, id3, id4)
        final_score = _bounded_round(((id1 + id5) / 2.0) * 2.0, 1, 10)
        final_marking = _sprint_final_marking(final_score)
        trial_1_time = round(times[0], 2) if len(times) > 0 else 0.0
        trial_2_time = round(times[1], 2) if len(times) > 1 else trial_1_time
        best_time = round(min([t for t in [trial_1_time, trial_2_time] if t > 0] or [0.0]), 2)
        metrics = {
            "Child Name": candidate_name or "",
            "Age": age if age is not None else "",
            "Trial 1 Time(s)": trial_1_time,
            "Trial 2 Time(s)": trial_2_time,
            "Best Time(s)": best_time,
            "Sprint Time Performance": _score_with_max(id1, 5),
            "Posture & Body Position": _score_with_max(id2, 6),
            "Arm Movement": _score_with_max(id3, 6),
            "Leg Action": _score_with_max(id4, 6),
            "Composite Technique Score": _score_with_max(id5, 6),
            "Final Score": _score_with_max(final_score, 10),
            "Final Marking": final_marking,
        }
        return metrics, final_score, 10, final_marking

    if activity == "high_knee_jump":
        row = trial_rows[0] if trial_rows else {}
        duration_seconds = float((trial_durations or [0.0])[0] or 0.0)
        id1 = _high_knee_complete_laps_score(
            age_group,
            age,
            float(_row_value(row, "Total_Lap", 0.0) or 0.0),
        )
        id2 = _high_knee_postural_maintenance(
            float(_row_value(row, "Avg_side_lean(deg)", 0.0) or 0.0),
            float(_row_value(row, "Avg_vertical_angle(deg)", 0.0) or 0.0),
        )
        id3 = _high_knee_consistency(
            _row_value(row, "Left_knee_height_data", []),
            _row_value(row, "Right_knee_height_data", []),
        )
        id4 = _high_knee_coordination_score(
            age_group,
            age,
            float(_row_value(row, "Arm-Leg_coordination", 0.0) or 0.0),
        )
        id5 = _high_knee_pace_rhythm_score(
            age_group,
            float(_row_value(row, "Pace", 0.0) or 0.0),
            float(_row_value(row, "Rhythm", 0.0) or 0.0),
        )
        id6 = _high_knee_task_completion_level(duration_seconds)
        id7 = round(id2 + id3 + id4 + id5, 2)
        id8 = _high_knee_quality_band(id7)
        base_score = _high_knee_base_score(id1, id7)
        adjusted_score = _high_knee_apply_completion_adjustment(base_score, id6, id1, id7)
        final_score = 1 if (id1 == 0 or id7 == 0) else max(1, min(5, int(round(adjusted_score))))
        final_marking = _high_knee_marking(final_score)
        laps_completed = int(float(_row_value(row, "Total_Lap", 0.0) or 0.0))
        metrics = {
            "Child Name": candidate_name or "",
            "Age": age if age is not None else "",
            "Duration Completed(min)": round(duration_seconds / 60.0, 2),
            "Laps Completed": laps_completed,
            "Complete Laps": _score_with_max(id1, 5),
            "Postural Maintenance": _score_with_max(id2, 8),
            "Knee Height Consistency": _score_with_max(id3, 5),
            "Arm-Leg Coordination": _score_with_max(id4, 4),
            "Pace and Rhythm Maintenance": f"{round(id5, 2)} / 3",
            "Task Completion Level": f"{id6} / 4",
            "Movement Quality Total": f"{round(id7, 2)} / 20",
            "Quality Band (internal)": _score_with_max(id8, 4),
            "Final Score": _score_with_max(final_score, 5),
            "Final Marking": final_marking,
        }
        return metrics, final_score, 5, final_marking

    if activity == "long_jump":
        distances = [float(value or 0.0) for value in (jumped_lengths or [])]
        if not distances:
            distances = [float(_row_value(row, "Jumped_distance_cm", 0.0) or 0.0) for row in trial_rows]
        best_index = 0
        if distances:
            best_index = max(range(len(distances)), key=lambda index: distances[index])
        best_row = trial_rows[best_index] if trial_rows else {}
        best_distance = distances[best_index] if best_index < len(distances) else 0.0
        id1 = _long_jump_distance_score(best_distance)
        id2 = _long_jump_arm_score(float(_row_value(best_row, "Avg_angle_final", 0.0) or 0.0))
        id3 = _long_jump_flight_score(float(_row_value(best_row, "Knee_lift_final", 0.0) or 0.0))
        id4 = _long_jump_landing_score(float(_row_value(best_row, "Ankle_diff_final", 0.0) or 0.0))
        stability_values = [int(value or 0) for value in (landing_stabilities or [])]
        id5 = stability_values[best_index] if best_index < len(stability_values) else 0
        id6 = _long_jump_composite(id2, id3, id4)
        final_score = _bounded_round(((id1 + id6) / 2.0) * 2.0, 1, 10)
        final_marking = _long_jump_marking(final_score)
        trial_1_distance = round(distances[0], 2) if len(distances) > 0 else 0.0
        trial_2_distance = round(distances[1], 2) if len(distances) > 1 else trial_1_distance
        best_distance = round(max(trial_1_distance, trial_2_distance), 2)
        metrics = {
            "Child Name": candidate_name or "",
            "Age": age if age is not None else "",
            "Trial 1 Distance(cm)": trial_1_distance,
            "Trial 2 Distance(cm)": trial_2_distance,
            "Best Distance(cm)": best_distance,
            "Jump Distance Performance": _score_with_max(id1, 5),
            "Arm Coordination & Takeoff": _score_with_max(id2, 5),
            "Flight Phase & Body Position": _score_with_max(id3, 5),
            "Landing Technique & Stability": _score_with_max(id4, 5),
            "Landing Stability Adjustment": _score_with_max(id5, 1),
            "Composite Technique Score": _score_with_max(id6, 5),
            "Final Score": _score_with_max(final_score, 10),
            "Final Marking": final_marking,
        }
        return metrics, final_score, 10, final_marking

    if activity == "shuttle_run":
        times = [float(_row_value(row, "Avg_turn_time", 0.0) or 0.0) for row in trial_rows]
        # Use legacy video-total time when available in the row fallback, otherwise derive from duration if needed.
        # Existing CSVs do not save shuttle total time, so derive it from trial video duration for ID1 scoring.
        if trial_durations:
            times = [float(value or 0.0) for value in trial_durations]
        avg_time = round(sum(times) / max(1, len(times)), 2)
        accuracy_scores = [
            _shuttle_line_touch_score(float(_row_value(row, "Accurate_lap_count", 0.0) or 0.0))
            for row in trial_rows
        ]
        turning_scores = [
            _shuttle_turning_score(
                float(_row_value(row, "Avg_turn_angle", 0.0) or 0.0),
                float(_row_value(row, "Avg_turn_time", 0.0) or 0.0),
            )
            for row in trial_rows
        ]
        movement_scores = [
            _shuttle_movement_score(
                float(_row_value(row, "Movement:speed_var", 0.0) or 0.0),
                float(_row_value(row, "Movement:sway", 0.0) or 0.0),
                float(_row_value(row, "Movement:accel_var", 0.0) or 0.0),
            )
            for row in trial_rows
        ]
        id1 = _shuttle_time_score(age_group, avg_time, age, gender)
        id2 = _round_score(sum(accuracy_scores) / max(1, len(accuracy_scores)), 1, 6)
        id3 = _round_score(sum(turning_scores) / max(1, len(turning_scores)), 1, 6)
        id4 = _round_score(sum(movement_scores) / max(1, len(movement_scores)), 1, 6)
        id5 = _shuttle_composite(id2, id3, id4)
        final_score = _bounded_round(((id1 + id5) / 2.0) * 2.0, 1, 10)
        final_marking = _shuttle_marking(final_score)
        trial_1_time = round(times[0], 2) if len(times) > 0 else 0.0
        trial_2_time = round(times[1], 2) if len(times) > 1 else trial_1_time
        best_time = round(min([t for t in [trial_1_time, trial_2_time] if t > 0] or [0.0]), 2)
        metrics = {
            "Child Name": candidate_name or "",
            "Age": age if age is not None else "",
            "Trial 1 Time(s)": trial_1_time,
            "Trial 2 Time(s)": trial_2_time,
            "Best Time(s)": best_time,
            "Shuttle Time Performance": _score_with_max(id1, 6),
            "Line Touch Accuracy": _score_with_max(id2, 6),
            "Turning Efficiency": _score_with_max(id3, 6),
            "Movement Control": _score_with_max(id4, 6),
            "Composite Technique Score": _score_with_max(id5, 6),
            "Final Score": _score_with_max(final_score, 10),
            "Final Marking": final_marking,
        }
        return metrics, final_score, 10, final_marking

    return {"Final Score": 0, "Final Marking": "Unknown"}, 0, 20, "Unknown"
