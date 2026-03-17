"""
Phase 5 — Asset Coordinator: Visual Sub-Pipeline.

Coordinates image generation (FLUX), video generation (LTX-2.3),
and upscaling (Real-ESRGAN). Handles regeneration of failed assets.

Called at states: IMAGES, IMAGE_REGEN, VIDEO.
"""

import logging
import time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from src.models.analytics import PhaseResult
from .image_gen import ImageGenerator, ImageGenConfig
from .image_prompt import enhance_prompt, enhance_scenes
from .video_gen import VideoGenerator, VideoGenConfig
from .upscaler import Upscaler

logger = logging.getLogger(__name__)


@dataclass
class AssetCoordinatorConfig:
    """Configuration for asset coordination."""
    comfyui_host: str = "http://localhost:8188"
    flux_model: str = "flux1-dev.safetensors"
    ltx_model: str = "ltx-video-2.3.safetensors"
    output_base: str = "output"
    image_width: int = 1920
    image_height: int = 1080
    video_duration_sec: float = 7.0
    max_regen_attempts: int = 2
    upscale_enabled: bool = True
    min_image_quality: float = 6.0


class AssetCoordinator:
    """
    Manages the visual asset pipeline.

    Called at different states:
    - IMAGES     → generate all scene images via FLUX
    - IMAGE_REGEN → regenerate only failed/rejected images
    - VIDEO      → generate video clips from approved images via LTX-2.3

    GPU model loading is handled externally by ResourceCoordinator.
    """

    def __init__(self, config=None, db=None):
        self.config = config or AssetCoordinatorConfig()
        self.db = db
        self.image_gen = ImageGenerator(ImageGenConfig(
            comfyui_host=self.config.comfyui_host,
            model_name=self.config.flux_model,
            width=self.config.image_width,
            height=self.config.image_height,
        ))
        self.video_gen = VideoGenerator(VideoGenConfig(
            comfyui_host=self.config.comfyui_host,
            model_name=self.config.ltx_model,
        ))
        self.upscaler = Upscaler() if self.config.upscale_enabled else None

    # ═══════════════════════════════════════════════════════
    # MAIN ENTRY POINT
    # ═══════════════════════════════════════════════════════

    def run(self, job_id: str) -> PhaseResult:
        """
        Route to the correct sub-step based on current job status.

        Args:
            job_id: The job identifier.

        Returns:
            PhaseResult indicating success/failure and any scenes needing regen.
        """
        job = self.db.get_job(job_id)
        status = job.get("status", "")

        if status == "IMAGES":
            return self._generate_all_images(job_id)
        elif status == "IMAGE_REGEN":
            return self._regenerate_failed(job_id)
        elif status == "VIDEO":
            return self._generate_all_videos(job_id)
        else:
            return PhaseResult(
                success=False,
                reason=f"AssetCoordinator called with unexpected status: {status}",
            )

    # ═══════════════════════════════════════════════════════
    # IMAGE GENERATION
    # ═══════════════════════════════════════════════════════

    def _generate_all_images(self, job_id: str) -> PhaseResult:
        """
        Generate images for all scenes using FLUX via ComfyUI.

        Steps:
        1. Load scenes from DB
        2. Enhance prompts (Arabic context → English FLUX prompts)
        3. Generate images sequentially (single GPU)
        4. Optionally upscale to 4K (CPU, parallel-safe)
        5. Store paths in DB
        """
        start = time.time()
        scenes = self.db.get_scenes(job_id)
        job = self.db.get_job(job_id)
        channel_id = job.get("channel_id", "")
        output_dir = str(Path(self.config.output_base) / job_id / "images")

        # Get channel LoRA if configured
        channel_lora = None
        if self.db and channel_id:
            channel = self.db.get_channel(channel_id)
            if channel:
                channel_lora = channel.get("lora")

        # Enhance visual prompts
        enhanced_scenes = enhance_scenes(scenes, channel_id=channel_id)

        failed_scenes = []
        for i, scene in enumerate(enhanced_scenes):
            idx = scene.get("scene_index", i)
            visual_prompt = scene.get("visual_prompt", "")
            negative_prompt = scene.get("negative_prompt", "")

            if not visual_prompt.strip():
                logger.warning(f"Scene {idx} has no visual prompt, skipping")
                continue

            logger.info(f"Generating image {i + 1}/{len(scenes)} (scene {idx})")

            result = self.image_gen.generate(
                prompt=visual_prompt,
                output_dir=output_dir,
                filename=f"scene_{idx:03d}",
                negative_prompt=negative_prompt,
                lora_name=channel_lora,
            )

            if result.success:
                # Store image path in DB
                self.db.update_scene_asset(
                    job_id, idx,
                    image_path=result.image_path,
                    image_seed=result.seed,
                )

                # Upscale to 4K (CPU — can run while GPU does next image)
                if self.upscaler and result.image_path:
                    upscaled_path = result.image_path.replace(".png", "_4k.png")
                    try:
                        self.upscaler.upscale_image(result.image_path, upscaled_path)
                        self.db.update_scene_asset(
                            job_id, idx, image_upscaled_path=upscaled_path,
                        )
                    except Exception as e:
                        logger.warning(f"Upscale failed for scene {idx}: {e}")
            else:
                logger.error(f"Image gen failed for scene {idx}: {result.error}")
                failed_scenes.append(idx)

        elapsed = round(time.time() - start, 2)
        total = len(scenes)
        passed = total - len(failed_scenes)

        logger.info(
            f"Image generation complete: {passed}/{total} ({elapsed}s)"
        )

        if failed_scenes:
            return PhaseResult(
                success=False,
                needs_regeneration=True,
                failed_scenes=failed_scenes,
                reason=f"{len(failed_scenes)} images failed generation",
                score=passed / total * 10 if total > 0 else 0,
            )

        return PhaseResult(success=True, score=10.0)

    # ═══════════════════════════════════════════════════════
    # IMAGE REGENERATION
    # ═══════════════════════════════════════════════════════

    def _regenerate_failed(self, job_id: str) -> PhaseResult:
        """
        Regenerate only failed or rejected images.

        Uses different seeds and potentially adjusted prompts.
        """
        job = self.db.get_job(job_id)
        scenes = self.db.get_scenes(job_id)
        output_dir = str(Path(self.config.output_base) / job_id / "images")

        # Get scenes that need regeneration
        regen_indices = job.get("regen_scene_indices", [])
        if not regen_indices:
            # Fall back to scenes without image paths
            regen_indices = [
                s["scene_index"] for s in scenes
                if not s.get("image_path")
            ]

        if not regen_indices:
            return PhaseResult(success=True, reason="No scenes need regeneration")

        failed_scenes = []
        for scene in scenes:
            idx = scene["scene_index"]
            if idx not in regen_indices:
                continue

            logger.info(f"Regenerating image for scene {idx}")

            # Use a new seed for variety
            result = self.image_gen.generate(
                prompt=scene.get("visual_prompt", ""),
                output_dir=output_dir,
                filename=f"scene_{idx:03d}_regen",
                negative_prompt=scene.get("negative_prompt", ""),
            )

            if result.success:
                self.db.update_scene_asset(
                    job_id, idx,
                    image_path=result.image_path,
                    image_seed=result.seed,
                )
                # Upscale
                if self.upscaler and result.image_path:
                    upscaled = result.image_path.replace(".png", "_4k.png")
                    try:
                        self.upscaler.upscale_image(result.image_path, upscaled)
                        self.db.update_scene_asset(
                            job_id, idx, image_upscaled_path=upscaled,
                        )
                    except Exception as e:
                        logger.warning(f"Upscale failed for regen scene {idx}: {e}")
            else:
                failed_scenes.append(idx)

        if failed_scenes:
            return PhaseResult(
                success=False,
                needs_regeneration=True,
                failed_scenes=failed_scenes,
                reason=f"{len(failed_scenes)} scenes still failed after regen",
            )

        return PhaseResult(success=True)

    # ═══════════════════════════════════════════════════════
    # VIDEO GENERATION
    # ═══════════════════════════════════════════════════════

    def _generate_all_videos(self, job_id: str) -> PhaseResult:
        """
        Generate video clips from approved images using LTX-2.3.

        Falls back to Ken Burns (FFmpeg pan/zoom) on LTX failure.
        """
        start = time.time()
        scenes = self.db.get_scenes(job_id)
        output_dir = str(Path(self.config.output_base) / job_id / "videos")

        failed_scenes = []
        for i, scene in enumerate(scenes):
            idx = scene.get("scene_index", i)
            image_path = scene.get("image_path")

            if not image_path or not Path(image_path).exists():
                logger.warning(f"Scene {idx} has no image, skipping video gen")
                failed_scenes.append(idx)
                continue

            camera_motion = scene.get("camera_motion", "slow_zoom_in")
            duration = scene.get("duration_seconds", self.config.video_duration_sec)

            logger.info(
                f"Generating video {i + 1}/{len(scenes)} "
                f"(scene {idx}, motion={camera_motion})"
            )

            result = self.video_gen.generate(
                image_path=image_path,
                output_dir=output_dir,
                filename=f"scene_{idx:03d}",
                camera_motion=camera_motion,
                duration_sec=duration,
            )

            if result.success:
                self.db.update_scene_asset(
                    job_id, idx, video_clip_path=result.video_path,
                )
            else:
                # Fallback to Ken Burns
                logger.warning(
                    f"LTX failed for scene {idx}, falling back to Ken Burns"
                )
                kb_result = self.video_gen.ken_burns_fallback(
                    image_path=image_path,
                    output_dir=output_dir,
                    filename=f"scene_{idx:03d}_kb",
                    motion=camera_motion,
                    duration_sec=duration,
                )
                if kb_result.success:
                    self.db.update_scene_asset(
                        job_id, idx, video_clip_path=kb_result.video_path,
                    )
                else:
                    failed_scenes.append(idx)

        elapsed = round(time.time() - start, 2)
        total = len(scenes)
        passed = total - len(failed_scenes)

        logger.info(f"Video generation complete: {passed}/{total} ({elapsed}s)")

        if failed_scenes:
            return PhaseResult(
                success=False,
                failed_scenes=failed_scenes,
                reason=f"{len(failed_scenes)} video clips failed",
                score=passed / total * 10 if total > 0 else 0,
            )

        return PhaseResult(success=True, score=10.0)
