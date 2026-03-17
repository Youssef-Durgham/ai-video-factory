"""
Comprehensive retry strategy for every external dependency.
Each service has its own failure mode → needs its own retry policy.

Wraps any service call with retry logic, exponential backoff,
failure classification, and recovery actions.
"""

import time
import logging
import subprocess
import platform
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional, Any

from src.core.event_bus import EventBus, Event, EventType

logger = logging.getLogger(__name__)


class FailureType(str, Enum):
    """Classification of failure types for appropriate handling."""
    TIMEOUT      = "timeout"
    OOM          = "oom"
    CRASH        = "crash"
    BAD_OUTPUT   = "bad_output"
    HUNG         = "hung"
    RATE_LIMIT   = "rate_limit"
    NETWORK      = "network"


@dataclass
class RetryPolicy:
    """Retry configuration for a specific service."""
    max_retries: int
    initial_delay_sec: float
    backoff_multiplier: float
    max_delay_sec: float
    timeout_sec: float
    on_exhaust: str                  # "block" | "skip" | "fallback" | "alert"
    fallback_action: Optional[str] = None


# ═══ PER-SERVICE RETRY POLICIES ═══

RETRY_POLICIES: dict[str, RetryPolicy] = {
    "ollama": RetryPolicy(
        max_retries=3,
        initial_delay_sec=10,
        backoff_multiplier=2.0,       # 10s → 20s → 40s
        max_delay_sec=60,
        timeout_sec=300,              # 5 min per generation
        on_exhaust="block",
    ),
    "comfyui": RetryPolicy(
        max_retries=3,
        initial_delay_sec=5,
        backoff_multiplier=2.0,
        max_delay_sec=30,
        timeout_sec=180,              # 3 min per image
        on_exhaust="block",
    ),
    "fish_speech": RetryPolicy(
        max_retries=2,
        initial_delay_sec=5,
        backoff_multiplier=2.0,
        max_delay_sec=20,
        timeout_sec=120,              # 2 min per scene narration
        on_exhaust="block",
    ),
    "musicgen": RetryPolicy(
        max_retries=2,
        initial_delay_sec=5,
        backoff_multiplier=2.0,
        max_delay_sec=20,
        timeout_sec=180,              # 3 min per music zone
        on_exhaust="fallback",
        fallback_action="use_stock_music",
    ),
    "ffmpeg": RetryPolicy(
        max_retries=2,
        initial_delay_sec=2,
        backoff_multiplier=1.5,
        max_delay_sec=10,
        timeout_sec=600,              # 10 min for full compose
        on_exhaust="block",
    ),
    "youtube_api": RetryPolicy(
        max_retries=5,
        initial_delay_sec=60,
        backoff_multiplier=2.0,
        max_delay_sec=900,            # Up to 15 min
        timeout_sec=120,
        on_exhaust="alert",
    ),
    "whisper": RetryPolicy(
        max_retries=2,
        initial_delay_sec=5,
        backoff_multiplier=2.0,
        max_delay_sec=15,
        timeout_sec=120,
        on_exhaust="skip",
    ),
}


class RetryExhausted(Exception):
    """Raised when all retries are exhausted."""
    def __init__(self, service: str, last_error: Exception, failure_type: FailureType):
        self.service = service
        self.last_error = last_error
        self.failure_type = failure_type
        super().__init__(f"Retries exhausted for {service}: {last_error}")


