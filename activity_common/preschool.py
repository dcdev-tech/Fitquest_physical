from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import mediapipe as mp
import numpy as np
from scipy.signal import find_peaks

from activity_common.base import ActivityCalculationResult
from activity_common.video_base import read_video_stats


mp_pose = mp.solutions.pose
mp_hands = mp.solutions.hands


@dataclass
class PreschoolResult(ActivityCalculationResult):
    metrics: dict[str, Any] = field(default_factory=dict)


def category_from_score(score: float, max_score: float = 5.0) -> str:
    ratio = max(0.0, min(1.0, float(score) / max_score))
    if ratio >= 0.85:
        return "Excellent"
    if ratio >= 0.65:
        return "Above Average"
    if ratio >= 0.45:
        return "Average"
    if ratio >= 0.25:
        return "Below Average"
    return "Poor"


def safe_mean(values: Any, default: float = 0.0) -> float:
    return float(np.mean(values)) if len(values) else float(default)


def safe_std(values: Any, default: float = 0.0) -> float:
    return float(np.std(values)) if len(values) else float(default)


def smooth(values: Any, k: int = 5) -> np.ndarray:
    if len(values) < k:
        return np.array(values)
    return np.convolve(values, np.ones(k) / k, mode="same")


def angle(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    a_arr, b_arr, c_arr = np.array(a), np.array(b), np.array(c)
    ba, bc = a_arr - b_arr, c_arr - b_arr
    cos = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-6)
    return float(np.degrees(np.arccos(np.clip(cos, -1, 1))))


def torso_angle(
    l_sh: tuple[float, float],
    r_sh: tuple[float, float],
    l_hip: tuple[float, float],
    r_hip: tuple[float, float],
) -> float:
    sh_mid = np.array([(l_sh[0] + r_sh[0]) / 2, (l_sh[1] + r_sh[1]) / 2])
    hip_mid = np.array([(l_hip[0] + r_hip[0]) / 2, (l_hip[1] + r_hip[1]) / 2])
    vec = sh_mid - hip_mid
    vertical = np.array([0, -1.0])
    cos = np.dot(vec, vertical) / (np.linalg.norm(vec) * np.linalg.norm(vertical) + 1e-6)
    return float(np.degrees(np.arccos(np.clip(cos, -1, 1))))


