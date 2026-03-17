"""
APScheduler wrapper for job scheduling.
Manages: analytics cron, daily cleanup, backups, quota reset checks.

All scheduled tasks are registered here — single source of truth
for "what runs when."
"""

import logging
from datetime import datetime
from typing import Callable, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

logger = logging.getLogger(__name__)


class FactoryScheduler:
    """
    APScheduler wrapper — manages all recurring tasks.

    Scheduled tasks (from settings.yaml):
    ├── WAL checkpoint:    every 5 min
    ├── Hot backup:        every 1 hour
    ├── Daily snapshot:    daily at 2:00 AM
    ├── Storage cleanup:   daily at 3:00 AM
    ├── Analytics capture: 24h, 48h, 7d, 30d after publish
    ├── Weekly report:     Sunday (configurable)
    ├── Monthly report:    1st of month (configurable)
    └── Watchdog:          every 30s (runs as thread, not APScheduler)
    """

    def __init__(self, config: dict):
        """
        Args:
            config: Full config dict from load_config().
        """
        self.config = config
        self.scheduler = BackgroundScheduler(
            timezone=config.get("settings", {}).get("factory", {}).get("timezone", "Asia/Baghdad")
        )
        self.scheduler.add_listener(self._on_job_event, EVENT_JOB_ERROR | EVENT_JOB_EXECUTED)
        self._jobs: dict[str, str] = {}  # name → job_id mapping
        logger.info("FactoryScheduler initialized")

    def start(self):
        """Start the scheduler."""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Scheduler started")

    def stop(self):
        """Gracefully stop the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)
            logger.info("Scheduler stopped")

    def add_interval(self, name: str, func: Callable, minutes: int = None,
                     hours: int = None, seconds: int = None, **kwargs):
        """Add an interval-based job."""
        trigger_kwargs = {}
        if minutes is not None:
            trigger_kwargs["minutes"] = minutes
        if hours is not None:
            trigger_kwargs["hours"] = hours
        if seconds is not None:
            trigger_kwargs["seconds"] = seconds

        job = self.scheduler.add_job(
            func, IntervalTrigger(**trigger_kwargs),
            id=name, name=name, replace_existing=True,
            kwargs=kwargs
        )
        self._jobs[name] = job.id
        logger.info(f"Scheduled interval job: {name} (every {trigger_kwargs})")

    def add_cron(self, name: str, func: Callable, hour: int = None,
                 minute: int = 0, day_of_week: str = None, day: int = None,
                 **kwargs):
        """Add a cron-based job."""
        trigger_kwargs = {"minute": minute}
        if hour is not None:
            trigger_kwargs["hour"] = hour
        if day_of_week is not None:
            trigger_kwargs["day_of_week"] = day_of_week
        if day is not None:
            trigger_kwargs["day"] = day

        job = self.scheduler.add_job(
            func, CronTrigger(**trigger_kwargs),
            id=name, name=name, replace_existing=True,
            kwargs=kwargs
        )
        self._jobs[name] = job.id
        logger.info(f"Scheduled cron job: {name} (trigger: {trigger_kwargs})")

    def add_one_shot(self, name: str, func: Callable, run_at: datetime, **kwargs):
        """Schedule a one-time job at a specific time."""
        job = self.scheduler.add_job(
            func, "date", run_date=run_at,
            id=name, name=name, replace_existing=True,
            kwargs=kwargs
        )
        self._jobs[name] = job.id
        logger.info(f"Scheduled one-shot job: {name} at {run_at}")

    def remove(self, name: str):
        """Remove a scheduled job by name."""
        if name in self._jobs:
            try:
                self.scheduler.remove_job(self._jobs[name])
                del self._jobs[name]
                logger.info(f"Removed scheduled job: {name}")
            except Exception as e:
                logger.warning(f"Failed to remove job {name}: {e}")

    def get_jobs(self) -> list[dict]:
        """Get all scheduled jobs with their next run time."""
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": str(job.next_run_time) if job.next_run_time else None,
                "trigger": str(job.trigger),
            })
        return jobs

    def setup_default_jobs(self, backup=None, storage=None, analytics=None):
        """
        Register all default scheduled jobs.

        Args:
            backup: DatabaseBackup instance
            storage: StorageManager instance
            analytics: Analytics capture callable
        """
        schedule_cfg = self.config.get("settings", {}).get("schedule", {})

        # Database backups
        if backup:
            self.add_interval("wal_checkpoint", backup.wal_checkpoint, minutes=5)
            self.add_interval("hot_backup", backup.hot_backup, hours=1)
            self.add_cron("daily_snapshot", backup.daily_snapshot, hour=2, minute=0)

        # Storage cleanup
        if storage:
            self.add_cron("daily_cleanup", storage.daily_cleanup, hour=3, minute=0)

        # Weekly report
        report_day = schedule_cfg.get("weekly_report_day", "sunday")
        day_map = {
            "monday": "mon", "tuesday": "tue", "wednesday": "wed",
            "thursday": "thu", "friday": "fri", "saturday": "sat", "sunday": "sun"
        }
        if analytics:
            self.add_cron(
                "weekly_report", analytics,
                hour=9, minute=0,
                day_of_week=day_map.get(report_day, "sun")
            )

            # Monthly report
            monthly_day = schedule_cfg.get("monthly_report_day", 1)
            self.add_cron("monthly_report", analytics, hour=9, minute=0, day=monthly_day)

        logger.info("Default scheduled jobs registered")

    def _on_job_event(self, event):
        """Handle scheduler job events (errors, completions)."""
        if event.exception:
            logger.error(
                f"Scheduled job failed: {event.job_id} — {event.exception}",
                exc_info=event.exception
            )
        else:
            logger.debug(f"Scheduled job completed: {event.job_id}")
