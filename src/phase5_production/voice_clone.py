"""
Phase 5 — Voice Cloning (One-Time Setup).

Creates voice embeddings from reference WAV files using Fish Audio S2 Pro.
Pipeline: denoise → normalize → create embedding → test → save.

Usage:
    python -m src.phase5_production.voice_clone \
        --input config/voices/male_authoritative_01.wav \
        --id v_male_auth_01
"""

import io
import time
import logging
import subprocess
import shutil
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Minimum quality score for a clone to be accepted
MIN_CLONE_QUALITY = 6.0

# Reference text for clone quality testing (Arabic)
TEST_TEXT = (
    "هذا اختبار لجودة الصوت المستنسخ. "
    "يجب أن يكون الصوت واضحاً وطبيعياً بدون تشويش أو تقطيع."
)


@dataclass
class VoiceCloneConfig:
    """Configuration for voice cloning."""
    fish_audio_host: str = "http://localhost:8080"
    model_path: str = "models/fish_audio_s2_pro"
    embeddings_dir: str = "config/voices/embeddings"
    sample_rate: int = 44100
    denoise_enabled: bool = True
    normalize_target_db: float = -3.0
    min_quality_score: float = 6.0
    timeout_sec: int = 300
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"


@dataclass
class VoiceCloneResult:
    """Result of a voice cloning operation."""
    success: bool
    voice_id: Optional[str] = None
    embedding_path: Optional[str] = None
    quality_score: float = 0.0
    test_audio_path: Optional[str] = None
    processing_time_sec: float = 0.0
    error: Optional[str] = None


