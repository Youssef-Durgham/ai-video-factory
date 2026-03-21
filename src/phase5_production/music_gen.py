"""
Phase 5 — Music Generation: ACE-Step 1.5 (direct Python, GPU) + library + FFmpeg fallback.

Primary:   ACE-Step 1.5 pipeline loaded directly on GPU (RTX 3090).
Fallback 1: Local library from data/ambient_library/.
Fallback 2: FFmpeg ambient noise generation.

IMPORTANT:
  - Before loading the model, ALL other GPU models must be unloaded.
  - After generation, call unload_model() to free VRAM for the next model.
  - ACE-Step 1.5 uses ~8-10GB VRAM in bf16.
"""

import gc
import json
import logging
import random
import subprocess
import sys
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

import torch

from src.phase5_production.ffmpeg_path import FFMPEG

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════
# Constants
# ════════════════════════════════════════════════════════════════

ACE_STEP_DIR = Path(r"C:\Users\3d\clawd\ACE-Step")
ACE_STEP_CHECKPOINT = str(ACE_STEP_DIR / "models" / "ACE-Step-v1-3.5B")

MOOD_KEYWORDS = {
    "dramatic": ["dramatic", "intense", "powerful", "conflict", "war", "battle", "crisis"],
    "calm": ["calm", "peaceful", "serene", "gentle", "quiet", "meditation", "nature"],
    "mysterious": ["mysterious", "unknown", "secret", "hidden", "enigma", "puzzle", "dark"],
    "tense": ["tense", "suspense", "danger", "threat", "anxiety", "fear", "thriller"],
    "hopeful": ["hopeful", "optimistic", "inspiring", "future", "dream", "light", "sunrise"],
    "epic": ["epic", "grand", "majestic", "triumph", "victory", "hero", "legendary"],
    "sad": ["sad", "melancholy", "loss", "grief", "tragic", "farewell", "tears"],
    "neutral": ["documentary", "informative", "educational", "analysis", "science"],
}

MOOD_PROMPTS = {
    "dramatic": "dramatic orchestral documentary background, minor key, building tension, cinematic, instrumental, background music, original composition, no covers, no samples, no existing melodies, no copyrighted material, unique musical arrangement",
    "calm": "calm peaceful ambient documentary, soft piano, gentle strings, serene, instrumental, background music, original composition, no covers, no samples, no existing melodies, no copyrighted material, unique musical arrangement",
    "mysterious": "mysterious dark ambient documentary, eerie pads, sparse percussion, enigmatic, instrumental, background music, original composition, no covers, no samples, no existing melodies, no copyrighted material, unique musical arrangement",
    "tense": "tense suspenseful documentary background, staccato strings, low drone, anxiety, instrumental, background music, original composition, no covers, no samples, no existing melodies, no copyrighted material, unique musical arrangement",
    "hopeful": "hopeful uplifting documentary music, major key, warm strings, inspiring, instrumental, background music, original composition, no covers, no samples, no existing melodies, no copyrighted material, unique musical arrangement",
    "epic": "epic grand orchestral documentary, full orchestra, triumphant brass, majestic, instrumental, background music, original composition, no covers, no samples, no existing melodies, no copyrighted material, unique musical arrangement",
    "sad": "sad melancholic documentary background, minor key, solo piano, emotional, instrumental, background music, original composition, no covers, no samples, no existing melodies, no copyrighted material, unique musical arrangement",
    "neutral": "neutral informative documentary background, light ambient, subtle, unobtrusive, instrumental, background music, original composition, no covers, no samples, no existing melodies, no copyrighted material, unique musical arrangement",
}

# Standard track roles with mood hints and durations
STANDARD_TRACKS = {
    "intro": {"mood": "epic", "duration_sec": 15.0, "desc": "intro music, epic dramatic"},
    "background": {"mood": "neutral", "duration_sec": 180.0, "desc": "main background, matches content mood"},
    "tension": {"mood": "tense", "duration_sec": 30.0, "desc": "tension climax dramatic"},
    "outro": {"mood": "calm", "duration_sec": 15.0, "desc": "outro calm reflective"},
}

