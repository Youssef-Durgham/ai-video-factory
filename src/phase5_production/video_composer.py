"""
Phase 5 — Video Composer Coordinator.

Wraps the existing composer.py (FFmpeg assembly) with the
PhaseResult-based coordinator interface expected by PhaseExecutor.

Called at state: COMPOSE.
"""

import logging
import time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from src.models.analytics import PhaseResult
from .composer import VideoComposer as FFmpegComposer, ComposerConfig, ComposerResult
from .font_selector import FontSelector

logger = logging.getLogger(__name__)


@dataclass
class VideoComposerCoordinatorConfig:
    """Configuration for the video composer coordinator."""
    output_base: str = "output"
    brands_dir: str = "config/brands"
    ffmpeg: str = "ffmpeg"
    fps: int = 24
    width: int = 1920
    height: int = 1080
    video_codec: str = "libx264"
    video_crf: int = 18
    audio_bitrate: str = "320k"
    target_lufs: float = -14.0


class VideoComposerCoordinator:
    """
    Coordinator that assembles the final video from all Phase 5 assets.

    Wraps the FFmpeg-based VideoComposer (composer.py) with:
    - DB integration for loading scene assets
    - Font/animation selection via FontSelector
    - Intro/outro from channel brand kit
    - PhaseResult return type for pipeline compatibility

    Called at COMPOSE state by PhaseExecutor.
    """

    def __init__(self, config=None, db=None):
        self.config = config or VideoComposerCoordinatorConfig()
        self.db = db
        self.composer = FFmpegComposer(ComposerConfig(
            ffmpeg=self.config.ffmpeg,
            fps=self.config.fps,
            width=self.config.width,
            height=self.config.height,
            video_codec=self.config.video_codec,
            video_crf=self.config.video_crf,
            audio_bitrate=self.config.audio_bitrate,
            target_lufs=self.config.target_lufs,
        ))
        self.font_selector = FontSelector(db=db)

    # ═══════════════════════════════════════════════════════
    # MAIN ENTRY POINT
    # ═══════════════════════════════════════════════════════

    def run(self, job_id: str) -> PhaseResult:
        """
        Compose the final video from all generated assets.

        Steps:
        1. Load all scene data + asset paths from DB
        2. Select font/animation style via FontSelector
        3. Build scene list with text overlays
        4. Load music tracks from DB
        5. Get intro/outro from channel brand kit
        6. Delegate to FFmpeg composer
        7. Store final video path in DB

        Args:
            job_id: The job identifier.

        Returns:
            PhaseResult with success status and output path.
        """
        start = time.time()
        job = self.db.get_job(job_id)
        scenes = self.db.get_scenes(job_id)
        channel_id = job.get("channel_id", "")
        output_path = str(
            Path(self.config.output_base) / job_id / "final.mp4"
        )

        try:
            # Select font + animation style
            font_config = self._get_font_config(job)

            # Build scene dicts for composer
            composer_scenes = self._build_composer_scenes(scenes, font_config)

            # Load music tracks
            music_tracks = self._load_music_tracks(job_id)

            # Get intro/outro paths
            intro_path, outro_path = self._get_intro_outro(channel_id)

            # Compose
            result: ComposerResult = self.composer.compose(
                scenes=composer_scenes,
                output_path=output_path,
                intro_path=intro_path,
                outro_path=outro_path,
                music_tracks=music_tracks,
            )

            elapsed = round(time.time() - start, 2)

            if result.success:
                # Store final video path in DB
                self.db.update_job(job_id, final_video_path=result.output_path)

                logger.info(
                    f"Video composed: {result.output_path} "
                    f"({result.duration_sec:.1f}s, {result.file_size_mb:.1f}MB, "
                    f"{elapsed}s)"
                )
                return PhaseResult(success=True, score=10.0)
            else:
                logger.error(f"Composition failed: {result.error}")
                return PhaseResult(
                    success=False,
                    reason=f"FFmpeg composition failed: {result.error}",
                )

        except Exception as e:
            logger.error(f"VideoComposer error: {e}", exc_info=True)
            return PhaseResult(success=False, reason=str(e))

    # ═══════════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════════

    def _build_composer_scenes(
        self, scenes: list[dict], font_config: Optional[dict]
    ) -> list[dict]:
        """
        Build the scene dicts expected by the FFmpeg composer.

        Merges DB scene data with text overlay configuration.
        """
        composer_scenes = []
        for scene in scenes:
            entry = {
                "scene_index": scene.get("scene_index", 0),
                "video_clip_path": scene.get("video_clip_path"),
                "voice_path": scene.get("voice_path"),
                "sfx_paths": scene.get("sfx_paths", []),
                "duration_seconds": scene.get(
                    "duration_seconds", scene.get("duration_sec", 7.0)
                ),
                "transition_to_next": scene.get("transition_to_next", "crossfade"),
            }

            # Add text overlay if scene has overlay text
            overlay_text = scene.get("overlay_text") or scene.get("text_overlay_text")
            if overlay_text and font_config:
                entry["text_overlay"] = {
                    "text": overlay_text,
                    "font_path": font_config.get("font_path", ""),
                    "font_size": font_config.get("font_size", 56),
                    "position": scene.get("text_position", "lower_third"),
                    "animation": font_config.get("entry_animation", "fade_in"),
                    "bg_style": font_config.get("background_style", "box"),
                }

            composer_scenes.append(entry)

        return composer_scenes

    def _get_font_config(self, job: dict) -> Optional[dict]:
        """Get font/animation config — from DB or via FontSelector."""
        # Check if already stored in job
        stored = job.get("font_animation_config")
        if stored:
            import json
            if isinstance(stored, str):
                try:
                    return json.loads(stored)
                except Exception:
                    pass
            elif isinstance(stored, dict):
                return stored

        # Select via FontSelector
        try:
            return self.font_selector.select(job)
        except Exception as e:
            logger.warning(f"FontSelector failed, using defaults: {e}")
            return None

    def _load_music_tracks(self, job_id: str) -> Optional[dict]:
        """Load music track paths from DB."""
        try:
            tracks = self.db.get_job_audio_tracks(job_id)
            if tracks:
                return {
                    role: track["audio_path"]
                    for role, track in tracks.items()
                    if track.get("audio_path")
                }
        except Exception as e:
            logger.warning(f"Failed to load music tracks: {e}")
        return None

    def _get_intro_outro(
        self, channel_id: str
    ) -> tuple[Optional[str], Optional[str]]:
        """Get intro/outro video paths from channel brand kit."""
        if not channel_id:
            return None, None

        brand_dir = Path(self.config.brands_dir) / channel_id
        intro = brand_dir / "intro.mp4"
        outro = brand_dir / "outro.mp4"

        return (
            str(intro) if intro.exists() else None,
            str(outro) if outro.exists() else None,
        )
