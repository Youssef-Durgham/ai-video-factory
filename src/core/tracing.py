"""
Tracing context — passed through the entire pipeline.
Every component uses this to emit properly-linked events.

Usage:
    trace = TracingContext(job_id="job_20260315_120000")
    
    with trace.span("pipeline_runner.run_job") as span:
        with trace.span("phase6a.image_qa", parent=span) as child:
            with trace.span("image_checker.verify_scene_5", parent=child) as leaf:
                result = check_image(...)
"""

import time
import uuid
import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.event_bus import EventBus

logger = logging.getLogger(__name__)


class Span:
    """Individual tracing span — tracks one operation."""

    def __init__(self, trace_id: str, job_id: str, source: str,
                 parent_span_id: Optional[str], event_bus: Optional["EventBus"]):
        self.trace_id = trace_id
        self.job_id = job_id
        self.source = source
        self.span_id = str(uuid.uuid4())[:8]
        self.parent_span_id = parent_span_id
        self.event_bus = event_bus
        self._start_time: Optional[float] = None

    def __enter__(self):
        self._start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = int((time.time() - self._start_time) * 1000)
        severity = "error" if exc_type else "info"

        if self.event_bus:
            try:
                from src.core.event_bus import Event, EventType
                event_type = (
                    EventType.PHASE_FAILED if exc_type
                    else EventType.PHASE_COMPLETED
                )
                self.event_bus.emit(Event(
                    type=event_type,
                    job_id=self.job_id,
                    data={
                        "trace_id": self.trace_id,
                        "span_id": self.span_id,
                        "parent_span_id": self.parent_span_id,
                        "source": self.source,
                        "severity": severity,
                        "duration_ms": duration_ms,
                        "error": str(exc_val) if exc_type else None,
                    }
                ))
            except Exception as e:
                logger.warning(f"Failed to emit span event: {e}")

        # Don't suppress exceptions
        return False

    def emit(self, event_type, data: dict = None, severity: str = "info"):
        """Emit an event within this span's context."""
        if self.event_bus:
            from src.core.event_bus import Event
            self.event_bus.emit(Event(
                type=event_type,
                job_id=self.job_id,
                data={
                    "trace_id": self.trace_id,
                    "span_id": str(uuid.uuid4())[:8],
                    "parent_span_id": self.span_id,
                    "source": self.source,
                    "severity": severity,
                    **(data or {}),
                }
            ))


class TracingContext:
    """
    Created once per job run. Passed to every phase/coordinator/checker.
    Enables distributed tracing across the entire pipeline.
    """

    def __init__(self, job_id: str):
        self.job_id = job_id
        self.trace_id = str(uuid.uuid4())[:12]
        self.event_bus: Optional["EventBus"] = None

    def set_event_bus(self, event_bus: "EventBus"):
        """Set by PipelineRunner after initialization."""
        self.event_bus = event_bus

    def span(self, source: str, parent: Optional[Span] = None) -> Span:
        """Create a tracing span (context manager)."""
        return Span(
            trace_id=self.trace_id,
            job_id=self.job_id,
            source=source,
            parent_span_id=parent.span_id if parent else None,
            event_bus=self.event_bus,
        )
