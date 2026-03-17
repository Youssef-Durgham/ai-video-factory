"""
Phase 7.5 — Review Gate.

Decides if a video needs manual review or can auto-publish based on:
- QA scores vs threshold
- Sensitive categories
- Channel's published video count (trust ramp)
- Review mode (all / selective / off)
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from src.core.config import get_setting

logger = logging.getLogger(__name__)


@dataclass
class ReviewDecision:
    """Result of the review gate evaluation."""
    needs_review: bool
    reasons: list[str] = field(default_factory=list)
    auto_publish_eligible: bool = False
    overall_score: float = 0.0
    flags: list[dict] = field(default_factory=list)
    sensitive_category_match: Optional[str] = None


class ReviewGate:
    """
    Evaluates whether a completed video should be auto-published
    or held for manual Telegram-based review.
    """

    def __init__(self, config: dict, db):
        self.config = config
        self.db = db
        self.review_config = config["settings"].get("manual_review", {})
        self.mode = self.review_config.get("mode", "selective")
        self.min_score = self.review_config.get("auto_publish_min_score", 8.0)
        self.trust_threshold = self.review_config.get("auto_publish_after_n_videos", 20)
        self.sensitive_categories = self.review_config.get("sensitive_categories", ["politics"])
        self.timeout_hours = self.review_config.get("timeout_hours", 24)
        self.timeout_action = self.review_config.get("timeout_action", "hold")

    def evaluate(self, job_id: str) -> ReviewDecision:
        """
        Evaluate whether a job needs manual review.

        Args:
            job_id: The job to evaluate.

        Returns:
            ReviewDecision with the gate verdict.
        """
        if self.mode == "off":
            logger.info(f"Review gate OFF — auto-publishing {job_id}")
            return ReviewDecision(needs_review=False, auto_publish_eligible=True)

        job = self.db.get_job(job_id)
        if not job:
            logger.error(f"Job not found: {job_id}")
            return ReviewDecision(needs_review=True, reasons=["Job not found"])

        decision = ReviewDecision(needs_review=False)

        # --- Mode: all ---
        if self.mode == "all":
            decision.needs_review = True
            decision.reasons.append("Review mode is 'all'")
            self._save_review_status(job_id, decision)
            return decision

        # --- Mode: selective ---
        # 1. Collect QA scores
        rubric_stats = self.db.get_rubric_stats(job_id)
        if rubric_stats:
            avg_scores = [s["avg_score"] for s in rubric_stats if s["avg_score"] is not None]
            decision.overall_score = sum(avg_scores) / len(avg_scores) if avg_scores else 0.0
        else:
            decision.overall_score = 0.0
            decision.needs_review = True
            decision.reasons.append("No QA rubric data available")

        # 2. Check score threshold
        if decision.overall_score < self.min_score:
            decision.needs_review = True
            decision.reasons.append(
                f"Overall score {decision.overall_score:.1f} < threshold {self.min_score}"
            )

        # 3. Check for human-flagged rubrics
        flags = self.db.get_job_flags(job_id)
        decision.flags = flags
        human_flags = [f for f in flags if f.get("severity") == "error"]
        if human_flags:
            decision.needs_review = True
            decision.reasons.append(f"{len(human_flags)} QA flag(s) require human review")

        # 4. Sensitive category check
        topic = job.get("topic", "").lower()
        topic_region = job.get("topic_region", "").lower()
        for cat in self.sensitive_categories:
            if cat.lower() in topic or cat.lower() in topic_region:
                decision.needs_review = True
                decision.sensitive_category_match = cat
                decision.reasons.append(f"Sensitive category detected: {cat}")
                break

        # 5. Trust ramp — auto-publish if channel has enough successful videos
        channel_id = job.get("channel_id", "")
        published_count = self.db.count_published_videos(channel_id)
        if published_count >= self.trust_threshold and not decision.sensitive_category_match:
            # High trust — only review if score is really low
            if decision.overall_score >= self.min_score and not human_flags:
                decision.needs_review = False
                decision.auto_publish_eligible = True
                decision.reasons = [
                    f"Trust ramp passed ({published_count} videos), "
                    f"score {decision.overall_score:.1f} >= {self.min_score}"
                ]

        # 6. Check for recent strikes on this channel
        strikes = self.db.get_recent_strikes(channel_id, days=90)
        if strikes:
            decision.needs_review = True
            decision.reasons.append(f"{len(strikes)} recent strike(s) — forcing review")

        self._save_review_status(job_id, decision)
        return decision

    def get_timeout_action(self) -> str:
        """Return what to do when review times out."""
        return self.timeout_action

    def get_timeout_hours(self) -> int:
        """Return review timeout in hours."""
        return self.timeout_hours

    def _save_review_status(self, job_id: str, decision: ReviewDecision):
        """Persist review decision to the jobs table."""
        self.db.conn.execute(
            "UPDATE jobs SET manual_review_required = ?, "
            "manual_review_status = ?, manual_review_notes = ?, "
            "updated_at = ? WHERE id = ?",
            (
                decision.needs_review,
                "pending" if decision.needs_review else "auto_approved",
                json.dumps({
                    "reasons": decision.reasons,
                    "overall_score": decision.overall_score,
                    "sensitive_category": decision.sensitive_category_match,
                    "flag_count": len(decision.flags),
                }),
                datetime.now().isoformat(),
                job_id,
            ),
        )
        if decision.needs_review:
            self.db.update_job_status(job_id, "review")
        self.db.conn.commit()

        logger.info(
            f"Review gate for {job_id}: "
            f"{'NEEDS REVIEW' if decision.needs_review else 'AUTO-PUBLISH'} "
            f"(score={decision.overall_score:.1f}, reasons={decision.reasons})"
        )
