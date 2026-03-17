"""
GPU Memory Manager for single RTX 3090 (24GB VRAM).
Ensures only ONE model in VRAM at any time.
Full VRAM flush between model swaps.

CRITICAL: In single-GPU setup, a VRAM leak = full pipeline crash.
Every operation is logged via GPULogger.
"""

import gc
import time
import subprocess
import logging
from typing import Optional

try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from src.core.gpu_logger import GPULogger

logger = logging.getLogger(__name__)


class GPUMemoryManager:
    """
    Low-level VRAM management: load, unload, flush, verify.
    Only ONE model in VRAM at any time.
    """

    # Expected VRAM per model (GB)
    MODEL_VRAM = {
        "qwen3.5:27b":       16.0,
        "qwen3.5-27b:vision": 7.0,
        "flux":               12.0,
        "ltx":                12.0,
        "fish_audio_s2_pro":   4.0,
        "ace_step_1.5":        4.0,
        "moss_soundeffect":    4.0,
        "sadtalker":           4.0,
    }

    # Model type mapping
    MODEL_TYPES = {
        "qwen3.5:27b":        "ollama",
        "qwen3.5-27b:vision": "ollama",
        "flux":                "comfyui",
        "ltx":                 "comfyui",
        "fish_audio_s2_pro":   "python",
        "ace_step_1.5":        "python",
        "moss_soundeffect":    "python",
        "sadtalker":           "python",
    }

    def __init__(self, gpu_config: dict):
        self.device = gpu_config.get("device", "cuda:0")
        self.total_vram = gpu_config.get("vram_gb", 24)
        self.safety_margin = gpu_config.get("safety_margin_gb", 2)
        self.current_model: Optional[str] = None
        self.current_type: Optional[str] = None
        self.ollama_host = gpu_config.get("ollama_host", "http://localhost:11434")
        self.comfyui_host = gpu_config.get("comfyui_host", "http://localhost:8188")

    def set_hosts(self, ollama_host: str, comfyui_host: str):
        self.ollama_host = ollama_host
        self.comfyui_host = comfyui_host

    # ─── Public API ────────────────────────────────────────

    def load_model(
        self,
        model_name: str,
        model_type: Optional[str] = None,
        gpu_logger: Optional[GPULogger] = None,
    ):
        """
        Load a model into VRAM.
        Steps: unload current → flush → verify free → load new.
        """
        if model_type is None:
            model_type = self.MODEL_TYPES.get(model_name, "python")

        expected_vram = self.MODEL_VRAM.get(model_name, 8.0)

        start = None
        if gpu_logger:
            start = gpu_logger.log_model_load_start(model_name, model_type, expected_vram)

        try:
            # 1. Unload current
            if self.current_model:
                self.unload_model(gpu_logger=gpu_logger)

            # 2. Flush VRAM
            self._flush_vram()

            # 3. Verify free
            free = self._get_free_vram()
            if free < expected_vram:
                raise RuntimeError(
                    f"Insufficient VRAM: need {expected_vram}GB, "
                    f"only {free:.1f}GB free"
                )

            # 4. Load
            if model_type == "ollama":
                self._load_ollama(model_name)
            elif model_type == "comfyui":
                self._load_comfyui(model_name)
            elif model_type == "python":
                pass  # Python models loaded by the calling phase

            self.current_model = model_name
            self.current_type = model_type

            if gpu_logger and start is not None:
                gpu_logger.log_model_load_end(model_name, start, success=True)

        except Exception as e:
            if gpu_logger and start is not None:
                gpu_logger.log_model_load_end(model_name, start, success=False)
            raise

    def unload_model(self, gpu_logger: Optional[GPULogger] = None):
        """Unload current model and free all VRAM."""
        if not self.current_model:
            return

        start = None
        if gpu_logger:
            start = gpu_logger.log_model_unload_start(self.current_model)

        model_name = self.current_model

        # Type-specific unloading
        if self.current_type == "ollama":
            self._unload_ollama(model_name)
        elif self.current_type == "comfyui":
            self._unload_comfyui()

        # Force cleanup
        self._flush_vram()
        self.current_model = None
        self.current_type = None

        # Wait for VRAM to release
        time.sleep(2)

        if gpu_logger and start is not None:
            gpu_logger.log_model_unload_end(model_name, start)

            # Leak detection
            free = self._get_free_vram()
            expected_free = self.total_vram - self.safety_margin - 1
            if free < expected_free:
                used = self.total_vram - free
                gpu_logger.log_vram_flush(
                    "leak_detected_post_unload", used, self._get_free_vram()
                )

    def emergency_cleanup(self, gpu_logger: Optional[GPULogger] = None):
        """Nuclear option: kill everything and reset GPU."""
        if gpu_logger:
            gpu_logger.log_gpu_reset("emergency_cleanup")

        self.current_model = None
        self.current_type = None

        # Kill Ollama
        try:
            subprocess.run(
                ["ollama", "stop"], capture_output=True, timeout=10
            )
        except Exception:
            pass

        # Flush PyTorch
        if HAS_TORCH and torch.cuda.is_available():
            torch.cuda.empty_cache()
            try:
                torch.cuda.ipc_collect()
            except Exception:
                pass

        gc.collect()
        time.sleep(3)

        logger.info("Emergency GPU cleanup completed")

    def get_free_vram(self) -> float:
        """Public accessor for free VRAM in GB."""
        return self._get_free_vram()

    def get_vram_usage_pct(self) -> float:
        """Return VRAM usage as percentage."""
        if not HAS_TORCH or not torch.cuda.is_available():
            return 0.0
        free, total = torch.cuda.mem_get_info()
        return round((1 - free / total) * 100, 1) if total else 0.0

    # ─── Internal Methods ──────────────────────────────────

    def _flush_vram(self):
        """Force-free all cached GPU memory."""
        if HAS_TORCH and torch.cuda.is_available():
            torch.cuda.empty_cache()
            try:
                torch.cuda.ipc_collect()
            except Exception:
                pass
        gc.collect()

    def _get_free_vram(self) -> float:
        """Free VRAM in GB."""
        if HAS_TORCH and torch.cuda.is_available():
            free, _total = torch.cuda.mem_get_info()
            return free / 1e9
        return 0.0

    def _load_ollama(self, model_name: str):
        """Warm up Ollama model (loads into VRAM)."""
        if not HAS_REQUESTS:
            logger.warning("requests not installed — skipping Ollama load")
            return
        resp = requests.post(
            f"{self.ollama_host}/api/generate",
            json={"model": model_name, "prompt": "test", "options": {"num_predict": 1}},
            timeout=120,
        )
        resp.raise_for_status()

    def _unload_ollama(self, model_name: str):
        """Tell Ollama to unload model from VRAM."""
        if not HAS_REQUESTS:
            return
        try:
            requests.post(
                f"{self.ollama_host}/api/generate",
                json={"model": model_name, "keep_alive": 0},
                timeout=30,
            )
        except Exception:
            pass

    def _load_comfyui(self, model_name: str):
        """ComfyUI loads models on first prompt — verify server is up."""
        if not HAS_REQUESTS:
            logger.warning("requests not installed — skipping ComfyUI check")
            return
        resp = requests.get(f"{self.comfyui_host}/system_stats", timeout=10)
        resp.raise_for_status()

    def _unload_comfyui(self):
        """Tell ComfyUI to free all models from VRAM."""
        if not HAS_REQUESTS:
            return
        try:
            requests.post(
                f"{self.comfyui_host}/free",
                json={"unload_models": True, "free_memory": True},
                timeout=30,
            )
        except Exception:
            pass
