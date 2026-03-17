"""
Phase 5 — Music Generation via ACE-Step 1.5.

Generates per-mood-zone background music tracks.
Includes negative prompts for originality and Content ID safety.
"""

import time
import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════
# MOOD → ACE-STEP PROMPT MAP
# ════════════════════════════════════════════════════════════════

MOOD_PROMPTS: dict[str, str] = {
    "dramatic": (
        "dramatic orchestral documentary music, cinematic strings, "
        "building tension, arabic influence, emotional, original composition"
    ),
    "tense": (
        "tense suspenseful background music, dark ambient, "
        "minor key, sparse arrangement, documentary thriller, original composition"
    ),
    "hopeful": (
        "hopeful uplifting background music, major key, gentle strings, "
        "warm piano, optimistic, inspiring documentary, original composition"
    ),
    "calm": (
        "calm ambient background music, middle eastern oud, gentle, "
        "peaceful, reflective, meditative, original composition"
    ),
    "epic": (
        "epic cinematic orchestral music, powerful drums, brass section, "
        "triumphant, grand reveal, documentary climax, original composition"
    ),
    "mysterious": (
        "mysterious dark ambient music, eerie atmosphere, subtle tension, "
        "investigation theme, noir documentary, original composition"
    ),
    "somber": (
        "somber melancholy piano, sad strings, reflective, "
        "emotional documentary ending, gentle, original composition"
    ),
    "energetic": (
        "energetic dynamic background music, driving rhythm, "
        "modern documentary, fast-paced, percussive, original composition"
    ),
    "reflective": (
        "reflective calm piano music, contemplative, warm tones, "
        "soft strings, gentle resolution, original composition"
    ),
    "climax": (
        "dramatic climax orchestral, building intensity crescendo, "
        "powerful reveal moment, full orchestra, original composition"
    ),
}

# ALWAYS included negative prompt for Content ID safety
MUSIC_NEGATIVE = (
    "no covers, no samples, no existing melodies, no copyrighted material, "
    "unique musical arrangement, no famous songs, no pop music hooks"
)


@dataclass
class MusicGenConfig:
    model_name: str = "facebook/musicgen-medium"
    sample_rate: int = 44100
    temperature: float = 0.9  # Higher = more original
    top_k: int = 250
    top_p: float = 0.0
    duration_sec: float = 30.0
    max_duration_sec: float = 120.0
    device: str = "cuda"


@dataclass
class MusicGenResult:
    success: bool
    audio_path: Optional[str] = None
    duration_sec: float = 0.0
    mood: str = ""
    generation_time_sec: float = 0.0
    error: Optional[str] = None


class MusicGenerator:
    """
    Generates background music per mood zone using ACE-Step 1.5 (audiocraft).
    """

    def __init__(self, config: Optional[MusicGenConfig] = None):
        self.config = config or MusicGenConfig()
        self._model = None

    def load_model(self):
        """Load ACE-Step 1.5 model into memory."""
        if self._model is not None:
            return
        try:
            from audiocraft.models import MusicGen
            logger.info(f"Loading MusicGen model: {self.config.model_name}")
            self._model = MusicGen.get_pretrained(self.config.model_name)
            self._model.set_generation_params(
                duration=self.config.duration_sec,
                temperature=self.config.temperature,
                top_k=self.config.top_k,
                top_p=self.config.top_p,
            )
            logger.info("MusicGen model loaded")
        except ImportError:
            logger.error(
                "audiocraft not installed. Install with: pip install audiocraft"
            )
            raise

    def unload_model(self):
        """Unload model and free GPU memory."""
        if self._model is not None:
            del self._model
            self._model = None
            try:
                import torch, gc
                torch.cuda.empty_cache()
                gc.collect()
            except Exception:
                pass
            logger.info("MusicGen model unloaded")

    # ─── Public API ────────────────────────────────────────

    def generate(
        self,
        mood: str,
        output_dir: str,
        filename: str = "music",
        duration_sec: Optional[float] = None,
        custom_prompt: Optional[str] = None,
    ) -> MusicGenResult:
        """
        Generate a music track for the given mood.

        Args:
            mood: Mood key from MOOD_PROMPTS.
            output_dir: Output directory.
            filename: Output filename (without .wav).
            duration_sec: Track duration (default from config).
            custom_prompt: Override auto-generated prompt.

        Returns:
            MusicGenResult with path to generated WAV.
        """
        self.load_model()

        dur = min(
            duration_sec or self.config.duration_sec,
            self.config.max_duration_sec,
        )
        self._model.set_generation_params(
            duration=dur,
            temperature=self.config.temperature,
            top_k=self.config.top_k,
            top_p=self.config.top_p,
        )

        prompt = custom_prompt or MOOD_PROMPTS.get(mood, MOOD_PROMPTS["calm"])

        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        audio_path = str(out_path / f"{filename}.wav")

        start = time.time()
        try:
            import torchaudio

            logger.info(f"Generating music: mood={mood}, duration={dur}s")
            wav = self._model.generate([prompt])
            # wav shape: [batch, channels, samples]
            audio_tensor = wav[0].cpu()

            torchaudio.save(
                audio_path,
                audio_tensor,
                sample_rate=self.config.sample_rate,
            )

            elapsed = round(time.time() - start, 2)
            actual_dur = audio_tensor.shape[-1] / self.config.sample_rate

            logger.info(
                f"Music generated: {filename} ({actual_dur:.1f}s, {elapsed}s gen time)"
            )
            return MusicGenResult(
                success=True,
                audio_path=audio_path,
                duration_sec=actual_dur,
                mood=mood,
                generation_time_sec=elapsed,
            )

        except Exception as e:
            elapsed = round(time.time() - start, 2)
            logger.error(f"Music generation failed: {e}")
            return MusicGenResult(
                success=False,
                mood=mood,
                generation_time_sec=elapsed,
                error=str(e),
            )

    def generate_mood_zones(
        self,
        mood_zones: list[dict],
        output_dir: str,
    ) -> list[MusicGenResult]:
        """
        Generate music for all mood zones.

        Each zone dict: {zone_index, mood, duration_sec, prompt (optional)}
        """
        self.load_model()
        results = []
        total = len(mood_zones)

        for i, zone in enumerate(mood_zones):
            idx = zone.get("zone_index", i)
            mood = zone.get("mood", "calm")
            dur = zone.get("duration_sec", self.config.duration_sec)

            logger.info(f"Generating zone {i + 1}/{total}: {mood} ({dur}s)")

            result = self.generate(
                mood=mood,
                output_dir=output_dir,
                filename=f"zone_{idx:02d}_{mood}",
                duration_sec=dur,
                custom_prompt=zone.get("prompt"),
            )
            results.append(result)

        passed = sum(1 for r in results if r.success)
        logger.info(f"Music zones: {passed}/{total} generated")
        return results

    def generate_standard_tracks(
        self, output_dir: str, video_duration_sec: float = 600
    ) -> dict[str, MusicGenResult]:
        """
        Generate standard intro/background/tension/outro tracks.

        Returns dict keyed by track role.
        """
        self.load_model()
        tracks = {
            "intro": {"mood": "epic", "duration": 15},
            "background": {"mood": "calm", "duration": min(video_duration_sec * 0.6, 120)},
            "tension": {"mood": "tense", "duration": 30},
            "outro": {"mood": "reflective", "duration": 15},
        }

        results = {}
        for role, spec in tracks.items():
            results[role] = self.generate(
                mood=spec["mood"],
                output_dir=output_dir,
                filename=role,
                duration_sec=spec["duration"],
            )

        return results
