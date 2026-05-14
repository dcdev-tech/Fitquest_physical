from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import math

import cv2
import mediapipe as mp
import numpy as np
from scipy.signal import find_peaks

from activity_common.base import ActivityCalculationResult
from activity_common.preschool import category_from_score, safe_mean, safe_std


mp_pose = mp.solutions.pose
mp_hands = mp.solutions.hands


@dataclass
class SchoolMotorResult(ActivityCalculationResult):
    metrics: dict[str, Any] = field(default_factory=dict)


def _result(score: float, metrics: dict[str, Any]) -> SchoolMotorResult:
    final = max(0.0, min(5.0, round(float(score), 2)))
    metrics = dict(metrics)
    metrics["Final Score"] = {"score": final, "maxValue": 5}
    metrics["Final Marking"] = category_from_score(final, 5)
    return SchoolMotorResult(score=final, category=category_from_score(final, 5), metrics=metrics)


def _hand_stability(x_coords: list[float], y_coords: list[float]) -> float:
    if len(x_coords) < 5:
        return 1.0
    return safe_std(x_coords) + safe_std(y_coords)


def _compute_bimanual_metrics(
    left_y: list[float],
    right_y: list[float],
    time_list: list[float],
) -> tuple[float, float, float, float]:
    min_len = min(len(left_y), len(right_y), len(time_list))
    if min_len < 5:
        return 1.0, 1.0, 1.0, 1.0
    left = np.array(left_y[:min_len])
    right = np.array(right_y[:min_len])
    time = np.array(time_list[:min_len])
    peaks_l, _ = find_peaks(-left, distance=5)
    peaks_r, _ = find_peaks(-right, distance=5)
    rhythm_values = []
    if len(peaks_l) > 1:
        rhythm_values.extend(np.diff(time[peaks_l]))
    if len(peaks_r) > 1:
        rhythm_values.extend(np.diff(time[peaks_r]))
    rhythm = safe_std(rhythm_values, 1.0)
    sync_diff = safe_mean(np.abs(left - right))
    fatigue = float(abs(safe_mean(left[: max(1, min_len // 3)]) - safe_mean(left[-max(1, min_len // 3) :])))
    stability = safe_std(left) + safe_std(right)
    return stability, rhythm, sync_diff, fatigue


def _hand_motion_metrics(video_path: str) -> dict[str, float]:
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    left_y: list[float] = []
    right_y: list[float] = []
    time_list: list[float] = []
    x_coords: list[float] = []
    y_coords: list[float] = []
    frame_idx = 0
    with mp_hands.Hands(min_detection_confidence=0.6) as hands:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            results = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            if results.multi_hand_landmarks:
                for hand_landmarks in results.multi_hand_landmarks:
                    lm = hand_landmarks.landmark
                    x = lm[8].x
                    y = lm[8].y
                    x_coords.append(x)
                    y_coords.append(y)
                    if x < 0.5:
                        left_y.append(y)
                    else:
                        right_y.append(y)
                    time_list.append(frame_idx / fps)
            frame_idx += 1
    cap.release()
    stability, rhythm, sync_diff, fatigue = _compute_bimanual_metrics(left_y, right_y, time_list)
    y = np.array(y_coords)
    if len(y) > 3:
        accel = np.diff(np.diff(y))
        jerk = np.diff(accel) if len(accel) > 1 else np.array([0])
        accel_var = safe_std(accel, 1.0)
        jerk_var = safe_std(jerk, 1.0)
    else:
        accel_var = 1.0
        jerk_var = 1.0
    return {
        "stability": _hand_stability(x_coords, y_coords) if x_coords else stability,
        "rhythm": rhythm,
        "sync": sync_diff,
        "fatigue": fatigue,
        "accel_var": accel_var,
        "jerk_var": jerk_var,
    }


def _peg_count_score(total_pegs: int) -> float:
    if total_pegs >= 20:
        return 5
    if total_pegs >= 16:
        return 4
    if total_pegs >= 12:
        return 3
    if total_pegs >= 8:
        return 2
    return 1


def _bead_count_score(bead_count: int) -> float:
    if bead_count >= 30:
        return 5
    if bead_count >= 24:
        return 4
    if bead_count >= 18:
        return 3
    if bead_count >= 12:
        return 2
    return 1


def _error_adjustment(base_score: float, errors: int) -> float:
    if errors <= 0:
        return base_score
    if errors <= 2:
        return base_score - 0.5
    if errors <= 5:
        return base_score - 1
    return min(base_score, 2)


def _fine_quality_score(stability: float, rhythm: float, sync: float, accel_var: float, jerk_var: float, fatigue: float) -> int:
    score = 0
    score += 2 if stability < 0.02 else 1 if stability < 0.05 else 0
    score += 2 if rhythm < 0.08 else 1 if rhythm < 0.15 else 0
    score += 2 if sync < 0.04 else 1 if sync < 0.08 else 0
    score += 1 if accel_var < 0.04 and jerk_var < 0.08 else 0
    score += 1 if fatigue < 0.05 else 0
    return max(1, min(8, score))


def _fine_final_score(base_score: float, quality: int) -> int:
    if base_score >= 4 and quality >= 6:
        return 5
    if base_score >= 3 and quality >= 4:
        return 4
    if base_score >= 3:
        return 3
    if base_score == 2:
        return 2
    return 1


def peg_board_test(video_path: str, *, peg_count: int, peg_drop_count: int = 0, age_group: str) -> SchoolMotorResult:
    metrics_raw = _hand_motion_metrics(video_path)
    base = _error_adjustment(_peg_count_score(int(peg_count)), int(peg_drop_count))
    quality = _fine_quality_score(
        metrics_raw["stability"],
        metrics_raw["rhythm"],
        metrics_raw["sync"],
        metrics_raw["accel_var"],
        metrics_raw["jerk_var"],
        metrics_raw["fatigue"],
    )
    final = _fine_final_score(base, quality)
    return _result(
        final,
        {
            "Age Group": age_group,
            "Peg Count": int(peg_count),
            "Peg Drop Count": int(peg_drop_count),
            "Primary Peg Score": {"score": round(base, 2), "maxValue": 5},
            "Quality Score": {"score": quality, "maxValue": 8},
            "Stability": round(metrics_raw["stability"], 3),
            "Rhythm": round(metrics_raw["rhythm"], 3),
            "Coordination": round(metrics_raw["sync"], 3),
            "Fatigue": round(metrics_raw["fatigue"], 3),
        },
    )


def beads_fm_test(video_path: str, *, beads_threaded: int, bead_drop_count: int = 0, age_group: str) -> SchoolMotorResult:
    metrics_raw = _hand_motion_metrics(video_path)
    base = _error_adjustment(_bead_count_score(int(beads_threaded)), int(bead_drop_count))
    quality = _fine_quality_score(
        metrics_raw["stability"],
        metrics_raw["rhythm"],
        metrics_raw["sync"],
        metrics_raw["accel_var"],
        metrics_raw["jerk_var"],
        metrics_raw["fatigue"],
    )
    final = _fine_final_score(base, quality)
    return _result(
        final,
        {
            "Age Group": age_group,
            "Beads Threaded": int(beads_threaded),
            "Bead Drop Count": int(bead_drop_count),
            "Primary Bead Score": {"score": round(base, 2), "maxValue": 5},
            "Quality Score": {"score": quality, "maxValue": 8},
            "Stability": round(metrics_raw["stability"], 3),
            "Rhythm": round(metrics_raw["rhythm"], 3),
            "Coordination": round(metrics_raw["sync"], 3),
            "Fatigue": round(metrics_raw["fatigue"], 3),
        },
    )


def _ball_age_bucket(age: float | int | None) -> str:
    return "6-7" if float(age or 0) < 8 else "8-9"


def _ball_success_score(catches: int, age_bucket: str) -> int:
    if age_bucket == "6-7":
        if catches >= 8:
            return 5
        if catches >= 6:
            return 4
        if catches >= 4:
            return 3
        if catches >= 2:
            return 2
        return 1
    if catches >= 9:
        return 5
    if catches >= 7:
        return 4
    if catches >= 5:
        return 3
    if catches >= 3:
        return 2
    return 1


def ball_catch_test(video_path: str, *, age: float | int | None, ball_catches: int, ball_drops: int) -> SchoolMotorResult:
    age_bucket = _ball_age_bucket(age)
    success = _ball_success_score(int(ball_catches), age_bucket)
    form = max(1, min(5, 5 - int(ball_drops) // 2))
    final = round((success + form) / 2)
    return _result(
        final,
        {
            "Age Band": age_bucket,
            "Ball Catches": int(ball_catches),
            "Ball Drops": int(ball_drops),
            "Success Score": {"score": success, "maxValue": 5},
            "Form Score": {"score": form, "maxValue": 5},
        },
    )


def _split_grid(img: np.ndarray) -> list[np.ndarray]:
    h, w = img.shape[:2]
    return [img[i * h // 2 : (i + 1) * h // 2, j * w // 4 : (j + 1) * w // 4] for i in range(2) for j in range(4)]


def _preprocess_shape(img: np.ndarray) -> np.ndarray:
    if len(img.shape) == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    img = cv2.GaussianBlur(img, (5, 5), 0)
    _, th = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    if np.sum(th == 255) > np.sum(th == 0):
        th = cv2.bitwise_not(th)
    return cv2.morphologyEx(th, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))


def _extract_shape(th: np.ndarray) -> np.ndarray | None:
    cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    x, y, w, h = cv2.boundingRect(max(cnts, key=cv2.contourArea))
    return th[y : y + h, x : x + w]


def _normalize_shape(img: np.ndarray) -> np.ndarray:
    canvas = np.zeros((128, 128), dtype=np.uint8)
    h, w = img.shape
    scale = 100 / max(h, w, 1)
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    resized = cv2.resize(img, (new_w, new_h))
    x_offset = (128 - new_w) // 2
    y_offset = (128 - new_h) // 2
    canvas[y_offset : y_offset + new_h, x_offset : x_offset + new_w] = resized
    return canvas


def _line_type(shape: np.ndarray) -> str:
    pts = np.column_stack(np.where(shape > 0))
    if len(pts) < 10:
        return "unknown"
    y_min, x_min = pts.min(axis=0)
    y_max, x_max = pts.max(axis=0)
    h = y_max - y_min + 1
    w = x_max - x_min + 1
    if h > 4 * w:
        return "vertical_line"
    if w > 4 * h:
        return "horizontal_line"
    return "other"


def _shape_similarity(img1: np.ndarray, img2: np.ndarray) -> float:
    crop1 = _extract_shape(_preprocess_shape(img1))
    crop2 = _extract_shape(_preprocess_shape(img2))
    if crop1 is None or crop2 is None:
        return 0.0
    norm1 = _normalize_shape(crop1)
    norm2 = _normalize_shape(crop2)
    type1 = _line_type(norm1)
    type2 = _line_type(norm2)
    if type1 != type2 and ("line" in type1 or "line" in type2):
        return 0.01
    edge1 = cv2.Canny(norm1, 50, 150)
    edge2 = cv2.Canny(norm2, 50, 150)
    dist1 = cv2.distanceTransform(255 - edge1, cv2.DIST_L2, 3)
    dist2 = cv2.distanceTransform(255 - edge2, cv2.DIST_L2, 3)
    pts1 = np.column_stack(np.where(edge1 > 0))
    pts2 = np.column_stack(np.where(edge2 > 0))
    if len(pts1) == 0 or len(pts2) == 0:
        return 0.0
    dist = (dist2[pts1[:, 0], pts1[:, 1]].mean() + dist1[pts2[:, 0], pts2[:, 1]].mean()) / 2
    return float(np.exp(-dist / 2.5))


def _shape_quality_score(shape: np.ndarray) -> int:
    edges = cv2.Canny(shape, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    perimeters = [cv2.arcLength(c, True) for c in contours]
    smoothness = np.std(perimeters) if perimeters else 1
    closure = sum(1 for c in contours if cv2.isContourConvex(c))
    h, w = shape.shape
    ratio = w / (h + 1e-6)
    score = 0
    score += 2 if smoothness < 10 else 1 if smoothness < 20 else 0
    score += 1 if closure >= 1 else 0
    score += 2 if 0.7 < ratio < 1.3 else 1 if 0.5 < ratio < 1.5 else 0
    return max(1, min(5, score))


def visual_integration_test(image_path: str, *, age: float | int | None) -> SchoolMotorResult:
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError("Unable to read uploaded visual integration image.")
    template_dir = Path(__file__).resolve().parents[1] / "ages_6-9" / "visual_integration" / "templates"
    template_order = ["vertical_line", "horizontal_line", "circle", "cross", "square", "x", "triangle", "diamond"]
    cells = _split_grid(img)
    correct = 0
    quality_scores = []
    similarities: dict[str, float] = {}
    for index, key in enumerate(template_order):
        template = cv2.imread(str(template_dir / f"{key}.png"), 0)
        if template is None:
            quality_scores.append(1)
            similarities[key] = 0.0
            continue
        cell = cells[index]
        sim = _shape_similarity(cell, template)
        similarities[key] = round(sim, 3)
        if sim > 0.5:
            correct += 1
        quality_scores.append(_shape_quality_score(_preprocess_shape(cell)))
    age_bucket = _ball_age_bucket(age)
    if age_bucket == "6-7":
        accuracy = 5 if correct >= 7 else 4 if correct >= 5 else 3 if correct >= 3 else 2 if correct >= 2 else 1
    else:
        accuracy = 5 if correct == 8 else 4 if correct >= 6 else 3 if correct >= 4 else 2 if correct >= 2 else 1
    quality = round(safe_mean(quality_scores)) if quality_scores else 1
    final = round((accuracy + quality) / 2)
    return _result(
        final,
        {
            "Age Band": age_bucket,
            "Shapes Correct": correct,
            "Accuracy Score": {"score": accuracy, "maxValue": 5},
            "Quality Score": {"score": quality, "maxValue": 5},
            "Shape Similarity": similarities,
        },
    )


def _time_score(time_sec: float) -> float:
    if time_sec <= 6.5:
        return 5
    if time_sec <= 7.5:
        return 4
    if time_sec <= 8.5:
        return 3
    if time_sec <= 9.5:
        return 2
    return 1


def agility_ladder_test(video_path: str, *, ladder_box_count: int) -> SchoolMotorResult:
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
    cap.release()
    duration = frame_count / fps if fps else 0.0
    time_score = _time_score(duration)
    expected_boxes = max(1, int(ladder_box_count))
    completion_ratio = min(1.0, expected_boxes / max(1, expected_boxes))
    final = round((time_score + (completion_ratio * 5)) / 2)
    return _result(
        final,
        {
            "Ladder Box Count": expected_boxes,
            "Duration Seconds": round(duration, 2),
            "Time Score": {"score": time_score, "maxValue": 5},
            "Box Completion Score": {"score": round(completion_ratio * 5, 2), "maxValue": 5},
        },
    )


def _torso_rotation(lms: Any) -> float:
    l_sh, r_sh = lms[11], lms[12]
    l_hip, r_hip = lms[23], lms[24]
    sh_vec = (r_sh.x - l_sh.x, r_sh.y - l_sh.y)
    hip_vec = (r_hip.x - l_hip.x, r_hip.y - l_hip.y)
    dot = sh_vec[0] * hip_vec[0] + sh_vec[1] * hip_vec[1]
    mag1 = math.sqrt(sh_vec[0] ** 2 + sh_vec[1] ** 2)
    mag2 = math.sqrt(hip_vec[0] ** 2 + hip_vec[1] ** 2)
    if mag1 == 0 or mag2 == 0:
        return 0.0
    return float(math.degrees(math.acos(max(-1.0, min(1.0, dot / (mag1 * mag2))))))


def _agility_time_score(total_time: float) -> float:
    if total_time <= 15.2:
        return 5
    if total_time <= 16.8:
        return 4
    if total_time <= 18.4:
        return 3
    if total_time <= 20.0:
        return 2
    return 1


def _agility_movement_metrics(
    hip_x: list[float],
    hip_y: list[float],
    left_y: list[float],
    right_y: list[float],
    time_list: list[float],
) -> tuple[float, float, float, float, float]:
    if len(time_list) < 5:
        return 0.2, 1.0, 1.0, 1.0, 1.0
    hip_x_arr = np.array(hip_x)
    hip_y_arr = np.array(hip_y)
    left_arr = np.array(left_y)
    right_arr = np.array(right_y)
    time_arr = np.array(time_list)
    peaks_l, _ = find_peaks(-left_arr, distance=5)
    peaks_r, _ = find_peaks(-right_arr, distance=5)
    intervals = []
    if len(peaks_l) > 1:
        intervals.extend(np.diff(time_arr[peaks_l]))
    if len(peaks_r) > 1:
        intervals.extend(np.diff(time_arr[peaks_r]))
    rhythm = safe_std(intervals, 0.2)
    min_len = min(len(left_arr), len(right_arr))
    sync_diff = safe_mean(np.abs(left_arr[:min_len] - right_arr[:min_len]))
    sway = safe_std(hip_x_arr)
    if len(time_arr) > 3:
        vel = np.diff(hip_y_arr) / np.maximum(np.diff(time_arr), 1e-6)
        accel = np.diff(vel)
        jerk = np.diff(accel)
        accel_var = safe_std(accel, 1.0)
        jerk_var = safe_std(jerk, 1.0)
    else:
        accel_var = 1.0
        jerk_var = 1.0
    return rhythm, sync_diff, sway, accel_var, jerk_var


def agility_test(video_path: str) -> SchoolMotorResult:
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)

    hip_x: list[float] = []
    hip_y: list[float] = []
    left_y: list[float] = []
    right_y: list[float] = []
    time_list: list[float] = []
    torso_angles: list[float] = []
    cone_hits: set[int] = set()
    fallback_cones = [
        int(frame_width * 0.15),
        int(frame_width * 0.35),
        int(frame_width * 0.55),
        int(frame_width * 0.75),
        int(frame_width * 0.9),
    ] if frame_width else [0, 1, 2, 3, 4]

    frame_idx = 0
    with mp_pose.Pose(min_detection_confidence=0.6) as pose:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            results = pose.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            if results.pose_landmarks:
                lms = results.pose_landmarks.landmark
                hx = (lms[23].x + lms[24].x) / 2
                hy = (lms[23].y + lms[24].y) / 2
                hip_x.append(hx)
                hip_y.append(hy)
                left_y.append(lms[31].y)
                right_y.append(lms[32].y)
                time_list.append(frame_idx / fps if fps else 0.0)
                torso_angles.append(_torso_rotation(lms))
                touch_point = hx * frame_width if frame_width else hx
                for index, cone_x in enumerate(fallback_cones):
                    if touch_point >= cone_x:
                        cone_hits.add(index)
            frame_idx += 1
    cap.release()

    total_time = frame_count / fps if fps else 0.0
    rhythm, sync_diff, sway, accel_var, jerk_var = _agility_movement_metrics(hip_x, hip_y, left_y, right_y, time_list)
    avg_angle = safe_mean(torso_angles)

    bal = 2 if sway < 0.02 else 1 if sway < 0.05 else 0
    rhy = 2 if rhythm < 0.05 else 1 if rhythm < 0.08 else 0
    syn = 2 if sync_diff < 0.02 else 1 if sync_diff < 0.05 else 0
    acc = 2 if len(cone_hits) >= 4 else 1 if len(cone_hits) >= 2 else 0
    flu = 2 if accel_var < 0.04 and jerk_var < 0.1 else 1 if accel_var < 0.08 else 0
    turn = 2 if avg_angle < 20 else 1 if avg_angle < 30 else 0
    movement_score = bal + rhy + syn + acc + flu + turn
    time_score = _agility_time_score(total_time)
    if movement_score >= 7:
        final = time_score
    elif movement_score >= 5:
        final = time_score - 0.5
    elif movement_score >= 3:
        final = time_score - 1
    else:
        final = min(time_score, 2)

    return _result(
        final,
        {
            "Duration Seconds": round(total_time, 2),
            "Cone Hits": len(cone_hits),
            "Time Score": {"score": time_score, "maxValue": 5},
            "Movement Score": {"score": movement_score, "maxValue": 12},
            "Rhythm": round(rhythm, 3),
            "Limb Sync": round(sync_diff, 3),
            "Sway": round(sway, 3),
            "Fluidity Accel Var": round(accel_var, 3),
            "Fluidity Jerk Var": round(jerk_var, 3),
            "Torso Angle": round(avg_angle, 2),
        },
    )