# FFmpeg ambient presets per mood (last-resort fallback)
AMBIENT_PRESETS = {
    "dramatic": 'anoisesrc=d={dur}:c=brown:r=44100:a=0.03',
    "calm": 'anoisesrc=d={dur}:c=brown:r=44100:a=0.01',
    "mysterious": 'anoisesrc=d={dur}:c=violet:r=44100:a=0.02',
    "tense": 'anoisesrc=d={dur}:c=brown:r=44100:a=0.025',
    "hopeful": 'anoisesrc=d={dur}:c=pink:r=44100:a=0.015',
    "epic": 'anoisesrc=d={dur}:c=brown:r=44100:a=0.04',
    "sad": 'anoisesrc=d={dur}:c=brown:r=44100:a=0.015',
    "neutral": 'anoisesrc=d={dur}:c=brown:r=44100:a=0.02',
}


# ════════════════════════════════════════════════════════════════
# Data classes
# ════════════════════════════════════════════════════════════════

@dataclass
class MusicGenConfig:
    library_dir: str = "data/ambient_library"
    fade_in_sec: float = 2.0
    fade_out_sec: float = 3.0
    ace_step_dir: Path = ACE_STEP_DIR
    ace_step_checkpoint: str = ACE_STEP_CHECKPOINT
    infer_step: int = 100          # Lower = faster, 60-150 range. 100 is good quality/speed.
    guidance_scale: float = 15.0
    device_id: int = 0
    bf16: bool = True
    model_name: str = "ace-step-1.5"  # For compatibility with AudioCoordinator


@dataclass
class MusicGenResult:
    success: bool
    audio_path: Optional[str] = None
    mood: str = ""
    method: str = ""  # "ace_step", "library", or "generated"
    duration_sec: float = 0.0
    zone_paths: list = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class MoodZone:
    """A group of consecutive scenes sharing a mood."""
    mood: str
    start_sec: float
    duration_sec: float
    scene_indices: list = field(default_factory=list)


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
# MusicGenerator
# ════════════════════════════════════════════════════════════════

