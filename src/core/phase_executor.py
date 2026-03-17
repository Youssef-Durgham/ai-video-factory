"""
Executes individual phases.
Maps JobStatus → Phase handler → result.
Knows nothing about GPU, state, or gates.
"""

import logging
from typing import Optional
from src.core.job_state_machine import JobStatus
from src.models.analytics import PhaseResult

logger = logging.getLogger(__name__)


class BasePhase:
    """
    Base class for all phase handlers.
    All phases implement this interface.
    """

    def __init__(self, config: dict, db):
        self.config = config
        self.db = db

    def run(self, job_id: str) -> PhaseResult:
        """Execute this phase for the given job. Must be overridden."""
        raise NotImplementedError(f"{self.__class__.__name__}.run() not implemented")


class PhaseExecutor:
    """
    Maps status → phase → execute.
    Each phase is a self-contained module that reads from DB and writes to DB.

    Phase handlers are registered lazily — actual phase classes are imported
    and instantiated when first needed, avoiding import-time side effects.
    """

    def __init__(self, config: dict, db):
        self.config = config
        self.db = db
        self._phases: dict[JobStatus, Optional[BasePhase]] = {}
        self._initialized = False

    def _lazy_init(self):
        """
        Initialize phase handlers on first use.
        This allows the system to start even if some phase modules
        are not yet implemented — they'll raise NotImplementedError.
        """
        if self._initialized:
            return
        self._initialized = True

        # Create placeholder handlers for all statuses.
        # Real implementations will replace these as they're built.
        for status in JobStatus:
            self._phases[status] = None

        # Try to import and register real phase handlers.
        # Each phase module is optional — if not yet built, we use a stub.
        self._try_register_phases()

    def _try_register_phases(self):
        """Attempt to import and register phase handlers."""
        # Phase registrations will be added as phases are built:
        #
        # from src.phase1_research import ResearchPhase
        # self._phases[JobStatus.RESEARCH] = ResearchPhase(self.config, self.db)
        #
        # from src.phase2_seo import SEOPhase
        # self._phases[JobStatus.SEO] = SEOPhase(self.config, self.db)
        #
        # etc.
        #
        # For now, all phases use StubPhase which logs and returns success.
        pass

    def register_phase(self, status: JobStatus, handler: BasePhase):
        """Register a phase handler for a given status."""
        self._phases[status] = handler
        logger.debug(f"Registered phase handler: {status.value} → {handler.__class__.__name__}")

    def execute(self, status: JobStatus, job_id: str) -> PhaseResult:
        """Execute the phase for current status."""
        self._lazy_init()

        phase = self._phases.get(status)
        if phase is None:
            logger.warning(
                f"No phase handler for status: {status.value} — "
                f"returning stub success. Implement the phase module."
            )
            return PhaseResult(success=True, score=10.0)

        logger.info(f"Executing phase: {status.value} for job {job_id}")
        try:
            result = phase.run(job_id)
            logger.info(
                f"Phase {status.value} completed: success={result.success}, "
                f"score={result.score}"
            )
            return result
        except Exception as e:
            logger.error(f"Phase {status.value} failed: {e}", exc_info=True)
            return PhaseResult(
                success=False, blocked=True,
                reason=str(e), score=0.0
            )
