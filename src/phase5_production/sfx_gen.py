"""
Phase 5 — SFX Generation: AudioGen (AI, GPU) + local library + FFmpeg synthesis fallback.

Primary:   AudioGen (facebook/audiogen-medium) via audiocraft — loaded on GPU.
Fallback 1: Local SFX library from data/sfx_library/.
Fallback 2: FFmpeg-synthesized sound effects.

IMPORTANT:
  - Before loading AudioGen, ALL other GPU models must be unloaded (call clear_vram).
  - After generation, call unload_model() to free VRAM for the next model.
  - AudioGen medium uses ~4GB VRAM.
"""

import gc
import json
import logging
import random
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

import torch

from src.phase5_production.ffmpeg_path import FFMPEG

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
# FFmpeg SFX synthesis recipes (last-resort fallback)
# ════════════════════════════════════════════════════════════════

SFX_RECIPES = {
    "whoosh": {
        "source": "sine=f=200:d={dur}",
        "filter": "afreqshift=shift=800:level_out=0.5,afade=t=in:d=0.1,afade=t=out:st={fade_out}:d=0.3,volume=0.4",
    },
    "impact": {
        "source": "anoisesrc=d=0.5:c=white:a=0.8",
        "filter": "afade=t=out:st=0.05:d=0.4,lowpass=f=400,volume=0.6",
        "fixed_dur": 0.5,
    },
    "ocean_waves": {
        "source": "anoisesrc=d={dur}:c=brown:r=44100:a=0.15",
        "filter": "lowpass=f=500,tremolo=f=0.1:d=0.4,volume=0.3",
    },
    "wind": {
        "source": "anoisesrc=d={dur}:c=pink:r=44100:a=0.1",
        "filter": "bandpass=f=800:w=400,tremolo=f=0.3:d=0.3,volume=0.25",
    },
    "thunder": {
        "source": "anoisesrc=d=2:c=brown:a=0.6",
        "filter": "lowpass=f=150,afade=t=in:d=0.2,afade=t=out:st=0.5:d=1.5,volume=0.5",
        "fixed_dur": 2.0,
    },
    "heartbeat": {
        "source": "sine=f=40:d={dur}",
        "filter": "apulsator=hz=1.2:amount=0.9,volume=0.4",
    },
    "clock_tick": {
        "source": "sine=f=2000:d=0.05",
        "filter": "afade=t=out:st=0.01:d=0.04,volume=0.3",
        "fixed_dur": 0.05,
        "loop": True,
    },
    "explosion": {
        "source": "anoisesrc=d=3:c=brown:a=0.9",
        "filter": "lowpass=f=200,afade=t=in:d=0.01,afade=t=out:st=0.3:d=2.7,volume=0.6",
        "fixed_dur": 3.0,
    },
    "rain": {
        "source": "anoisesrc=d={dur}:c=pink:r=44100:a=0.08",
        "filter": "highpass=f=2000,lowpass=f=8000,volume=0.2",
    },
    "fire": {
        "source": "anoisesrc=d={dur}:c=white:r=44100:a=0.06",
        "filter": "bandpass=f=3000:w=2000,tremolo=f=8:d=0.3,volume=0.2",
    },
    "footsteps": {
        "source": "anoisesrc=d=0.1:c=brown:a=0.5",
        "filter": "highpass=f=200,afade=t=out:st=0.02:d=0.08,volume=0.3",
        "fixed_dur": 0.1,
        "loop": True,
        "loop_interval": 0.5,
    },
}

SFX_ALIASES = {
    "swoosh": "whoosh", "swish": "whoosh",
    "waves": "ocean_waves", "ocean": "ocean_waves", "sea": "ocean_waves",
    "boom": "explosion", "blast": "explosion",
    "storm": "thunder", "lightning": "thunder",
    "breeze": "wind", "gust": "wind",
    "pulse": "heartbeat", "heart": "heartbeat",
    "tick": "clock_tick", "clock": "clock_tick",
    "hit": "impact", "punch": "impact", "crash": "impact",
    "rainfall": "rain", "drizzle": "rain",
    "flame": "fire", "burning": "fire",
    "steps": "footsteps", "walking": "footsteps",
}


# ════════════════════════════════════════════════════════════════
# GPU Memory Management
# ════════════════════════════════════════════════════════════════

def clear_vram():
    """Aggressively clear GPU VRAM before loading a new model."""
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.ipc_collect()
        allocated = torch.cuda.memory_allocated() / (1024 ** 3)
        reserved = torch.cuda.memory_reserved() / (1024 ** 3)
        logger.info(f"VRAM after clear: {allocated:.2f}GB allocated, {reserved:.2f}GB reserved")


# ════════════════════════════════════════════════════════════════
# Data classes
# ════════════════════════════════════════════════════════════════

