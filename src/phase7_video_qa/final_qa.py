"""
Phase 7 — Final QA: Last quality gate before publish.

Validates final.mp4 technical specs: codec, bitrate, resolution, duration, streams.
Simple pass/warn system.
"""

import json
import logging
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class FinalQAResult:
    success: bool
    passed: bool = False
    score: float = 0.0
    checks: dict = None
    warnings: list = None
    error: Optional[str] = None

    def __post_init__(self):
        if self.checks is None:
            self.checks = {}
        if self.warnings is None:
            self.warnings = []


class FinalQA:
    """Final quality gate for the composed video."""

    def check(self, video_path: str, target_duration_sec: float = 0) -> FinalQAResult:
        """Run final QA checks on the video."""
        p = Path(video_path)
        if not p.exists():
            return FinalQAResult(success=False, error=f"File not found: {video_path}")

        checks = {}
        warnings = []
        score = 10.0

        # 1. File validity
        size_bytes = p.stat().st_size
        checks["file_size_mb"] = round(size_bytes / (1024 * 1024), 2)
        if size_bytes < 100_000:
            warnings.append("File suspiciously small")
            score -= 3

        # 2. FFprobe analysis
        probe = self._ffprobe_json(video_path)
        if not probe:
            return FinalQAResult(success=False, error="FFprobe failed to analyze file")

        fmt = probe.get("format", {})
        streams = probe.get("streams", [])

        duration = float(fmt.get("duration", 0))
        checks["duration_sec"] = round(duration, 2)
        checks["bitrate_kbps"] = int(fmt.get("bit_rate", 0)) // 1000

        # 3. Stream checks
        video_stream = None
        audio_stream = None
        for s in streams:
            if s.get("codec_type") == "video":
                video_stream = s
            elif s.get("codec_type") == "audio":
                audio_stream = s

        if not video_stream:
            warnings.append("No video stream")
            score -= 5
        else:
            checks["video_codec"] = video_stream.get("codec_name", "unknown")
            checks["resolution"] = f"{video_stream.get('width', '?')}x{video_stream.get('height', '?')}"
            checks["fps"] = video_stream.get("r_frame_rate", "?")

            if video_stream.get("codec_name") not in ("h264", "hevc", "vp9"):
                warnings.append(f"Unexpected video codec: {video_stream.get('codec_name')}")
                score -= 1

            width = int(video_stream.get("width", 0))
            if width < 1000:
                warnings.append(f"Low resolution: {width}px wide")
                score -= 2

        if not audio_stream:
            warnings.append("No audio stream")
            score -= 3
        else:
            checks["audio_codec"] = audio_stream.get("codec_name", "unknown")
            checks["audio_channels"] = audio_stream.get("channels", 0)
            checks["audio_sample_rate"] = audio_stream.get("sample_rate", "?")

        # 4. Duration check
        if target_duration_sec > 0:
            diff_pct = abs(duration - target_duration_sec) / target_duration_sec * 100
            checks["duration_diff_pct"] = round(diff_pct, 1)
            if diff_pct > 10:
                warnings.append(f"Duration off by {diff_pct:.0f}% (target: {target_duration_sec:.0f}s, actual: {duration:.0f}s)")
                score -= 2

        # 5. Minimum duration
        if duration < 30:
            warnings.append(f"Video very short: {duration:.0f}s")
            score -= 2

        score = max(0, min(10, score))
        passed = score >= 6.0

        logger.info(f"Final QA: score={score:.1f}, passed={passed}, warnings={len(warnings)}")
        return FinalQAResult(
            success=True, passed=passed, score=score,
            checks=checks, warnings=warnings,
        )

    def _ffprobe_json(self, path: str) -> Optional[dict]:
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", path],
                capture_output=True, text=True, timeout=30,
            )
            return json.loads(result.stdout)
        except Exception as e:
            logger.error(f"FFprobe failed: {e}")
            return None