class RetryEngine:
    """
    Wraps any service call with retry logic.

    Usage:
        retry = RetryEngine("ollama", event_bus=bus)
        result = retry.execute(lambda: ollama.generate(...))

    On each failure:
    1. Classify failure type
    2. Log failure + attempt number
    3. Emit RETRY_ATTEMPTED event
    4. Attempt recovery action (service-specific)
    5. Wait (exponential backoff)
    6. Retry

    On exhaust:
    - "block": raise RetryExhausted → caller blocks job
    - "skip": return None → caller skips step
    - "fallback": return sentinel → caller uses fallback
    - "alert": return None → alert sent via event bus
    """

    def __init__(self, service: str, event_bus: Optional[EventBus] = None,
                 gpu_manager=None):
        """
        Args:
            service: Service name (key in RETRY_POLICIES).
            event_bus: For emitting retry events.
            gpu_manager: For OOM recovery (emergency_cleanup).
        """
        if service not in RETRY_POLICIES:
            raise ValueError(f"Unknown service: {service}. Known: {list(RETRY_POLICIES.keys())}")
        self.policy = RETRY_POLICIES[service]
        self.service = service
        self.event_bus = event_bus
        self.gpu_manager = gpu_manager

    def execute(self, fn: Callable, *args, **kwargs) -> Any:
        """
        Execute function with retry logic.

        Returns the function result on success.
        On exhaustion, behavior depends on policy.on_exhaust.
        """
        last_error = None
        last_failure_type = FailureType.NETWORK

        for attempt in range(1, self.policy.max_retries + 1):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                last_error = e
                last_failure_type = self._classify_failure(e)
                delay = self._calculate_delay(attempt)

                logger.warning(
                    f"Retry {attempt}/{self.policy.max_retries} for {self.service}: "
                    f"{last_failure_type.value} — {e} — waiting {delay:.1f}s"
                )

                if self.event_bus:
                    self.event_bus.emit(Event(
                        type=EventType.RETRY_ATTEMPTED,
                        data={
                            "service": self.service,
                            "attempt": attempt,
                            "max_retries": self.policy.max_retries,
                            "failure_type": last_failure_type.value,
                            "error": str(e),
                            "delay_sec": delay,
                        },
                        source=f"retry_engine.{self.service}",
                        severity="warn",
                    ))

                self._attempt_recovery(last_failure_type)

                if attempt < self.policy.max_retries:
                    time.sleep(delay)

        return self._handle_exhaustion(last_error, last_failure_type)

    def _classify_failure(self, error: Exception) -> FailureType:
        """Classify error into FailureType for appropriate handling."""
        error_str = str(error).lower()

        if "timeout" in error_str or "timed out" in error_str:
            return FailureType.TIMEOUT
        elif "cuda out of memory" in error_str or "oom" in error_str:
            return FailureType.OOM
        elif "connection refused" in error_str or "connection reset" in error_str:
            return FailureType.CRASH
        elif "rate limit" in error_str or "quota" in error_str or "429" in error_str:
            return FailureType.RATE_LIMIT
        elif "connection" in error_str or "network" in error_str:
            return FailureType.NETWORK
        else:
            return FailureType.BAD_OUTPUT

    def _attempt_recovery(self, failure_type: FailureType):
        """Service-specific recovery actions."""
        try:
            if self.service == "ollama" and failure_type in (FailureType.CRASH, FailureType.HUNG):
                # Stop ollama — it auto-restarts via service manager
                subprocess.run(
                    ["ollama", "stop"], capture_output=True, timeout=10
                )
                time.sleep(5)

            elif self.service == "comfyui" and failure_type == FailureType.HUNG:
                try:
                    import requests
                    requests.post(
                        "http://localhost:8188/queue",
                        json={"clear": True}, timeout=5
                    )
                except Exception:
                    pass
                time.sleep(3)

            elif failure_type == FailureType.OOM and self.gpu_manager:
                self.gpu_manager.emergency_cleanup()
                time.sleep(10)

        except Exception as e:
            logger.warning(f"Recovery action failed for {self.service}: {e}")

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay with exponential backoff."""
        delay = self.policy.initial_delay_sec * (
            self.policy.backoff_multiplier ** (attempt - 1)
        )
        return min(delay, self.policy.max_delay_sec)

    def _handle_exhaustion(self, last_error: Exception,
                           failure_type: FailureType) -> Any:
        """Handle retry exhaustion based on policy."""
        logger.error(
            f"Retries exhausted for {self.service}: {failure_type.value} — {last_error}"
        )

        if self.event_bus:
            self.event_bus.emit(Event(
                type=EventType.RETRY_EXHAUSTED,
                data={
                    "service": self.service,
                    "failure_type": failure_type.value,
                    "error": str(last_error),
                    "action": self.policy.on_exhaust,
                },
                source=f"retry_engine.{self.service}",
                severity="error",
            ))

        if self.policy.on_exhaust == "block":
            raise RetryExhausted(self.service, last_error, failure_type)
        elif self.policy.on_exhaust == "skip":
            logger.info(f"Skipping {self.service} after exhaustion")
            return None
        elif self.policy.on_exhaust == "fallback":
            logger.info(
                f"Using fallback for {self.service}: {self.policy.fallback_action}"
            )
            return {"fallback": self.policy.fallback_action}
        elif self.policy.on_exhaust == "alert":
            logger.info(f"Alerting for {self.service} exhaustion")
            return None
        else:
            raise RetryExhausted(self.service, last_error, failure_type)