class MusicGenerator:
    """Generates background music for documentary videos using ACE-Step 1.5 (direct Python, GPU)."""

    def __init__(self, config: Optional[MusicGenConfig] = None):
        self.config = config or MusicGenConfig()
        self._pipeline = None
        self._model_loaded = False

    # ── Model lifecycle ────────────────────────────────────

    def load_model(self):
        """Load ACE-Step 1.5 pipeline onto GPU. Clears VRAM first."""
        if self._model_loaded and self._pipeline is not None:
            logger.info("ACE-Step model already loaded")
            return True

        logger.info("Clearing VRAM before loading ACE-Step 1.5...")
        clear_vram()

        # Ensure ACE-Step is importable
        ace_step_dir = str(self.config.ace_step_dir)
        if ace_step_dir not in sys.path:
            sys.path.insert(0, ace_step_dir)

        try:
            from acestep.pipeline_ace_step import ACEStepPipeline

            logger.info(f"Loading ACE-Step 1.5 from {self.config.ace_step_checkpoint}...")
            self._pipeline = ACEStepPipeline(
                checkpoint_dir=self.config.ace_step_checkpoint,
                device_id=self.config.device_id,
                dtype="bfloat16" if self.config.bf16 else "float32",
                torch_compile=False,
                cpu_offload=False,
            )
            # Trigger actual weight loading
            self._pipeline.load_checkpoint(self.config.ace_step_checkpoint)
            self._model_loaded = True

            if torch.cuda.is_available():
                allocated = torch.cuda.memory_allocated() / (1024 ** 3)
                logger.info(f"ACE-Step 1.5 loaded. VRAM: {allocated:.2f}GB")

            return True

        except Exception as e:
            logger.error(f"Failed to load ACE-Step 1.5: {e}", exc_info=True)
            self._pipeline = None
            self._model_loaded = False
            return False

    def unload_model(self):
        """Unload ACE-Step model and free GPU memory."""
        if self._pipeline is not None:
            logger.info("Unloading ACE-Step 1.5 model...")
            # Delete all model components
            for attr in ["ace_step_transformer", "music_dcae", "text_encoder_model",
                         "tokenizer", "lyric_tokenizer", "vocoder"]:
                if hasattr(self._pipeline, attr):
                    obj = getattr(self._pipeline, attr)
                    if obj is not None:
                        del obj
                        setattr(self._pipeline, attr, None)

            del self._pipeline
            self._pipeline = None
            self._model_loaded = False

        clear_vram()
        logger.info("ACE-Step 1.5 unloaded, VRAM freed")

    # ── Mood detection ─────────────────────────────────────

    def detect_mood(self, scenes: list[dict]) -> str:
        """Detect overall mood from scene data."""
        text_blob = ""
        for s in scenes:
            text_blob += " " + (s.get("narration_text", "") or "")
            text_blob += " " + (s.get("music_mood", "") or "")
            sfx = s.get("sfx_tags")
            if sfx:
                if isinstance(sfx, str):
                    try:
                        sfx = json.loads(sfx)
                    except (json.JSONDecodeError, TypeError):
                        sfx = [sfx]
                if isinstance(sfx, list):
                    text_blob += " " + " ".join(str(t) for t in sfx)

        text_lower = text_blob.lower()
        scores = {}
        for mood, keywords in MOOD_KEYWORDS.items():
            scores[mood] = sum(1 for kw in keywords if kw in text_lower)

        for s in scenes:
            mm = (s.get("music_mood") or "").lower()
            if mm in scores:
                scores[mm] += 3

        best = max(scores, key=scores.get)
        if scores[best] == 0:
            return "neutral"
        return best

    def _detect_scene_mood(self, scene: dict) -> str:
        """Detect mood for a single scene."""
        mm = (scene.get("music_mood") or "").lower().strip()
        if mm and mm in MOOD_PROMPTS:
            return mm
        return self.detect_mood([scene])

    # ── Mood zones ─────────────────────────────────────────

    def _build_mood_zones(self, scenes: list[dict]) -> list[MoodZone]:
        """Group consecutive scenes by mood into zones."""
        if not scenes:
            return []

        zones = []
        current_offset = 0.0

        for i, scene in enumerate(scenes):
            mood = self._detect_scene_mood(scene)
            dur = float(scene.get("duration_sec", 6) or 6)
            idx = scene.get("scene_index", i)

            if zones and zones[-1].mood == mood:
                zones[-1].duration_sec += dur
                zones[-1].scene_indices.append(idx)
            else:
                zones.append(MoodZone(
                    mood=mood,
                    start_sec=current_offset,
                    duration_sec=dur,
                    scene_indices=[idx],
                ))
            current_offset += dur

        return zones

    # ── ACE-Step generation (direct Python, GPU) ───────────

    def _generate_ace_step(self, prompt: str, duration: float, output_path: str) -> bool:
        """Generate music using ACE-Step pipeline directly on GPU. Returns True on success."""
        if not self._model_loaded or self._pipeline is None:
            logger.warning("ACE-Step model not loaded")
            return False

        try:
            logger.info(f"Generating music: {duration:.0f}s — prompt: {prompt[:80]}...")
            result = self._pipeline(
                audio_duration=duration,
                prompt=prompt,
                lyrics="",
                infer_step=self.config.infer_step,
                guidance_scale=self.config.guidance_scale,
                scheduler_type="euler",
                cfg_type="apg",
                omega_scale=10.0,
                manual_seeds=[random.randint(0, 999999)],
                guidance_interval=0.5,
                guidance_interval_decay=1.0,
                min_guidance_scale=3.0,
                use_erg_tag=True,
                use_erg_lyric=False,
                use_erg_diffusion=True,
                oss_steps="",
                guidance_scale_text=0.0,
                guidance_scale_lyric=0.0,
                save_path=output_path,
            )

            # Result is a list: [audio_path, ..., params_json_dict]
            if result and isinstance(result, list):
                # Check if any output audio file exists
                for item in result:
                    if isinstance(item, str) and Path(item).exists() and Path(item).suffix in (".wav", ".mp3"):
                        # If output differs from requested path, copy
                        if str(Path(item).resolve()) != str(Path(output_path).resolve()):
                            import shutil
                            shutil.copy2(item, output_path)
                        logger.info(f"ACE-Step generated: {output_path} ({duration:.0f}s)")
                        return True

            # Fallback: check if output_path was created directly
            if Path(output_path).exists() and Path(output_path).stat().st_size > 1000:
                logger.info(f"ACE-Step generated: {output_path} ({duration:.0f}s)")
                return True

            logger.warning("ACE-Step generation returned no valid audio file")
            return False

        except Exception as e:
            logger.error(f"ACE-Step generation failed: {e}", exc_info=True)
            return False

    # ── Standard tracks (interface for AudioCoordinator) ───

    def generate_standard_tracks(
        self,
        output_dir: str,
        video_duration_sec: float,
    ) -> dict[str, MusicGenResult]:
        """
        Generate standard documentary music tracks: intro, background, tension, outro.
        Called by AudioCoordinator._generate_music().

        Loads ACE-Step once, generates all tracks, then caller should call unload_model().
        """
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        results = {}

        # Try to load model
        model_available = self.load_model()

        for role, spec in STANDARD_TRACKS.items():
            duration = spec["duration_sec"]
            # Background track matches actual video duration
            if role == "background":
                duration = max(duration, video_duration_sec)

            mood = spec["mood"]
            output_path = str(Path(output_dir) / f"{role}.wav")

            if model_available:
                prompt = MOOD_PROMPTS.get(mood, MOOD_PROMPTS["neutral"])
                if self._generate_ace_step(prompt, duration, output_path):
                    # Convert to mp3 with fade
                    mp3_path = str(Path(output_dir) / f"{role}.mp3")
                    if self._convert_with_fade(output_path, mp3_path, duration):
                        results[role] = MusicGenResult(
                            success=True, audio_path=mp3_path,
                            mood=mood, method="ace_step",
                            duration_sec=duration,
                        )
                        continue

            # Fallback: library
            mp3_path = str(Path(output_dir) / f"{role}.mp3")
            lib_result = self._from_library(mood, mp3_path, duration)
            if lib_result.success:
                results[role] = lib_result
                continue

            # Last resort: FFmpeg ambient
            results[role] = self._generate_ambient(mood, mp3_path, duration)

        return results

    # ── Zone-based generation ──────────────────────────────

    def generate(
        self,
        scenes: list[dict] = None,
        output_dir: str = "",
        duration_sec: float = 60.0,
        mood_override: Optional[str] = None,
        mood: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> MusicGenResult:
        """
        Generate background music. Can be called standalone or by AudioCoordinator for regen.

        Args:
            scenes: Scene data for mood detection (optional)
            output_dir: Output directory
            duration_sec: Total duration
            mood_override: Force a specific mood
            mood: Alias for mood_override (for AudioCoordinator compat)
            filename: Output filename without extension (optional)
        """
        scenes = scenes or []
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        effective_mood = mood_override or mood or self.detect_mood(scenes) if scenes else (mood_override or mood or "neutral")
        out_name = filename or "background"
        output_mp3 = str(Path(output_dir) / f"{out_name}.mp3")

        logger.info(f"Music mood: {effective_mood}")

        # Try ACE-Step
        model_available = self._model_loaded or self.load_model()
        if model_available:
            if scenes:
                zones = self._build_mood_zones(scenes)
                if zones:
                    result = self._generate_zones(zones, output_dir, output_mp3, duration_sec)
                    if result.success:
                        return result

            # Single track
            prompt = MOOD_PROMPTS.get(effective_mood, MOOD_PROMPTS["neutral"])
            ace_out = str(Path(output_dir) / f"{out_name}_raw.wav")
            if self._generate_ace_step(prompt, duration_sec, ace_out):
                if self._convert_with_fade(ace_out, output_mp3, duration_sec):
                    return MusicGenResult(
                        success=True, audio_path=output_mp3,
                        mood=effective_mood, method="ace_step",
                        duration_sec=duration_sec,
                    )

        # Fallback: library
        result = self._from_library(effective_mood, output_mp3, duration_sec)
        if result.success:
            return result

        # Last resort: ffmpeg ambient
        return self._generate_ambient(effective_mood, output_mp3, duration_sec)

    def _generate_zones(
        self, zones: list[MoodZone], output_dir: str, final_path: str, total_dur: float
    ) -> MusicGenResult:
        """Generate per-zone music and concatenate with crossfade."""
        zone_paths = []

        for i, zone in enumerate(zones):
            gen_dur = zone.duration_sec + 2.0  # Padding for crossfade
            prompt = MOOD_PROMPTS.get(zone.mood, MOOD_PROMPTS["neutral"])
            zone_path = str(Path(output_dir) / f"zone_{i:02d}_{zone.mood}.wav")

            if not self._generate_ace_step(prompt, gen_dur, zone_path):
                logger.warning(f"Failed to generate zone {i} ({zone.mood})")
                return MusicGenResult(success=False, error=f"Zone {i} generation failed")

            zone_paths.append(zone_path)

        if not zone_paths:
            return MusicGenResult(success=False, error="No zones generated")

        if len(zone_paths) == 1:
            if self._convert_with_fade(zone_paths[0], final_path, total_dur):
                return MusicGenResult(
                    success=True, audio_path=final_path,
                    mood=zones[0].mood, method="ace_step",
                    duration_sec=total_dur, zone_paths=zone_paths,
                )
            return MusicGenResult(success=False, error="Conversion failed")

        if self._concat_with_crossfade(zone_paths, final_path, total_dur):
            return MusicGenResult(
                success=True, audio_path=final_path,
                mood="mixed", method="ace_step",
                duration_sec=total_dur, zone_paths=zone_paths,
            )

        return MusicGenResult(success=False, error="Crossfade concat failed")

    # ── FFmpeg helpers ─────────────────────────────────────

    def _convert_with_fade(self, input_path: str, output_path: str, duration: float) -> bool:
        """Convert wav to mp3 with fade in/out."""
        fade_in = self.config.fade_in_sec
        fade_out = self.config.fade_out_sec
        af = f"afade=t=in:st=0:d={fade_in},afade=t=out:st={max(0, duration - fade_out)}:d={fade_out}"

        cmd = [
            FFMPEG, "-y", "-i", input_path,
            "-t", str(duration),
            "-af", af,
            "-codec:a", "libmp3lame", "-qscale:a", "2",
            output_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return proc.returncode == 0

    def _concat_with_crossfade(self, paths: list[str], output_path: str, total_dur: float) -> bool:
        """Concatenate audio files with 1s crossfade between them."""
        if len(paths) < 2:
            return False

        inputs = []
        for p in paths:
            inputs.extend(["-i", p])

        cf_dur = 1.0
        if len(paths) == 2:
            filter_str = f"[0:a][1:a]acrossfade=d={cf_dur}:c1=tri:c2=tri[out]"
        else:
            filter_parts = [f"[0:a][1:a]acrossfade=d={cf_dur}:c1=tri:c2=tri[cf1]"]
            for i in range(2, len(paths)):
                prev = f"[cf{i-1}]"
                curr = f"[{i}:a]"
                out = "[out]" if i == len(paths) - 1 else f"[cf{i}]"
                filter_parts.append(f"{prev}{curr}acrossfade=d={cf_dur}:c1=tri:c2=tri{out}")
            filter_str = ";".join(filter_parts)

        fade_out = self.config.fade_out_sec
        fade_in = self.config.fade_in_sec
        filter_str += f";[out]afade=t=in:st=0:d={fade_in},afade=t=out:st={max(0, total_dur - fade_out)}:d={fade_out}[final]"

        cmd = [
            FFMPEG, "-y", *inputs,
            "-filter_complex", filter_str,
            "-map", "[final]",
            "-t", str(total_dur),
            "-codec:a", "libmp3lame", "-qscale:a", "2",
            output_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            logger.warning(f"Crossfade concat failed: {proc.stderr[:300]}")
            return self._simple_concat(paths, output_path, total_dur)
        return True

    def _simple_concat(self, paths: list[str], output_path: str, total_dur: float) -> bool:
        """Simple concat fallback without crossfade."""
        list_file = str(Path(output_path).parent / "concat_list.txt")
        with open(list_file, "w") as f:
            for p in paths:
                f.write(f"file '{p}'\n")

        fade_out = self.config.fade_out_sec
        af = f"afade=t=in:st=0:d={self.config.fade_in_sec},afade=t=out:st={max(0, total_dur - fade_out)}:d={fade_out}"

        cmd = [
            FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", list_file,
            "-t", str(total_dur), "-af", af,
            "-codec:a", "libmp3lame", "-qscale:a", "2",
            output_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return proc.returncode == 0

    # ── Library fallback ───────────────────────────────────

    def _from_library(self, mood: str, output_path: str, duration_sec: float) -> MusicGenResult:
        """Select and trim a track from the local library."""
        lib_dir = Path(self.config.library_dir)
        if not lib_dir.exists():
            return MusicGenResult(success=False, error="Library dir not found")

        candidates = []
        mood_dir = lib_dir / mood
        if mood_dir.exists():
            candidates = list(mood_dir.glob("*.mp3")) + list(mood_dir.glob("*.wav"))
        if not candidates:
            for ext in ("*.mp3", "*.wav", "*.ogg"):
                candidates.extend(lib_dir.glob(ext))

        if not candidates:
            return MusicGenResult(success=False, error="No tracks in library")

        track = random.choice(candidates)
        logger.info(f"Selected library track: {track.name}")

        fade_in = self.config.fade_in_sec
        fade_out = self.config.fade_out_sec
        af = f"afade=t=in:st=0:d={fade_in},afade=t=out:st={max(0, duration_sec - fade_out)}:d={fade_out}"

        cmd = [
            FFMPEG, "-y", "-stream_loop", "-1",
            "-i", str(track),
            "-t", str(duration_sec),
            "-af", af,
            "-codec:a", "libmp3lame", "-qscale:a", "2",
            output_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            return MusicGenResult(success=False, error=f"FFmpeg trim failed: {proc.stderr[:200]}")

        return MusicGenResult(
            success=True, audio_path=output_path,
            mood=mood, method="library",
            duration_sec=duration_sec,
        )

    # ── FFmpeg ambient fallback ────────────────────────────

    def _generate_ambient(self, mood: str, output_path: str, duration_sec: float) -> MusicGenResult:
        """Generate simple ambient noise via FFmpeg (last resort)."""
        preset = AMBIENT_PRESETS.get(mood, AMBIENT_PRESETS["neutral"])
        src = preset.format(dur=int(duration_sec) + 1)

        fade_out = self.config.fade_out_sec
        af = f"lowpass=f=200,volume=0.3,afade=t=in:st=0:d=2,afade=t=out:st={max(0, duration_sec - fade_out)}:d={fade_out}"

        cmd = [
            FFMPEG, "-y",
            "-f", "lavfi", "-i", src,
            "-t", str(duration_sec),
            "-af", af,
            "-codec:a", "libmp3lame", "-qscale:a", "4",
            output_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            return MusicGenResult(success=False, error=f"Ambient gen failed: {proc.stderr[:200]}")

        logger.info(f"Generated ambient music: {mood}, {duration_sec}s")
        return MusicGenResult(
            success=True, audio_path=output_path,
            mood=mood, method="generated",
            duration_sec=duration_sec,
        )
