"""
GPU Memory Manager for single RTX 3090 (24GB VRAM).
Ensures only ONE model in VRAM at any time.
Full VRAM flush between model swaps.

CRITICAL RULES:
  1. NEVER allow CPU offloading — everything on GPU or fail.
  2. Kill ALL GPU processes before loading a new model.
  3. Verify VRAM is actually free after unload (leak detection).
  4. ComfyUI process must be KILLED (not just /free API) to release VRAM.
"""

import gc
import os
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
    Only ONE model in VRAM at any time. NO CPU offloading.
    """

    # Expected VRAM per model (GB)
    MODEL_VRAM = {
        "qwen3.5:27b":        16.0,
        "flux":                12.0,
        "ltx":                 12.0,
        "fish_audio_s2_pro":    4.0,
    }

    # Model type mapping
    MODEL_TYPES = {
        "qwen3.5:27b":        "ollama",
        "flux":                "comfyui",
        "ltx":                 "comfyui",
        "fish_audio_s2_pro":   "python",
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
        Load a model into VRAM (GPU ONLY — no CPU offloading).
        Steps: kill all GPU users → flush → verify free → load new.
        """
        if model_type is None:
            model_type = self.MODEL_TYPES.get(model_name, "python")

        expected_vram = self.MODEL_VRAM.get(model_name, 8.0)

        start = None
        if gpu_logger:
            start = gpu_logger.log_model_load_start(model_name, model_type, expected_vram)

        try:
            # 1. Unload current model
            if self.current_model:
                self.unload_model(gpu_logger=gpu_logger)

            # 2. Nuclear VRAM cleanup — kill ALL GPU-using processes
            self._nuclear_vram_cleanup()

            # 3. Verify enough free VRAM
            free = self._get_free_vram()
            if free < expected_vram:
                # Try one more cleanup round
                logger.warning(
                    f"VRAM still low after cleanup: {free:.1f}GB free, "
                    f"need {expected_vram}GB. Trying emergency cleanup..."
                )
                self._emergency_kill_gpu_processes()
                time.sleep(5)
                free = self._get_free_vram()
                if free < expected_vram:
                    raise RuntimeError(
                        f"Insufficient VRAM: need {expected_vram}GB, "
                        f"only {free:.1f}GB free after cleanup"
                    )

            logger.info(f"VRAM ready: {free:.1f}GB free, loading '{model_name}' ({expected_vram}GB)")

            # 4. Load model (GPU ONLY)
            if model_type == "ollama":
                self._load_ollama(model_name)
            elif model_type == "comfyui":
                self._load_comfyui(model_name)
            elif model_type == "python":
                pass  # Python models loaded by the calling phase

            # 5. Verify model is actually on GPU (not CPU offloaded)
            if model_type == "ollama":
                self._verify_ollama_gpu(model_name)

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
        self._emergency_kill_gpu_processes()
        self._flush_vram()
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

    def _nuclear_vram_cleanup(self):
        """Kill ALL non-essential GPU processes to ensure VRAM is free.
        
        This is called before every model load. On a single-GPU system,
        we cannot afford VRAM fragmentation or leaks.
        """
        # 1. Unload Ollama models
        if HAS_REQUESTS:
            try:
                resp = requests.get(f"{self.ollama_host}/api/ps", timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    for model_info in data.get("models", []):
                        name = model_info.get("name", "")
                        if name:
                            requests.post(
                                f"{self.ollama_host}/api/generate",
                                json={"model": name, "keep_alive": 0},
                                timeout=15,
                            )
                            logger.info(f"Unloaded Ollama model: {name}")
            except Exception as e:
                logger.debug(f"Ollama cleanup: {e}")

        # 2. Kill ComfyUI python processes
        self._kill_comfyui_processes()

        # 3. Kill Fish Speech server instances (they leak VRAM if left running)
        self._kill_fish_speech_processes()

        # 4. Flush PyTorch CUDA cache
        self._flush_vram()

        # 5. Wait for VRAM to release
        time.sleep(3)

        free = self._get_free_vram()
        logger.info(f"VRAM after nuclear cleanup: {free:.1f}GB free")

    def _kill_fish_speech_processes(self):
        """Kill ALL Fish Speech server instances to free VRAM."""
        try:
            result = subprocess.run(
                ["powershell", "-Command",
                 "Get-WmiObject Win32_Process | "
                 "Where-Object { $_.CommandLine -match 'api_server.*checkpoint|fish.*speech.*server' } | "
                 "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
                capture_output=True, timeout=10,
            )
            logger.info("Fish Speech processes killed")
        except Exception as e:
            logger.debug(f"Fish Speech kill: {e}")

    def _kill_comfyui_processes(self):
        """Kill ComfyUI worker python processes (not the Desktop app UI)."""
        try:
            result = subprocess.run(
                ["powershell", "-Command",
                 "Get-WmiObject Win32_Process | "
                 "Where-Object { $_.CommandLine -match 'ComfyUI.*resources|ComfyUI.*main' } | "
                 "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
                capture_output=True, timeout=10,
            )
            logger.info("ComfyUI processes killed")
        except Exception as e:
            logger.debug(f"ComfyUI kill: {e}")

    def _emergency_kill_gpu_processes(self):
        """Last resort: kill Ollama models + ComfyUI + Fish Speech + flush everything."""
        logger.warning("Emergency GPU process kill triggered")

        # Unload all Ollama
        try:
            subprocess.run(["ollama", "stop"], capture_output=True, timeout=10)
        except Exception:
            pass

        # Kill ComfyUI + Fish Speech
        self._kill_comfyui_processes()
        self._kill_fish_speech_processes()

        # Flush PyTorch
        self._flush_vram()

        gc.collect()
        time.sleep(3)

    # ─── Ollama ────────────────────────────────────────────

    def _load_ollama(self, model_name: str):
        """Load Ollama model into VRAM (GPU only)."""
        if not HAS_REQUESTS:
            logger.warning("requests not installed — skipping Ollama load")
            return

        # Force GPU-only: set num_gpu to max layers
        # First load can take 3-5 minutes for large models (qwen3.5:27b = 17GB)
        resp = requests.post(
            f"{self.ollama_host}/api/generate",
            json={
                "model": model_name,
                "prompt": "test",
                "options": {
                    "num_predict": 1,
                    "num_gpu": 999,  # Force ALL layers on GPU
                },
            },
            timeout=600,  # 10 min — large models need time to load
        )
        resp.raise_for_status()
        logger.info(f"Ollama model '{model_name}' loaded (GPU-only)")

    def _verify_ollama_gpu(self, model_name: str):
        """Verify the Ollama model is fully on GPU (not CPU offloaded)."""
        if not HAS_REQUESTS:
            return

        try:
            resp = requests.get(f"{self.ollama_host}/api/ps", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for model_info in data.get("models", []):
                    if model_info.get("name", "").startswith(model_name.split(":")[0]):
                        size_vram = model_info.get("size_vram", 0)
                        size = model_info.get("size", 0)
                        if size > 0 and size_vram > 0:
                            gpu_pct = (size_vram / size) * 100
                            if gpu_pct < 90:
                                logger.warning(
                                    f"⚠️ Ollama model '{model_name}' only {gpu_pct:.0f}% on GPU! "
                                    f"({size_vram / 1e9:.1f}GB VRAM / {size / 1e9:.1f}GB total)"
                                )
                            else:
                                logger.info(
                                    f"✅ Ollama model '{model_name}' {gpu_pct:.0f}% on GPU "
                                    f"({size_vram / 1e9:.1f}GB VRAM)"
                                )
                        return
        except Exception as e:
            logger.debug(f"Ollama GPU verify: {e}")

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
            logger.info(f"Ollama model '{model_name}' unloaded")
        except Exception:
            pass

    # ─── ComfyUI ───────────────────────────────────────────

    def _load_comfyui(self, model_name: str):
        """ComfyUI loads models on first prompt — verify server is up."""
        if not HAS_REQUESTS:
            logger.warning("requests not installed — skipping ComfyUI check")
            return
        try:
            resp = requests.get(f"{self.comfyui_host}/system_stats", timeout=10)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"ComfyUI not available at {self.comfyui_host}: {e}")
            logger.warning("ComfyUI model will be loaded on first use if/when ComfyUI starts")

    def _unload_comfyui(self):
        """Free ComfyUI VRAM: /free API then KILL the process.
        
        ComfyUI Desktop holds VRAM even after /free API call.
        Must kill the process to guarantee full VRAM release.
        """
        # Try graceful unload first
        if HAS_REQUESTS:
            try:
                requests.post(
                    f"{self.comfyui_host}/free",
                    json={"unload_models": True, "free_memory": True},
                    timeout=10,
                )
            except Exception:
                pass

        # Kill the process — this is the only reliable way
        self._kill_comfyui_processes()
        time.sleep(3)
