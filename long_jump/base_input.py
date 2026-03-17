from __future__ import annotations

from activity_common.video_base import VideoStats, iter_video_frames, read_video_stats


def read_long_jump_input(video_path: str) -> VideoStats:
    return read_video_stats(video_path)


def frame_count_from_stream(video_path: str) -> int:
    count = 0
    for _idx, _frame in iter_video_frames(video_path):
        count += 1
    return count
