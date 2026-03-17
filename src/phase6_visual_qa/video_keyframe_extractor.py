"""
Phase 6B — Video Keyframe Extractor.

Extracts keyframes from video clips using FFmpeg for QA analysis.
Primary method: I-frame extraction with fallback to evenly-spaced frames.

Usage:
    extractor = VideoKeyframeExtractor()
    paths = extractor.extract("clip.mp4", count=5)
"""

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class VideoKeyframeExtractor:
    """
    Extract keyframes from video clips for QA verification.

    Strategies:
    1. I-frame extraction: `ffmpeg -vf "select='eq(pict_type,I)'" -frames:v N`
    2. Fallback: evenly-spaced frames based on duration
    """

    def __init__(self, ffmpeg_path: str = "ffmpeg", ffprobe_path: str = "ffprobe"):
        self.ffmpeg = ffmpeg_path
        self.ffprobe = ffprobe_path

    def extract(
        self,
        video_path: str,
        count: int = 5,
        output_dir: Optional[str] = None,
        strategy: str = "iframe",
    ) -> list[str]:
        """
        Extract keyframes from a video file.

        Args:
            video_path: Path to the video file.
            count: Number of keyframes to extract.
            output_dir: Directory for output PNGs (temp dir if None).
            strategy: "iframe" (I-frame based) or "even" (evenly spaced).

        Returns:
            List of paths to extracted keyframe PNG files.

        Raises:
            FileNotFoundError: If video file doesn't exist.
            RuntimeError: If no keyframes could be extracted.
        """
        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"Video not found: {video_path}")

        if output_dir is None:
            output_dir = tempfile.mkdtemp(prefix="vqa_keyframes_")
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        # Try I-frame extraction first
        if strategy == "iframe":
            frames = self._extract_iframes(video_path, count, out_dir)
            if frames:
                return frames
            logger.info("I-frame extraction yielded no results, falling back to even spacing")

        # Fallback: evenly spaced
        frames = self._extract_even(video_path, count, out_dir)
        if not frames:
            raise RuntimeError(f"Failed to extract any keyframes from {video_path}")

        return frames

    def _extract_iframes(self, video_path: Path, count: int, out_dir: Path) -> list[str]:
        """Extract I-frames (keyframes) from video using FFmpeg select filter."""
        pattern = str(out_dir / "iframe_%03d.png")
        cmd = [
            self.ffmpeg, "-y",
            "-i", str(video_path),
            "-vf", "select='eq(pict_type,I)'",
            "-vsync", "vfr",
            "-frames:v", str(count),
            "-q:v", "2",
            pattern,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=60,
                text=True,
            )
            # FFmpeg may return non-zero but still produce output
            frames = sorted(out_dir.glob("iframe_*.png"))
            paths = [str(f) for f in frames[:count]]
            if paths:
                logger.info(f"Extracted {len(paths)} I-frames from {video_path.name}")
            return paths
        except subprocess.TimeoutExpired:
            logger.warning(f"I-frame extraction timed out for {video_path.name}")
            return []
        except Exception as e:
            logger.warning(f"I-frame extraction failed: {e}")
            return []

    def _extract_even(self, video_path: Path, count: int, out_dir: Path) -> list[str]:
        """Extract evenly-spaced frames based on video duration."""
        duration = self._get_duration(video_path)
        if duration <= 0:
            # Try single frame at start
            return self._extract_single(video_path, 0.1, out_dir)

        if count == 1:
            timestamps = [duration / 2]
        else:
            step = duration / (count + 1)
            timestamps = [step * (i + 1) for i in range(count)]

        frames = []
        for i, ts in enumerate(timestamps):
            out_path = str(out_dir / f"frame_{i:03d}.png")
            cmd = [
                self.ffmpeg, "-y",
                "-ss", f"{ts:.3f}",
                "-i", str(video_path),
                "-frames:v", "1",
                "-q:v", "2",
                out_path,
            ]
            try:
                subprocess.run(cmd, capture_output=True, timeout=30, check=True)
                if Path(out_path).exists() and Path(out_path).stat().st_size > 100:
                    frames.append(out_path)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                logger.warning(f"Failed to extract frame at {ts:.1f}s: {e}")

        if frames:
            logger.info(f"Extracted {len(frames)} evenly-spaced frames from {video_path.name}")
        return frames

    def _extract_single(self, video_path: Path, timestamp: float, out_dir: Path) -> list[str]:
        """Extract a single frame as fallback."""
        out_path = str(out_dir / "frame_000.png")
        cmd = [
            self.ffmpeg, "-y",
            "-ss", f"{timestamp:.3f}",
            "-i", str(video_path),
            "-frames:v", "1",
            "-q:v", "2",
            out_path,
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=30, check=True)
            if Path(out_path).exists():
                return [out_path]
        except Exception:
            pass
        return []

    def _get_duration(self, video_path: Path) -> float:
        """Get video duration in seconds using ffprobe."""
        cmd = [
            self.ffprobe, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            return float(result.stdout.strip())
        except (subprocess.CalledProcessError, ValueError, subprocess.TimeoutExpired):
            return 0.0

    def cleanup(self, keyframe_paths: list[str]) -> None:
        """Remove extracted keyframe files."""
        for path in keyframe_paths:
            try:
                Path(path).unlink(missing_ok=True)
            except Exception:
                pass
