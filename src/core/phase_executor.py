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

# Import ResourceCoordinator for GPU management
try:
    from src.core.resource_coordinator import ResourceCoordinator
    HAS_RESOURCE_COORDINATOR = True
except ImportError:
    HAS_RESOURCE_COORDINATOR = False


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

    def __init__(self, config: dict, db, resource_coordinator: Optional["ResourceCoordinator"] = None):
        self.config = config
        self.db = db
        self._phases: dict[JobStatus, Optional[BasePhase]] = {}
        self._initialized = False
        self._resource_coordinator = resource_coordinator

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
        """Import and register all phase handlers."""
        try:
            from src.core.phase_handlers import (
                ResearchPhase, SEOPhase, ScriptPhase, CompliancePhase,
                ImagesPhase, ImageQAPhase, ImageRegenPhase,
                VideoPhase, VideoQAPhase, VideoRegenPhase,
                VoicePhase, MusicPhase, SFXPhase,
                ComposePhase, OverlayQAPhase,
                FinalQAPhase, ManualReviewPhase, PublishPhase,
            )

            handler_map = {
                JobStatus.RESEARCH:      ResearchPhase,
                JobStatus.SEO:           SEOPhase,
                JobStatus.SCRIPT:        ScriptPhase,
                JobStatus.COMPLIANCE:    CompliancePhase,
                JobStatus.IMAGES:        ImagesPhase,
                JobStatus.IMAGE_QA:      ImageQAPhase,
                JobStatus.IMAGE_REGEN:   ImageRegenPhase,
                JobStatus.VIDEO:         VideoPhase,
                JobStatus.VIDEO_QA:      VideoQAPhase,
                JobStatus.VIDEO_REGEN:   VideoRegenPhase,
                JobStatus.VOICE:         VoicePhase,
                JobStatus.MUSIC:         MusicPhase,
                JobStatus.SFX:           SFXPhase,
                JobStatus.COMPOSE:       ComposePhase,
                JobStatus.OVERLAY_QA:    OverlayQAPhase,
                JobStatus.FINAL_QA:      FinalQAPhase,
                JobStatus.MANUAL_REVIEW: ManualReviewPhase,
                JobStatus.PUBLISH:       PublishPhase,
            }

            for status, cls in handler_map.items():
                self._phases[status] = cls(self.config, self.db)

            logger.info(f"Registered {len(handler_map)} phase handlers")

        except Exception as e:
            logger.error(f"Failed to register phase handlers: {e}", exc_info=True)

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

        # ── Notify user via Telegram ──
        self._notify_phase_start(status.value, job_id)

        # ── GPU: ensure correct model is loaded before phase runs ──
        if self._resource_coordinator:
            try:
                self._resource_coordinator.prepare_for_status(status.value)
            except Exception as e:
                logger.error(f"GPU preparation failed for {status.value}: {e}", exc_info=True)
                self._notify_phase_error(status.value, job_id, str(e))
                return PhaseResult(
                    success=False, blocked=True,
                    reason=f"GPU preparation failed: {e}", score=0.0
                )

        try:
            result = phase.run(job_id)
            logger.info(
                f"Phase {status.value} completed: success={result.success}, "
                f"score={result.score}"
            )
            # Phase handlers send their own detailed notifications
            return result
        except Exception as e:
            logger.error(f"Phase {status.value} failed: {e}", exc_info=True)
            self._notify_phase_error(status.value, job_id, str(e))
            return PhaseResult(
                success=False, blocked=True,
                reason=str(e), score=0.0
            )

    # ── Telegram Notifications ─────────────────────────────

    PHASE_NAMES = {
        "research": "🔍 البحث",
        "seo": "📊 SEO",
        "script": "📝 السكربت",
        "compliance": "✅ المراجعة",
        "images": "🎨 الصور",
        "image_qa": "🔎 فحص الصور",
        "image_regen": "🔄 إعادة توليد الصور",
        "voice": "🎙️ التعليق الصوتي",
        "music": "🎵 الموسيقى",
        "sfx": "🔊 المؤثرات الصوتية",
        "video": "🎬 الفيديو",
        "video_qa": "🔎 فحص الفيديو",
        "compose": "🎞️ التجميع النهائي",
        "overlay_qa": "🔎 فحص النص",
        "final_qa": "🔎 الفحص النهائي",
        "manual_review": "👁️ المراجعة اليدوية",
        "publish": "📤 النشر",
    }

    def _notify_phase_start(self, phase: str, job_id: str):
        """Send Telegram notification when a phase starts."""
        name = self.PHASE_NAMES.get(phase, phase)
        try:
            from src.core.telegram_callbacks import send_telegram_sync
            send_telegram_sync(f"⏳ <b>{name}</b> — بدأت\n🆔 <code>{job_id}</code>")
        except Exception:
            pass  # Don't block pipeline if notification fails

    def _notify_phase_done(self, phase: str, job_id: str, result: PhaseResult):
        """Send Telegram notification when a phase completes."""
        name = self.PHASE_NAMES.get(phase, phase)
        icon = "✅" if result.success else "⚠️"
        try:
            from src.core.telegram_callbacks import send_telegram_sync
            send_telegram_sync(
                f"{icon} <b>{name}</b> — {'اكتملت' if result.success else 'فشلت'}\n"
                f"📈 النتيجة: {result.score:.1f}/10\n"
                f"🆔 <code>{job_id}</code>"
            )
        except Exception:
            pass

    def _notify_phase_error(self, phase: str, job_id: str, error: str):
        """Send Telegram notification on phase error."""
        name = self.PHASE_NAMES.get(phase, phase)
        try:
            from src.core.telegram_callbacks import send_telegram_sync
            send_telegram_sync(
                f"❌ <b>{name}</b> — خطأ\n"
                f"📝 {error[:200]}\n"
                f"🆔 <code>{job_id}</code>"
            )
        except Exception:
            pass
