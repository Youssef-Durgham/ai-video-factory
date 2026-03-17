"""
Phase 7.5 — Manual Review (Telegram Interactive Review Gate).

Determines if a video needs human review, sends preview to Telegram,
and handles approve/reject/change-request flow.

This module wraps ReviewGate (decision logic) and ReviewHandler (Telegram UI)
into a unified phase interface.
"""

import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.core.database import FactoryDB
    from src.core.event_bus import EventBus
    from src.core.telegram_bot import TelegramBot

logger = logging.getLogger(__name__)


class ManualReview:
    """
    Unified manual review phase.
    
    Flow:
    1. ReviewGate decides if manual review is needed
    2. If yes → send video + scores to Telegram via ReviewHandler
    3. Wait for human response (approve/reject/changes)
    4. Return decision to PipelineRunner
    
    When manual review is NOT needed:
    - Auto-publish threshold met (QA score > config threshold)
    - Channel configured for auto-publish
    
    When manual review IS needed:
    - QA score below threshold
    - Sensitive topic flagged by compliance
    - First video on a new channel
    - Content has been regenerated 2+ times
    """

    def __init__(self, db: "FactoryDB", event_bus: "EventBus",
                 telegram: Optional["TelegramBot"] = None, config: dict = None):
        self.db = db
        self.event_bus = event_bus
        self.telegram = telegram
        self.config = config or {}

        # Import sub-components
        from src.phase7_5_review.review_gate import ReviewGate
        from src.phase7_5_review.review_handler import ReviewHandler

        self.gate = ReviewGate(db, config)
        self.handler = ReviewHandler(db, event_bus, telegram) if telegram else None

    def needs_review(self, job_id: str) -> bool:
        """
        Check if this job needs manual review.
        
        Returns True if:
        - QA score < auto_publish_threshold
        - Topic flagged as sensitive
        - First video on channel
        - Multiple regeneration cycles
        """
        job = self.db.get_job(job_id)
        if not job:
            return True  # Safety: unknown job = review

        # Get review config
        review_config = self.config.get("settings", {}).get("manual_review", {})
        auto_threshold = review_config.get("auto_publish_threshold", 8.0)
        always_review = review_config.get("always_review", False)

        if always_review:
            return True

        # Check QA score
        qa_scores = self.db.conn.execute(
            "SELECT AVG(score) FROM qa_rubrics WHERE job_id = ?",
            (job_id,)
        ).fetchone()

        avg_score = qa_scores[0] if qa_scores and qa_scores[0] else 0
        if avg_score < auto_threshold:
            logger.info(f"Job {job_id}: QA score {avg_score:.1f} < {auto_threshold} → needs review")
            return True

        # Check if topic was flagged as sensitive
        compliance = self.db.conn.execute(
            "SELECT sensitivity_flag FROM compliance_checks WHERE job_id = ? AND sensitivity_flag = 1",
            (job_id,)
        ).fetchone()
        if compliance:
            logger.info(f"Job {job_id}: sensitive topic → needs review")
            return True

        # Check regeneration count (2+ regens = review)
        regen_count = self.db.conn.execute(
            "SELECT COUNT(*) FROM asset_versions WHERE job_id = ? AND creation_reason LIKE 'regen%'",
            (job_id,)
        ).fetchone()[0]
        if regen_count >= 2:
            logger.info(f"Job {job_id}: {regen_count} regenerations → needs review")
            return True

        # Check if first video on channel
        channel_id = job.get("channel_id", "")
        published_count = self.db.conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE channel_id = ? AND status = 'published'",
            (channel_id,)
        ).fetchone()[0]
        if published_count == 0:
            logger.info(f"Job {job_id}: first video on channel {channel_id} → needs review")
            return True

        logger.info(f"Job {job_id}: QA score {avg_score:.1f} ≥ {auto_threshold} → auto-publish")
        return False

    async def request_review(self, job_id: str) -> str:
        """
        Send review request to Telegram and return immediately.
        The PipelineRunner will pause the job in MANUAL_REVIEW state.
        
        Returns: 'review_requested' or 'auto_publish'
        """
        if not self.needs_review(job_id):
            return "auto_publish"

        if self.handler:
            await self.handler.send_review_request(job_id)

        # Emit event
        from src.core.event_bus import Event, EventType
        self.event_bus.emit(Event(
            type=EventType.MANUAL_REVIEW_REQUESTED,
            job_id=job_id,
            data={"source": "manual_review"}
        ))

        return "review_requested"

    async def handle_decision(self, job_id: str, decision: str,
                               notes: str = "") -> dict:
        """
        Process human decision.
        
        Args:
            decision: 'approve' | 'reject' | 'changes'
            notes: Optional notes from reviewer.
        
        Returns:
            {"action": "publish" | "block" | "regen", "notes": str}
        """
        from src.core.event_bus import Event, EventType

        if decision == "approve":
            self.event_bus.emit(Event(
                type=EventType.MANUAL_REVIEW_APPROVED,
                job_id=job_id,
                data={"notes": notes}
            ))
            return {"action": "publish", "notes": notes}

        elif decision == "reject":
            self.event_bus.emit(Event(
                type=EventType.MANUAL_REVIEW_REJECTED,
                job_id=job_id,
                data={"notes": notes}
            ))
            return {"action": "block", "notes": notes}

        elif decision == "changes":
            # Specific changes requested — will trigger partial regen
            return {"action": "regen", "notes": notes}

        else:
            logger.warning(f"Unknown review decision: {decision}")
            return {"action": "block", "notes": f"Unknown decision: {decision}"}

    def get_review_summary(self, job_id: str) -> dict:
        """
        Build review summary for Telegram display.
        
        Returns: {
            "job_id": str,
            "topic": str,
            "qa_scores": {...},
            "avg_score": float,
            "regen_count": int,
            "compliance_flags": [...],
            "duration_min": float,
            "final_video_path": str,
        }
        """
        job = self.db.get_job(job_id)
        if not job:
            return {"job_id": job_id, "error": "Job not found"}

        # QA scores
        qa_rows = self.db.conn.execute(
            "SELECT check_type, score FROM qa_rubrics WHERE job_id = ?",
            (job_id,)
        ).fetchall()
        qa_scores = {row[0]: row[1] for row in qa_rows}
        avg_score = sum(qa_scores.values()) / len(qa_scores) if qa_scores else 0

        # Regen count
        regen_count = self.db.conn.execute(
            "SELECT COUNT(*) FROM asset_versions WHERE job_id = ? AND creation_reason LIKE 'regen%'",
            (job_id,)
        ).fetchone()[0]

        # Compliance flags
        compliance_rows = self.db.conn.execute(
            "SELECT check_type, result, notes FROM compliance_checks WHERE job_id = ?",
            (job_id,)
        ).fetchall()
        compliance_flags = [
            {"type": r[0], "result": r[1], "notes": r[2]}
            for r in compliance_rows
        ]

        return {
            "job_id": job_id,
            "topic": job.get("topic", "Unknown"),
            "channel_id": job.get("channel_id", ""),
            "qa_scores": qa_scores,
            "avg_score": round(avg_score, 2),
            "regen_count": regen_count,
            "compliance_flags": compliance_flags,
            "status": job.get("status", "unknown"),
        }
