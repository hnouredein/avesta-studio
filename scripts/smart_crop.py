"""
100% Free, Zero-Dependency (FFmpeg + NumPy) Smart Auto-Crop Detector.

Samples 6 evenly spaced frames at 180x320 and detects:
  1. Solid letterbox / pillarbox bars (black, white, or uniform color).
  2. Static top/bottom social-media title banners (text on white/dark header bars
     that remain temporally static across the video while the real footage moves).

Returns safe crop percentages {cropTop, cropBottom, cropLeft, cropRight} (capped
at 28% per edge / 42% total vertical so faces and main subjects are never cut).
"""

import json
import subprocess
import sys
from typing import Any

import numpy as np


def _probe_duration(video_path: str) -> float:
    res = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    try:
        return max(0.0, float(res.stdout.strip()))
    except Exception:
        return 0.0


def _sample_frames(video_path: str, w: int = 180, h: int = 320, count: int = 6) -> np.ndarray | None:
    dur = _probe_duration(video_path)
    if dur <= 0.5:
        return None
    fps = count / max(1.0, dur)
    cmd = [
        "ffmpeg", "-v", "error",
        "-i", video_path,
        "-vf", f"fps={fps:.4f},scale={w}:{h}",
        "-frames:v", str(count),
        "-f", "rawvideo",
        "-pix_fmt", "gray",
        "-",
    ]
    res = subprocess.run(cmd, capture_output=True, timeout=25)
    raw = res.stdout or b""
    frame_bytes = w * h
    n_frames = len(raw) // frame_bytes
    if n_frames < 2:
        return None
    arr = np.frombuffer(raw[: n_frames * frame_bytes], dtype=np.uint8)
    return arr.reshape((n_frames, h, w)).astype(np.float32)


def detect_smart_crop(
    video_path: str,
    max_v_pct: float = 28.0,
    max_h_pct: float = 18.0,
) -> dict[str, float]:
    """Detect static top/bottom banners and letterbox/pillarbox bars."""
    empty = {"cropTop": 0.0, "cropBottom": 0.0, "cropLeft": 0.0, "cropRight": 0.0}
    frames = _sample_frames(video_path)
    if frames is None:
        return empty

    n, h, w = frames.shape
    # Row-wise temporal difference (how much each row moves across the video)
    diffs = np.abs(np.diff(frames, axis=0))  # (n-1, h, w)
    row_motion = diffs.mean(axis=(0, 2))     # (h,)
    col_motion = diffs.mean(axis=(0, 1))     # (w,)

    # Spatial uniformity (solid bars have very low std dev across width/height)
    row_std = frames.std(axis=2).mean(axis=0)  # (h,)
    col_std = frames.std(axis=1).mean(axis=0)  # (w,)

    # Only trust temporal static detection if the middle of the video actually has motion
    mid_motion = float(np.median(row_motion[int(h * 0.32) : int(h * 0.68)]))
    has_scene_motion = mid_motion > 4.0

    def is_bar_row(y: int) -> bool:
        # Solid bar (black/white/gray) OR temporally frozen header/footer banner
        if row_std[y] < 12.0:
            return True
        if has_scene_motion and row_motion[y] < min(3.2, mid_motion * 0.25):
            return True
        return False

    def is_bar_col(x: int) -> bool:
        return bool(col_std[x] < 10.0)

    max_top_y = int(h * (max_v_pct / 100.0))
    top_y = 0
    for y in range(max_top_y):
        if is_bar_row(y):
            top_y = y + 1
        else:
            break

    max_bot_rows = int(h * (max_v_pct / 100.0))
    bot_rows = 0
    for dy in range(max_bot_rows):
        y = h - 1 - dy
        if is_bar_row(y):
            bot_rows = dy + 1
        else:
            break

    max_side_x = int(w * (max_h_pct / 100.0))
    left_x = 0
    for x in range(max_side_x):
        if is_bar_col(x):
            left_x = x + 1
        else:
            break

    right_x = 0
    for dx in range(max_side_x):
        x = w - 1 - dx
        if is_bar_col(x):
            right_x = dx + 1
        else:
            break

    crop_top = round((top_y / h) * 100.0, 1)
    crop_bot = round((bot_rows / h) * 100.0, 1)
    crop_left = round((left_x / w) * 100.0, 1)
    crop_right = round((right_x / w) * 100.0, 1)

    # Ignore tiny < 3% edge noise; add +1.5% clean safety margin when real bar detected
    crop_top = min(max_v_pct, round(crop_top + 1.5, 1)) if crop_top >= 3.0 else 0.0
    crop_bot = min(max_v_pct, round(crop_bot + 1.5, 1)) if crop_bot >= 3.0 else 0.0
    crop_left = min(max_h_pct, round(crop_left + 1.0, 1)) if crop_left >= 3.0 else 0.0
    crop_right = min(max_h_pct, round(crop_right + 1.0, 1)) if crop_right >= 3.0 else 0.0

    # Keep total vertical crop safe (<= 42%)
    if crop_top + crop_bot > 42.0:
        scale = 42.0 / (crop_top + crop_bot)
        crop_top = round(crop_top * scale, 1)
        crop_bot = round(crop_bot * scale, 1)

    return {
        "cropTop": crop_top,
        "cropBottom": crop_bot,
        "cropLeft": crop_left,
        "cropRight": crop_right,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/smart_crop.py <video_path>")
        sys.exit(1)
    print(json.dumps(detect_smart_crop(sys.argv[1]), ensure_ascii=False))

