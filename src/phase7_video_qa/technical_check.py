"""
Phase 7A — Technical QA: A/V sync, duration, resolution, bitrate, file integrity.
Uses ffprobe (part of FFmpeg) — no GPU needed.
"""

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ═══ Thresholds ═══
MIN_RESOLUTION_W = 1920
MIN_RESOLUTION_H = 1080
MIN_BITRATE_KBPS = 2000
MAX_BITRATE_KBPS = 50000
MIN_DURATION_SEC = 60
MAX_DURATION_SEC = 3600
MAX_AV_DRIFT_SEC = 0.5
MIN_FPS = 23.0
MAX_FPS = 61.0
MIN_AUDIO_BITRATE_KBPS = 96
EXPECTED_AUDIO_CHANNELS = 2
EXPECTED_AUDIO_SAMPLE_RATE = 44100


@dataclass
class TechnicalResult:
    """Result from technical QA checks."""
    passed: bool = True
    score: float = 10.0
    width: int = 0
    height: int = 0
    duration_sec: float = 0.0
    video_bitrate_kbps: float = 0.0
    audio_bitrate_kbps: float = 0.0
    fps: float = 0.0
    codec_video: str = ""
    codec_audio: str = ""
    audio_channels: int = 0
    audio_sample_rate: int = 0
    av_drift_sec: float = 0.0
    file_size_mb: float = 0.0
    file_valid: bool = True
    issues: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)


