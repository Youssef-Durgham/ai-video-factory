"""
Phase 5 — Audio Coordinator: Voice + Music + SFX Sub-Pipeline.

Coordinates all audio generation in sequence (different GPU models).
Called at states: VOICE, MUSIC, SFX.
"""

import logging
import time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from src.models.analytics import PhaseResult
from .voice_gen import VoiceGenerator, VoiceGenConfig
from .voice_selector import VoiceSelector
from .music_gen import MusicGenerator, MusicGenConfig
from .sfx_gen import SFXGenerator, SFXGenConfig
from .content_id_guard import ContentIDGuard, ContentIDConfig

logger = logging.getLogger(__name__)


@dataclass
class AudioCoordinatorConfig:
    """Configuration for audio coordination."""
    output_base: str = "output"
    fish_audio_host: str = "http://localhost:8080"
    voice_model_path: str = "models/fish_audio_s2_pro"
    music_model: str = "facebook/musicgen-medium"
    voice_min_quality: float = 6.0
    max_voice_retries: int = 3
    content_id_enabled: bool = True
    music_regen_on_content_id: bool = True


class AudioCoordinator:
    """
    Manages the audio asset pipeline.

    Called at different states:
    - VOICE → generate narration for all scenes
    - MUSIC → generate background music tracks
    - SFX   → generate sound effects per scene

    Each step loads its own GPU model; ResourceCoordinator handles
    model swapping between steps.
    """

    def __init__(self, config=None, db=None):
        self.config = config or AudioCoordinatorConfig()
        self.db = db
        self.voice_gen = VoiceGenerator(VoiceGenConfig(
            fish_audio_host=self.config.fish_audio_host,
            model_path=self.config.voice_model_path,
            min_quality_score=self.config.voice_min_quality,
        ))
        self.voice_selector = VoiceSelector(db=db)
        self.music_gen = MusicGenerator(MusicGenConfig(
            model_name=self.config.music_model,
        ))
        self.sfx_gen = SFXGenerator(SFXGenConfig())
        self.content_id_guard = (
            ContentIDGuard(ContentIDConfig())
            if self.config.content_id_enabled else None
        )

    # ═══════════════════════════════════════════════════════
    # MAIN ENTRY POINT
    # ═══════════════════════════════════════════════════════

    def run(self, job_id: str) -> PhaseResult:
        """
        Route to the correct audio sub-step based on current job status.

        Args:
            job_id: The job identifier.

        Returns:
            PhaseResult indicating success/failure.
        """
        job = self.db.get_job(job_id)
        status = job.get("status", "")

        if status == "VOICE":
            return self._generate_voice(job_id)
        elif status == "MUSIC":
            return self._generate_music(job_id)
        elif status == "SFX":
            return self._generate_sfx(job_id)
        else:
            return PhaseResult(
                success=False,
                reason=f"AudioCoordinator called with unexpected status: {status}",
            )

    # ═══════════════════════════════════════════════════════
    # VOICE GENERATION
    # ═══════════════════════════════════════════════════════

    def _generate_voice(self, job_id: str) -> PhaseResult:
        """
        Generate narration audio for all scenes.

        Steps:
        1. Select voice via VoiceSelector (channel default > content match)
        2. Load voice embedding
        3. Generate per-scene narration with emotion tags
        4. Quality check each output
        5. Retry failures up to max_voice_retries
        """
        start = time.time()
        job = self.db.get_job(job_id)
        scenes = self.db.get_scenes(job_id)
        channel_id = job.get("channel_id", "")
        output_dir = str(Path(self.config.output_base) / job_id / "audio" / "voice")

        # Select voice
        channel = self.db.get_channel(channel_id) if channel_id else {}
        voice_id, embedding_path = self.voice_selector.select_voice(
            job=job, channel=channel or {},
        )
        logger.info(f"Selected voice: {voice_id}")

        # Load voice embedding
        if embedding_path:
            self.voice_gen.load_voice(voice_id, embedding_path)

        # Generate for each scene
        failed_scenes = []
        for i, scene in enumerate(scenes):
            idx = scene.get("scene_index", i)
            text = scene.get("narration_text", "")
            if not text.strip():
                continue

            emotion = scene.get("voice_emotion", "calm")
            success = False

            for attempt in range(self.config.max_voice_retries):
                result = self.voice_gen.generate(
                    text=text,
                    output_dir=output_dir,
                    filename=f"scene_{idx:03d}",
                    emotion=emotion,
                )

                if result.success:
                    self.db.update_scene_asset(
                        job_id, idx,
                        voice_path=result.audio_path,
                        voice_duration_sec=result.duration_sec,
                    )
                    success = True
                    break
                else:
                    logger.warning(
                        f"Voice gen attempt {attempt + 1} failed for scene {idx}: "
                        f"{result.error}"
                    )

            if not success:
                failed_scenes.append(idx)

        elapsed = round(time.time() - start, 2)
        total = sum(1 for s in scenes if s.get("narration_text", "").strip())
        passed = total - len(failed_scenes)

        logger.info(f"Voice generation complete: {passed}/{total} ({elapsed}s)")

        if failed_scenes:
            return PhaseResult(
                success=False,
                failed_scenes=failed_scenes,
                reason=f"{len(failed_scenes)} voice segments failed",
                score=passed / total * 10 if total > 0 else 0,
            )

        return PhaseResult(success=True, score=10.0)

    # ═══════════════════════════════════════════════════════
    # MUSIC GENERATION
    # ═══════════════════════════════════════════════════════

    def _generate_music(self, job_id: str) -> PhaseResult:
        """
        Generate background music tracks.

        Steps:
        1. Load MusicGen model
        2. Generate standard tracks (intro, background, tension, outro)
        3. Run Content ID guard on each track
        4. Regenerate flagged tracks with different seeds
        5. Unload model to free GPU
        """
        start = time.time()
        job = self.db.get_job(job_id)
        output_dir = str(Path(self.config.output_base) / job_id / "audio" / "music")

        # Calculate approximate video duration from scenes
        scenes = self.db.get_scenes(job_id)
        total_duration = sum(
            s.get("duration_seconds", s.get("duration_sec", 7.0))
            for s in scenes
        )

        try:
            # Generate standard music tracks
            track_results = self.music_gen.generate_standard_tracks(
                output_dir=output_dir,
                video_duration_sec=total_duration,
            )

            # Content ID check
            failed_tracks = []
            for role, result in track_results.items():
                if not result.success:
                    failed_tracks.append(role)
                    continue

                if self.content_id_guard and result.audio_path:
                    cid_result = self.content_id_guard.check(result.audio_path)
                    if not cid_result.safe:
                        logger.warning(
                            f"Content ID flag on {role} track: {cid_result.reason}"
                        )
                        if self.config.music_regen_on_content_id:
                            # Regenerate with different temperature
                            regen = self.music_gen.generate(
                                mood=result.mood or "calm",
                                output_dir=output_dir,
                                filename=f"{role}_regen",
                                duration_sec=result.duration_sec,
                            )
                            if regen.success:
                                track_results[role] = regen
                            else:
                                failed_tracks.append(role)
                        else:
                            failed_tracks.append(role)

                # Store in DB
                if result.success and result.audio_path:
                    self.db.update_job_audio(
                        job_id, track_role=role, audio_path=result.audio_path,
                    )

        finally:
            # Always unload to free GPU
            self.music_gen.unload_model()

        elapsed = round(time.time() - start, 2)
        logger.info(f"Music generation complete ({elapsed}s)")

        if failed_tracks:
            return PhaseResult(
                success=False,
                reason=f"Failed music tracks: {', '.join(failed_tracks)}",
                score=5.0,
            )

        return PhaseResult(success=True, score=10.0)

    # ═══════════════════════════════════════════════════════
    # SFX GENERATION
    # ═══════════════════════════════════════════════════════

    def _generate_sfx(self, job_id: str) -> PhaseResult:
        """
        Generate sound effects for scenes that have SFX tags.

        Steps:
        1. Load SFX model (MOSS-SoundEffect)
        2. Generate per-scene SFX from tags
        3. Fall back to pre-downloaded SFX library if generation fails
        4. Store paths in DB
        """
        start = time.time()
        scenes = self.db.get_scenes(job_id)
        output_dir = str(Path(self.config.output_base) / job_id / "audio" / "sfx")

        scenes_with_sfx = [
            s for s in scenes if s.get("sfx_tags") or s.get("sfx_description")
        ]

        if not scenes_with_sfx:
            logger.info("No scenes require SFX generation")
            return PhaseResult(success=True, reason="No SFX needed")

        failed_scenes = []
        for scene in scenes_with_sfx:
            idx = scene["scene_index"]
            sfx_tags = scene.get("sfx_tags", [])
            if isinstance(sfx_tags, str):
                import json
                try:
                    sfx_tags = json.loads(sfx_tags)
                except Exception:
                    sfx_tags = [sfx_tags]

            sfx_description = scene.get("sfx_description", "")

            # Generate each SFX for this scene
            scene_sfx_paths = []
            for j, tag in enumerate(sfx_tags):
                result = self.sfx_gen.generate(
                    description=tag if isinstance(tag, str) else sfx_description,
                    output_dir=output_dir,
                    filename=f"scene_{idx:03d}_sfx_{j:02d}",
                )

                if result.success and result.audio_path:
                    scene_sfx_paths.append(result.audio_path)
                else:
                    logger.warning(f"SFX gen failed for scene {idx} tag '{tag}'")

            if scene_sfx_paths:
                self.db.update_scene_asset(
                    job_id, idx, sfx_paths=scene_sfx_paths,
                )
            elif sfx_tags:
                failed_scenes.append(idx)

        elapsed = round(time.time() - start, 2)
        total = len(scenes_with_sfx)
        passed = total - len(failed_scenes)

        logger.info(f"SFX generation complete: {passed}/{total} ({elapsed}s)")

        # SFX failures are non-blocking (video can work without SFX)
        return PhaseResult(
            success=True,
            score=passed / total * 10 if total > 0 else 10.0,
            reason=f"{len(failed_scenes)} SFX scenes had partial failures" if failed_scenes else "",
        )
