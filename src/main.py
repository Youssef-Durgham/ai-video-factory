"""
AI Video Factory — Main Entry Point.
"""
import sys, os
# Fix Windows cp1252 encoding for Unicode arrows/emojis in logs
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
"""

Initializes all components, wires up the event system,
starts the QueueRunner, and handles graceful shutdown.
"""

import asyncio
import logging
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("factory")


def setup_logging():
    """Configure structured logging."""
    log_dir = Path("logs/pipeline")
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / f"factory_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    # Reduce noise from libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def create_directories():
    """Ensure all required directories exist."""
    dirs = [
        "data", "output", "logs/gpu", "logs/pipeline", "logs/alerts",
        "data/seo_cache", "data/sfx_library", "data/ambient_library",
        "data/competitor_data", "data/performance_rules",
        "config/voices/embeddings",
    ]
    for d in dirs:
        Path(d).mkdir(parents=True, exist_ok=True)


class Factory:
    """
    Main factory orchestrator. Wires all components together
    and runs the production queue loop.
    """

    def __init__(self):
        from src.core.config import load_config
        from src.core.database import FactoryDB
        from src.core.gpu_manager import GPUMemoryManager
        from src.core.event_bus import EventBus, EventType
        from src.core.event_store import EventStore
        from src.core.pipeline_runner import PipelineRunner
        from src.core.job_queue import JobQueue, QueueRunner
        from src.core.telegram_bot import TelegramBot
        from src.core.watchdog import ServiceWatchdog
        from src.core.scheduler import FactoryScheduler
        from src.core.db_backup import DatabaseBackup as DBBackup

        # Load config
        self.config = load_config()
        settings = self.config["settings"]

        # Database
        self.db = FactoryDB(settings["database"]["path"])
        logger.info(f"Database initialized: {settings['database']['path']}")

        # GPU Manager
        self.gpu = GPUMemoryManager(settings["gpu"])
        logger.info(f"GPU manager ready: {settings['gpu'].get('device', 'cuda:0')}")

        # Event system
        self.event_bus = EventBus()
        self.event_store = EventStore(self.db)
        self.event_bus.subscribe_all(self.event_store.store)
        logger.info("Event bus + store wired")

        # Telegram bot
        self.telegram = TelegramBot(settings["telegram"])
        logger.info("Telegram bot initialized")

        # Pipeline runner
        self.pipeline = PipelineRunner()
        logger.info("Pipeline runner ready")

        # Job queue
        self.queue = JobQueue(self.db)
        self.queue_runner = QueueRunner(
            queue=self.queue,
            pipeline=self.pipeline,
            event_bus=self.event_bus,
        )
        logger.info("Job queue + runner ready")

        # Watchdog (disabled — false positives during model loading)
        self.watchdog = None
        logger.info("Service watchdog DISABLED (fix pending)")

        # Scheduler
        self.scheduler = FactoryScheduler(settings)
        self._setup_scheduled_jobs(settings)
        logger.info("Scheduler configured")

        # Backup
        self.backup = DBBackup(settings["database"]["path"])
        logger.info("DB backup system ready")

        # Shutdown flag
        self._shutdown = False

    def _setup_scheduled_jobs(self, settings):
        """Configure scheduled/cron jobs."""
        from src.core.db_backup import DatabaseBackup as DBBackup

        # Daily content calendar generation
        daily_time = settings.get("schedule", {}).get("daily_run_time", "06:00")
        daily_h, daily_m = (int(x) for x in daily_time.split(":"))
        self.scheduler.add_cron("content_calendar", self._run_content_calendar, hour=daily_h, minute=daily_m)

        # DB backup every 6 hours
        self.scheduler.add_interval("db_backup", self._run_backup, hours=6)

        # Analytics collection at configured intervals
        analytics_intervals = settings.get("schedule", {}).get("analytics_intervals", [24, 48, 168, 720])
        for interval_h in analytics_intervals:
            self.scheduler.add_interval(
                f"analytics_{interval_h}h",
                lambda h=interval_h: self._run_analytics(h),
                hours=interval_h,
            )

        # Competitor monitoring every 4 hours
        self.scheduler.add_interval("competitor_check", self._run_competitor_check, hours=4)

        # Watchdog health check every 5 minutes
        self.scheduler.add_interval("watchdog", self._run_watchdog, minutes=5)

        # Weekly report
        weekly_day = settings.get("schedule", {}).get("weekly_report_day", "sunday")
        self.scheduler.add_cron("weekly_report", self._run_weekly_report, day_of_week=weekly_day[:3], hour=9, minute=0)

    def start(self):
        """Start the factory."""
        logger.info("=" * 60)
        logger.info("  AI VIDEO FACTORY — Starting")
        logger.info("=" * 60)

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        try:
            # Start watchdog (disabled)
            if self.watchdog:
                self.watchdog.start()
                logger.info("✅ Watchdog started")
            else:
                logger.info("⏸️ Watchdog disabled")

            # Start scheduler
            self.scheduler.start()
            logger.info("✅ Scheduler started")

            # Start Telegram bot (async)
            self._start_telegram()
            logger.info("✅ Telegram bot started")

            # Startup notification
            self._notify_startup()

            # Run the queue loop (blocking)
            logger.info("✅ Queue runner starting — entering main loop")
            self._run_queue_loop()

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        except Exception as e:
            logger.critical(f"Fatal error: {e}", exc_info=True)
        finally:
            self.shutdown()

    def shutdown(self):
        """Graceful shutdown."""
        if self._shutdown:
            return
        self._shutdown = True

        logger.info("Shutting down factory...")

        try:
            self.scheduler.stop()
            logger.info("Scheduler stopped")
        except Exception as e:
            logger.warning(f"Scheduler shutdown error: {e}")

        try:
            if self.watchdog:
                self.watchdog.stop()
                logger.info("Watchdog stopped")
        except Exception as e:
            logger.warning(f"Watchdog shutdown error: {e}")

        try:
            self.gpu.cleanup()
            logger.info("GPU resources released")
        except Exception as e:
            logger.warning(f"GPU cleanup error: {e}")

        try:
            self.backup.run()
            logger.info("Final backup completed")
        except Exception as e:
            logger.warning(f"Final backup error: {e}")

        try:
            self._notify_shutdown()
        except Exception:
            pass

        logger.info("Factory shutdown complete")

    def _run_queue_loop(self):
        """Main queue processing loop."""
        while not self._shutdown:
            try:
                job_id = self.queue.get_next_job()

                if job_id is None:
                    time.sleep(30)
                    continue

                # Check if job is already being run by a callback thread
                from src.core.telegram_callbacks import _running_jobs
                if job_id in _running_jobs:
                    logger.info(f"Job {job_id} already running via callback — skipping")
                    time.sleep(10)
                    continue
                
                # Don't auto-start jobs that need user input
                # (voice without selected_voice_id, image_qa needing approval)
                job_data = self.db.get_job(job_id)
                job_status = job_data.get("status", "") if job_data else ""
                if job_status == "voice" and not job_data.get("selected_voice_id"):
                    # Voice phase needs user to select voice first
                    time.sleep(30)
                    continue

                logger.info(f"Processing job: {job_id}")
                _running_jobs.add(job_id)
                try:
                    result = self.pipeline.run_job(job_id)
                finally:
                    _running_jobs.discard(job_id)

                if result == "paused":
                    next_job = self.queue.can_interleave(job_id)
                    if next_job:
                        logger.info(f"Interleaving: {job_id} paused → starting {next_job}")
                        self.pipeline.run_job(next_job)
                elif result == "completed":
                    logger.info(f"Job {job_id} completed ✅")
                elif result == "blocked":
                    logger.warning(f"Job {job_id} blocked ⚠️")

            except Exception as e:
                logger.error(f"Queue loop error: {e}", exc_info=True)
                time.sleep(60)

    def _signal_handler(self, signum, frame):
        """Handle OS signals for graceful shutdown."""
        logger.info(f"Signal {signum} received — initiating shutdown")
        self._shutdown = True

    def _start_telegram(self):
        """Start Telegram bot in background."""
        try:
            import threading

            def _run_polling():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(self.telegram.start_polling())
                except Exception as e:
                    logger.warning(f"Telegram polling error: {e}")
                finally:
                    loop.close()

            t = threading.Thread(target=_run_polling, daemon=True)
            t.start()
        except Exception as e:
            logger.warning(f"Telegram bot start failed: {e}")

    def _notify_startup(self):
        """Send startup notification."""
        try:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(
                self.telegram.send("🏭 <b>AI Video Factory started</b>\n\n"
                                   f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            )
            loop.close()
        except Exception:
            pass

    def _notify_shutdown(self):
        """Send shutdown notification."""
        try:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(
                self.telegram.send("🛑 <b>AI Video Factory stopped</b>")
            )
            loop.close()
        except Exception:
            pass

    # ─── Scheduled Job Handlers ────────────────────────

    def _run_content_calendar(self):
        """Generate weekly content calendar for all channels."""
        from src.agents.core_agents.content_calendar import ContentCalendarAgent
        try:
            agent = ContentCalendarAgent(self.db, self.telegram)
            channels = self.config.get("channels", {}).get("channels", [])
            for ch in channels:
                agent.run(ch["id"])
        except Exception as e:
            logger.error(f"Content calendar error: {e}")

    def _run_backup(self):
        """Run database backup."""
        try:
            self.backup.run()
        except Exception as e:
            logger.error(f"Backup error: {e}")

    def _run_analytics(self, interval_hours: int):
        """Run analytics collection."""
        try:
            from src.phase9_intelligence.reporter import IntelligenceReporter
            reporter = IntelligenceReporter(self.db)
            reporter.run(interval_hours=interval_hours)
        except Exception as e:
            logger.error(f"Analytics error: {e}")

    def _run_competitor_check(self):
        """Run competitor monitoring."""
        try:
            from src.agents.optimization_agents.competitor_alert import CompetitorAlert
            agent = CompetitorAlert(self.db, telegram_bot=self.telegram)
            channels = self.config.get("channels", {}).get("channels", [])
            for ch in channels:
                agent.run(ch["id"])
        except Exception as e:
            logger.error(f"Competitor check error: {e}")

    def _run_watchdog(self):
        """Run watchdog health check."""
        try:
            if self.watchdog:
                self.watchdog.check_all()
        except Exception as e:
            logger.error(f"Watchdog error: {e}")

    def _run_weekly_report(self):
        """Generate weekly performance report."""
        try:
            from src.phase9_intelligence.reporter import IntelligenceReporter
            reporter = IntelligenceReporter(self.db)
            report = reporter.weekly_report()
            if self.telegram and report:
                import asyncio
                asyncio.get_event_loop().run_until_complete(
                    self.telegram.send(f"📊 <b>Weekly Report</b>\n\n{report}")
                )
        except Exception as e:
            logger.error(f"Weekly report error: {e}")


def main():
    """Main entry point."""
    setup_logging()
    create_directories()

    logger.info("AI Video Factory v1.0.0")
    logger.info(f"Python {sys.version}")
    logger.info(f"Working directory: {os.getcwd()}")

    # Check GPU
    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            vram = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            logger.info(f"GPU: {gpu_name} ({vram:.1f} GB)")
        else:
            logger.warning("No CUDA GPU detected!")
    except ImportError:
        logger.warning("PyTorch not installed — GPU features unavailable")

    factory = Factory()
    factory.start()


if __name__ == "__main__":
    main()
