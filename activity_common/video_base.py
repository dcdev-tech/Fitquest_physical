from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Generator

import cv2


@dataclass
class VideoStats:
    fps: float
    frame_count: int
    duration_seconds: float
    width: int
    height: int


def read_video_stats(video_path: str) -> VideoStats:
    path = Path(video_path)
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError(f"Unable to open video: {video_path}")

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    cap.release()

    duration = (frame_count / fps) if fps > 0 else 0.0
    return VideoStats(
        fps=fps,
        frame_count=frame_count,
        duration_seconds=duration,
        width=width,
        height=height,
    )


def iter_video_frames(video_path: str) -> Generator[tuple[int, object], None, None]:
    cap = cv2.VideoCapture(str(Path(video_path)))
    if not cap.isOpened():
        raise ValueError(f"Unable to open video: {video_path}")
    index = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            index += 1
            yield index, frame
    finally:
        cap.release()
