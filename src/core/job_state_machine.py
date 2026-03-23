"""
Formal state machine for job lifecycle.
Every status transition must be explicitly defined here.
Invalid transitions raise StateError — prevents bugs.
Resumable after crashes via SQLite-persisted status.
"""

from enum import Enum
from typing import Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    PENDING       = "pending"
    RESEARCH      = "research"
    SEO           = "seo"
    SCRIPT        = "script"
    COMPLIANCE    = "compliance"

    # Phase 5+6 sub-states
    # ORDER: images → voice/music/sfx → video (video length = voice length)
    IMAGES        = "images"
    IMAGE_QA      = "image_qa"
    IMAGE_REGEN   = "image_regen"
    VOICE         = "voice"         # Voice BEFORE video — determines duration
    MUSIC         = "music"         # Music scored to voice duration
    SFX           = "sfx"           # SFX timed to scenes
    VIDEO         = "video"         # Video generated to match voice duration
    VIDEO_QA      = "video_qa"
    VIDEO_REGEN   = "video_regen"
    COMPOSE       = "compose"       # Final assembly: video + voice + music + sfx
    OVERLAY_QA    = "overlay_qa"

    FINAL_QA      = "final_qa"
    MANUAL_REVIEW = "manual_review"
    PUBLISH       = "publish"
    PUBLISHED     = "published"

    # Terminal / special states
    BLOCKED       = "blocked"
    CANCELLED     = "cancelled"

    # Phase 9 tracking states
    TRACKING_24H  = "tracking_24h"
    TRACKING_7D   = "tracking_7d"
    TRACKING_30D  = "tracking_30d"
    COMPLETE      = "complete"


# ═══ TRANSITION MAP ═══
# Only these transitions are allowed. Anything else = bug.
TRANSITIONS: dict[JobStatus, list[JobStatus]] = {
    JobStatus.PENDING:       [JobStatus.RESEARCH],
    JobStatus.RESEARCH:      [JobStatus.SEO, JobStatus.BLOCKED],
    JobStatus.SEO:           [JobStatus.SCRIPT, JobStatus.BLOCKED],
    JobStatus.SCRIPT:        [JobStatus.COMPLIANCE, JobStatus.MANUAL_REVIEW, JobStatus.BLOCKED],
    JobStatus.COMPLIANCE:    [JobStatus.IMAGES, JobStatus.BLOCKED],

    # Phase 5+6 sub-pipeline
    # NEW ORDER: images → voice → music → sfx → video → compose
    # Voice/music/sfx FIRST so video knows the target duration
    JobStatus.IMAGES:        [JobStatus.IMAGE_QA, JobStatus.BLOCKED],
    JobStatus.IMAGE_QA:      [JobStatus.VOICE, JobStatus.IMAGE_REGEN, JobStatus.BLOCKED],
    JobStatus.IMAGE_REGEN:   [JobStatus.IMAGE_QA],
    JobStatus.VOICE:         [JobStatus.MUSIC, JobStatus.BLOCKED],
    JobStatus.MUSIC:         [JobStatus.SFX, JobStatus.BLOCKED],
    JobStatus.SFX:           [JobStatus.VIDEO, JobStatus.BLOCKED],
    JobStatus.VIDEO:         [JobStatus.VIDEO_QA, JobStatus.BLOCKED],
    JobStatus.VIDEO_QA:      [JobStatus.COMPOSE, JobStatus.VIDEO_REGEN, JobStatus.BLOCKED],
    JobStatus.VIDEO_REGEN:   [JobStatus.VIDEO_QA],
    JobStatus.COMPOSE:       [JobStatus.OVERLAY_QA, JobStatus.BLOCKED],
    JobStatus.OVERLAY_QA:    [JobStatus.FINAL_QA, JobStatus.COMPOSE, JobStatus.BLOCKED],

    JobStatus.FINAL_QA:      [JobStatus.MANUAL_REVIEW, JobStatus.PUBLISH, JobStatus.BLOCKED],
    JobStatus.MANUAL_REVIEW: [JobStatus.PUBLISH, JobStatus.BLOCKED, JobStatus.CANCELLED],
    JobStatus.PUBLISH:       [JobStatus.PUBLISHED, JobStatus.BLOCKED],
    JobStatus.PUBLISHED:     [JobStatus.TRACKING_24H],

    # Phase 9 tracking
    JobStatus.TRACKING_24H:  [JobStatus.TRACKING_7D],
    JobStatus.TRACKING_7D:   [JobStatus.TRACKING_30D],
    JobStatus.TRACKING_30D:  [JobStatus.COMPLETE],

    # Blocked can be unblocked → resume from blocked_phase
    JobStatus.BLOCKED:       [
        JobStatus.RESEARCH, JobStatus.SEO, JobStatus.SCRIPT,
        JobStatus.COMPLIANCE, JobStatus.IMAGES, JobStatus.IMAGE_QA,
        JobStatus.VIDEO, JobStatus.VIDEO_QA, JobStatus.VOICE, JobStatus.MUSIC,
        JobStatus.SFX, JobStatus.COMPOSE, JobStatus.OVERLAY_QA,
        JobStatus.FINAL_QA, JobStatus.PUBLISH, JobStatus.CANCELLED,
    ],

    # Terminal states — no transitions out
    JobStatus.CANCELLED:     [],
    JobStatus.COMPLETE:      [],
}

