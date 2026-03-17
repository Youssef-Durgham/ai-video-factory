"""
Internal event system.
Decouples phases from side effects (notifications, logging, analytics).
Simple in-process pub/sub — not a message broker.
"""

from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable
import logging

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    # Job lifecycle
    JOB_CREATED           = "job.created"
    JOB_STATUS_CHANGED    = "job.status_changed"
    JOB_BLOCKED           = "job.blocked"
    JOB_UNBLOCKED         = "job.unblocked"
    JOB_CANCELLED         = "job.cancelled"
    JOB_PUBLISHED         = "job.published"

    # Phase events
    PHASE_STARTED         = "phase.started"
    PHASE_COMPLETED       = "phase.completed"
    PHASE_FAILED          = "phase.failed"

    # Gate events
    GATE_PASSED           = "gate.passed"
    GATE_FAILED           = "gate.failed"
    GATE_BLOCKED          = "gate.blocked"

    # Production events
    IMAGE_GENERATED       = "production.image_generated"
    IMAGE_REGENERATED     = "production.image_regenerated"
    VIDEO_GENERATED       = "production.video_generated"
    VOICE_GENERATED       = "production.voice_generated"
    MUSIC_GENERATED       = "production.music_generated"
    COMPOSE_COMPLETED     = "production.compose_completed"

    # GPU events
    GPU_MODEL_LOADED      = "gpu.model_loaded"
    GPU_MODEL_UNLOADED    = "gpu.model_unloaded"
    GPU_OOM               = "gpu.oom"
    GPU_VRAM_LEAK         = "gpu.vram_leak"

    # Human interaction
    TOPIC_SELECTED        = "human.topic_selected"
    MANUAL_REVIEW_REQUESTED = "human.review_requested"
    MANUAL_REVIEW_APPROVED  = "human.review_approved"
    MANUAL_REVIEW_REJECTED  = "human.review_rejected"

    # Intelligence
    ANALYTICS_CAPTURED    = "intel.analytics_captured"
    RULE_DISCOVERED       = "intel.rule_discovered"
    REPORT_GENERATED      = "intel.report_generated"

    # Content ID
    CONTENT_ID_SAFE       = "content_id.safe"
    CONTENT_ID_CLAIMED    = "content_id.claimed"

    # Operational
    SERVICE_UNHEALTHY     = "ops.service_unhealthy"
    SERVICE_RESTARTED     = "ops.service_restarted"
    QUOTA_LOW             = "ops.quota_low"
    QUOTA_EXHAUSTED       = "ops.quota_exhausted"
    DISK_LOW              = "ops.disk_low"
    STORAGE_CLEANED       = "ops.storage_cleaned"
    RETRY_ATTEMPTED       = "ops.retry_attempted"
    RETRY_EXHAUSTED       = "ops.retry_exhausted"


@dataclass
class Event:
    type: EventType
    job_id: str = ""
    data: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    # Tracing fields
    trace_id: str = ""
    span_id: str = ""
    parent_span_id: str = ""
    source: str = ""
    severity: str = "info"
    duration_ms: int = 0


class EventBus:
    """
    Simple in-process event bus.
    Phases emit events → subscribers react.

    Example subscribers:
    - TelegramBot listens to JOB_BLOCKED → sends alert
    - EventStore listens to ALL → persists to DB
    """

    def __init__(self):
        self._subscribers: dict[EventType, list[Callable]] = {}
        self._global_subscribers: list[Callable] = []

    def subscribe(self, event_type: EventType, handler: Callable):
        """Subscribe to a specific event type."""
        self._subscribers.setdefault(event_type, []).append(handler)

    def subscribe_all(self, handler: Callable):
        """Subscribe to ALL events (for logging/persistence)."""
        self._global_subscribers.append(handler)

    def emit(self, event: Event):
        """Emit an event to all subscribers."""
        logger.debug(f"Event: {event.type.value} | job={event.job_id}")

        # Global subscribers first (logging)
        for handler in self._global_subscribers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Global event handler error: {e}")

        # Type-specific subscribers
        for handler in self._subscribers.get(event.type, []):
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Event handler error for {event.type.value}: {e}")
