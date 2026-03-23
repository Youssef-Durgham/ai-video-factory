"""
Phase 6 — Overlay QA: Basic quality checks on the composed final video.

Extracts sample frames, checks for black/corrupt frames,
validates audio stream and duration.
"""

import logging
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class OverlayQAResult:
    success: bool
    passed: bool = False
    checks: dict = None
    warnings: list = None
    error: Optional[str] = None

    def __post_init__(self):
        if self.checks is None:
            self.checks = {}
        if self.warnings is None:
            self.warnings = []


class OverlayQA:
    """Run quality checks on the final composed video."""

    def check(self, video_path: str, expected_duration_sec: float = 0) -> OverlayQAResult:
        """Run all overlay QA checks."""
        if not Path(video_path).exists():
            return OverlayQAResult(success=False, error=f"Video not found: {video_path}")

        checks = {}
        warnings = []

        # 1. File size check
        size_mb = Path(video_path).stat().st_size / (1024 * 1024)
        checks["file_size_mb"] = round(size_mb, 2)
        if size_mb < 0.5:
            warnings.append(f"Video file very small: {size_mb:.1f}MB")

        # 2. FFprobe metadata
        probe = self._ffprobe(video_path)
        if not probe:
            return OverlayQAResult(success=False, error="FFprobe failed")

        checks["duration_sec"] = probe.get("duration", 0)
        checks["has_video"] = probe.get("has_video", False)
        checks["has_audio"] = probe.get("has_audio", False)
        checks["resolution"] = probe.get("resolution", "unknown")
        checks["video_codec"] = probe.get("video_codec", "unknown")
        checks["audio_codec"] = probe.get("audio_codec", "unknown")

        if not probe.get("has_video"):
            warnings.append("No video stream found")
        if not probe.get("has_audio"):
            warnings.append("No audio stream found")

        # 3. Duration check
        if expected_duration_sec > 0:
            actual = probe.get("duration", 0)
            diff_pct = abs(actual - expected_duration_sec) / expected_duration_sec * 100
            checks["duration_diff_pct"] = round(diff_pct, 1)
            if diff_pct > 20:
                warnings.append(f"Duration mismatch: expected {expected_duration_sec:.0f}s, got {actual:.0f}s ({diff_pct:.0f}% off)")

        # 4. Extract and check sample frames
        frames_ok = self._check_sample_frames(video_path, probe.get("duration", 60))
        checks["frames_ok"] = frames_ok
        if not frames_ok:
            warnings.append("Some sample frames appear black or corrupt")

        passed = len(warnings) == 0 or all("small" in w.lower() for w in warnings)
        return OverlayQAResult(success=True, passed=passed, checks=checks, warnings=warnings)

    def _ffprobe(self, path: str) -> Optional[dict]:
        """Get video metadata via ffprobe."""
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_format", "-show_streams",
                 "-of", "json", path],
                capture_output=True, text=True, timeout=30,
            )
            import json
            data = json.loads(result.stdout)

            info = {"has_video": False, "has_audio": False}
            info["duration"] = float(data.get("format", {}).get("duration", 0))

            for stream in data.get("streams", []):
                if stream.get("codec_type") == "video":
                    info["has_video"] = True
                    info["video_codec"] = stream.get("codec_name", "unknown")
                    info["resolution"] = f"{stream.get('width', '?')}x{stream.get('height', '?')}"
                elif stream.get("codec_type") == "audio":
                    info["has_audio"] = True
                    info["audio_codec"] = stream.get("codec_name", "unknown")
            return info
        except Exception as e:
            logger.error(f"FFprobe failed: {e}")
            return None

    def _check_sample_frames(self, video_path: str, duration: float, num_frames: int = 5) -> bool:
        """Extract sample frames and check they're not all black."""
        import tempfile
        tmpdir = tempfile.mkdtemp()
        interval = max(1, duration / (num_frames + 1))

        ok_count = 0
        for i in range(num_frames):
            ts = interval * (i + 1)
            frame_path = str(Path(tmpdir) / f"frame_{i}.jpg")
            cmd = [
                "ffmpeg", "-y", "-ss", str(ts),
                "-i", video_path,
                "-frames:v", "1", "-q:v", "2",
                frame_path,
            ]
            subprocess.run(cmd, capture_output=True, timeout=30)

            if Path(frame_path).exists() and Path(frame_path).stat().st_size > 5000:
                ok_count += 1

        # Cleanup
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)

        return ok_count >= (num_frames // 2)