class TechnicalChecker:
    """Technical video QA using ffprobe."""

    def __init__(self, config: dict = None):
        self.config = config or {}

    def check(self, video_path: str) -> TechnicalResult:
        """
        Run full technical checks on composed video.
        Returns TechnicalResult with score and issues.
        """
        result = TechnicalResult()
        path = Path(video_path)

        # File integrity
        if not path.exists():
            result.passed = False
            result.file_valid = False
            result.score = 0.0
            result.issues.append("Video file does not exist")
            return result

        result.file_size_mb = round(path.stat().st_size / (1024 * 1024), 2)
        if result.file_size_mb < 1.0:
            result.passed = False
            result.file_valid = False
            result.score = 0.0
            result.issues.append(f"File too small ({result.file_size_mb} MB) — likely corrupt")
            return result

        # Probe with ffprobe
        probe = self._ffprobe(video_path)
        if probe is None:
            result.passed = False
            result.file_valid = False
            result.score = 0.0
            result.issues.append("ffprobe failed — file may be corrupt")
            return result

        # Parse streams
        video_stream = None
        audio_stream = None
        for stream in probe.get("streams", []):
            if stream.get("codec_type") == "video" and video_stream is None:
                video_stream = stream
            elif stream.get("codec_type") == "audio" and audio_stream is None:
                audio_stream = stream

        if video_stream is None:
            result.passed = False
            result.score = 0.0
            result.issues.append("No video stream found")
            return result

        if audio_stream is None:
            result.passed = False
            result.score = 0.0
            result.issues.append("No audio stream found")
            return result

        # Extract video properties
        result.width = int(video_stream.get("width", 0))
        result.height = int(video_stream.get("height", 0))
        result.codec_video = video_stream.get("codec_name", "unknown")
        result.fps = self._parse_fps(video_stream.get("r_frame_rate", "0/1"))

        # Duration
        fmt = probe.get("format", {})
        result.duration_sec = float(fmt.get("duration", 0))

        # Video bitrate
        video_br = int(video_stream.get("bit_rate", 0))
        if video_br == 0:
            # Estimate from format bitrate
            total_br = int(fmt.get("bit_rate", 0))
            audio_br = int(audio_stream.get("bit_rate", 0))
            video_br = total_br - audio_br
        result.video_bitrate_kbps = round(video_br / 1000, 1)

        # Audio properties
        result.codec_audio = audio_stream.get("codec_name", "unknown")
        result.audio_bitrate_kbps = round(int(audio_stream.get("bit_rate", 0)) / 1000, 1)
        result.audio_channels = int(audio_stream.get("channels", 0))
        result.audio_sample_rate = int(audio_stream.get("sample_rate", 0))

        # A/V sync (drift between video and audio start times)
        v_start = float(video_stream.get("start_time", 0))
        a_start = float(audio_stream.get("start_time", 0))
        result.av_drift_sec = round(abs(v_start - a_start), 4)

        # ─── Scoring ───
        penalty = 0.0

        # Resolution check
        if result.width < MIN_RESOLUTION_W or result.height < MIN_RESOLUTION_H:
            result.issues.append(
                f"Resolution {result.width}x{result.height} below "
                f"{MIN_RESOLUTION_W}x{MIN_RESOLUTION_H}"
            )
            penalty += 3.0

        # Duration check
        if result.duration_sec < MIN_DURATION_SEC:
            result.issues.append(
                f"Duration {result.duration_sec:.1f}s below minimum {MIN_DURATION_SEC}s"
            )
            penalty += 2.0
        elif result.duration_sec > MAX_DURATION_SEC:
            result.issues.append(
                f"Duration {result.duration_sec:.1f}s exceeds maximum {MAX_DURATION_SEC}s"
            )
            penalty += 1.0

        # Bitrate check
        if result.video_bitrate_kbps < MIN_BITRATE_KBPS:
            result.issues.append(
                f"Video bitrate {result.video_bitrate_kbps:.0f} kbps below {MIN_BITRATE_KBPS}"
            )
            penalty += 2.0
        elif result.video_bitrate_kbps > MAX_BITRATE_KBPS:
            result.issues.append(
                f"Video bitrate {result.video_bitrate_kbps:.0f} kbps exceeds {MAX_BITRATE_KBPS}"
            )
            penalty += 0.5

        # FPS check
        if result.fps < MIN_FPS or result.fps > MAX_FPS:
            result.issues.append(f"FPS {result.fps:.1f} outside range {MIN_FPS}-{MAX_FPS}")
            penalty += 1.5

        # A/V sync check
        if result.av_drift_sec > MAX_AV_DRIFT_SEC:
            result.issues.append(
                f"A/V drift {result.av_drift_sec:.3f}s exceeds {MAX_AV_DRIFT_SEC}s"
            )
            penalty += 3.0

        # Audio bitrate
        if result.audio_bitrate_kbps < MIN_AUDIO_BITRATE_KBPS:
            result.issues.append(
                f"Audio bitrate {result.audio_bitrate_kbps:.0f} kbps below {MIN_AUDIO_BITRATE_KBPS}"
            )
            penalty += 1.0

        # Audio channels
        if result.audio_channels < EXPECTED_AUDIO_CHANNELS:
            result.issues.append(f"Audio channels: {result.audio_channels} (expected stereo)")
            penalty += 0.5

        result.score = round(max(0.0, 10.0 - penalty), 2)
        result.passed = result.score >= 6.0

        result.details = {
            "format_name": fmt.get("format_name", ""),
            "format_long_name": fmt.get("format_long_name", ""),
            "nb_streams": int(fmt.get("nb_streams", 0)),
        }

        logger.info(
            "Technical QA: score=%.1f passed=%s issues=%d (%s)",
            result.score, result.passed, len(result.issues), video_path,
        )
        return result

    # ─── Internal Helpers ────────────────────────────────

    def _ffprobe(self, video_path: str) -> Optional[dict]:
        """Run ffprobe and return parsed JSON output."""
        try:
            cmd = [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                str(video_path),
            ]
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
            )
            if proc.returncode != 0:
                logger.error("ffprobe failed: %s", proc.stderr[:500])
                return None
            return json.loads(proc.stdout)
        except FileNotFoundError:
            logger.error("ffprobe not found — is FFmpeg installed?")
            return None
        except subprocess.TimeoutExpired:
            logger.error("ffprobe timed out")
            return None
        except Exception as e:
            logger.error("ffprobe error: %s", e)
            return None

    @staticmethod
    def _parse_fps(rate_str: str) -> float:
        """Parse frame rate string like '30000/1001' → 29.97."""
        try:
            if "/" in rate_str:
                num, den = rate_str.split("/")
                den_val = int(den)
                if den_val == 0:
                    return 0.0
                return round(int(num) / den_val, 2)
            return float(rate_str)
        except (ValueError, ZeroDivisionError):
            return 0.0
