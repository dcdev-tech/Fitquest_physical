from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Iterable, Sequence

import cv2
import numpy as np


RUNTIME_DATA_DIR = Path(os.getenv("RUNTIME_DATA_DIR", "."))


def _resolve_runtime_path(csv_path: str | Path) -> Path:
    path = Path(csv_path)
    if path.is_absolute():
        return path
    return RUNTIME_DATA_DIR / path


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    try:
        if denominator == 0:
            return default
        return numerator / denominator
    except Exception:
        return default


def safe_mean(values: Sequence[float] | np.ndarray, default: float = 0.0, digits: int | None = None) -> float:
    try:
        if len(values) == 0:
            return default
        result = float(np.mean(values))
        return round(result, digits) if digits is not None else result
    except Exception:
        return default


def safe_std(values: Sequence[float] | np.ndarray, default: float = 0.0, digits: int | None = None) -> float:
    try:
        if len(values) == 0:
            return default
        result = float(np.std(values))
        return round(result, digits) if digits is not None else result
    except Exception:
        return default


def safe_min(values: Sequence[float], default: float = 0.0, digits: int | None = None) -> float:
    try:
        if len(values) == 0:
            return default
        result = float(min(values))
        return round(result, digits) if digits is not None else result
    except Exception:
        return default


def safe_max(values: Sequence[float], default: float = 0.0, digits: int | None = None) -> float:
    try:
        if len(values) == 0:
            return default
        result = float(max(values))
        return round(result, digits) if digits is not None else result
    except Exception:
        return default


def ensure_capture_opened(cap: cv2.VideoCapture, path: str | int) -> None:
    if not cap.isOpened():
        raise ValueError(f"Unable to open video source: {path}")


def safe_video_meta(cap: cv2.VideoCapture, default_fps: float = 30.0) -> tuple[int, int, float, int, float]:
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if fps <= 0:
        fps = default_fps
    video_time = safe_divide(frame_count, fps, 0.0)
    return frame_width, frame_height, fps, frame_count, video_time


def safe_csv_append(csv_path: str | Path, row: Iterable[object]) -> None:
    try:
        path = _resolve_runtime_path(csv_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerow(list(row))
    except OSError:
        pass


def ensure_csv_header(csv_path: str | Path, header: Sequence[object]) -> None:
    path = _resolve_runtime_path(csv_path)
    if path.exists() and path.stat().st_size > 0:
        return
    safe_csv_append(path, header)
