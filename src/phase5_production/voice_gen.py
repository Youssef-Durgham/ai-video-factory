"""
Phase 5 — Voice Generation via Fish Audio S2 Pro.

Generates per-scene narration with emotion tags, speed control,
and quality checks.
"""

import io
import json
import time
import wave
import struct
import logging
import subprocess
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════
# EMOTION → FISH AUDIO PARAMETERS
# ════════════════════════════════════════════════════════════════

EMOTION_PARAMS: dict[str, dict] = {
    "calm":       {"speed": 1.00, "pitch_shift": 0,  "energy": 0.5},
    "dramatic":   {"speed": 0.92, "pitch_shift": -1, "energy": 0.8},
    "mysterious": {"speed": 0.88, "pitch_shift": -2, "energy": 0.4},
    "urgent":     {"speed": 1.18, "pitch_shift": 1,  "energy": 0.9},
    "excited":    {"speed": 1.12, "pitch_shift": 1,  "energy": 0.85},
    "whisper":    {"speed": 0.82, "pitch_shift": -1, "energy": 0.25},
    "reflective": {"speed": 0.95, "pitch_shift": 0,  "energy": 0.4},
    "somber":     {"speed": 0.90, "pitch_shift": -2, "energy": 0.35},
    "hopeful":    {"speed": 1.02, "pitch_shift": 0,  "energy": 0.6},
    "tense":      {"speed": 0.95, "pitch_shift": -1, "energy": 0.7},
}

DEFAULT_EMOTION = "calm"


@dataclass
class VoiceGenConfig:
    fish_audio_host: str = "http://localhost:8080"
    model_path: str = "models/fish_audio_s2_pro"
    sample_rate: int = 44100
    timeout_sec: int = 120
    min_quality_score: float = 6.0


@dataclass
class VoiceGenResult:
    success: bool
    audio_path: Optional[str] = None
    duration_sec: float = 0.0
    generation_time_sec: float = 0.0
    quality_score: float = 0.0
    word_timestamps: Optional[list] = None
    error: Optional[str] = None