# Which states require which GPU model
GPU_REQUIREMENTS: dict[JobStatus, Optional[str]] = {
    JobStatus.RESEARCH:     "qwen3.5:27b",
    JobStatus.SEO:          "qwen3.5:27b",
    JobStatus.SCRIPT:       "qwen3.5:27b",
    JobStatus.COMPLIANCE:   "qwen3.5:27b",
    JobStatus.IMAGES:       "flux",
    JobStatus.IMAGE_QA:     "qwen3.5-vision:27b",
    JobStatus.IMAGE_REGEN:  "flux",
    JobStatus.VIDEO:        "ltx",
    JobStatus.VIDEO_QA:     "qwen3.5-vision:27b",
    JobStatus.VIDEO_REGEN:  "ltx",
    JobStatus.VOICE:        "fish_audio_s2_pro",
    JobStatus.MUSIC:        "ace_step",
    JobStatus.SFX:          "moss_sfx",
    JobStatus.COMPOSE:      None,           # CPU only (FFmpeg)
    JobStatus.OVERLAY_QA:   "qwen3.5-vision:27b",
    JobStatus.FINAL_QA:     "qwen3.5-vision:27b",
    JobStatus.MANUAL_REVIEW: None,          # Waiting for human
    JobStatus.PUBLISH:      "flux",         # Thumbnails
}

# Consecutive states that use the SAME model (batch without unload)
GPU_BATCHES = [
    [JobStatus.RESEARCH, JobStatus.SEO, JobStatus.SCRIPT, JobStatus.COMPLIANCE],
]

# States that are terminal or pausing
TERMINAL_STATES = {JobStatus.PUBLISHED, JobStatus.CANCELLED, JobStatus.COMPLETE}
PAUSE_STATES = {JobStatus.BLOCKED, JobStatus.MANUAL_REVIEW}


class StateError(Exception):
    """Raised when an invalid state transition is attempted."""
    pass


class JobStateMachine:
    """
    Enforces valid state transitions.
    Every status change in the system MUST go through this class.
    Backed by SQLite — survives crashes.
    """

    def __init__(self, db):
        self.db = db

    def transition(self, job_id: str, to_status: JobStatus) -> JobStatus:
        """
        Transition job to new status.
        Raises StateError if transition is invalid.
        Returns previous status for logging.
        """
        job = self.db.get_job(job_id)
        if not job:
            raise StateError(f"Job not found: {job_id}")

        current = JobStatus(job["status"])

        allowed = TRANSITIONS.get(current, [])
        if to_status not in allowed:
            raise StateError(
                f"Invalid transition: {current.value} → {to_status.value}. "
                f"Allowed: {[s.value for s in allowed]}"
            )

        self.db.update_job_status(job_id, to_status.value)
        logger.info(f"Job {job_id}: {current.value} → {to_status.value}")
        return current

    def get_next_status(self, current: JobStatus) -> Optional[JobStatus]:
        """Get the default next status (first in transition list, skipping BLOCKED)."""
        options = TRANSITIONS.get(current, [])
        for opt in options:
            if opt != JobStatus.BLOCKED:
                return opt
        return None

    def get_required_gpu(self, status: JobStatus) -> Optional[str]:
        """What GPU model does this status need?"""
        return GPU_REQUIREMENTS.get(status)

    def can_batch_with_next(self, current: JobStatus, next_status: JobStatus) -> bool:
        """Can we keep the same GPU model loaded for the next status?"""
        for batch in GPU_BATCHES:
            if current in batch and next_status in batch:
                return True
        return False

    def get_resume_status(self, job_id: str) -> JobStatus:
        """After crash, where should this job resume?"""
        job = self.db.get_job(job_id)
        if not job:
            raise StateError(f"Job not found: {job_id}")

        status = JobStatus(job["status"])

        # If blocked, resume from the phase that blocked it
        if status == JobStatus.BLOCKED:
            blocked_phase = job.get("blocked_phase")
            if blocked_phase:
                try:
                    return JobStatus(blocked_phase)
                except ValueError:
                    pass

        return status

    def is_terminal(self, status: JobStatus) -> bool:
        """Check if status is a terminal state."""
        return status in TERMINAL_STATES

    def is_paused(self, status: JobStatus) -> bool:
        """Check if status is a pause state (waiting for human or blocked)."""
        return status in PAUSE_STATES

    def force_reset(self, job_id: str, to_status: JobStatus) -> JobStatus:
        """
        Force-reset a job to any phase (for manual rewind).
        Bypasses normal transition rules. Clears blocked state.
        Returns previous status.
        """
        job = self.db.get_job(job_id)
        if not job:
            raise StateError(f"Job not found: {job_id}")

        current = JobStatus(job["status"])

        # Clear blocked state
        self.db.conn.execute("""
            UPDATE jobs SET
                status = ?,
                blocked_at = NULL,
                blocked_reason = NULL,
                blocked_phase = NULL,
                manual_review_required = FALSE,
                manual_review_status = NULL,
                updated_at = ?
            WHERE id = ?
        """, (to_status.value, datetime.utcnow().isoformat(), job_id))
        self.db.conn.commit()

        logger.info(f"Job {job_id}: FORCE RESET {current.value} → {to_status.value}")
        return current
