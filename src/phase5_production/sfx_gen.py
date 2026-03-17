"""
Phase 5 — SFX Generation via MOSS-SoundEffect (audiocraft).

Generates sound effects from text descriptions per scene.
Falls back to a pre-downloaded SFX library.
"""

import time
import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════
# COMMON SFX PRESETS (for prompt enhancement)
# ════════════════════════════════════════════════════════════════

SFX_PRESETS: dict[str, str] = {
    "explosion": "distant explosion rumble, war documentary, realistic",
    "crowd": "large crowd murmuring, outdoor gathering, documentary ambience",
    "crowd_cheering": "crowd cheering and clapping, stadium, celebration",
    "gunshot": "single gunshot in distance, echo, realistic",
    "rain": "heavy rain on rooftop, thunder in distance, ambient",
    "wind": "strong desert wind, sand blowing, atmospheric",
    "footsteps": "footsteps on gravel, walking pace, realistic",
    "door": "heavy wooden door opening slowly, creak, interior",
    "car": "car engine starting and driving away, urban street",
    "siren": "distant police siren, urban, night atmosphere",
    "typing": "keyboard typing, office ambient, modern",
    "paper": "paper rustling, document handling, office",
    "radio_static": "radio static and tuning, vintage, crackling",
    "heartbeat": "heartbeat pounding, tense moment, close-up",
    "clock_ticking": "clock ticking slowly, tension building, quiet room",
    "water": "calm water flowing, river or stream, nature",
    "fire": "crackling fire, campfire or building, atmospheric",
    "thunder": "thunder rolling in distance, ominous, powerful",
    "birds": "birds chirping, morning, peaceful countryside",
    "helicopter": "helicopter flying overhead, military, documentary",
    "tank": "tank engine rumbling, military vehicle moving, ground shaking",
    "whoosh": "cinematic whoosh transition sound, fast movement",
    "impact": "heavy impact hit, dramatic, cinematic stinger",
    "riser": "tension riser sound, building suspense, cinematic",
    "drone_ambient": "dark ambient drone, ominous, documentary tension",
}


@dataclass
class SFXGenConfig:
    model_name: str = "facebook/audiogen-medium"
    sample_rate: int = 44100
    duration_sec: float = 5.0
    max_duration_sec: float = 15.0
    temperature: float = 1.0
    device: str = "cuda"
    fallback_library: str = "data/sfx_library"


@dataclass
class SFXGenResult:
    success: bool
    audio_path: Optional[str] = None
    duration_sec: float = 0.0
    tag: str = ""
    method: str = "generated"  # "generated" | "library"
    generation_time_sec: float = 0.0
    error: Optional[str] = None