class VoiceCloner:
    """
    One-time voice cloning setup using Fish Audio S2 Pro.

    Pipeline:
    1. Denoise reference audio (FFmpeg noise reduction)
    2. Normalize volume to target dB
    3. Create voice embedding via Fish Audio S2 Pro
    4. Generate test audio and score quality
    5. Save embedding to config/voices/embeddings/

    The embedding is then used by VoiceGenerator for all future TTS.
    """

    def __init__(self, config: Optional[VoiceCloneConfig] = None):
        self.config = config or VoiceCloneConfig()

    def clone_voice(
        self,
        reference_wav: str,
        voice_id: str,
        voice_metadata: Optional[dict] = None,
    ) -> VoiceCloneResult:
        """
        Clone a voice from a reference WAV file.

        Args:
            reference_wav: Path to reference audio (WAV, 10-60 seconds).
            voice_id: Unique identifier (e.g. "v_male_auth_01").
            voice_metadata: Optional metadata (name, gender, style, etc.).

        Returns:
            VoiceCloneResult with embedding path and quality score.
        """
        start = time.time()
        ref_path = Path(reference_wav)

        if not ref_path.exists():
            return VoiceCloneResult(
                success=False, error=f"Reference file not found: {reference_wav}"
            )

        logger.info(f"Starting voice clone: {voice_id} from {ref_path.name}")

        try:
            # Step 1: Validate reference audio
            duration = self._get_duration(str(ref_path))
            if duration < 5.0:
                return VoiceCloneResult(
                    success=False,
                    error=f"Reference too short ({duration:.1f}s). Need ≥5 seconds.",
                )
            if duration > 120.0:
                logger.warning(
                    f"Reference is {duration:.1f}s — trimming to 60s for optimal cloning"
                )

            # Step 2: Denoise
            work_dir = Path(self.config.embeddings_dir) / f".tmp_{voice_id}"
            work_dir.mkdir(parents=True, exist_ok=True)

            if self.config.denoise_enabled:
                denoised_path = str(work_dir / "denoised.wav")
                self._denoise(str(ref_path), denoised_path)
                processed = denoised_path
            else:
                processed = str(ref_path)

            # Step 3: Normalize
            normalized_path = str(work_dir / "normalized.wav")
            self._normalize(processed, normalized_path)

            # Step 4: Create embedding via Fish Audio S2 Pro
            embedding_path = str(
                Path(self.config.embeddings_dir) / f"{voice_id}.pt"
            )
            Path(self.config.embeddings_dir).mkdir(parents=True, exist_ok=True)

            self._create_embedding(normalized_path, embedding_path)

            # Step 5: Test the clone
            test_audio_path = str(work_dir / "test_output.wav")
            quality_score = self._test_clone(
                embedding_path, test_audio_path,
            )

            # Step 6: Quality gate
            elapsed = round(time.time() - start, 2)

            if quality_score < self.config.min_quality_score:
                logger.warning(
                    f"Clone quality {quality_score:.1f} below threshold "
                    f"{self.config.min_quality_score}"
                )
                return VoiceCloneResult(
                    success=False,
                    voice_id=voice_id,
                    embedding_path=embedding_path,
                    quality_score=quality_score,
                    test_audio_path=test_audio_path,
                    processing_time_sec=elapsed,
                    error=f"Quality {quality_score:.1f} below {self.config.min_quality_score}",
                )

            # Step 7: Save metadata
            if voice_metadata:
                self._save_metadata(voice_id, embedding_path, voice_metadata, quality_score)

            logger.info(
                f"Voice clone complete: {voice_id} "
                f"(quality={quality_score:.1f}, {elapsed}s)"
            )

            # Cleanup work dir (keep test audio for review)
            final_test = str(
                Path(self.config.embeddings_dir) / f"{voice_id}_test.wav"
            )
            if Path(test_audio_path).exists():
                shutil.copy2(test_audio_path, final_test)
            shutil.rmtree(work_dir, ignore_errors=True)

            return VoiceCloneResult(
                success=True,
                voice_id=voice_id,
                embedding_path=embedding_path,
                quality_score=quality_score,
                test_audio_path=final_test,
                processing_time_sec=elapsed,
            )

        except Exception as e:
            elapsed = round(time.time() - start, 2)
            logger.error(f"Voice cloning failed: {e}", exc_info=True)
            return VoiceCloneResult(
                success=False,
                voice_id=voice_id,
                processing_time_sec=elapsed,
                error=str(e),
            )

    # ═══════════════════════════════════════════════════════
    # PROCESSING STEPS
    # ═══════════════════════════════════════════════════════

    def _denoise(self, input_path: str, output_path: str):
        """
        Denoise reference audio using FFmpeg's afftdn filter.
        """
        cmd = [
            self.config.ffmpeg, "-y",
            "-i", input_path,
            "-af", "afftdn=nf=-25:nt=w:om=o",
            "-ar", str(self.config.sample_rate),
            "-ac", "1",  # Mono for voice cloning
            output_path,
        ]
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60,
        )
        if proc.returncode != 0:
            logger.warning(f"Denoise failed, using original: {proc.stderr[:200]}")
            shutil.copy2(input_path, output_path)

    def _normalize(self, input_path: str, output_path: str):
        """
        Normalize audio volume to target dB level.
        """
        target = self.config.normalize_target_db
        cmd = [
            self.config.ffmpeg, "-y",
            "-i", input_path,
            "-af", f"loudnorm=I=-16:TP={target}:LRA=11",
            "-ar", str(self.config.sample_rate),
            "-ac", "1",
            output_path,
        ]
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60,
        )
        if proc.returncode != 0:
            logger.warning(f"Normalize failed: {proc.stderr[:200]}")
            shutil.copy2(input_path, output_path)

    def _create_embedding(self, audio_path: str, embedding_path: str):
        """
        Create a voice embedding using Fish Audio S2 Pro API.
        """
        import requests

        with open(audio_path, "rb") as f:
            audio_data = f.read()

        r = requests.post(
            f"{self.config.fish_audio_host}/v1/clone",
            files={"audio": ("reference.wav", audio_data, "audio/wav")},
            timeout=self.config.timeout_sec,
        )
        r.raise_for_status()

        # Fish Audio returns the embedding bytes
        content_type = r.headers.get("content-type", "")
        if "application/json" in content_type:
            import json, base64
            data = r.json()
            embedding_bytes = base64.b64decode(data.get("embedding", ""))
        else:
            embedding_bytes = r.content

        with open(embedding_path, "wb") as f:
            f.write(embedding_bytes)

        logger.info(f"Embedding saved: {embedding_path} ({len(embedding_bytes)} bytes)")

    def _test_clone(self, embedding_path: str, output_path: str) -> float:
        """
        Generate test audio with the clone and score quality.

        Returns quality score 0-10.
        """
        import requests

        with open(embedding_path, "rb") as f:
            embedding_data = f.read()

        # Generate test audio
        r = requests.post(
            f"{self.config.fish_audio_host}/v1/tts",
            data={
                "text": TEST_TEXT,
                "speed": 1.0,
                "format": "wav",
                "sample_rate": self.config.sample_rate,
            },
            files={
                "speaker_embedding": ("embedding.pt", io.BytesIO(embedding_data), "application/octet-stream"),
            },
            timeout=self.config.timeout_sec,
        )
        r.raise_for_status()

        # Save test audio
        content_type = r.headers.get("content-type", "")
        if "application/json" in content_type:
            import json, base64
            data = r.json()
            audio_bytes = base64.b64decode(data.get("audio", ""))
        else:
            audio_bytes = r.content

        with open(output_path, "wb") as f:
            f.write(audio_bytes)

        # Score quality
        return self._score_quality(output_path)

    def _score_quality(self, audio_path: str) -> float:
        """
        Score the quality of generated test audio.

        Checks: duration, clipping, silence, SNR.
        Returns score 0-10.
        """
        score = 10.0

        duration = self._get_duration(audio_path)
        if duration < 1.0:
            return 0.0

        # Expected duration for test text (~15-25 words)
        if duration < 3.0 or duration > 30.0:
            score -= 3.0

        # Clipping detection
        try:
            proc = subprocess.run(
                [self.config.ffmpeg, "-i", audio_path,
                 "-af", "astats=metadata=1:reset=1",
                 "-f", "null", "-"],
                capture_output=True, text=True, timeout=30,
            )
            clip_count = proc.stderr.count("Flat_factor")
            if clip_count > 5:
                score -= 2.0
        except Exception:
            pass

        # SNR check
        try:
            proc = subprocess.run(
                [self.config.ffmpeg, "-i", audio_path,
                 "-af", "volumedetect", "-f", "null", "-"],
                capture_output=True, text=True, timeout=30,
            )
            for line in proc.stderr.split("\n"):
                if "mean_volume" in line:
                    parts = line.split("mean_volume:")
                    if len(parts) > 1:
                        mean_db = float(parts[1].strip().split()[0])
                        snr = abs(mean_db - (-60))
                        if snr < 20:
                            score -= 2.0
                        elif snr < 30:
                            score -= 0.5
        except Exception:
            pass

        return max(0.0, min(10.0, score))

    def _get_duration(self, path: str) -> float:
        """Get audio duration in seconds."""
        try:
            proc = subprocess.run(
                [self.config.ffprobe, "-v", "error",
                 "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", path],
                capture_output=True, text=True, timeout=10,
            )
            return float(proc.stdout.strip())
        except Exception:
            return 0.0

    def _save_metadata(
        self,
        voice_id: str,
        embedding_path: str,
        metadata: dict,
        quality_score: float,
    ):
        """Save voice metadata to voice_library.yaml."""
        import yaml

        library_path = Path(self.config.embeddings_dir).parent / "voice_library.yaml"

        # Load existing
        library = {}
        if library_path.exists():
            with open(library_path, "r", encoding="utf-8") as f:
                library = yaml.safe_load(f) or {}

        if "voices" not in library:
            library["voices"] = {}

        library["voices"][voice_id] = {
            "embedding_path": embedding_path,
            "quality_score": quality_score,
            **metadata,
        }

        with open(library_path, "w", encoding="utf-8") as f:
            yaml.dump(library, f, allow_unicode=True, default_flow_style=False)

        logger.info(f"Voice metadata saved: {voice_id} → {library_path}")


