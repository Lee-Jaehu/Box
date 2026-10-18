"""Timestamp-preserving scene and periodic sampling."""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from .types import Frame, Limits


def _hash(path: Path) -> int:
    with Image.open(path) as image:
        small = image.convert("L").resize((8, 8))
        pixels = [small.getpixel((x, y)) for y in range(8) for x in range(8)]
    mean = sum(pixels) / len(pixels)
    return sum((value >= mean) << i for i, value in enumerate(pixels))


def sample_frames(video_path: Path, out_dir: Path, limits: Limits = Limits()) -> list[Frame]:
    if limits.max_frames <= 0:
        return []
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="sampling-", dir=out_dir) as temp:
            result = subprocess.run(
                ["ffmpeg", "-hide_banner", "-i", str(video_path.resolve()), "-vf",
                 "select='isnan(prev_t)+gt(floor(t),floor(prev_t))+gt(scene,0.3)',showinfo",
                 "-fps_mode", "vfr", str(Path(temp) / "%08d.jpg")],
                shell=False, timeout=limits.ffmpeg_timeout_s, capture_output=True, text=True,
            )
            if result.returncode:
                return []
            timestamps = [float(ts) for ts in re.findall(r"\bpts_time:([\d.eE+\-]+)", result.stderr)]
            unique = []
            hashes = []
            for path, ts in zip(sorted(Path(temp).glob("*.jpg")), timestamps):
                fingerprint = _hash(path)
                if any((fingerprint ^ previous).bit_count() <= 2 for previous in hashes):
                    continue
                hashes.append(fingerprint)
                unique.append((ts, path))
            if len(unique) > limits.max_frames:
                if limits.max_frames == 1:
                    unique = [unique[len(unique) // 2]]
                else:
                    # Choose candidates nearest evenly spaced times, preserving endpoints.
                    chosen = set()
                    for i in range(limits.max_frames):
                        target = unique[0][0] + (unique[-1][0] - unique[0][0]) * i / (limits.max_frames - 1)
                        index = min((j for j in range(len(unique)) if j not in chosen), key=lambda j: abs(unique[j][0] - target))
                        chosen.add(index)
                    unique = [unique[j] for j in sorted(chosen)]
            frames = []
            for ts, path in unique:
                target = out_dir / path.name
                path.replace(target)
                frames.append(Frame(ts, target))
            return frames
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return []
