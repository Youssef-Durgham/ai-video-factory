"""
Manages disk space across the entire pipeline.
Policies: what to keep, what to archive, what to delete, and when.

Each video produces ~5-10GB intermediate files. Without cleanup,
disk fills in days.
"""

import os
import glob
import shutil
import logging
import fnmatch
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

from src.core.event_bus import EventBus, Event, EventType
from src.core.config import resolve_path

logger = logging.getLogger(__name__)


class StorageManager:
    """
    Disk cleanup with tiered policies.

    Called by:
    - PipelineRunner after COMPOSE → delete overlay MOVs (DELETE_AFTER_COMPOSE)
    - Cron job daily at 3 AM → apply 3-day and 7-day policies
    - Manual → full_clean (keeps only KEEP_FOREVER)
    - Watchdog → emergency_cleanup when disk critically low
    """

    # ─── Cleanup Policies ──────────────────────────────

    KEEP_FOREVER = [
        "final/final.mp4",
        "final/final_metadata.json",
        "thumbnails/*_final.*",
        "subtitles/*.ass",
        "subtitles/*.srt",
    ]

    ARCHIVE_AFTER_7D = [
        "images/*_final.png",
        "audio/voice/*.wav",
        "qa/reports/*.json",
    ]

    DELETE_AFTER_3D = [
        "images/*_v[0-9]*.png",
        "images_graded/",
        "videos/*_v[0-9]*.mp4",
        "overlays/",
        "compose/*_v[0-9]*.mp4",
        "qa/keyframes/",
    ]

    DELETE_AFTER_COMPOSE = [
        "overlays/*.mov",
    ]

    def __init__(self, config: dict, event_bus: Optional[EventBus] = None,
                 telegram=None):
        """
        Args:
            config: Full config dict from load_config().
            event_bus: For emitting storage events.
            telegram: TelegramBot for alerts.
        """
        self.config = config
        self.event_bus = event_bus
        self.telegram = telegram

        storage_cfg = config.get("settings", {}).get("storage", {})
        self.output_dir = str(resolve_path(storage_cfg.get("output_dir", "output")))
        self.archive_dir = str(resolve_path(storage_cfg.get("archive_dir", "archive")))
        self.max_disk_gb = storage_cfg.get("max_disk_usage_gb", 500)
        self.emergency_free_gb = storage_cfg.get("emergency_free_gb", 50)

        os.makedirs(self.archive_dir, exist_ok=True)
        logger.info(f"StorageManager initialized: output={self.output_dir}")

    def cleanup_job(self, job_id: str, policy: str = "post_publish"):
        """
        Run cleanup for a specific job.

        Policies:
        - 'post_compose': Delete overlay MOVs immediately
        - 'post_publish': Delete 3-day items
        - 'archive': Archive 7-day items
        - 'full_clean': Keep only KEEP_FOREVER
        """
        job_dir = os.path.join(self.output_dir, job_id)
        if not os.path.exists(job_dir):
            logger.warning(f"Job directory not found: {job_dir}")
            return

        freed_bytes = 0

        if policy == "post_compose":
            freed_bytes = self._delete_patterns(job_dir, self.DELETE_AFTER_COMPOSE)

        elif policy == "post_publish":
            freed_bytes = self._delete_patterns(job_dir, self.DELETE_AFTER_3D)

        elif policy == "archive":
            freed_bytes = self._archive_patterns(job_id, job_dir, self.ARCHIVE_AFTER_7D)

        elif policy == "full_clean":
            # Delete everything except KEEP_FOREVER
            freed_bytes = self._full_clean(job_dir)

        freed_mb = freed_bytes / (1024 * 1024)
        if freed_mb > 0:
            logger.info(f"Cleanup {policy} for {job_id}: freed {freed_mb:.1f}MB")
            if self.event_bus:
                self.event_bus.emit(Event(
                    type=EventType.STORAGE_CLEANED,
                    job_id=job_id,
                    data={"policy": policy, "freed_mb": round(freed_mb, 1)},
                    source="storage_manager",
                ))

    def daily_cleanup(self):
        """
        Daily cleanup job (runs at 3 AM via scheduler).
        Applies time-based policies to all jobs.
        """
        now = datetime.now()
        total_freed = 0

        if not os.path.exists(self.output_dir):
            return

        for job_dir_name in os.listdir(self.output_dir):
            job_dir = os.path.join(self.output_dir, job_dir_name)
            if not os.path.isdir(job_dir):
                continue

            # Get job age from directory modification time
            dir_mtime = datetime.fromtimestamp(os.path.getmtime(job_dir))
            age_days = (now - dir_mtime).days

            if age_days >= 7:
                total_freed += self._archive_patterns(
                    job_dir_name, job_dir, self.ARCHIVE_AFTER_7D
                )

            if age_days >= 3:
                total_freed += self._delete_patterns(job_dir, self.DELETE_AFTER_3D)

        freed_mb = total_freed / (1024 * 1024)
        if freed_mb > 0:
            logger.info(f"Daily cleanup freed {freed_mb:.1f}MB total")

    def get_disk_usage(self) -> dict:
        """
        Get disk usage report for /disk command.

        Returns dict with total_gb, by_job, by_type, etc.
        """
        result = {
            "total_gb": 0.0,
            "by_job": {},
            "by_type": {"images": 0, "videos": 0, "audio": 0, "overlays": 0, "other": 0},
            "oldest_uncleaned_job": None,
            "estimated_days_until_full": None,
            "job_count": 0,
        }

        if not os.path.exists(self.output_dir):
            return result

        oldest_mtime = None
        for job_dir_name in os.listdir(self.output_dir):
            job_dir = os.path.join(self.output_dir, job_dir_name)
            if not os.path.isdir(job_dir):
                continue

            result["job_count"] += 1
            job_size = self._dir_size(job_dir)
            job_gb = job_size / (1024 ** 3)
            result["by_job"][job_dir_name] = round(job_gb, 3)
            result["total_gb"] += job_gb

            # Track oldest
            mtime = os.path.getmtime(job_dir)
            if oldest_mtime is None or mtime < oldest_mtime:
                oldest_mtime = mtime
                result["oldest_uncleaned_job"] = job_dir_name

            # Categorize by type
            for root, _, files in os.walk(job_dir):
                rel = os.path.relpath(root, job_dir).replace("\\", "/")
                for f in files:
                    fsize = os.path.getsize(os.path.join(root, f))
                    if rel.startswith("images"):
                        result["by_type"]["images"] += fsize
                    elif rel.startswith("videos"):
                        result["by_type"]["videos"] += fsize
                    elif rel.startswith("audio"):
                        result["by_type"]["audio"] += fsize
                    elif rel.startswith("overlays"):
                        result["by_type"]["overlays"] += fsize
                    else:
                        result["by_type"]["other"] += fsize

        # Convert by_type to GB
        for k in result["by_type"]:
            result["by_type"][k] = round(result["by_type"][k] / (1024 ** 3), 3)

        result["total_gb"] = round(result["total_gb"], 2)

        # Estimate days until full
        try:
            import psutil
            disk = psutil.disk_usage(self.output_dir)
            free_gb = disk.free / (1024 ** 3)
            if result["job_count"] > 0 and result["total_gb"] > 0:
                avg_per_job = result["total_gb"] / result["job_count"]
                if avg_per_job > 0:
                    result["estimated_days_until_full"] = round(free_gb / avg_per_job, 1)
        except Exception:
            pass

        return result

    def emergency_cleanup(self, target_free_gb: float = None):
        """
        When disk is critically low:
        1. Delete all DELETE_AFTER_3D for ALL jobs (not just old ones)
        2. Archive all ARCHIVE_AFTER_7D immediately
        3. If still not enough → alert via Telegram
        """
        if target_free_gb is None:
            target_free_gb = self.emergency_free_gb

        logger.warning(f"Emergency cleanup triggered! Target: {target_free_gb}GB free")
        total_freed = 0

        if not os.path.exists(self.output_dir):
            return

        # Phase 1: Delete all 3-day items from ALL jobs
        for job_dir_name in os.listdir(self.output_dir):
            job_dir = os.path.join(self.output_dir, job_dir_name)
            if os.path.isdir(job_dir):
                total_freed += self._delete_patterns(job_dir, self.DELETE_AFTER_3D)
                total_freed += self._delete_patterns(job_dir, self.DELETE_AFTER_COMPOSE)

        # Check if enough
        try:
            import psutil
            free_gb = psutil.disk_usage(self.output_dir).free / (1024 ** 3)
            if free_gb >= target_free_gb:
                logger.info(
                    f"Emergency cleanup sufficient: {free_gb:.1f}GB free "
                    f"(freed {total_freed / (1024**3):.1f}GB)"
                )
                return
        except Exception:
            pass

        # Phase 2: Archive 7-day items immediately
        for job_dir_name in os.listdir(self.output_dir):
            job_dir = os.path.join(self.output_dir, job_dir_name)
            if os.path.isdir(job_dir):
                total_freed += self._archive_patterns(
                    job_dir_name, job_dir, self.ARCHIVE_AFTER_7D
                )

        freed_gb = total_freed / (1024 ** 3)
        logger.info(f"Emergency cleanup freed {freed_gb:.1f}GB total")

        # Alert if still not enough
        if self.telegram:
            try:
                import asyncio
                asyncio.get_event_loop().run_until_complete(
                    self.telegram.alert(
                        f"🚨 Emergency disk cleanup completed.\n"
                        f"Freed: {freed_gb:.1f}GB\n"
                        f"Manual cleanup may be needed."
                    )
                )
            except Exception:
                pass

        if self.event_bus:
            self.event_bus.emit(Event(
                type=EventType.DISK_LOW,
                data={"freed_gb": round(freed_gb, 2), "emergency": True},
                source="storage_manager",
                severity="warn",
            ))

    # ─── Private Helpers ───────────────────────────────

    def _delete_patterns(self, job_dir: str, patterns: list[str]) -> int:
        """Delete files matching patterns. Returns bytes freed."""
        freed = 0
        for pattern in patterns:
            target = os.path.join(job_dir, pattern)
            if pattern.endswith("/"):
                # Directory pattern
                dir_path = os.path.join(job_dir, pattern.rstrip("/"))
                if os.path.isdir(dir_path):
                    freed += self._dir_size(dir_path)
                    shutil.rmtree(dir_path, ignore_errors=True)
            else:
                for f in glob.glob(target):
                    if os.path.isfile(f) and not self._is_protected(job_dir, f):
                        freed += os.path.getsize(f)
                        os.remove(f)
        return freed

    def _archive_patterns(self, job_id: str, job_dir: str,
                          patterns: list[str]) -> int:
        """Archive files matching patterns. Returns bytes freed from output."""
        freed = 0
        archive_job_dir = os.path.join(self.archive_dir, job_id)

        for pattern in patterns:
            for f in glob.glob(os.path.join(job_dir, pattern)):
                if os.path.isfile(f) and not self._is_protected(job_dir, f):
                    rel = os.path.relpath(f, job_dir)
                    dest = os.path.join(archive_job_dir, rel)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    shutil.move(f, dest)
                    freed += os.path.getsize(dest)
        return freed

    def _full_clean(self, job_dir: str) -> int:
        """Delete everything except KEEP_FOREVER patterns."""
        freed = 0
        for root, dirs, files in os.walk(job_dir, topdown=False):
            for f in files:
                full_path = os.path.join(root, f)
                if not self._is_protected(job_dir, full_path):
                    freed += os.path.getsize(full_path)
                    os.remove(full_path)
            # Remove empty directories
            for d in dirs:
                dir_path = os.path.join(root, d)
                if os.path.isdir(dir_path) and not os.listdir(dir_path):
                    os.rmdir(dir_path)
        return freed

    def _is_protected(self, job_dir: str, file_path: str) -> bool:
        """Check if file matches any KEEP_FOREVER pattern."""
        rel = os.path.relpath(file_path, job_dir).replace("\\", "/")
        for pattern in self.KEEP_FOREVER:
            if fnmatch.fnmatch(rel, pattern):
                return True
        return False

    def _dir_size(self, path: str) -> int:
        """Calculate total size of a directory."""
        total = 0
        for root, _, files in os.walk(path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
        return total
