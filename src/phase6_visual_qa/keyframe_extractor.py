"""
Keyframe extraction from video clips using FFmpeg.
Used by video_checker.py and content_check.py.
"""

import subprocess
import logging
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def extract_keyframes(
    video_path: str,
    count: int = 5,
    output_dir: Optional[str] = None,
) -> list[str]:
    """
    Extract evenly-spaced keyframes from a video file.
    
    Args:
        video_path: Path to input video
        count: Number of keyframes to extract
        output_dir: Directory for output PNGs (temp if None)
    
    Returns:
        List of paths to extracted keyframe PNGs
    """
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="keyframes_")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Get video duration
    duration = get_duration(str(video_path))
    if duration <= 0:
        raise ValueError(f"Invalid video duration: {duration}")

    # Calculate timestamps for evenly-spaced frames
    if count == 1:
        timestamps = [duration / 2]
    else:
        step = duration / (count + 1)
        timestamps = [step * (i + 1) for i in range(count)]

    frames = []
    for i, ts in enumerate(timestamps):
        out_path = str(output_dir / f"keyframe_{i:03d}.png")
        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{ts:.3f}",
            "-i", str(video_path),
            "-frames:v", "1",
            "-q:v", "2",
            out_path,
        ]
        try:
            subprocess.run(
                cmd, capture_output=True, timeout=30,
                check=True,
            )
            if Path(out_path).exists():
                frames.append(out_path)
        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to extract keyframe at {ts:.1f}s: {e.stderr[:200] if e.stderr else ''}")
        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout extracting keyframe at {ts:.1f}s")

    if not frames:
        raise RuntimeError(f"Failed to extract any keyframes from {video_path}")

    logger.info(f"Extracted {len(frames)} keyframes from {video_path.name}")
    return frames


def get_duration(video_path: str) -> float:
    """Get video duration in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError, subprocess.TimeoutExpired):
        return 0.0


def get_video_info(video_path: str) -> dict:
    """Get video metadata via ffprobe (resolution, fps, codec, duration, bitrate)."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,codec_name,bit_rate,duration",
        "-show_entries", "format=duration,bit_rate,size",
        "-of", "json",
        video_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        import json
        data = json.loads(result.stdout)
        stream = data.get("streams", [{}])[0]
        fmt = data.get("format", {})
        
        # Parse frame rate fraction
        fps_str = stream.get("r_frame_rate", "0/1")
        if "/" in fps_str:
            num, den = fps_str.split("/")
            fps = float(num) / float(den) if float(den) > 0 else 0
        else:
            fps = float(fps_str)

        return {
            "width": int(stream.get("width", 0)),
            "height": int(stream.get("height", 0)),
            "fps": round(fps, 2),
            "codec": stream.get("codec_name", "unknown"),
            "duration": float(fmt.get("duration", stream.get("duration", 0))),
            "bitrate": int(fmt.get("bit_rate", 0)),
            "file_size": int(fmt.get("size", 0)),
        }
    except Exception as e:
        logger.error(f"ffprobe failed for {video_path}: {e}")
        return {}