def threshold_bounds(video_path: str) -> tuple[float, float]:
    cap = cv2.VideoCapture(video_path)
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    cap.release()
    if frame_width <= 0:
        return 0.10, 0.85

    try:
        from ultralytics import YOLO

        model_path = Path("best.pt")
        if not model_path.exists():
            return 0.10, 0.85
        model = YOLO(str(model_path))
        cap = cv2.VideoCapture(video_path)
        left_x: list[int] = []
        right_x: list[int] = []
        while len(left_x) <= 50:
            ret, frame = cap.read()
            if not ret:
                break
            results = model(frame, conf=0.5, verbose=False)
            centers = []
            for box in results[0].boxes:
                x1, _y1, x2, _y2 = map(int, box.xyxy[0])
                centers.append((x1 + x2) // 2)
            if len(centers) >= 2:
                centers.sort()
                left_x.append(centers[0])
                right_x.append(centers[-1])
        cap.release()
        if not left_x or not right_x:
            return 0.10, 0.85
        return round(int(np.mean(left_x)) / frame_width, 2), round(int(np.mean(right_x)) / frame_width, 2)
    except Exception:
        return 0.10, 0.85


def _pose_series(video_path: str) -> dict[str, Any]:
    left_bound, right_bound = threshold_bounds(video_path)
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    data: dict[str, list[Any]] = {
        "hip_x": [],
        "hip_y": [],
        "l_ank_y": [],
        "r_ank_y": [],
        "l_knee_y": [],
        "r_knee_y": [],
        "l_knee_ang": [],
        "r_knee_ang": [],
        "l_el_y": [],
        "r_el_y": [],
        "l_wri_y": [],
        "r_wri_y": [],
        "l_sh_y": [],
        "r_sh_y": [],
        "l_el_ang": [],
        "r_el_ang": [],
        "torso_ang": [],
    }

    with mp_pose.Pose(min_detection_confidence=0.6) as pose:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            res = pose.process(rgb)
            if not res.pose_landmarks:
                continue
            lms = res.pose_landmarks.landmark
            hx = (lms[23].x + lms[24].x) / 2
            if not (left_bound <= hx <= right_bound) or lms[23].visibility < 0.5:
                continue

            l_sh = (lms[11].x, lms[11].y)
            r_sh = (lms[12].x, lms[12].y)
            l_el = (lms[13].x, lms[13].y)
            r_el = (lms[14].x, lms[14].y)
            l_wri = (lms[15].x, lms[15].y)
            r_wri = (lms[16].x, lms[16].y)
            l_hip = (lms[23].x, lms[23].y)
            r_hip = (lms[24].x, lms[24].y)
            l_knee = (lms[25].x, lms[25].y)
            r_knee = (lms[26].x, lms[26].y)
            l_ank = (lms[27].x, lms[27].y)
            r_ank = (lms[28].x, lms[28].y)

            data["hip_x"].append(hx)
            data["hip_y"].append((l_hip[1] + r_hip[1]) / 2)
            data["l_ank_y"].append(l_ank[1])
            data["r_ank_y"].append(r_ank[1])
            data["l_knee_y"].append(l_knee[1])
            data["r_knee_y"].append(r_knee[1])
            data["l_knee_ang"].append(angle(l_hip, l_knee, l_ank))
            data["r_knee_ang"].append(angle(r_hip, r_knee, r_ank))
            data["l_el_y"].append(l_el[1])
            data["r_el_y"].append(r_el[1])
            data["l_wri_y"].append(l_wri[1])
            data["r_wri_y"].append(r_wri[1])
            data["l_sh_y"].append(l_sh[1])
            data["r_sh_y"].append(r_sh[1])
            data["l_el_ang"].append(angle(l_sh, l_el, l_wri))
            data["r_el_ang"].append(angle(r_sh, r_el, r_wri))
            data["torso_ang"].append(torso_angle(l_sh, r_sh, l_hip, r_hip))

    cap.release()
    data["fps"] = fps
    data["left_bound"] = left_bound
    data["right_bound"] = right_bound
    return data


def _score_result(final_score: float, metrics: dict[str, Any]) -> PreschoolResult:
    rounded = round(float(final_score), 2)
    metrics = dict(metrics)
    metrics["Final Score"] = {"score": rounded, "maxValue": 5}
    metrics["Final Marking"] = category_from_score(rounded)
    return PreschoolResult(score=rounded, category=category_from_score(rounded), metrics=metrics)


def running_test(video_path: str) -> PreschoolResult:
    data = _pose_series(video_path)
    hip_x = smooth(data["hip_x"])
    hip_y = smooth(data["hip_y"])
    l_ank_y = smooth(data["l_ank_y"])
    r_ank_y = smooth(data["r_ank_y"])
    n = min(len(hip_x), len(hip_y), len(l_ank_y), len(r_ank_y))
    if n < 10:
        return _score_result(1, {"Reason": "Insufficient pose data"})
    hip_x, l_ank_y, r_ank_y = hip_x[:n], l_ank_y[:n], r_ank_y[:n]
    l_el_y, r_ank_for_corr = data["l_el_y"][:n], r_ank_y[:n]
    foot_score_val = safe_mean(data["l_knee_ang"][:n])
    knee_val = safe_mean(data["l_knee_ang"][:n] + data["r_knee_ang"][:n])
    flight = ~(
        (l_ank_y[1:] > np.percentile(l_ank_y, 70)) & (np.abs(np.diff(l_ank_y)) < 0.01)
        | (r_ank_y[1:] > np.percentile(r_ank_y, 70)) & (np.abs(np.diff(r_ank_y)) < 0.01)
    )
    corr = float(np.nan_to_num(np.corrcoef(l_el_y[: len(r_ank_for_corr)], r_ank_for_corr)[0, 1]))
    t_idx = np.arange(len(hip_x))
    coef = np.polyfit(t_idx, hip_x, 1)
    traj_error = safe_mean(np.abs(hip_x - np.polyval(coef, t_idx)))
    scores = {
        "Arm-Leg Opposition": 5 if corr < -0.7 else 4 if corr < -0.5 else 3 if corr < -0.3 else 2 if corr < -0.1 else 1,
        "Flight Phase": 5 if safe_mean(flight) > 0.6 else 4 if safe_mean(flight) > 0.45 else 3 if safe_mean(flight) > 0.3 else 2 if safe_mean(flight) > 0.1 else 1,
        "Foot Placement": 5 if foot_score_val < 90 else 4 if foot_score_val < 110 else 3 if foot_score_val < 130 else 2 if foot_score_val < 150 else 1,
        "Leg Flexion": 5 if knee_val < 90 else 4 if knee_val < 110 else 3 if knee_val < 130 else 2 if knee_val < 150 else 1,
        "Trajectory": 5 if traj_error < 0.005 else 4 if traj_error < 0.01 else 3 if traj_error < 0.02 else 2 if traj_error < 0.04 else 1,
    }
    return _score_result(safe_mean(list(scores.values())), {k: {"score": v, "maxValue": 5} for k, v in scores.items()})


def galloping_test(video_path: str) -> PreschoolResult:
    data = _pose_series(video_path)
    l_ank_y, r_ank_y = smooth(data["l_ank_y"]), smooth(data["r_ank_y"])
    l_knee_y, r_knee_y = smooth(data["l_knee_y"]), smooth(data["r_knee_y"])
    n = min(len(l_ank_y), len(r_ank_y), len(l_knee_y), len(r_knee_y))
    if n < 12:
        return _score_result(1, {"Reason": "Insufficient pose data"})
    peaks, _ = find_peaks(-l_ank_y[:n], distance=6)
    lead_seq = ["L" if l_knee_y[i] < r_knee_y[i] else "R" for i in range(n)]
    switches = sum(lead_seq[i] != lead_seq[i - 1] for i in range(1, len(lead_seq)))
    rhythm_var = safe_std(np.diff(peaks) / max(data["fps"], 1)) if len(peaks) > 1 else 1.0
    flight = ~(
        (l_ank_y[1:n] > np.percentile(l_ank_y[:n], 70)) & (np.abs(np.diff(l_ank_y[:n])) < 0.01)
        | (r_ank_y[1:n] > np.percentile(r_ank_y[:n], 70)) & (np.abs(np.diff(r_ank_y[:n])) < 0.01)
    )
    arm_pos = [
        1
        if abs(data["l_el_y"][i] - data["l_sh_y"][i]) < 0.1
        and abs(data["r_el_y"][i] - data["r_sh_y"][i]) < 0.1
        and 60 < data["l_el_ang"][i] < 120
        and 60 < data["r_el_ang"][i] < 120
        else 0
        for i in range(n)
    ]
    scores = {
        "Lead Leg Consistency": 5 if switches == 0 else 4 if switches == 1 else 3 if switches <= 3 else 2 if switches <= 6 else 1,
        "Rhythm": 5 if len(peaks) >= 4 and rhythm_var < 0.1 else 4 if len(peaks) >= 3 and rhythm_var < 0.15 else 3 if len(peaks) >= 2 else 2 if len(peaks) >= 1 else 1,
        "Flight Phase": 5 if safe_mean(flight) > 0.6 else 4 if safe_mean(flight) > 0.45 else 3 if safe_mean(flight) > 0.3 else 2 if safe_mean(flight) > 0.1 else 1,
        "Arm Position": 5 if safe_mean(arm_pos) > 0.8 else 4 if safe_mean(arm_pos) > 0.6 else 3 if safe_mean(arm_pos) > 0.4 else 2 if safe_mean(arm_pos) > 0.2 else 1,
    }
    return _score_result(safe_mean(list(scores.values())), {k: {"score": v, "maxValue": 5} for k, v in scores.items()})


def hopping_test(video_path: str) -> PreschoolResult:
    data = _pose_series(video_path)
    l_ank_y, r_ank_y, hip_y = smooth(data["l_ank_y"]), smooth(data["r_ank_y"]), smooth(data["hip_y"])
    n = min(len(l_ank_y), len(r_ank_y), len(hip_y))
    if n < 12:
        return _score_result(1, {"Reason": "Insufficient pose data"})
    peaks, _ = find_peaks(-hip_y[:n], distance=5)
    support_seq = ["L" if l_ank_y[i] > r_ank_y[i] else "R" for i in range(n)]
    main_foot = max(set(support_seq), key=support_seq.count)
    same_count = support_seq.count(main_foot)
    free_leg_motion = safe_std(l_ank_y[:n] - r_ank_y[:n])
    knee_val = safe_mean(data["l_knee_ang"][:n] + data["r_knee_ang"][:n])
    arm_motion = safe_std(data["l_wri_y"][:n]) + safe_std(data["r_wri_y"][:n])
    scores = {
        "Same Foot Landing": 5 if same_count >= 5 else 4 if same_count == 4 else 3 if same_count == 3 else 2 if same_count == 2 else 1,
        "Free Leg Swing": 5 if free_leg_motion > 0.05 else 4 if free_leg_motion > 0.04 else 3 if free_leg_motion > 0.03 else 2 if free_leg_motion > 0.02 else 1,
        "Knee Flexion": 5 if knee_val < 90 else 4 if knee_val < 110 else 3 if knee_val < 130 else 2 if knee_val < 150 else 1,
        "Arm Movement": 5 if arm_motion > 0.08 else 4 if arm_motion > 0.06 else 3 if arm_motion > 0.04 else 2 if arm_motion > 0.02 else 1,
        "Consecutive Hops": 5 if len(peaks) >= 5 else 4 if len(peaks) >= 4 else 3 if len(peaks) >= 3 else 2 if len(peaks) >= 2 else 1,
    }
    return _score_result(safe_mean(list(scores.values())), {k: {"score": v, "maxValue": 5} for k, v in scores.items()})


def skipping_test(video_path: str) -> PreschoolResult:
    data = _pose_series(video_path)
    hip_y, l_ank_y, r_ank_y = smooth(data["hip_y"]), smooth(data["l_ank_y"]), smooth(data["r_ank_y"])
    n = min(len(hip_y), len(l_ank_y), len(r_ank_y))
    if n < 15:
        return _score_result(1, {"Reason": "Insufficient pose data"})
    peaks, _ = find_peaks(-hip_y[:n], distance=6)
    lead_seq = ["L" if l_ank_y[i] < r_ank_y[i] else "R" for i in peaks if i < n]
    alternations = sum(lead_seq[i] != lead_seq[i - 1] for i in range(1, len(lead_seq)))
    alt_ratio = alternations / max(len(lead_seq) - 1, 1)
    rhythm_var = safe_std(np.diff(peaks) / max(data["fps"], 1)) if len(peaks) > 1 else 1.0
    min_len = min(len(data["l_el_y"]), len(r_ank_y), n)
    corr = float(np.nan_to_num(np.corrcoef(data["l_el_y"][:min_len], r_ank_y[:min_len])[0, 1]))
    accel = np.diff(np.diff(hip_y[:n]))
    jerk = np.diff(accel) if len(accel) > 1 else np.array([0])
    scores = {
        "Step-Hop Pattern": 5 if alt_ratio > 0.9 else 4 if alt_ratio > 0.75 else 3 if alt_ratio > 0.5 else 2 if alt_ratio > 0.25 else 1,
        "Rhythmic Flow": 5 if rhythm_var < 0.08 else 4 if rhythm_var < 0.12 else 3 if rhythm_var < 0.18 else 2 if rhythm_var < 0.25 else 1,
        "Arm Opposition": 5 if corr < -0.7 else 4 if corr < -0.5 else 3 if corr < -0.3 else 2 if corr < -0.1 else 1,
        "Fluid Movement": 5 if safe_std(accel) < 0.01 and safe_std(jerk) < 0.01 else 4 if safe_std(accel) < 0.02 else 3 if safe_std(accel) < 0.03 else 2 if safe_std(accel) < 0.05 else 1,
    }
    return _score_result(safe_mean(list(scores.values())), {k: {"score": v, "maxValue": 5} for k, v in scores.items()})


def jumping_test(video_path: str) -> PreschoolResult:
    data = _pose_series(video_path)
    hip_y, l_ank_y, r_ank_y = smooth(data["hip_y"]), smooth(data["l_ank_y"]), smooth(data["r_ank_y"])
    n = min(len(hip_y), len(l_ank_y), len(r_ank_y))
    if n < 12:
        return _score_result(1, {"Reason": "Insufficient pose data"})
    peaks, _ = find_peaks(-hip_y[:n], distance=6)
    takeoff_diffs, landing_diffs, arm_patterns, align_vals = [], [], [], []
    for peak in peaks:
        i0, i1 = max(peak - 3, 0), min(peak + 3, n - 1)
        vel_l, vel_r = np.diff(l_ank_y[i0 : i1 + 1]), np.diff(r_ank_y[i0 : i1 + 1])
        if len(vel_l) and len(vel_r):
            takeoff_diffs.append(abs(int(np.argmin(vel_l)) - int(np.argmin(vel_r))))
            landing_diffs.append(abs(int(np.argmax(vel_l)) - int(np.argmax(vel_r))))
        wr = np.array(data["l_wri_y"][i0 : i1 + 1]) - np.array(data["l_sh_y"][i0 : i1 + 1])
        if len(wr) > 3:
            arm_patterns.append(float(np.max(wr) - np.min(wr)))
        align_vals.append(safe_mean(data["torso_ang"][i0 : i1 + 1]))
    takeoff_ratio = 1 - (safe_mean(takeoff_diffs) / 5.0)
    landing_ratio = 1 - (safe_mean(landing_diffs) / 5.0)
    arm_amp = safe_mean(arm_patterns)
    align_mean = safe_mean(align_vals)
    scores = {
        "Two-Foot Takeoff": 5 if takeoff_ratio > 0.85 else 4 if takeoff_ratio > 0.7 else 3 if takeoff_ratio > 0.5 else 2 if takeoff_ratio > 0.3 else 1,
        "Two-Foot Landing": 5 if landing_ratio > 0.85 else 4 if landing_ratio > 0.7 else 3 if landing_ratio > 0.5 else 2 if landing_ratio > 0.3 else 1,
        "Arm Swing": 5 if arm_amp > 0.12 else 4 if arm_amp > 0.09 else 3 if arm_amp > 0.06 else 2 if arm_amp > 0.03 else 1,
        "Body Alignment": 5 if align_mean < 10 else 4 if align_mean < 20 else 3 if align_mean < 30 else 2 if align_mean < 40 else 1,
    }
    return _score_result(safe_mean(list(scores.values())), {k: {"score": v, "maxValue": 5} for k, v in scores.items()})


def compute_hand_quality(hand_data: dict[str, list[tuple[float, float]]]) -> int:
    thumb = np.array(hand_data["thumb"])
    index = np.array(hand_data["index"])
    middle = np.array(hand_data["middle"])
    ring = np.array(hand_data["ring"])
    pinky = np.array(hand_data["pinky"])
    n = min(len(thumb), len(index), len(middle), len(ring), len(pinky))
    if n < 5:
        return 1
    thumb, index, middle, ring, pinky = thumb[:n], index[:n], middle[:n], ring[:n], pinky[:n]
    pinch = safe_mean(np.linalg.norm(thumb - index, axis=1))
    grip = np.mean([
        np.linalg.norm(thumb - middle, axis=1),
        np.linalg.norm(thumb - ring, axis=1),
        np.linalg.norm(thumb - pinky, axis=1),
    ])
    spread = np.std([index[:, 1], middle[:, 1], ring[:, 1], pinky[:, 1]])
    vel = np.diff(index[:, 1])
    accel = np.diff(vel) if len(vel) > 1 else np.array([0])
    jerk = np.diff(accel) if len(accel) > 1 else np.array([0])
    stability = safe_std(index[:, 0]) + safe_std(index[:, 1])
    path = np.sum(np.linalg.norm(np.diff(index, axis=0), axis=1))
    efficiency = np.linalg.norm(index[-1] - index[0]) / (path + 1e-6)
    score = 0
    score += 2 if pinch < 0.03 else 1 if pinch < 0.06 else 0
    score += 1 if grip < 0.1 else 0
    score += 1 if spread > 0.01 else 0
    score += 2 if safe_std(jerk) < 0.005 else 1 if safe_std(jerk) < 0.01 else 0
    score += 1 if stability < 0.01 else 0
    score += 1 if efficiency > 0.7 else 0
    return max(1, min(5, round(score)))


def hand_quality(video_path: str, bilateral: bool = False) -> tuple[int, dict[str, Any]]:
    primary = {k: [] for k in ["thumb", "index", "middle", "ring", "pinky", "wrist"]}
    support = {k: [] for k in ["thumb", "index", "middle", "ring", "pinky", "wrist"]}
    dom_y: list[float] = []
    sup_y: list[float] = []
    with mp_hands.Hands(min_detection_confidence=0.6) as hands:
        cap = cv2.VideoCapture(video_path)
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            results = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            if not results.multi_hand_landmarks:
                continue
            for hand_landmarks in results.multi_hand_landmarks:
                lm = hand_landmarks.landmark
                target = primary if not bilateral or lm[8].x > 0.5 else support
                target["thumb"].append((lm[4].x, lm[4].y))
                target["index"].append((lm[8].x, lm[8].y))
                target["middle"].append((lm[12].x, lm[12].y))
                target["ring"].append((lm[16].x, lm[16].y))
                target["pinky"].append((lm[20].x, lm[20].y))
                target["wrist"].append((lm[0].x, lm[0].y))
                (dom_y if lm[8].x > 0.5 else sup_y).append(lm[8].y)
        cap.release()

    q_primary = compute_hand_quality(primary)
    if not bilateral:
        return q_primary, {"Quality Score": {"score": q_primary, "maxValue": 5}}

    q_support = compute_hand_quality(support)
    min_len = min(len(dom_y), len(sup_y))
    sync = safe_mean(np.abs(np.array(dom_y[:min_len]) - np.array(sup_y[:min_len]))) if min_len > 5 else 0.1
    quality = round((q_primary + q_support) / 2)
    if sync >= 0.05:
        quality = max(1, quality - 2)
    elif sync >= 0.02:
        quality = max(1, quality - 1)
    quality = max(1, min(5, quality))
    return quality, {
        "Dominant Quality": {"score": q_primary, "maxValue": 5},
        "Support Quality": {"score": q_support, "maxValue": 5},
        "Bilateral Sync": round(sync, 3),
        "Final Quality Score": {"score": quality, "maxValue": 5},
    }


def preschool_age_bucket(age: float | int | None) -> str:
    age_value = float(age or 0)
    if age_value < 3:
        return "2.5-3"
    if age_value < 4:
        return "3-4"
    return "4-5"


def block_score(blocks: int, quality: int, age_bucket: str) -> int:
    low, high = {"2.5-3": (3, 4), "3-4": (5, 6), "4-5": (7, 8)}.get(age_bucket, (5, 6))
    if blocks <= 1 or quality < 2:
        return 1
    if blocks >= high + 1 and quality >= 4.5:
        return 5
    if blocks >= high and 4.0 <= quality < 4.5:
        return 4
    if blocks >= low and 3.0 <= quality < 4.0:
        return 3
    if blocks >= low - 2 and 2.0 <= quality < 3.0:
        return 2
    return 1


def bead_score(beads: int, quality: int, age_bucket: str) -> int:
    low, high = {"2.5-3": (4, 6), "3-4": (7, 9), "4-5": (10, 12)}.get(age_bucket, (7, 9))
    if beads <= 3 or quality < 2:
        return 1
    if beads >= high and quality >= 4.5:
        return 5
    if beads >= high - 1 and 4.0 <= quality < 4.5:
        return 4
    if beads >= low and 3.0 <= quality < 4.0:
        return 3
    if beads >= low - 3 and 2.0 <= quality < 3.0:
        return 2
    return 1


def block_stacking_test(video_path: str, *, age: float | int | None, blocks_stood: int, blocks_dropped: int) -> PreschoolResult:
    quality, quality_metrics = hand_quality(video_path, bilateral=False)
    age_bucket = preschool_age_bucket(age)
    final = block_score(int(blocks_stood), quality, age_bucket)
    metrics = {
        "Age Band": age_bucket,
        "Blocks Stood": int(blocks_stood),
        "Blocks Dropped": int(blocks_dropped),
        **quality_metrics,
    }
    return _score_result(final, metrics)


def bead_threading_test(video_path: str, *, age: float | int | None, beads_threaded: int, beads_dropped: int) -> PreschoolResult:
    quality, quality_metrics = hand_quality(video_path, bilateral=True)
    age_bucket = preschool_age_bucket(age)
    final = bead_score(int(beads_threaded), quality, age_bucket)
    metrics = {
        "Age Band": age_bucket,
        "Beads Threaded": int(beads_threaded),
        "Beads Dropped": int(beads_dropped),
        **quality_metrics,
    }
    return _score_result(final, metrics)