@dataclass
class SFXGenConfig:
    library_dir: str = "data/sfx_library"
    fallback_volume: float = 0.1
    model_name: str = "facebook/audiogen-medium"
    device: str = "cuda"
    max_duration_sec: float = 10.0  # AudioGen max is ~10s per generation


@dataclass
class SFXGenResult:
    success: bool
    audio_path: Optional[str] = None
    matched_tags: list = None
    method: str = ""  # "audiogen", "library", "synthesized", or "ambient"
    duration_sec: float = 0.0
    error: Optional[str] = None

    def __post_init__(self):
        if self.matched_tags is None:
            self.matched_tags = []


# ════════════════════════════════════════════════════════════════
# SFXGenerator
# ════════════════════════════════════════════════════════════════

class SFXGenerator:
    """Generates per-scene SFX using AudioGen (AI, GPU), library, or FFmpeg synthesis."""

    def __init__(self, config: Optional[SFXGenConfig] = None):
        self.config = config or SFXGenConfig()
        self._model = None
        self._model_loaded = False
        self._index = self._build_index()

    # ── Model lifecycle ────────────────────────────────────

    def load_model(self) -> bool:
        """Load AudioGen model onto GPU. Clears VRAM first."""
        if self._model_loaded and self._model is not None:
            logger.info("AudioGen model already loaded")
            return True

        logger.info("Clearing VRAM before loading AudioGen...")
        clear_vram()

        try:
            from audiocraft.models import AudioGen

            # AudioGen must be loaded directly on target device (no .to() method)
            device = self.config.device
            if device == "cuda" and not torch.cuda.is_available():
                device = "cpu"
                logger.warning("CUDA not available, falling back to CPU")

            logger.info(f"Loading AudioGen from {self.config.model_name} on {device}...")
            self._model = AudioGen.get_pretrained(self.config.model_name, device=device)

            # Set generation params
            self._model.set_generation_params(
                duration=self.config.max_duration_sec,
                use_sampling=True,
                top_k=250,
                top_p=0.0,
                temperature=1.0,
                cfg_coef=3.0,
            )

            self._model_loaded = True

            if torch.cuda.is_available():
                allocated = torch.cuda.memory_allocated() / (1024 ** 3)
                logger.info(f"AudioGen loaded on {device}. VRAM: {allocated:.2f}GB")

            return True

        except Exception as e:
            logger.error(f"Failed to load AudioGen: {e}", exc_info=True)
            self._model = None
            self._model_loaded = False
            return False

    def unload_model(self):
        """Unload AudioGen model and free GPU memory."""
        if self._model is not None:
            logger.info("Unloading AudioGen model...")
            # AudioGen stores sub-models — delete them explicitly
            for attr in ["lm", "compression_model"]:
                if hasattr(self._model, attr):
                    sub = getattr(self._model, attr)
                    if sub is not None:
                        del sub
            del self._model
            self._model = None
            self._model_loaded = False

        clear_vram()
        logger.info("AudioGen unloaded, VRAM freed")

    # ── Library index ──────────────────────────────────────

    def _build_index(self) -> dict[str, list[Path]]:
        """Build tag → file mapping from library directory structure."""
        lib = Path(self.config.library_dir)
        index = {}
        if not lib.exists():
            return index

        for f in lib.rglob("*"):
            if f.suffix.lower() not in (".mp3", ".wav", ".ogg"):
                continue
            keys = set()
            keys.add(f.stem.lower().replace("-", "_").replace(" ", "_"))
            if f.parent != lib:
                keys.add(f.parent.name.lower().replace("-", "_").replace(" ", "_"))
            for k in keys:
                index.setdefault(k, []).append(f)

        logger.info(f"SFX library indexed: {len(index)} categories, {sum(len(v) for v in index.values())} files")
        return index

    def _find_match(self, tags: list[str]) -> Optional[Path]:
        """Find best matching SFX file for given tags."""
        for tag in tags:
            normalized = tag.lower().strip().replace("-", "_").replace(" ", "_")
            if normalized in self._index:
                return random.choice(self._index[normalized])
            for key, files in self._index.items():
                if normalized in key or key in normalized:
                    return random.choice(files)
        return None

    def _resolve_recipe(self, tag: str) -> Optional[str]:
        """Resolve a tag to an FFmpeg recipe name."""
        normalized = tag.lower().strip().replace("-", "_").replace(" ", "_")
        if normalized in SFX_RECIPES:
            return normalized
        if normalized in SFX_ALIASES:
            return SFX_ALIASES[normalized]
        for key in SFX_RECIPES:
            if normalized in key or key in normalized:
                return key
        for alias, recipe in SFX_ALIASES.items():
            if normalized in alias or alias in normalized:
                return recipe
        return None

    # ── AudioGen generation (AI, GPU) ──────────────────────

    def _generate_audiogen(self, description: str, duration_sec: float, output_path: str) -> bool:
        """Generate SFX using AudioGen on GPU. Returns True on success."""
        if not self._model_loaded or self._model is None:
            return False

        try:
            import torchaudio

            # AudioGen max ~10s — for longer, generate and loop
            gen_duration = min(duration_sec, self.config.max_duration_sec)

            # Update generation duration
            self._model.set_generation_params(duration=gen_duration)

            logger.info(f"AudioGen generating: '{description}' ({gen_duration:.1f}s)")
            wav = self._model.generate([description])  # Shape: [1, 1, samples]

            # wav is [batch, channels, samples] tensor on GPU
            wav = wav.squeeze(0).cpu()  # → [1, samples]
            sample_rate = self._model.sample_rate

            # Save as wav first
            wav_path = output_path if output_path.endswith(".wav") else output_path + ".tmp.wav"
            torchaudio.save(wav_path, wav, sample_rate)

            # If output wants mp3 or we need to trim/loop to exact duration
            if not output_path.endswith(".wav") or abs(gen_duration - duration_sec) > 0.5:
                final_path = output_path
                fade_out_start = max(0, duration_sec - 1.0)
                af = f"afade=t=in:st=0:d=0.3,afade=t=out:st={fade_out_start}:d=1.0,volume=0.5"

                cmd_parts = [FFMPEG, "-y"]
                if duration_sec > gen_duration:
                    # Loop if needed
                    cmd_parts.extend(["-stream_loop", "-1"])
                cmd_parts.extend([
                    "-i", wav_path,
                    "-t", str(duration_sec),
                    "-af", af,
                    "-codec:a", "libmp3lame", "-qscale:a", "4",
                    final_path,
                ])
                proc = subprocess.run(cmd_parts, capture_output=True, text=True, timeout=60)

                # Clean up temp wav if different from output
                if wav_path != output_path:
                    Path(wav_path).unlink(missing_ok=True)

                if proc.returncode != 0:
                    logger.warning(f"FFmpeg post-process failed: {proc.stderr[:200]}")
                    return False
            else:
                # wav output, correct duration — already saved
                pass

            if Path(output_path).exists() and Path(output_path).stat().st_size > 100:
                logger.info(f"AudioGen generated: {output_path} ({duration_sec:.1f}s)")
                return True

            return False

        except Exception as e:
            logger.error(f"AudioGen generation failed: {e}", exc_info=True)
            return False

    # ── Main generate (per-scene) ──────────────────────────

    def generate(
        self,
        sfx_tags: list[str] = None,
        duration_sec: float = 6.0,
        output_path: str = "",
        description: str = "",
        output_dir: str = "",
        filename: str = "",
    ) -> SFXGenResult:
        """
        Generate SFX for a single scene.

        Supports two calling conventions:
        1. Pipeline style: sfx_tags=["wind", "rain"], duration_sec=6, output_path="scene_001.mp3"
        2. AudioCoordinator style: description="wind blowing", output_dir="path/", filename="scene_001_sfx_00"
        """
        # Resolve parameters from either convention
        if not output_path and output_dir and filename:
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            output_path = str(Path(output_dir) / f"{filename}.mp3")

        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        tags = sfx_tags or []
        if description and not tags:
            tags = [description]

        # Build a combined text description for AudioGen
        ai_description = description or " ".join(tags) if tags else ""

        # ── 1. Try AudioGen (AI) ──
        if ai_description and (self._model_loaded or self.load_model()):
            if self._generate_audiogen(ai_description, duration_sec, output_path):
                return SFXGenResult(
                    success=True, audio_path=output_path,
                    matched_tags=tags, method="audiogen",
                    duration_sec=duration_sec,
                )

        # ── 2. Try library ──
        if tags:
            match = self._find_match(tags)
            if match:
                return self._trim_to_duration(match, output_path, duration_sec, tags)

        # ── 3. Try FFmpeg synthesis ──
        if tags:
            for tag in tags:
                recipe_name = self._resolve_recipe(tag)
                if recipe_name:
                    result = self._synthesize_sfx(recipe_name, output_path, duration_sec, tags)
                    if result.success:
                        return result

        # ── 4. Fallback: subtle ambient ──
        return self._generate_ambient(output_path, duration_sec)

    def generate_batch(
        self,
        scenes: list[dict],
        output_dir: str,
    ) -> list[SFXGenResult]:
        """
        Generate SFX for all scenes. Loads AudioGen once, generates all, then unloads.
        """
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        results = []

        # Pre-load the model for the batch
        has_ai_scenes = any(
            s.get("sfx_tags") or s.get("sfx_description")
            for s in scenes
        )
        if has_ai_scenes:
            self.load_model()

        for i, scene in enumerate(scenes):
            idx = scene.get("scene_index", i)
            tags_raw = scene.get("sfx_tags")
            tags = []
            if tags_raw:
                if isinstance(tags_raw, str):
                    try:
                        tags = json.loads(tags_raw)
                    except (json.JSONDecodeError, TypeError):
                        tags = [tags_raw]
                elif isinstance(tags_raw, list):
                    tags = tags_raw

            duration = scene.get("duration_sec", 6.0) or 6.0
            description = scene.get("sfx_description", "")

            # Build rich description for AudioGen
            if tags and not description:
                description = ", ".join(tags)

            out_path = str(Path(output_dir) / f"scene_{idx:03d}.mp3")

            result = self.generate(
                sfx_tags=tags,
                duration_sec=float(duration),
                output_path=out_path,
                description=description,
            )
            results.append(result)
            logger.info(f"SFX scene {idx}: {result.method} ({result.matched_tags})")

        return results

    # ── Library/FFmpeg helpers ─────────────────────────────

    def _trim_to_duration(self, source: Path, output_path: str, duration: float, tags: list) -> SFXGenResult:
        """Trim/loop a library file to exact duration."""
        cmd = [
            FFMPEG, "-y", "-stream_loop", "-1",
            "-i", str(source),
            "-t", str(duration),
            "-af", f"afade=t=in:st=0:d=0.5,afade=t=out:st={max(0, duration - 1)}:d=1,volume=0.4",
            "-codec:a", "libmp3lame", "-qscale:a", "4",
            output_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            return SFXGenResult(success=False, error=f"FFmpeg trim failed: {proc.stderr[:200]}")

        return SFXGenResult(
            success=True, audio_path=output_path,
            matched_tags=tags, method="library",
            duration_sec=duration,
        )

    def _synthesize_sfx(self, recipe_name: str, output_path: str, duration: float, tags: list) -> SFXGenResult:
        """Synthesize SFX using FFmpeg lavfi based on recipe."""
        recipe = SFX_RECIPES[recipe_name]
        fixed_dur = recipe.get("fixed_dur")
        should_loop = recipe.get("loop", False)

        actual_dur = fixed_dur if fixed_dur and not should_loop else duration
        source = recipe["source"].format(dur=actual_dur)
        fade_out = max(0, actual_dur - 0.3)
        af = recipe["filter"].format(dur=actual_dur, fade_out=fade_out)

        if should_loop and fixed_dur:
            single_path = output_path + ".single.wav"
            cmd = [
                FFMPEG, "-y",
                "-f", "lavfi", "-i", source,
                "-t", str(fixed_dur),
                "-af", af,
                single_path,
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if proc.returncode != 0:
                return SFXGenResult(success=False, error=f"SFX synth failed: {proc.stderr[:200]}")

            cmd2 = [
                FFMPEG, "-y", "-stream_loop", "-1",
                "-i", single_path,
                "-t", str(duration),
                "-af", f"afade=t=out:st={max(0, duration - 1)}:d=1,volume=0.3",
                "-codec:a", "libmp3lame", "-qscale:a", "4",
                output_path,
            ]
            proc2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=30)
            Path(single_path).unlink(missing_ok=True)
            if proc2.returncode != 0:
                return SFXGenResult(success=False, error=f"SFX loop failed: {proc2.stderr[:200]}")
        else:
            cmd = [
                FFMPEG, "-y",
                "-f", "lavfi", "-i", source,
                "-t", str(duration if not fixed_dur else min(fixed_dur, duration)),
                "-af", af,
                "-codec:a", "libmp3lame", "-qscale:a", "4",
                output_path,
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if proc.returncode != 0:
                return SFXGenResult(success=False, error=f"SFX synth failed: {proc.stderr[:200]}")

        logger.info(f"Synthesized SFX '{recipe_name}' for {duration:.1f}s")
        return SFXGenResult(
            success=True, audio_path=output_path,
            matched_tags=tags, method="synthesized",
            duration_sec=duration,
        )

    def _generate_ambient(self, output_path: str, duration: float) -> SFXGenResult:
        """Generate subtle ambient noise as SFX fallback."""
        cmd = [
            FFMPEG, "-y",
            "-f", "lavfi", "-i", f"anoisesrc=d={int(duration) + 1}:c=brown:r=44100:a=0.005",
            "-t", str(duration),
            "-af", f"lowpass=f=300,volume={self.config.fallback_volume}",
            "-codec:a", "libmp3lame", "-qscale:a", "6",
            output_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode != 0:
            return SFXGenResult(success=False, error=f"Ambient gen failed: {proc.stderr[:200]}")

        return SFXGenResult(
            success=True, audio_path=output_path,
            method="ambient", duration_sec=duration,
        )
