"""
Job queue — manages multiple jobs on a single GPU.
Only ONE job can use the GPU at a time, but multiple jobs
can be in different lifecycle stages.

Key insight: some phases need GPU, some don't.
We can interleave GPU work from different jobs.

Priority levels:
  P0 (urgent):    Trending topic hijack (time-sensitive)
  P1 (normal):    Scheduled content calendar videos
  P2 (background): Re-optimization, shorts generation
"""

import time
import logging
from datetime import datetime
from typing import Optional

from src.core.event_bus import EventBus, Event, EventType

logger = logging.getLogger(__name__)


class JobQueue:
    """
    Queue with priority levels and interleaving support.

    When a job pauses for human review, another job can use the GPU.
    This maximizes GPU utilization.

    DB table: job_queue (already in FactoryDB schema).
    """

    def __init__(self, db, event_bus: Optional[EventBus] = None,
                 telegram=None):
        """
        Args:
            db: FactoryDB instance.
            event_bus: For emitting queue events.
            telegram: TelegramBot instance for notifications.
        """
        self.db = db
        self.event_bus = event_bus
        self.telegram = telegram

    def enqueue(self, job_id: str, priority: int = 1,
                scheduled_start: str = None, channel_id: str = None) -> int:
        """
        Add job to queue. Returns queue position.

        Args:
            job_id: Job ID to enqueue.
            priority: 0=urgent, 1=normal, 2=background.
            scheduled_start: ISO timestamp — don't start before this time.
            channel_id: YouTube channel ID for the job.
        """
        position = self._next_position(priority)
        self.db.conn.execute("""
            INSERT OR REPLACE INTO job_queue
                (job_id, priority, position, scheduled_start, channel_id)
            VALUES (?, ?, ?, ?, ?)
        """, (job_id, priority, position, scheduled_start, channel_id))
        self.db.conn.commit()

        priority_labels = {0: "🔴 Urgent", 1: "🟢 Normal", 2: "🔵 Background"}
        label = priority_labels.get(priority, f"P{priority}")

        if self.telegram:
            try:
                import asyncio
                asyncio.get_event_loop().run_until_complete(
                    self.telegram.send(
                        f"📋 Job queued: {job_id}\n"
                        f"Priority: {label}\n"
                        f"Position: #{position}"
                    )
                )
            except Exception:
                pass

        if self.event_bus:
            self.event_bus.emit(Event(
                type=EventType.JOB_CREATED,
                job_id=job_id,
                data={"priority": priority, "position": position},
                source="job_queue"
            ))

        logger.info(f"Job enqueued: {job_id} | priority={priority} | position={position}")
        return position

    def get_next_job(self) -> Optional[str]:
        """
        Get the next job that should run.

        Logic:
        1. P0 (urgent) jobs first
        2. Then P1 by position
        3. Then P2 if nothing else
        4. Skip jobs whose scheduled_start is in the future
        5. Skip completed/cancelled jobs
        """
        row = self.db.conn.execute("""
            SELECT jq.job_id FROM job_queue jq
            JOIN jobs j ON jq.job_id = j.id
            WHERE j.status NOT IN ('published', 'cancelled', 'complete')
            AND (jq.scheduled_start IS NULL OR jq.scheduled_start <= CURRENT_TIMESTAMP)
            ORDER BY jq.priority ASC, jq.position ASC
            LIMIT 1
        """).fetchone()
        return row["job_id"] if row else None

    def can_interleave(self, current_job_id: str) -> Optional[str]:
        """
        If current job is paused (manual_review, blocked),
        can another job use the GPU?

        Returns: job_id of interleave candidate, or None.
        """
        current = self.db.get_job(current_job_id)
        if not current or current["status"] not in ("manual_review", "blocked"):
            return None

        # Find next queued job that isn't the current one
        row = self.db.conn.execute("""
            SELECT jq.job_id FROM job_queue jq
            JOIN jobs j ON jq.job_id = j.id
            WHERE j.status NOT IN ('published', 'cancelled', 'complete',
                                   'manual_review', 'blocked')
            AND jq.job_id != ?
            AND (jq.scheduled_start IS NULL OR jq.scheduled_start <= CURRENT_TIMESTAMP)
            ORDER BY jq.priority ASC, jq.position ASC
            LIMIT 1
        """, (current_job_id,)).fetchone()
        return row["job_id"] if row else None

    def reorder(self, job_id: str, new_position: int):
        """Move job to new position in queue."""
        self.db.conn.execute(
            "UPDATE job_queue SET position = ? WHERE job_id = ?",
            (new_position, job_id)
        )
        self.db.conn.commit()
        logger.info(f"Job {job_id} moved to position {new_position}")

    def promote(self, job_id: str):
        """Promote to P0 (urgent). Used by trending_hijack agent."""
        self.db.conn.execute(
            "UPDATE job_queue SET priority = 0, position = 0 WHERE job_id = ?",
            (job_id,)
        )
        self.db.conn.commit()
        logger.info(f"Job {job_id} promoted to P0 urgent")

        if self.event_bus:
            self.event_bus.emit(Event(
                type=EventType.JOB_STATUS_CHANGED,
                job_id=job_id,
                data={"action": "promoted_to_urgent"},
                source="job_queue"
            ))

    def remove(self, job_id: str):
        """Remove job from queue."""
        self.db.conn.execute("DELETE FROM job_queue WHERE job_id = ?", (job_id,))
        self.db.conn.commit()
        logger.info(f"Job {job_id} removed from queue")

    def get_queue_status(self) -> list[dict]:
        """Get full queue status for /queue command."""
        rows = self.db.conn.execute("""
            SELECT jq.*, j.status, j.topic, j.channel_id as job_channel
            FROM job_queue jq
            JOIN jobs j ON jq.job_id = j.id
            WHERE j.status NOT IN ('published', 'cancelled', 'complete')
            ORDER BY jq.priority ASC, jq.position ASC
        """).fetchall()
        return [dict(r) for r in rows]

    def _next_position(self, priority: int) -> int:
        """Get next position number for a given priority level."""
        row = self.db.conn.execute(
            "SELECT COALESCE(MAX(position), 0) + 1 as next_pos "
            "FROM job_queue WHERE priority = ?",
            (priority,)
        ).fetchone()
        return row["next_pos"]


