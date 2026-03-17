"""
YouTube Data API v3 quota tracking.
10,000 units per day, resets at midnight Pacific Time.
Without tracking, quota exhaustion = silent failures.

One full publish cycle ≈ 2,501 units → max 4 videos/day.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from src.core.event_bus import EventBus, Event, EventType

logger = logging.getLogger(__name__)

# Pacific Time offset (UTC-8, or UTC-7 during DST)
PT_OFFSET = timedelta(hours=-8)


class QuotaTracker:
    """
    Tracks YouTube API quota usage in real-time.
    Prevents operations that would exceed quota.

    DB table: api_quota_log (already in FactoryDB schema).
    """

    DAILY_LIMIT = 10_000

    OPERATION_COSTS: dict[str, int] = {
        "videos.insert":        1600,
        "videos.update":        50,
        "videos.list":          1,
        "captions.insert":      400,
        "captions.list":        1,
        "channels.list":        1,
        "search.list":          100,
        "thumbnails.set":       50,
        "playlistItems.insert": 50,
        "playlistItems.list":   1,
        "analytics.query":      5,
    }

    # Cost of a full publish cycle
    PUBLISH_COST = 2501  # upload + thumbnail + 2 captions + playlist + verify

    def __init__(self, db, event_bus: Optional[EventBus] = None,
                 telegram=None, reserve: int = 3000):
        """
        Args:
            db: FactoryDB instance.
            event_bus: For emitting quota events.
            telegram: TelegramBot for alerts.
            reserve: Units to keep in reserve (from settings.yaml).
        """
        self.db = db
        self.event_bus = event_bus
        self.telegram = telegram
        self.reserve = reserve
        logger.info("QuotaTracker initialized")

    def can_afford(self, operation: str) -> bool:
        """Check if we have enough quota for this operation."""
        cost = self.OPERATION_COSTS.get(operation, 10)
        used_today = self._get_today_usage()
        remaining = self.DAILY_LIMIT - used_today

        if remaining < cost:
            logger.warning(
                f"Quota insufficient: need {cost}, have {remaining}"
            )
            return False
        return True

    def can_publish(self) -> bool:
        """Check if we have enough quota for a full publish cycle."""
        used_today = self._get_today_usage()
        remaining = self.DAILY_LIMIT - used_today
        return remaining >= self.PUBLISH_COST

    def record_usage(self, operation: str, job_id: str = None,
                     status: int = 200):
        """
        Record an API call's quota usage.
        Emits warning when quota is getting low.
        """
        cost = self.OPERATION_COSTS.get(operation, 10)
        today = self._pacific_today()

        self.db.conn.execute(
            "INSERT INTO api_quota_log (date, operation, units_used, job_id, response_status) "
            "VALUES (?, ?, ?, ?, ?)",
            (today, operation, cost, job_id, status)
        )
        self.db.conn.commit()

        remaining = self.DAILY_LIMIT - self._get_today_usage()

        # Alert thresholds
        if remaining < 2000 and self.event_bus:
            self.event_bus.emit(Event(
                type=EventType.QUOTA_LOW,
                data={
                    "remaining": remaining,
                    "used": self.DAILY_LIMIT - remaining,
                    "operation": operation,
                },
                source="quota_tracker",
                severity="warn",
            ))

        if remaining < 2000 and self.telegram:
            try:
                import asyncio
                asyncio.get_event_loop().run_until_complete(
                    self.telegram.alert(
                        f"⚠️ YouTube quota low: {remaining:,}/10,000 remaining"
                    )
                )
            except Exception:
                pass

        if remaining <= 0 and self.event_bus:
            self.event_bus.emit(Event(
                type=EventType.QUOTA_EXHAUSTED,
                data={"date": today},
                source="quota_tracker",
                severity="error",
            ))

    def get_status(self) -> dict:
        """Current quota status — for /quota command."""
        used = self._get_today_usage()
        remaining = self.DAILY_LIMIT - used
        return {
            "date": self._pacific_today(),
            "used": used,
            "remaining": remaining,
            "percent_used": round(used / self.DAILY_LIMIT * 100, 1),
            "max_videos_remaining": max(0, remaining // self.PUBLISH_COST),
            "reset_time": "midnight Pacific Time",
            "reserve": self.reserve,
            "effective_remaining": max(0, remaining - self.reserve),
        }

    def schedule_if_needed(self, operation: str, job_id: str) -> str:
        """
        If quota insufficient now, schedule for after midnight PT reset.

        Returns: 'now' | 'scheduled:YYYY-MM-DDTHH:MM:SS'
        """
        if self.can_afford(operation):
            return "now"

        reset_time = self._next_reset_time()
        scheduled_at = reset_time.isoformat()

        if self.telegram:
            try:
                import asyncio
                asyncio.get_event_loop().run_until_complete(
                    self.telegram.send(
                        f"⏳ YouTube quota exhausted.\n"
                        f"Operation: {operation}\n"
                        f"Job: {job_id}\n"
                        f"Scheduled after quota reset: {scheduled_at}"
                    )
                )
            except Exception:
                pass

        logger.info(
            f"Quota insufficient for {operation}. "
            f"Scheduled for {scheduled_at}"
        )
        return f"scheduled:{scheduled_at}"

    def get_today_breakdown(self) -> list[dict]:
        """Get breakdown of today's usage by operation — for detailed /quota."""
        today = self._pacific_today()
        rows = self.db.conn.execute("""
            SELECT operation, SUM(units_used) as total_units, COUNT(*) as call_count
            FROM api_quota_log
            WHERE date = ?
            GROUP BY operation
            ORDER BY total_units DESC
        """, (today,)).fetchall()
        return [dict(r) for r in rows]

    def get_weekly_usage(self) -> list[dict]:
        """Get last 7 days of quota usage."""
        rows = self.db.conn.execute("""
            SELECT date, SUM(units_used) as total_units, COUNT(*) as call_count
            FROM api_quota_log
            WHERE date >= date('now', '-7 days')
            GROUP BY date
            ORDER BY date DESC
        """).fetchall()
        return [dict(r) for r in rows]

    # ─── Private Helpers ───────────────────────────────

    def _get_today_usage(self) -> int:
        """Get total quota used today (Pacific Time)."""
        today = self._pacific_today()
        row = self.db.conn.execute(
            "SELECT COALESCE(SUM(units_used), 0) FROM api_quota_log WHERE date = ?",
            (today,)
        ).fetchone()
        return row[0]

    def _pacific_today(self) -> str:
        """Get current date in Pacific Time (YouTube quota reset timezone)."""
        # Use fixed PT offset; for DST-aware, use pytz/zoneinfo
        try:
            from zoneinfo import ZoneInfo
            pt = ZoneInfo("America/Los_Angeles")
        except ImportError:
            pt = timezone(PT_OFFSET)
        return datetime.now(pt).strftime("%Y-%m-%d")

    def _next_reset_time(self) -> datetime:
        """Get the next midnight Pacific Time (quota reset)."""
        try:
            from zoneinfo import ZoneInfo
            pt = ZoneInfo("America/Los_Angeles")
        except ImportError:
            pt = timezone(PT_OFFSET)

        now_pt = datetime.now(pt)
        # Next midnight PT + 5 min safety margin
        tomorrow_pt = now_pt.replace(
            hour=0, minute=5, second=0, microsecond=0
        ) + timedelta(days=1)
        return tomorrow_pt
