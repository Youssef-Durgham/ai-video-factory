"""
GPU Precision Logger — logs every GPU operation with timestamps and VRAM state.
In a single-GPU environment, one unlogged VRAM leak = full pipeline crash.

Outputs:
  - Human-readable .log file
  - Structured .jsonl event file  
  - VRAM timeline .csv (for graphs/analysis)
"""

import logging
import time
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


class GPULogger:
    """
    Precision logging for every GPU model operation.
    Every load, unload, generation, OOM, and leak is recorded.
    """

    def __init__(self, job_id: str, log_dir: str = "logs/gpu"):
        self.job_id = job_id
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Human-readable log
        self.file_logger = logging.getLogger(f"gpu.{job_id}")
        self.file_logger.setLevel(logging.DEBUG)
        # Prevent duplicate handlers on re-instantiation
        self.file_logger.handlers.clear()
        handler = logging.FileHandler(
            self.log_dir / f"{self.session_id}_{job_id}.log",
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s.%(msecs)03d | %(levelname)-7s | %(message)s",
            datefmt="%H:%M:%S",
        ))
        self.file_logger.addHandler(handler)

        # Structured event log (JSONL)
        self.events_path = self.log_dir / f"{self.session_id}_{job_id}_events.jsonl"

        # VRAM snapshot CSV
        self.snapshots_path = self.log_dir / f"{self.session_id}_{job_id}_vram.csv"
        self._init_vram_csv()

    # ─── VRAM Introspection ────────────────────────────────

    def _get_vram_state(self) -> dict:
        """Snapshot current VRAM state."""
        if not HAS_TORCH or not torch.cuda.is_available():
            return {
                "total_gb": 0, "free_gb": 0, "used_gb": 0,
                "allocated_gb": 0, "reserved_gb": 0, "fragmented_gb": 0,
                "usage_pct": 0, "temp_c": -1,
            }
        free, total = torch.cuda.mem_get_info()
        allocated = torch.cuda.memory_allocated()
        reserved = torch.cuda.memory_reserved()
        return {
            "total_gb": round(total / 1e9, 2),
            "free_gb": round(free / 1e9, 2),
            "used_gb": round((total - free) / 1e9, 2),
            "allocated_gb": round(allocated / 1e9, 2),
            "reserved_gb": round(reserved / 1e9, 2),
            "fragmented_gb": round((reserved - allocated) / 1e9, 2),
            "usage_pct": round((1 - free / total) * 100, 1) if total else 0,
            "temp_c": self._get_gpu_temp(),
        }

    def _get_gpu_temp(self) -> int:
        """GPU temperature via nvidia-smi."""
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=5,
            )
            return int(result.stdout.strip())
        except Exception:
            return -1

    # ─── Structured Event Logging ──────────────────────────

    def _log_event(self, event_type: str, data: dict):
        """Append structured event to JSONL file."""
        event = {
            "timestamp": datetime.now().isoformat(),
            "job_id": self.job_id,
            "event": event_type,
            "vram": self._get_vram_state(),
            **data,
        }
        with open(self.events_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    # ─── Model Lifecycle ───────────────────────────────────

    def log_model_load_start(
        self, model_name: str, model_type: str, expected_vram_gb: float
    ) -> float:
        """Log model load start. Returns start timestamp for duration calc."""
        vram = self._get_vram_state()
        self.file_logger.info(
            f"🔄 LOAD START | model={model_name} | type={model_type} | "
            f"expected_vram={expected_vram_gb}GB | "
            f"available_vram={vram['free_gb']}GB | temp={vram['temp_c']}°C"
        )
        if vram["free_gb"] < expected_vram_gb:
            self.file_logger.critical(
                f"⛔ INSUFFICIENT VRAM! Need {expected_vram_gb}GB "
                f"but only {vram['free_gb']}GB free!"
            )
        self._log_event("model_load_start", {
            "model": model_name, "type": model_type,
            "expected_vram_gb": expected_vram_gb,
        })
        return time.time()

    def log_model_load_end(
        self, model_name: str, start_time: float, success: bool
    ):
        elapsed = round(time.time() - start_time, 2)
        vram = self._get_vram_state()
        status = "✅ SUCCESS" if success else "❌ FAILED"
        self.file_logger.info(
            f"{status} LOAD | model={model_name} | "
            f"took={elapsed}s | vram_used={vram['used_gb']}GB "
            f"({vram['usage_pct']}%) | temp={vram['temp_c']}°C"
        )
        self._log_event("model_load_end", {
            "model": model_name, "success": success, "elapsed_sec": elapsed,
        })

    def log_model_unload_start(self, model_name: str) -> float:
        vram = self._get_vram_state()
        self.file_logger.info(
            f"🗑️ UNLOAD START | model={model_name} | "
            f"vram_before={vram['used_gb']}GB ({vram['usage_pct']}%)"
        )
        self._log_event("model_unload_start", {"model": model_name})
        return time.time()

    def log_model_unload_end(self, model_name: str, start_time: float):
        elapsed = round(time.time() - start_time, 2)
        vram = self._get_vram_state()
        if vram["usage_pct"] > 15:
            self.file_logger.critical(
                f"🚨 VRAM LEAK DETECTED! After unloading {model_name}: "
                f"still {vram['used_gb']}GB used ({vram['usage_pct']}%)"
            )
            self._log_event("vram_leak_detected", {
                "model": model_name, "leaked_gb": vram["used_gb"],
            })
        else:
            self.file_logger.info(
                f"✅ UNLOAD COMPLETE | model={model_name} | "
                f"took={elapsed}s | vram_after={vram['used_gb']}GB "
                f"({vram['usage_pct']}%)"
            )
        self._log_event("model_unload_end", {
            "model": model_name, "elapsed_sec": elapsed,
        })

    # ─── Generation Tasks ──────────────────────────────────

    def log_generation_start(
        self, model_name: str, task: str, batch_size: int
    ) -> float:
        vram = self._get_vram_state()
        self.file_logger.info(
            f"⚡ GEN START | model={model_name} | task={task} | "
            f"batch={batch_size} | vram={vram['used_gb']}GB | "
            f"temp={vram['temp_c']}°C"
        )
        self._log_event("generation_start", {
            "model": model_name, "task": task, "batch_size": batch_size,
        })
        return time.time()

    def log_generation_progress(
        self, model_name: str, current: int, total: int
    ):
        vram = self._get_vram_state()
        pct = round(current / total * 100, 1) if total else 0
        self.file_logger.info(
            f"📊 PROGRESS | model={model_name} | {current}/{total} ({pct}%) | "
            f"vram={vram['used_gb']}GB ({vram['usage_pct']}%) | "
            f"temp={vram['temp_c']}°C"
        )
        if vram["usage_pct"] > 85:
            self.file_logger.warning(
                f"⚠️ VRAM HIGH during generation! {vram['usage_pct']}% — potential leak"
            )
        if vram["temp_c"] > 85:
            self.file_logger.warning(
                f"🌡️ GPU HOT! {vram['temp_c']}°C — may throttle"
            )
        self._log_event("generation_progress", {
            "model": model_name, "current": current, "total": total,
        })

    def log_generation_end(
        self, model_name: str, task: str, start_time: float,
        success: bool, items_produced: int,
    ):
        elapsed = round(time.time() - start_time, 2)
        rate = round(items_produced / elapsed * 60, 1) if elapsed > 0 else 0
        vram = self._get_vram_state()
        status = "✅" if success else "❌"
        self.file_logger.info(
            f"{status} GEN END | model={model_name} | task={task} | "
            f"produced={items_produced} | took={elapsed}s | rate={rate}/min | "
            f"vram={vram['used_gb']}GB | temp={vram['temp_c']}°C"
        )
        self._log_event("generation_end", {
            "model": model_name, "task": task, "success": success,
            "items_produced": items_produced, "elapsed_sec": elapsed,
            "rate_per_min": rate,
        })

    # ─── Emergency / Flush ─────────────────────────────────

    def log_vram_flush(self, reason: str, before_gb: float, after_gb: float):
        self.file_logger.warning(
            f"🔧 VRAM FLUSH | reason={reason} | "
            f"before={before_gb}GB → after={after_gb}GB | "
            f"freed={round(before_gb - after_gb, 2)}GB"
        )
        self._log_event("vram_flush", {
            "reason": reason, "before_gb": before_gb, "after_gb": after_gb,
        })

    def log_oom_event(self, model_name: str, task: str):
        vram = self._get_vram_state()
        self.file_logger.critical(
            f"💥 OOM EVENT | model={model_name} | task={task} | "
            f"vram={vram['used_gb']}GB/{vram['total_gb']}GB | "
            f"temp={vram['temp_c']}°C"
        )
        self._log_event("oom_event", {"model": model_name, "task": task})

    def log_gpu_reset(self, reason: str):
        self.file_logger.critical(
            f"🔴 GPU RESET | reason={reason}"
        )
        self._log_event("gpu_reset", {"reason": reason})

    # ─── VRAM Continuous Snapshots ─────────────────────────

    def _init_vram_csv(self):
        with open(self.snapshots_path, "w", encoding="utf-8") as f:
            f.write(
                "timestamp,used_gb,free_gb,allocated_gb,reserved_gb,"
                "fragmented_gb,usage_pct,temp_c,active_model\n"
            )

    def snapshot_vram(self, active_model: str = "none"):
        """Called periodically by VRAMMonitor — builds continuous timeline."""
        vram = self._get_vram_state()
        with open(self.snapshots_path, "a", encoding="utf-8") as f:
            f.write(
                f"{datetime.now().isoformat()},"
                f"{vram['used_gb']},{vram['free_gb']},"
                f"{vram['allocated_gb']},{vram['reserved_gb']},"
                f"{vram['fragmented_gb']},{vram['usage_pct']},"
                f"{vram['temp_c']},{active_model}\n"
            )

    # ─── Leak Detection ────────────────────────────────────

    def check_vram_leak(self, total_vram_gb: float = 24.0) -> bool:
        """
        Verify VRAM is actually freed after unload.
        Returns True if leak detected (>15% still used).
        """
        vram = self._get_vram_state()
        if vram["usage_pct"] > 15:
            self.file_logger.critical(
                f"🚨 VRAM LEAK CHECK FAILED | "
                f"{vram['used_gb']}GB still used ({vram['usage_pct']}%) | "
                f"Expected <15% after full unload"
            )
            self._log_event("vram_leak_check_failed", {
                "used_gb": vram["used_gb"],
                "usage_pct": vram["usage_pct"],
            })
            return True
        self.file_logger.info(
            f"✅ VRAM LEAK CHECK PASSED | "
            f"{vram['used_gb']}GB used ({vram['usage_pct']}%)"
        )
        return False
