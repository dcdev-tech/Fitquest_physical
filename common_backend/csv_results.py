from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


CSV_BY_ACTIVITY = {
    "high_knee_jump": "high_knee_results.csv",
    "shuttle_run": "shuttle_run_results.csv",
    "sprint_run_20m": "meter_run_results.csv",
    "long_jump": "long_jump.csv",
}

EXPECTED_HEADERS = {
    "high_knee_jump": [
        "ID",
        "Name",
        "Age",
        "Video_path",
        "Total_Lap",
        "MIN_side_lean",
        "MAX_side_lean",
        "Avg_side_lean(deg)",
        "MIN_vertical_angle",
        "MAX_vertical_angle",
        "Avg_vertical_angle(deg)",
        "Left_knee_height_data",
        "Right_knee_height_data",
        "Arm-Leg_coordination",
        "Pace",
        "Rhythm",
        "Score_10",
        "Category",
    ],
    "shuttle_run": [
        "ID",
        "Name",
        "Video_path",
        "Accurate_lap_count",
        "Partial_lap_count",
        "Avg_turn_angle",
        "Movement:speed_var",
        "Movement:sway",
        "Movement:accel_var",
        "Avg_turn_time",
        "Score_18",
        "Category",
    ],
    "shuttle_run_14col": [
        "ID",
        "Name",
        "Age",
        "Gender",
        "Video_path",
        "Accurate_lap_count",
        "Partial_lap_count",
        "Avg_turn_angle",
        "Movement:speed_var",
        "Movement:sway",
        "Movement:accel_var",
        "Avg_turn_time",
        "Score_18",
        "Category",
    ],
    "sprint_run_20m": [
        "ID",
        "Name",
        "Video_path",
        "Sprint_time",
        "Trunk_angle_avg",
        "Shoulder_y_diff_avg",
        "Avg_elbow_angle_avg",
        "Cross_amount_avg",
        "Knee_lift_avg",
        "Avg_knee_angle_avg",
        "Score_18",
        "Category",
    ],
    "long_jump": [
        "ID",
        "Name",
        "Video_path",
        "Jumped_distance_cm",
        "Avg_angle_final",
        "Knee_lift_final",
        "Ankle_diff_final",
        "Score_18",
        "Category",
    ],
}


def _expected_header_for_row(activity: str | None, row_len: int) -> list[str] | None:
    if activity == "shuttle_run" and row_len == 14:
        return EXPECTED_HEADERS["shuttle_run_14col"]
    if activity:
        expected = EXPECTED_HEADERS.get(activity)
        if expected and len(expected) == row_len:
            return expected
    return EXPECTED_HEADERS.get(activity or "")

CSV_FALLBACK_GLOBS = {
    "high_knee_jump": [
        "ages_*/high_knee/raw/high_knee_results.csv",
        "raw/ages_*/high_knee/raw/high_knee_results.csv",
    ],
    "shuttle_run": [
        "ages_*/shuttle_run/raw/shuttle_run_results.csv",
        "raw/ages_*/shuttle_run/raw/shuttle_run_results.csv",
    ],
    "sprint_run_20m": [
        "ages_*/20m_running/raw/meter_run_results.csv",
        "raw/ages_*/20m_running/raw/meter_run_results.csv",
    ],
    "long_jump": [
        "ages_*/long_jump/raw/long_jump.csv",
        "raw/ages_*/long_jump/raw/long_jump.csv",
    ],
}


def _header_looks_valid(header: list[str], expected_header: list[str] | None) -> bool:
    if not header:
        return False
    if expected_header and header == expected_header:
        return True
    return "ID" in header and ("Category" in header or any(col.startswith("Score_") for col in header))


def _row_to_map(
    *,
    activity: str | None,
    header: list[str] | None,
    values: list[str],
) -> dict[str, str] | None:
    resolved_header = header
    if not resolved_header or len(values) != len(resolved_header):
        resolved_header = _expected_header_for_row(activity, len(values))
    if not resolved_header:
        return None
    padded_values = values + [""] * max(0, len(resolved_header) - len(values))
    return dict(zip(resolved_header, padded_values))


def _read_last_row(
    csv_path: Path,
    activity: str | None = None,
    *,
    candidate_id: str | None = None,
    video_path: str | None = None,
) -> dict[str, Any] | None:
    try:
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.reader(handle))
        if not rows:
            return None
        first_row = rows[0]
        expected_header = _expected_header_for_row(activity, len(first_row))
        file_header: list[str] | None = None
        if _header_looks_valid(first_row, expected_header):
            if len(rows) < 2:
                return None
            header = first_row
            file_header = first_row
            values = rows[-1]
        else:
            if not expected_header or len(first_row) != len(expected_header):
                return None
            header = expected_header
            data_rows = rows
            values = first_row if len(rows) == 1 else rows[-1]
        if 'data_rows' not in locals():
            data_rows = rows[1:]
        if candidate_id or video_path:
            normalized_video_path = (video_path or "").replace("/", "\\").lower()
            matched = False
            for candidate_values in reversed(data_rows):
                row_map = _row_to_map(
                    activity=activity,
                    header=file_header or header,
                    values=candidate_values,
                )
                if not row_map:
                    continue
                row_id = str(row_map.get("ID", "")).strip()
                row_video_path = str(row_map.get("Video_path", "")).replace("/", "\\").lower()
                if candidate_id and row_id == candidate_id:
                    values = candidate_values
                    header = list(row_map.keys())
                    matched = True
                    break
                if normalized_video_path and row_video_path == normalized_video_path:
                    values = candidate_values
                    header = list(row_map.keys())
                    matched = True
                    break
            if not matched:
                return None
        row_map = _row_to_map(activity=activity, header=file_header or header, values=values)
        if not row_map:
            return None
        return {
            "csv_file": str(csv_path.resolve()),
            "row": row_map,
        }
    except Exception:
        return None


def _latest_fallback_csv(activity: str) -> Path | None:
    patterns = CSV_FALLBACK_GLOBS.get(activity, [])
    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(Path(".").glob(pattern))
    files = [p for p in candidates if p.is_file()]
    if not files:
        return None
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0]


def read_latest_csv_row(
    activity: str,
    *,
    candidate_id: str | None = None,
    video_path: str | None = None,
) -> dict[str, Any] | None:
    file_name = CSV_BY_ACTIVITY.get(activity)
    if file_name:
        root_csv = Path(file_name)
        if root_csv.exists():
            row = _read_last_row(
                root_csv,
                activity,
                candidate_id=candidate_id,
                video_path=video_path,
            )
            if row:
                return row

    fallback_csv = _latest_fallback_csv(activity)
    if fallback_csv is None:
        return None
    return _read_last_row(
        fallback_csv,
        activity,
        candidate_id=candidate_id,
        video_path=video_path,
    )
