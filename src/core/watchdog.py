"""
ServiceWatchdog — background monitor for all external services.
Detects: hangs, crashes, unresponsive services, resource exhaustion.
Recovers: restart, alert, pause pipeline.

Runs as a daemon thread alongside the pipeline.
"""

import threading
import time
import subprocess
import logging
from datetime import datetime
from typing import Optional, Callable

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

logger = logging.getLogger(__name__)


class ServiceWatchdog(threading.Thread):
    """
    Background monitor — checks service health every 30 seconds.
    
    Monitored:
      - Ollama (HTTP health + process alive)
      - ComfyUI (HTTP health + queue status)
      - GPU (temperature, VRAM, utilization)
      - Disk (free space)
      - RAM (available memory)
      - Pipeline progress (stuck detection)
    """

    daemon = True  # Dies when main process exits

    def __init__(
        self,
        ollama_host: str = "http://localhost:11434",
        comfyui_host: str = "http://localhost:8188",
        check_interval: int = 30,
        gpu_temp_warning: int = 85,
        gpu_temp_critical: int = 90,
        disk_warning_gb: float = 50.0,
        disk_critical_gb: float = 20.0,
        ram_warning_gb: float = 16.0,
        ram_critical_gb: float = 8.0,
        pipeline_stuck_minutes: int = 30,
        on_alert: Optional[Callable] = None,
        on_critical: Optional[Callable] = None,
    ):
        super().__init__(name="ServiceWatchdog")
        self.ollama_host = ollama_host
        self.comfyui_host = comfyui_host
        self.check_interval = check_interval
        self.gpu_temp_warning = gpu_temp_warning
        self.gpu_temp_critical = gpu_temp_critical
        self.disk_warning_gb = disk_warning_gb
        self.disk_critical_gb = disk_critical_gb
        self.ram_warning_gb = ram_warning_gb
        self.ram_critical_gb = ram_critical_gb
        self.pipeline_stuck_minutes = pipeline_stuck_minutes

        # Callbacks
        self._on_alert = on_alert or (lambda msg: logger.warning(msg))
        self._on_critical = on_critical or (lambda msg: logger.critical(msg))

        # Pipeline progress tracking
        self._last_status_change = time.time()
        self._last_job_status: Optional[str] = None
        self._current_job_id: Optional[str] = None

        self.running = True

    def run(self):
        """Main loop — check all services periodically."""
        logger.info("ServiceWatchdog started")
        while self.running:
            try:
                self._check_all()
            except Exception as e:
                logger.error(f"Watchdog error: {e}")
            time.sleep(self.check_interval)

    def stop(self):
        """Stop the watchdog."""
        self.running = False

    def update_pipeline_status(self, job_id: str, status: str):
        """Called by PipelineRunner when job status changes."""
        if status != self._last_job_status or job_id != self._current_job_id:
            self._last_job_status = status
            self._current_job_id = job_id
            self._last_status_change = time.time()

    # ─── Health Checks ─────────────────────────────────────

    def _check_all(self):
        results = {}
        results["ollama"] = self._check_ollama()
        results["comfyui"] = self._check_comfyui()
        results["gpu"] = self._check_gpu()
        results["disk"] = self._check_disk()
        results["ram"] = self._check_ram()
        results["pipeline"] = self._check_pipeline_progress()

        for service, status in results.items():
            if not status["healthy"]:
                self._handle_unhealthy(service, status)

    def _check_ollama(self) -> dict:
        if not HAS_REQUESTS:
            return {"healthy": True, "detail": "requests not installed — skip"}
        try:
            r = requests.get(f"{self.ollama_host}/api/tags", timeout=5)
            return {"healthy": r.status_code == 200, "detail": "OK"}
        except Exception:
            alive = False
            if HAS_PSUTIL:
                alive = any(
                    "ollama" in (p.name() or "").lower()
                    for p in psutil.process_iter(["name"])
                )
            detail = "process_alive_but_unresponsive" if alive else "process_dead"
            return {"healthy": False, "detail": detail, "recovery": "restart_ollama"}

    def _check_comfyui(self) -> dict:
        if not HAS_REQUESTS:
            return {"healthy": True, "detail": "requests not installed — skip"}
        try:
            r = requests.get(f"{self.comfyui_host}/system_stats", timeout=5)
            return {"healthy": r.status_code == 200, "detail": "OK"}
        except Exception:
            return {"healthy": False, "detail": "unreachable", "recovery": "restart_comfyui"}

    def _check_gpu(self) -> dict:
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=temperature.gpu,memory.used,memory.total,utilization.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True, text=True, timeout=10,
            )
            parts = result.stdout.strip().split(", ")
            if len(parts) < 4:
                return {"healthy": True, "detail": "nvidia-smi parse issue"}

            temp = int(parts[0])
            vram_used = int(parts[1])
            vram_total = int(parts[2])
            util = int(parts[3])

            healthy = True
            detail = "OK"

            if temp > self.gpu_temp_critical:
                healthy = False
                detail = f"CRITICAL: GPU temp {temp}°C — PAUSE PIPELINE"
            elif temp > self.gpu_temp_warning:
                detail = f"WARNING: GPU temp {temp}°C — throttling likely"

            if vram_total > 0 and vram_used / vram_total > 0.95:
                healthy = False
                detail = f"VRAM LEAK: {vram_used}/{vram_total}MB used"

            return {
                "healthy": healthy,
                "temp_c": temp,
                "vram_used_mb": vram_used,
                "vram_total_mb": vram_total,
                "utilization": util,
                "detail": detail,
            }
        except Exception:
            return {"healthy": True, "detail": "nvidia-smi unavailable"}

    def _check_disk(self) -> dict:
        if not HAS_PSUTIL:
            return {"healthy": True, "detail": "psutil not installed — skip"}
        try:
            usage = psutil.disk_usage(".")
            free_gb = usage.free / (1024 ** 3)
            if free_gb < self.disk_critical_gb:
                return {
                    "healthy": False,
                    "detail": f"CRITICAL: {free_gb:.1f}GB free",
                    "recovery": "emergency_cleanup",
                }
            elif free_gb < self.disk_warning_gb:
                return {"healthy": True, "detail": f"WARNING: {free_gb:.1f}GB free"}
            return {"healthy": True, "free_gb": round(free_gb, 1), "detail": "OK"}
        except Exception:
            return {"healthy": True, "detail": "disk check failed"}

    def _check_ram(self) -> dict:
        if not HAS_PSUTIL:
            return {"healthy": True, "detail": "psutil not installed — skip"}
        try:
            available_gb = psutil.virtual_memory().available / (1024 ** 3)
            if available_gb < self.ram_critical_gb:
                return {
                    "healthy": False,
                    "detail": f"LOW RAM: {available_gb:.1f}GB available",
                }
            return {
                "healthy": True,
                "available_gb": round(available_gb, 1),
                "detail": "OK",
            }
        except Exception:
            return {"healthy": True, "detail": "RAM check failed"}

    def _check_pipeline_progress(self) -> dict:
        if self._last_job_status is None:
            return {"healthy": True, "detail": "no active jobs"}

        if self._last_job_status in ("manual_review", "blocked", "published", "complete"):
            return {"healthy": True, "detail": f"status={self._last_job_status}"}

        stuck_minutes = (time.time() - self._last_status_change) / 60
        if stuck_minutes > self.pipeline_stuck_minutes:
            return {
                "healthy": False,
                "detail": (
                    f"Pipeline stuck in '{self._last_job_status}' "
                    f"for {stuck_minutes:.0f}min"
                ),
                "recovery": "alert",
            }
        return {
            "healthy": True,
            "detail": f"Progress OK ({self._last_job_status})",
            "minutes_in_state": round(stuck_minutes, 1),
        }

    # ─── Recovery ──────────────────────────────────────────

    def _handle_unhealthy(self, service: str, status: dict):
        recovery = status.get("recovery", "alert")
        msg = (
            f"🚨 Watchdog: {service} unhealthy\n"
            f"Detail: {status['detail']}\n"
            f"Action: {recovery}\n"
            f"Time: {datetime.now().isoformat()}"
        )

        if recovery == "restart_ollama":
            self._restart_ollama()
        elif recovery == "restart_comfyui":
            self._restart_comfyui()

        # Always alert
        if "CRITICAL" in status.get("detail", "") or recovery != "alert":
            self._on_critical(msg)
        else:
            self._on_alert(msg)

    def _restart_ollama(self):
        logger.info("Watchdog: attempting Ollama restart")
        try:
            subprocess.run(["ollama", "stop"], capture_output=True, timeout=10)
            time.sleep(5)
            subprocess.Popen(["ollama", "serve"])
            time.sleep(10)
            logger.info("Watchdog: Ollama restarted")
        except Exception as e:
            logger.error(f"Watchdog: failed to restart Ollama: {e}")

    def _restart_comfyui(self):
        logger.info("Watchdog: attempting ComfyUI restart")
        if not HAS_PSUTIL:
            logger.warning("psutil not installed — cannot restart ComfyUI")
            return
        try:
            for p in psutil.process_iter(["name", "cmdline"]):
                cmdline = " ".join(p.info.get("cmdline") or [])
                if "comfyui" in cmdline.lower() or "comfyui" in (p.info.get("name") or "").lower():
                    p.kill()
            time.sleep(5)
            logger.info("Watchdog: ComfyUI processes killed — needs manual restart")
        except Exception as e:
            logger.error(f"Watchdog: failed to restart ComfyUI: {e}")

    # ─── Status Report ─────────────────────────────────────

    def get_health_report(self) -> dict:
        """Get current health status of all services."""
        return {
            "ollama": self._check_ollama(),
            "comfyui": self._check_comfyui(),
            "gpu": self._check_gpu(),
            "disk": self._check_disk(),
            "ram": self._check_ram(),
            "pipeline": self._check_pipeline_progress(),
            "timestamp": datetime.now().isoformat(),
        }


