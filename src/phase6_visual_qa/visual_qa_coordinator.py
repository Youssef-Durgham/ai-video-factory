"""
Phase 6 — Visual QA Master Coordinator.

Orchestrates the full Phase 6 pipeline:
  Step 1: Load Qwen 3.5-27B
  Step 2: IMAGE QA (Stage 6A) — verify images, style, sequence, telegram gallery
  Step 3: Unload Qwen → Load FLUX (if regen needed) → regen → re-verify
  Step 4: Unload Qwen → VIDEO GENERATION (Phase 5b, external)
  Step 5: VIDEO QA (Stage 6B) — verify clips, fallbacks, telegram video gallery
  Step 6: OVERLAY QA (Stage 6C) — verify text overlays after composition
  
Manages GPU model swaps between Qwen/FLUX/LTX.
"""

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests

from src.phase6_visual_qa.image_qa_coordinator import ImageQACoordinator, AggregateImageQAResult
from src.phase6_visual_qa.video_script_verifier import VideoScriptVerifier, VideoVerification
from src.phase6_visual_qa.video_keyframe_extractor import VideoKeyframeExtractor
from src.phase6_visual_qa.telegram_video_gallery import TelegramVideoGallery
from src.phase6_visual_qa.overlay_checker import OverlayChecker
from src.phase6_visual_qa.overlay_auto_fixer import OverlayAutoFixer

logger = logging.getLogger(__name__)

OLLAMA_HOST = "http://localhost:11434"
VISION_MODEL = "qwen3.5:27b"

# Gate thresholds for video QA
VIDEO_GATE_PASS_RATIO = 0.85
MAX_OVERLAY_FIX_ATTEMPTS = 2


@dataclass
class Phase6Result:
    """Aggregate result for the entire Phase 6 pipeline."""
    job_id: str = ""

    # Stage 6A: Image QA
    image_qa: Optional[AggregateImageQAResult] = None
    image_gate: str = ""  # "pass" | "regen" | "block"

    # Stage 6B: Video QA
    video_verifications: list[VideoVerification] = field(default_factory=list)
    video_passed: int = 0
    video_regen: int = 0
    video_ken_burns: int = 0
    video_flagged: int = 0
    video_gate: str = ""  # "pass" | "regen" | "block"

    # Stage 6C: Overlay QA
    overlay_passed: bool = False
    overlay_fixes_applied: int = 0

    # Overall
    overall_gate: str = ""  # "pass" | "block"
    total_ms: int = 0
    model_swaps: int = 0