class QueueRunner:
    """
    Main loop that manages the queue.

    Loop:
    1. Get next job from queue
    2. Run it through PipelineRunner
    3. If job pauses (manual_review) → check for interleave
    4. If job completes → get next from queue
    5. If queue empty → sleep and wait for new jobs
    """

    def __init__(self, queue: JobQueue, pipeline, event_bus: Optional[EventBus] = None):
        """
        Args:
            queue: JobQueue instance.
            pipeline: PipelineRunner instance.
            event_bus: For emitting events.
        """
        self.queue = queue
        self.pipeline = pipeline
        self.event_bus = event_bus
        self.running = False

    def run_forever(self):
        """Main queue loop — runs until stopped."""
        self.running = True
        logger.info("QueueRunner started")

        while self.running:
            job_id = self.queue.get_next_job()

            if job_id is None:
                time.sleep(30)
                continue

            try:
                result = self.pipeline.run_job(job_id)

                if result == "paused":
                    next_job = self.queue.can_interleave(job_id)
                    if next_job:
                        logger.info(
                            f"Interleaving: {job_id} paused, starting {next_job}"
                        )
                        self.pipeline.run_job(next_job)

                elif result == "completed":
                    logger.info(f"Job {job_id} completed")
                    self.queue.remove(job_id)

                elif result == "blocked":
                    logger.warning(f"Job {job_id} blocked — check Telegram")
                    # Try interleave on blocked jobs too
                    next_job = self.queue.can_interleave(job_id)
                    if next_job:
                        logger.info(
                            f"Interleaving: {job_id} blocked, starting {next_job}"
                        )
                        self.pipeline.run_job(next_job)

            except Exception as e:
                logger.error(f"QueueRunner error for job {job_id}: {e}")
                if self.event_bus:
                    self.event_bus.emit(Event(
                        type=EventType.PHASE_FAILED,
                        job_id=job_id,
                        data={"error": str(e), "source": "queue_runner"},
                        severity="error"
                    ))
                time.sleep(60)

    def stop(self):
        """Signal the runner to stop after current job."""
        self.running = False
        logger.info("QueueRunner stopping...")