class VRAMMonitor(threading.Thread):
    """
    Background thread that snapshots VRAM every N seconds.
    Alerts on high temperature or unexpected VRAM usage.
    """

    daemon = True

    def __init__(
        self,
        gpu_logger: "GPULogger",
        interval_sec: int = 5,
        temp_warning: int = 85,
        vram_warning_pct: float = 90.0,
        vram_critical_pct: float = 98.0,
        on_alert: Optional[Callable] = None,
    ):
        super().__init__(name="VRAMMonitor")
        self.gpu_logger = gpu_logger
        self.interval_sec = interval_sec
        self.temp_warning = temp_warning
        self.vram_warning_pct = vram_warning_pct
        self.vram_critical_pct = vram_critical_pct
        self._on_alert = on_alert or (lambda msg: logger.warning(msg))
        self.running = True
        self._active_model = "none"

    def set_active_model(self, model: str):
        self._active_model = model or "none"

    def run(self):
        logger.info("VRAMMonitor started (interval=%ds)", self.interval_sec)
        while self.running:
            try:
                self._tick()
            except Exception as e:
                logger.error(f"VRAMMonitor error: {e}")
            time.sleep(self.interval_sec)

    def stop(self):
        self.running = False

    def _tick(self):
        # Snapshot to CSV
        self.gpu_logger.snapshot_vram(self._active_model)

        # Check thresholds
        if not HAS_TORCH or not torch.cuda.is_available():
            return

        free, total = torch.cuda.mem_get_info()
        usage_pct = (1 - free / total) * 100 if total else 0

        if usage_pct > self.vram_critical_pct:
            self._on_alert(
                f"🚨 VRAM CRITICAL: {usage_pct:.1f}% used — "
                f"OOM imminent! Model: {self._active_model}"
            )
            # Force cache clear
            torch.cuda.empty_cache()
        elif usage_pct > self.vram_warning_pct:
            self._on_alert(
                f"⚠️ VRAM HIGH: {usage_pct:.1f}% used — "
                f"Model: {self._active_model}"
            )

        # Temperature check
        temp = self.gpu_logger._get_gpu_temp()
        if temp > self.temp_warning:
            self._on_alert(
                f"🌡️ GPU temp {temp}°C — throttling likely!"
            )
