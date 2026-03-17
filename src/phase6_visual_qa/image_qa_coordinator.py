"""
Phase 6A — Image QA Coordinator.

Orchestrates the full image QA pipeline:
  1. Load Qwen 3.5-27B vision model
  2. Run image_script_verifier on each scene
  3. Run style_checker on all images
  4. Run sequence_checker on all images in order
  5. Send telegram_gallery for human review
  6. Return aggregate ImageQAResult with gate decision
"""

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests

from src.phase6_visual_qa.image_script_verifier import ImageScriptVerifier, ImageVerification
from src.phase6_visual_qa.style_checker import StyleChecker
from src.phase6_visual_qa.sequence_checker import SequenceChecker
from src.phase6_visual_qa.telegram_gallery import TelegramGallery

logger = logging.getLogger(__name__)

OLLAMA_HOST = "http://localhost:11434"
VISION_MODEL = "qwen3.5:27b"

# Gate thresholds
GATE_PASS_RATIO = 0.90      # >90% pass → continue
GATE_REGEN_RATIO = 0.70     # 70-90% → regenerate failed images
# Below 70% → block pipeline


@dataclass
class AggregateImageQAResult:
    """Aggregate result for all images in a job."""
    job_id: str = ""
    total_scenes: int = 0
    passed: int = 0
    regen_needed: int = 0
    flagged_human: int = 0
    failed: int = 0
    avg_score: float = 0.0
    per_scene: list[ImageVerification] = field(default_factory=list)
    style_consistent: bool = True
    style_outliers: list[int] = field(default_factory=list)
    sequence_score: float = 0.0
    jarring_transitions: list = field(default_factory=list)
    gate_decision: str = "pass"  # "pass" | "regen" | "block"
    total_ms: int = 0


class ImageQACoordinator:
    """
    Orchestrates Stage 6A: Image QA for all scenes in a job.
    Runs verification, style checks, sequence checks, and Telegram gallery.
    """

    def __init__(self, db=None, config: dict = None, telegram_token: str = "", telegram_chat_id: str = ""):
        self.db = db
        self.config = config or {}
        self.verifier = ImageScriptVerifier(config)
        self.style_checker = StyleChecker(config)
        self.sequence_checker = SequenceChecker(config)
        self.telegram = TelegramGallery(
            bot_token=telegram_token or self.config.get("telegram_bot_token", ""),
            chat_id=telegram_chat_id or self.config.get("telegram_chat_id", ""),
        )

    def run(
        self,
        job_id: str,
        scenes: list[dict],
        image_dir: str = "",
    ) -> AggregateImageQAResult:
        """
        Run full image QA pipeline for a job.

        Args:
            job_id: Pipeline job identifier.
            scenes: List of scene dicts with keys:
                - image_path (str): path to generated image
                - narration_text (str)
                - visual_prompt (str)
                - expected_elements (list[str])
                - style_description (str)
                - scene_mood (str)
            image_dir: Base directory for image paths (if relative).

        Returns:
            AggregateImageQAResult with gate decision.
        """
        t0 = time.perf_counter_ns()
        result = AggregateImageQAResult(job_id=job_id, total_scenes=len(scenes))

        logger.info(f"[{job_id}] Starting Image QA for {len(scenes)} scenes")

        # Ensure Qwen vision model is loaded
        self._ensure_model_loaded()

        # ─── Step 1: Verify each image against script ───
        image_paths = []
        for i, scene in enumerate(scenes):
            img_path = scene.get("image_path", "")
            if image_dir and not Path(img_path).is_absolute():
                img_path = str(Path(image_dir) / img_path)
            image_paths.append(img_path)

            verification = self.verifier.verify(
                image_path=img_path,
                scene_index=i,
                narration_text=scene.get("narration_text", ""),
                visual_prompt=scene.get("visual_prompt", ""),
                expected_elements=scene.get("expected_elements", []),
                style_description=scene.get("style_description", ""),
                scene_mood=scene.get("scene_mood", ""),
            )
            result.per_scene.append(verification)

            if verification.verdict == "pass":
                result.passed += 1
            elif verification.verdict in ("regen_adjust", "regen_new"):
                result.regen_needed += 1
            elif verification.verdict == "flag_human":
                result.flagged_human += 1
            else:
                result.failed += 1

            logger.info(
                f"  Scene {i}: score={verification.weighted_score:.1f} "
                f"verdict={verification.verdict}"
            )

        # Average score
        scores = [v.weighted_score for v in result.per_scene]
        result.avg_score = round(sum(scores) / len(scores), 2) if scores else 0.0

        # ─── Step 2: Style consistency check ───
        valid_paths = [p for p in image_paths if Path(p).exists()]
        if len(valid_paths) >= 2:
            style_result = self.style_checker.check_style_consistency(valid_paths)
            result.style_consistent = style_result.consistent
            result.style_outliers = style_result.outlier_indices
        else:
            logger.warning(f"[{job_id}] Not enough valid images for style check")

        # ─── Step 3: Sequence flow check ───
        if len(valid_paths) >= 3:
            seq_result = self.sequence_checker.check_sequence_flow(
                image_paths=valid_paths,
                scenes=scenes,
            )
            result.sequence_score = seq_result.overall_score
            result.jarring_transitions = [
                (t.scene_a, t.scene_b, t.reason)
                for t in getattr(seq_result, "transitions", [])
                if getattr(t, "jarring", False)
            ]

        # ─── Step 4: Send Telegram gallery ───
        try:
            self.telegram.send_gallery(
                job_id=job_id,
                scenes=scenes,
                image_paths=image_paths,
                verifications=result.per_scene,
                style_outliers=result.style_outliers,
            )
        except Exception as e:
            logger.error(f"[{job_id}] Telegram gallery failed: {e}")

        # ─── Step 5: Gate decision ───
        pass_ratio = result.passed / result.total_scenes if result.total_scenes > 0 else 0
        if pass_ratio >= GATE_PASS_RATIO:
            result.gate_decision = "pass"
        elif pass_ratio >= GATE_REGEN_RATIO:
            result.gate_decision = "regen"
        else:
            result.gate_decision = "block"

        result.total_ms = (time.perf_counter_ns() - t0) // 1_000_000
        logger.info(
            f"[{job_id}] Image QA complete: {result.passed}/{result.total_scenes} passed, "
            f"gate={result.gate_decision}, avg={result.avg_score:.1f}, {result.total_ms}ms"
        )

        # Store results in DB
        self._store_results(result)

        return result

    def _ensure_model_loaded(self) -> None:
        """Ensure Qwen vision model is loaded in Ollama."""
        try:
            resp = requests.post(
                f"{OLLAMA_HOST}/api/generate",
                json={"model": VISION_MODEL, "prompt": "test", "options": {"num_predict": 1}},
                timeout=60,
            )
            resp.raise_for_status()
            logger.info(f"Vision model {VISION_MODEL} is ready")
        except Exception as e:
            logger.warning(f"Could not pre-load vision model: {e}")

    def _store_results(self, result: AggregateImageQAResult) -> None:
        """Store QA results in the database."""
        if not self.db:
            return
        try:
            for v in result.per_scene:
                self.db.store_qa_rubric(
                    job_id=result.job_id,
                    asset_type="image",
                    scene_index=v.scene_index,
                    check_phase="phase6a",
                    score=v.weighted_score,
                    verdict=v.verdict,
                    rubric_data={
                        "rubric": v.rubric,
                        "flags": v.flags,
                        "hard_fail": v.hard_fail,
                    },
                )
        except Exception as e:
            logger.error(f"Failed to store QA results: {e}")