class SFXGenerator:
    """
    Generates sound effects via MOSS-SoundEffect (audiocraft AudioGen).
    Falls back to pre-downloaded SFX library.
    """

    def __init__(self, config: Optional[SFXGenConfig] = None):
        self.config = config or SFXGenConfig()
        self._model = None

    def load_model(self):
        """Load AudioGen model."""
        if self._model is not None:
            return
        try:
            from audiocraft.models import AudioGen
            logger.info(f"Loading AudioGen: {self.config.model_name}")
            self._model = AudioGen.get_pretrained(self.config.model_name)
            self._model.set_generation_params(
                duration=self.config.duration_sec,
                temperature=self.config.temperature,
            )
            logger.info("AudioGen model loaded")
        except ImportError:
            logger.warning("audiocraft not installed — SFX will use library fallback only")

    def unload_model(self):
        """Unload model and free GPU."""
        if self._model is not None:
            del self._model
            self._model = None
            try:
                import torch, gc
                torch.cuda.empty_cache()
                gc.collect()
            except Exception:
                pass
            logger.info("AudioGen model unloaded")

    # ─── Public API ────────────────────────────────────────

    def generate(
        self,
        tag: str,
        output_dir: str,
        filename: str = "sfx",
        duration_sec: Optional[float] = None,
    ) -> SFXGenResult:
        """
        Generate a single SFX from a text tag.

        Tries AI generation first, falls back to library.
        """
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        audio_path = str(out_path / f"{filename}.wav")

        # Try library first for common sounds (faster, reliable)
        lib_result = self._try_library(tag, audio_path)
        if lib_result:
            return lib_result

        # AI generation
        return self._generate_ai(tag, audio_path, duration_sec)

    def generate_for_scenes(
        self,
        scenes: list[dict],
        output_dir: str,
    ) -> list[list[SFXGenResult]]:
        """
        Generate SFX for all scenes.

        Each scene dict needs: scene_index, sfx_tags (list of tag strings).
        Returns nested list: results[scene_idx][sfx_idx].
        """
        all_results = []
        # Collect all tags to batch
        has_ai_tags = False
        for scene in scenes:
            tags = scene.get("sfx_tags") or scene.get("sfx", [])
            if isinstance(tags, str):
                import json as _json
                try:
                    tags = _json.loads(tags)
                except Exception:
                    tags = [tags]
            for tag in tags:
                if not self._find_in_library(tag):
                    has_ai_tags = True
                    break

        if has_ai_tags:
            self.load_model()

        for scene in scenes:
            idx = scene.get("scene_index", 0)
            tags = scene.get("sfx_tags") or scene.get("sfx", [])
            if isinstance(tags, str):
                import json as _json
                try:
                    tags = _json.loads(tags)
                except Exception:
                    tags = [tags]

            scene_results = []
            for j, tag in enumerate(tags):
                if not tag or not tag.strip():
                    continue
                result = self.generate(
                    tag=tag,
                    output_dir=output_dir,
                    filename=f"scene_{idx:03d}_sfx_{j:02d}",
                )
                scene_results.append(result)

            all_results.append(scene_results)

        total = sum(len(sr) for sr in all_results)
        passed = sum(1 for sr in all_results for r in sr if r.success)
        logger.info(f"SFX batch: {passed}/{total} generated")
        return all_results

    # ─── AI Generation ─────────────────────────────────────

    def _generate_ai(
        self, tag: str, audio_path: str, duration_sec: Optional[float]
    ) -> SFXGenResult:
        """Generate SFX via AudioGen model."""
        if self._model is None:
            self.load_model()
            if self._model is None:
                return SFXGenResult(
                    success=False, tag=tag,
                    error="AudioGen model not available",
                )

        dur = min(
            duration_sec or self.config.duration_sec,
            self.config.max_duration_sec,
        )
        self._model.set_generation_params(
            duration=dur, temperature=self.config.temperature,
        )

        # Enhance prompt
        prompt = SFX_PRESETS.get(tag.lower().replace(" ", "_"), tag)

        start = time.time()
        try:
            import torchaudio
            wav = self._model.generate([prompt])
            audio_tensor = wav[0].cpu()
            torchaudio.save(audio_path, audio_tensor, sample_rate=self.config.sample_rate)

            elapsed = round(time.time() - start, 2)
            actual_dur = audio_tensor.shape[-1] / self.config.sample_rate

            logger.info(f"SFX generated: {tag} ({actual_dur:.1f}s)")
            return SFXGenResult(
                success=True,
                audio_path=audio_path,
                duration_sec=actual_dur,
                tag=tag,
                method="generated",
                generation_time_sec=elapsed,
            )

        except Exception as e:
            elapsed = round(time.time() - start, 2)
            logger.error(f"SFX generation failed for '{tag}': {e}")
            return SFXGenResult(
                success=False, tag=tag, method="generated",
                generation_time_sec=elapsed, error=str(e),
            )

    # ─── Library Fallback ──────────────────────────────────

    def _try_library(self, tag: str, dest_path: str) -> Optional[SFXGenResult]:
        """Try to find a matching SFX in the pre-downloaded library."""
        src = self._find_in_library(tag)
        if not src:
            return None

        import shutil
        shutil.copy2(src, dest_path)
        logger.info(f"SFX from library: {tag} → {Path(src).name}")

        return SFXGenResult(
            success=True,
            audio_path=dest_path,
            duration_sec=self._get_duration(dest_path),
            tag=tag,
            method="library",
        )

    def _find_in_library(self, tag: str) -> Optional[str]:
        """Search SFX library for a file matching the tag."""
        lib_dir = Path(self.config.fallback_library)
        if not lib_dir.exists():
            return None

        # Normalize tag for filename matching
        tag_norm = tag.lower().replace(" ", "_").replace("-", "_")
        for ext in ("wav", "mp3", "ogg", "flac"):
            candidates = list(lib_dir.glob(f"*{tag_norm}*.{ext}"))
            if candidates:
                return str(candidates[0])

        return None

    def _get_duration(self, path: str) -> float:
        try:
            import subprocess
            proc = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", path],
                capture_output=True, text=True, timeout=10,
            )
            return float(proc.stdout.strip())
        except Exception:
            return 0.0