# ═══════════════════════════════════════════════════════════════
# CLI ENTRY POINT
# ═══════════════════════════════════════════════════════════════

def main():
    """CLI for one-time voice cloning."""
    import argparse

    parser = argparse.ArgumentParser(description="Clone a voice for TTS")
    parser.add_argument("--input", required=True, help="Path to reference WAV")
    parser.add_argument("--id", required=True, help="Voice ID (e.g. v_male_auth_01)")
    parser.add_argument("--name", default="", help="Human-readable name")
    parser.add_argument("--gender", default="male", help="Gender (male/female)")
    parser.add_argument("--style", default="", help="Voice style description")
    parser.add_argument("--host", default="http://localhost:8080", help="Fish Audio host")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    config = VoiceCloneConfig(fish_audio_host=args.host)
    cloner = VoiceCloner(config)

    metadata = {
        "name": args.name or args.id,
        "gender": args.gender,
        "style": args.style,
    }

    result = cloner.clone_voice(
        reference_wav=args.input,
        voice_id=args.id,
        voice_metadata=metadata,
    )

    if result.success:
        print(f"✅ Voice cloned: {result.voice_id}")
        print(f"   Embedding: {result.embedding_path}")
        print(f"   Quality: {result.quality_score:.1f}/10")
        print(f"   Test audio: {result.test_audio_path}")
    else:
        print(f"❌ Clone failed: {result.error}")
        exit(1)


if __name__ == "__main__":
    main()
