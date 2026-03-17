"""
ResourceCoordinator — high-level GPU orchestration.
Knows which model each pipeline phase needs and handles batching
to minimize GPU model swaps.

Wraps GPUMemoryManager with state-machine awareness.
"""

import logging
from typing import Optional
from enum import Enum

from src.core.gpu_manager import GPUMemoryManager
from src.core.gpu_logger import GPULogger

logger = logging.getLogger(__name__)


# ═══ GPU Requirements per pipeline status ═══
# Maps each job status to the GPU model it needs.
# None = CPU-only phase (no GPU needed).

GPU_REQUIREMENTS: dict[str, Optional[str]] = {
    "research":      "qwen3.5:27b",
    "seo":           "qwen3.5:27b",
    "script":        "qwen3.5:27b",
    "compliance":    "qwen3.5:27b",
    "images":        "flux",
    "image_qa":      "qwen3.5-27b:vision",
    "image_regen":   "flux",
    "video":         "ltx",
    "video_qa":      "qwen3.5-27b:vision",
    "video_regen":   "ltx",
    "voice":         "fish_audio_s2_pro",
    "music":         "ace_step_1.5",
    "sfx":           "moss_soundeffect",
    "compose":       None,                  # CPU only (FFmpeg)
    "overlay_qa":    "qwen3.5-27b:vision",
    "final_qa":      "qwen3.5-27b:vision",
    "manual_review": None,                  # Waiting for human
    "publish":       "flux",                # Thumbnails
}

# ═══ Consecutive states using the SAME model (batch without unload) ═══
# If current and next status are in the same batch, skip the swap.
GPU_BATCHES: list[list[str]] = [
    ["research", "seo", "script", "compliance"],       # All Qwen 3.5
    ["image_qa", "video_qa", "overlay_qa", "final_qa"],  # All Qwen Vision
    ["images", "image_regen"],                          # Both FLUX
    ["video", "video_regen"],                           # Both LTX
]


class ResourceCoordinator:
    """
    High-level GPU orchestration.
    Knows: which model is loaded, which model the next phase needs,
    whether to batch or swap.
    """

    def __init__(self, gpu_manager: GPUMemoryManager):
        self.gpu = gpu_manager
        self.current_model: Optional[str] = None
        self._logger: Optional[GPULogger] = None

    def set_logger(self, gpu_logger: GPULogger):
        self._logger = gpu_logger

    def prepare_for_status(self, status: str):
        """
        Ensure the correct GPU model is loaded for this pipeline status.
        Handles: no-op (already loaded), swap, or skip (CPU-only).
        """
        required = GPU_REQUIREMENTS.get(status)

        if required is None:
            # CPU-only phase — unload GPU if anything loaded
            if self.current_model:
                logger.info(f"Status '{status}' is CPU-only — releasing GPU")
                self.gpu.unload_model(gpu_logger=self._logger)
                self.current_model = None
            return

        if required == self.current_model:
            # Already loaded — no swap needed (batching)
            logger.info(
                f"Status '{status}' needs '{required}' — already loaded (batched)"
            )
            return

        # Need to swap
        if self.current_model:
            logger.info(
                f"Swapping GPU: '{self.current_model}' → '{required}' "
                f"for status '{status}'"
            )
            self.gpu.unload_model(gpu_logger=self._logger)

        model_type = self._get_model_type(required)
        logger.info(f"Loading '{required}' ({model_type}) for status '{status}'")
        self.gpu.load_model(required, model_type=model_type, gpu_logger=self._logger)
        self.current_model = required

    def release_all(self):
        """Release GPU at end of pipeline or on error."""
        if self.current_model:
            logger.info(f"Releasing GPU model '{self.current_model}'")
            self.gpu.unload_model(gpu_logger=self._logger)
            self.current_model = None

    def emergency_release(self):
        """Nuclear option — force free everything."""
        logger.warning("Emergency GPU release triggered!")
        self.gpu.emergency_cleanup(gpu_logger=self._logger)
        self.current_model = None

    def can_batch_with_next(self, current_status: str, next_status: str) -> bool:
        """
        Check if current and next status use the same GPU model,
        meaning we can skip the unload/reload cycle.
        """
        for batch in GPU_BATCHES:
            if current_status in batch and next_status in batch:
                return True
        # Also check if they simply need the same model
        req_current = GPU_REQUIREMENTS.get(current_status)
        req_next = GPU_REQUIREMENTS.get(next_status)
        return req_current is not None and req_current == req_next

    def get_required_model(self, status: str) -> Optional[str]:
        """What GPU model does this status need?"""
        return GPU_REQUIREMENTS.get(status)

    def get_current_model(self) -> Optional[str]:
        """What model is currently loaded?"""
        return self.current_model

    # ─── Batch Processing ──────────────────────────────────

    def get_optimal_phase_order(self, phases: list[str]) -> list[str]:
        """
        Reorder phases to minimize GPU swaps.
        Groups phases by the model they need.
        
        Example:
          Input:  [images, voice, image_qa, music, video]
          Output: [images, image_qa, video, voice, music]
          (groups FLUX phases, then LTX, then audio models)
        """
        # Group by required model
        model_groups: dict[Optional[str], list[str]] = {}
        for phase in phases:
            model = GPU_REQUIREMENTS.get(phase)
            model_groups.setdefault(model, []).append(phase)

        # Order: keep original relative order within groups
        # but group same-model phases together
        result = []
        seen_models = set()
        for phase in phases:
            model = GPU_REQUIREMENTS.get(phase)
            if model not in seen_models:
                seen_models.add(model)
                result.extend(model_groups[model])

        return result

    # ─── Internal ──────────────────────────────────────────

    @staticmethod
    def _get_model_type(model_name: str) -> str:
        """Determine model type from name."""
        if model_name in ("qwen3.5:27b", "qwen3.5-27b:vision"):
            return "ollama"
        elif model_name in ("flux", "ltx"):
            return "comfyui"
        else:
            return "python"