class VisualQACoordinator:
    """
    Master coordinator for Phase 6 Visual QA.
    Manages the full pipeline: Image QA → Video QA → Overlay QA.
    Handles GPU model swaps between Qwen, FLUX, and LTX.
    """

    def __init__(self, db=None, config: dict = None):
        self.db = db
        self.config = config or {}

        telegram_token = self.config.get("telegram_bot_token", "")
        telegram_chat = self.config.get("telegram_chat_id", "")

        self.image_qa = ImageQACoordinator(
            db=db, config=config,
            telegram_token=telegram_token,
            telegram_chat_id=telegram_chat,
        )
        self.video_verifier = VideoScriptVerifier(config)
        self.video_gallery = TelegramVideoGallery(
            bot_token=telegram_token,
            chat_id=telegram_chat,
        )
        self.overlay_checker = OverlayChecker(config)
        self.overlay_fixer = OverlayAutoFixer(config)

    def run(
        self,
        job_id: str,
        scenes: list[dict],
        image_dir: str = "",
        video_dir: str = "",
        composed_video_path: str = "",
    ) -> Phase6Result:
        """
        Run the full Phase 6 Visual QA pipeline.

        Args:
            job_id: Pipeline job identifier.
            scenes: List of scene dicts with all metadata.
            image_dir: Directory containing generated images.
            video_dir: Directory containing generated video clips.
            composed_video_path: Path to the composed video with overlays.

        Returns:
            Phase6Result with gate decisions for each stage.
        """
        t0 = time.perf_counter_ns()
        result = Phase6Result(job_id=job_id)

        # ═══ STEP 1-2: IMAGE QA (Stage 6A) ═══
        logger.info(f"[{job_id}] ═══ Phase 6A: Image QA ═══")
        self._load_vision_model()
        result.model_swaps += 1

        result.image_qa = self.image_qa.run(
            job_id=job_id,
            scenes=scenes,
            image_dir=image_dir,
        )
        result.image_gate = result.image_qa.gate_decision

        if result.image_gate == "block":
            logger.warning(f"[{job_id}] Image QA BLOCKED pipeline — too many failures")
            result.overall_gate = "block"
            result.total_ms = (time.perf_counter_ns() - t0) // 1_000_000
            return result

        # ═══ STEP 3: REGENERATE FAILED IMAGES (if needed) ═══
        if result.image_gate == "regen":
            logger.info(f"[{job_id}] Regenerating failed images...")
            regen_indices = [
                v.scene_index for v in result.image_qa.per_scene
                if v.verdict in ("regen_adjust", "regen_new", "fail")
            ]
            # Unload Qwen, load FLUX for regeneration
            self._unload_model(VISION_MODEL)
            result.model_swaps += 1

            # NOTE: Actual FLUX regeneration is handled by the pipeline runner.
            # This coordinator signals which scenes need regeneration.
            logger.info(f"[{job_id}] Scenes needing regen: {regen_indices}")

            # After regen, reload Qwen and re-verify
            self._load_vision_model()
            result.model_swaps += 1

            # Re-run image QA on regenerated images
            result.image_qa = self.image_qa.run(
                job_id=job_id,
                scenes=scenes,
                image_dir=image_dir,
            )
            result.image_gate = result.image_qa.gate_decision

        # ═══ STEP 4: VIDEO GENERATION (external — Phase 5b) ═══
        # Unload Qwen to free VRAM for LTX
        self._unload_model(VISION_MODEL)
        result.model_swaps += 1
        logger.info(f"[{job_id}] ═══ Unloaded Qwen — ready for video generation ═══")

        # NOTE: Video generation (LTX) is handled externally by the pipeline runner.
        # This method continues after video generation is complete.

        # ═══ STEP 5: VIDEO QA (Stage 6B) ═══
        if video_dir and Path(video_dir).exists():
            logger.info(f"[{job_id}] ═══ Phase 6B: Video QA ═══")
            self._load_vision_model()
            result.model_swaps += 1

            video_paths = []
            for i, scene in enumerate(scenes):
                vp = scene.get("video_path", "")
                if not vp:
                    vp = str(Path(video_dir) / f"scene_{i:03d}.mp4")
                video_paths.append(vp)

            for i, scene in enumerate(scenes):
                vpath = video_paths[i]
                if not Path(vpath).exists():
                    logger.warning(f"Video clip missing: {vpath}")
                    continue

                vv = self.video_verifier.verify(
                    video_path=vpath,
                    scene_index=i,
                    narration_text=scene.get("narration_text", ""),
                    motion_prompt=scene.get("motion_prompt", ""),
                    expected_duration_sec=scene.get("duration_seconds", 0),
                    retry_count=scene.get("retry_count", 0),
                )
                result.video_verifications.append(vv)

                if vv.verdict == "pass":
                    result.video_passed += 1
                elif vv.verdict == "regen_video":
                    result.video_regen += 1
                elif vv.verdict == "ken_burns":
                    result.video_ken_burns += 1
                elif vv.verdict == "flag_human":
                    result.video_flagged += 1

                logger.info(
                    f"  Video {i}: score={vv.weighted_score:.1f} verdict={vv.verdict}"
                )

            # Send video gallery to Telegram
            try:
                self.video_gallery.send_gallery(
                    job_id=job_id,
                    scenes=scenes,
                    video_paths=video_paths,
                    verifications=result.video_verifications,
                )
            except Exception as e:
                logger.error(f"Video gallery send failed: {e}")

            # Video gate decision
            total_videos = len(result.video_verifications)
            if total_videos > 0:
                pass_ratio = result.video_passed / total_videos
                result.video_gate = "pass" if pass_ratio >= VIDEO_GATE_PASS_RATIO else "regen"
            else:
                result.video_gate = "block"

        # ═══ STEP 6: OVERLAY QA (Stage 6C) ═══
        if composed_video_path and Path(composed_video_path).exists():
            logger.info(f"[{job_id}] ═══ Phase 6C: Overlay QA ═══")

            overlay_result = self.overlay_checker.check_overlays(
                video_path=composed_video_path,
                scenes=scenes,
            )

            if overlay_result.overall_pass:
                result.overlay_passed = True
            elif overlay_result.auto_fixable:
                # Apply auto-fixes
                for attempt in range(MAX_OVERLAY_FIX_ATTEMPTS):
                    logger.info(f"Overlay auto-fix attempt {attempt + 1}")
                    fixed_path = self.overlay_fixer.apply_fixes(
                        video_path=composed_video_path,
                        fix_instructions=overlay_result.fix_instructions,
                    )
                    if fixed_path:
                        composed_video_path = fixed_path
                        result.overlay_fixes_applied += 1

                        # Re-check
                        overlay_result = self.overlay_checker.check_overlays(
                            video_path=composed_video_path,
                            scenes=scenes,
                        )
                        if overlay_result.overall_pass:
                            result.overlay_passed = True
                            break
            else:
                logger.warning(f"[{job_id}] Overlay issues not auto-fixable")

        # Unload vision model
        self._unload_model(VISION_MODEL)
        result.model_swaps += 1

        # ═══ OVERALL GATE ═══
        if result.image_gate == "block" or result.video_gate == "block":
            result.overall_gate = "block"
        else:
            result.overall_gate = "pass"

        result.total_ms = (time.perf_counter_ns() - t0) // 1_000_000
        logger.info(
            f"[{job_id}] Phase 6 complete: image={result.image_gate} video={result.video_gate} "
            f"overlay={'pass' if result.overlay_passed else 'fail'} "
            f"overall={result.overall_gate} swaps={result.model_swaps} {result.total_ms}ms"
        )

        return result

    # ═══ Model Management ═══════════════════════════════════════

    def _load_vision_model(self) -> None:
        """Load the vision model into Ollama (warms up GPU)."""
        try:
            resp = requests.post(
                f"{OLLAMA_HOST}/api/generate",
                json={"model": VISION_MODEL, "prompt": "test", "options": {"num_predict": 1}},
                timeout=120,
            )
            logger.info(f"Vision model {VISION_MODEL} loaded")
        except Exception as e:
            logger.warning(f"Could not pre-load vision model: {e}")

    def _unload_model(self, model_name: str) -> None:
        """Unload a model from Ollama to free VRAM."""
        try:
            resp = requests.post(
                f"{OLLAMA_HOST}/api/generate",
                json={"model": model_name, "prompt": "", "keep_alive": 0},
                timeout=30,
            )
            logger.info(f"Unloaded model {model_name}")
        except Exception as e:
            logger.warning(f"Could not unload model {model_name}: {e}")
