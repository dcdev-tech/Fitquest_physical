from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
import threading
from typing import Any

import cv2


def _normalize_source(source: object) -> str | None:
    if isinstance(source, (str, Path)):
        try:
            return str(Path(source).resolve()).lower()
        except Exception:
            return str(source).lower()
    return None


@dataclass
class ProgressState:
    request_id: str
    activity: str
    video_path: str
    total_frames: int
    expected_reads: int
    processed_reads: int = 0
    progress_percent: int = 0
    status: str = "pending"
    message: str = ""
    error: str | None = None
    video_path_key: str | None = field(default=None)

    def snapshot(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "activity": self.activity,
            "status": self.status,
            "progress_percent": self.progress_percent,
            "processed_reads": self.processed_reads,
            "expected_reads": self.expected_reads,
            "message": self.message,
            "error": self.error,
        }


_LOCK = threading.Lock()
_STATE: dict[str, ProgressState] = {}
_THREAD_LOCAL = threading.local()
_ORIGINAL_VIDEO_CAPTURE = cv2.VideoCapture


class TrackingVideoCapture:
    def __init__(self, source: object = 0, *args, **kwargs):
        self._source = source
        self._source_key = _normalize_source(source)
        self._capture = _ORIGINAL_VIDEO_CAPTURE(source, *args, **kwargs)

    def read(self):
        ok, frame = self._capture.read()
        if ok:
            tracker: ProgressState | None = getattr(_THREAD_LOCAL, "tracker", None)
            if tracker and tracker.video_path_key and tracker.video_path_key == self._source_key:
                increment_progress(tracker.request_id)
        return ok, frame

    def __getattr__(self, name: str):
        return getattr(self._capture, name)


cv2.VideoCapture = TrackingVideoCapture


def initialize_progress(
    *,
    request_id: str,
    activity: str,
    video_path: str,
    total_frames: int,
    expected_reads: int,
) -> None:
    state = ProgressState(
        request_id=request_id,
        activity=activity,
        video_path=video_path,
        total_frames=max(0, int(total_frames)),
        expected_reads=max(1, int(expected_reads)),
        status="processing",
        message="Starting analysis",
        video_path_key=_normalize_source(video_path),
    )
    with _LOCK:
        _STATE[request_id] = state


def set_progress_message(request_id: str, message: str, *, status: str | None = None) -> None:
    with _LOCK:
        state = _STATE.get(request_id)
        if not state:
            return
        state.message = message
        if status is not None:
            state.status = status


def increment_progress(request_id: str, step: int = 1) -> None:
    with _LOCK:
        state = _STATE.get(request_id)
        if not state or state.status in {"completed", "failed"}:
            return
        state.processed_reads += step
        ratio = min(0.99, state.processed_reads / max(1, state.expected_reads))
        state.progress_percent = max(state.progress_percent, int(ratio * 100))
        if not state.message:
            state.message = "Processing video"


def complete_progress(request_id: str, message: str = "Analysis complete") -> None:
    with _LOCK:
        state = _STATE.get(request_id)
        if not state:
            return
        state.status = "completed"
        state.progress_percent = 100
        state.message = message


def fail_progress(request_id: str, error: str) -> None:
    with _LOCK:
        state = _STATE.get(request_id)
        if not state:
            return
        state.status = "failed"
        state.error = error
        state.message = error


def get_progress(request_id: str) -> dict[str, Any] | None:
    with _LOCK:
        state = _STATE.get(request_id)
        return state.snapshot() if state else None


@contextmanager
def track_request_progress(request_id: str | None):
    previous = getattr(_THREAD_LOCAL, "tracker", None)
    current = None
    if request_id:
        with _LOCK:
            current = _STATE.get(request_id)
    _THREAD_LOCAL.tracker = current
    try:
        yield current
    finally:
        _THREAD_LOCAL.tracker = previous