class VoiceGenerator:
    """
    Generates Arabic narration using Fish Audio S2 Pro voice cloning.

    Supports per-scene emotion tags and speed control.
    """

    def __init__(self, config: Optional[VoiceGenConfig] = None):
        self.config = config or VoiceGenConfig()
        self._voice_embedding: Optional[bytes] = None
        self._voice_id: Optional[str] = None

    def load_voice(self, voice_id: str, embedding_path: str):
        """
        Load a cloned voice embedding for generation.

        Args:
            voice_id: Voice identifier (e.g. "v_male_auth_01").
            embedding_path: Path to .pt or .npy embedding file.
        """
        self._voice_id = voice_id
        emb_path = Path(embedding_path)
        if not emb_path.exists():
            raise FileNotFoundError(f"Voice embedding not found: {embedding_path}")
        with open(emb_path, "rb") as f:
            self._voice_embedding = f.read()
        logger.info(f"Loaded voice embedding: {voice_id} ({emb_path.name})")

    # ─── Public API ────────────────────────────────────────

    def generate(
        self,
        text: str,
        output_dir: str,
        filename: str = "voice",
        emotion: str = DEFAULT_EMOTION,
        speed_override: Optional[float] = None,
        reference_wav: Optional[str] = None,
    ) -> VoiceGenResult:
        """
        Generate narration audio for a single text segment.

        Args:
            text: Arabic narration text.
            output_dir: Output directory.
            filename: Output filename (without .wav).
            emotion: Emotion tag (maps to speed/pitch).
            speed_override: Manual speed (overrides emotion preset).
            reference_wav: Optional reference audio for zero-shot clone.

        Returns:
            VoiceGenResult with audio path and quality metrics.
        """
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        audio_path = str(out_path / f"{filename}.wav")

        params = EMOTION_PARAMS.get(emotion, EMOTION_PARAMS[DEFAULT_EMOTION])
        speed = speed_override if speed_override is not None else params["speed"]

        start = time.time()
        try:
            # Call Fish Audio S2 Pro API
            audio_data, word_timestamps = self._call_fish_audio(
                text=text,
                speed=speed,
                pitch_shift=params.get("pitch_shift", 0),
                energy=params.get("energy", 0.5),
                reference_wav=reference_wav,
            )

            # Save WAV
            self._save_wav(audio_data, audio_path)

            # Quality check
            duration = self._get_wav_duration(audio_path)
            quality = self._check_quality(audio_path, text)

            elapsed = round(time.time() - start, 2)
            logger.info(
                f"Voice generated: {filename} ({duration:.1f}s, "
                f"quality={quality:.1f}, emotion={emotion})"
            )

            return VoiceGenResult(
                success=quality >= self.config.min_quality_score,
                audio_path=audio_path,
                duration_sec=duration,
                generation_time_sec=elapsed,
                quality_score=quality,
                word_timestamps=word_timestamps,
                error=None if quality >= self.config.min_quality_score
                else f"Quality {quality:.1f} below threshold {self.config.min_quality_score}",
            )

        except Exception as e:
            elapsed = round(time.time() - start, 2)
            logger.error(f"Voice generation failed: {e}")
            return VoiceGenResult(
                success=False,
                generation_time_sec=elapsed,
                error=str(e),
            )

    def generate_batch(
        self,
        scenes: list[dict],
        output_dir: str,
        voice_id: Optional[str] = None,
        embedding_path: Optional[str] = None,
    ) -> list[VoiceGenResult]:
        """
        Generate narration for all scenes.

        Each scene dict needs: scene_index, narration_text, voice_emotion
        """
        if voice_id and embedding_path and self._voice_id != voice_id:
            self.load_voice(voice_id, embedding_path)

        results = []
        total = len(scenes)
        for i, scene in enumerate(scenes):
            idx = scene.get("scene_index", i)
            text = scene.get("narration_text", "")
            if not text.strip():
                results.append(VoiceGenResult(success=True, duration_sec=0))
                continue

            emotion = scene.get("voice_emotion", DEFAULT_EMOTION)
            logger.info(f"Generating voice {i + 1}/{total} (scene {idx}, {emotion})")

            result = self.generate(
                text=text,
                output_dir=output_dir,
                filename=f"scene_{idx:03d}",
                emotion=emotion,
            )
            results.append(result)

        passed = sum(1 for r in results if r.success)
        logger.info(f"Voice batch: {passed}/{total} generated")
        return results

    # ─── Fish Audio S2 Pro API ─────────────────────────────

    def _call_fish_audio(
        self,
        text: str,
        speed: float,
        pitch_shift: int,
        energy: float,
        reference_wav: Optional[str],
    ) -> tuple[bytes, Optional[list]]:
        """
        Call Fish Audio S2 Pro TTS endpoint.

        Returns (audio_bytes, word_timestamps).
        """
        import requests

        # Build request
        payload = {
            "text": text,
            "speed": speed,
            "pitch_shift": pitch_shift,
            "energy": energy,
            "format": "wav",
            "sample_rate": self.config.sample_rate,
        }

        files = {}

        # Voice embedding
        if self._voice_embedding:
            files["speaker_embedding"] = (
                f"{self._voice_id}.pt",
                io.BytesIO(self._voice_embedding),
                "application/octet-stream",
            )
        elif reference_wav:
            with open(reference_wav, "rb") as f:
                files["reference_audio"] = (
                    Path(reference_wav).name,
                    f.read(),
                    "audio/wav",
                )

        r = requests.post(
            f"{self.config.fish_audio_host}/v1/tts",
            data=payload,
            files=files if files else None,
            timeout=self.config.timeout_sec,
        )
        r.raise_for_status()

        # Parse response — Fish Audio may return JSON with audio + timestamps
        content_type = r.headers.get("content-type", "")
        if "application/json" in content_type:
            data = r.json()
            import base64
            audio_bytes = base64.b64decode(data.get("audio", ""))
            timestamps = data.get("word_timestamps")
            return audio_bytes, timestamps
        else:
            # Raw audio bytes
            return r.content, None

    # ─── Quality Checks ───────────────────────────────────

    def _check_quality(self, audio_path: str, expected_text: str) -> float:
        """
        Basic quality checks on generated audio.

        Returns score 0–10.
        """
        score = 10.0

        try:
            duration = self._get_wav_duration(audio_path)

            # Check 1: Not empty / too short
            if duration < 0.5:
                return 0.0

            # Check 2: Expected duration (rough: ~2.5 words/sec for Arabic)
            word_count = len(expected_text.split())
            expected_dur = word_count / 2.5
            ratio = duration / expected_dur if expected_dur > 0 else 1.0
            if ratio < 0.5 or ratio > 2.5:
                score -= 3.0  # Way off expected duration

            # Check 3: Clipping detection via FFmpeg
            clipping = self._detect_clipping(audio_path)
            if clipping > 5:
                score -= 2.0

            # Check 4: Silence gaps
            silence_gaps = self._detect_silence_gaps(audio_path)
            if silence_gaps > 3:
                score -= 1.5

            # Check 5: SNR (basic — via loudness stats)
            snr = self._estimate_snr(audio_path)
            if snr < 20:
                score -= 2.0
            elif snr < 30:
                score -= 0.5

        except Exception as e:
            logger.warning(f"Quality check error: {e}")
            score -= 1.0

        return max(0.0, min(10.0, score))

    def _detect_clipping(self, audio_path: str) -> int:
        """Count clipping events using FFmpeg astats."""
        try:
            cmd = [
                "ffmpeg", "-i", audio_path,
                "-af", "astats=metadata=1:reset=1",
                "-f", "null", "-",
            ]
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30
            )
            # Count "Flat_factor" warnings or peak near 1.0
            clip_count = proc.stderr.count("Flat_factor")
            return clip_count
        except Exception:
            return 0

    def _detect_silence_gaps(self, audio_path: str) -> int:
        """Detect long silence gaps using FFmpeg silencedetect."""
        try:
            cmd = [
                "ffmpeg", "-i", audio_path,
                "-af", "silencedetect=noise=-40dB:d=1.5",
                "-f", "null", "-",
            ]
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30
            )
            return proc.stderr.count("silence_end")
        except Exception:
            return 0

    def _estimate_snr(self, audio_path: str) -> float:
        """Rough SNR estimate via RMS levels."""
        try:
            cmd = [
                "ffmpeg", "-i", audio_path,
                "-af", "volumedetect",
                "-f", "null", "-",
            ]
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30
            )
            # Parse mean_volume and max_volume
            for line in proc.stderr.split("\n"):
                if "mean_volume" in line:
                    parts = line.split("mean_volume:")
                    if len(parts) > 1:
                        mean_db = float(parts[1].strip().split()[0])
                        # Rough SNR: difference from noise floor (~-60dB)
                        return abs(mean_db - (-60))
            return 40.0  # Default OK
        except Exception:
            return 40.0

    # ─── Helpers ───────────────────────────────────────────

    def _save_wav(self, audio_data: bytes, path: str):
        """Save raw audio bytes as WAV file."""
        with open(path, "wb") as f:
            f.write(audio_data)

    def _get_wav_duration(self, path: str) -> float:
        """Get duration of a WAV file in seconds."""
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                path,
            ]
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10
            )
            return float(proc.stdout.strip())
        except Exception:
            return 0.0
