"""
Evaluates QA gate results.
Decides: PASS (continue) | RETRY (regenerate) | BLOCK (alert human)
Separated from phase logic for testability.
"""

import logging
from typing import Optional
from src.core.job_state_machine import JobStatus

logger = logging.getLogger(__name__)


class GateResult:
    __slots__ = ("passed", "action", "reason", "retry_phase", "failed_items", "score")

    def __init__(self, passed: bool, action: str, reason: str = "",
                 retry_phase: Optional[str] = None, failed_items: list = None,
                 score: float = 0.0):
        self.passed = passed
        self.action = action  # "continue" | "retry" | "block" | "manual_review"
        self.reason = reason
        self.retry_phase = retry_phase
        self.failed_items = failed_items or []
        self.score = score


class GateEvaluator:
    """Evaluates results from QA phases and decides next action."""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}

    def evaluate(self, status: JobStatus, phase_result) -> GateResult:
        """
        Dispatch gate evaluation based on current status.
        phase_result should have: is_gate, gate_data, score
        """
        evaluators = {
            JobStatus.COMPLIANCE: self.evaluate_compliance,
            JobStatus.IMAGE_QA: self.evaluate_image_qa,
            JobStatus.VIDEO_QA: self.evaluate_video_qa,
            JobStatus.OVERLAY_QA: self.evaluate_overlay_qa,
            JobStatus.FINAL_QA: self.evaluate_final_qa,
        }
        evaluator = evaluators.get(status)
        if evaluator:
            return evaluator(phase_result.gate_data)
        # Non-gate phases always pass
        return GateResult(passed=True, action="continue", score=phase_result.score)

    def evaluate_compliance(self, data: dict) -> GateResult:
        """Phase 4: Script compliance gate."""
        check_results = data.get("checks", [])
        if not check_results:
            return GateResult(passed=True, action="continue", score=10.0)

        blocked = [r for r in check_results if r.get("status") == "block"]
        warnings = [r for r in check_results if r.get("status") == "warn"]

        if blocked:
            return GateResult(
                passed=False, action="block",
                reason=f"Compliance violation: {blocked[0].get('details', 'unknown')}"
            )

        if len(warnings) > 2:
            return GateResult(
                passed=False, action="block",
                reason=f"Too many warnings ({len(warnings)}): {warnings[0].get('details', '')}"
            )

        scores = [r.get("score", 5) for r in check_results]
        avg_score = sum(scores) / len(scores) if scores else 0
        return GateResult(passed=True, action="continue", score=avg_score)

    def evaluate_image_qa(self, data: dict) -> GateResult:
        """Phase 6A: Image QA gate."""
        image_scores = data.get("image_scores", [])
        if not image_scores:
            return GateResult(passed=True, action="continue", score=10.0)

        total = len(image_scores)
        failed = [s for s in image_scores if s.get("score", 0) < 7]
        pass_rate = (total - len(failed)) / total if total > 0 else 0

        if pass_rate >= 0.9:
            return GateResult(passed=True, action="continue", score=pass_rate * 10)
        elif pass_rate >= 0.7:
            return GateResult(
                passed=False, action="retry",
                retry_phase=JobStatus.IMAGE_REGEN.value,
                failed_items=[s.get("scene_index") for s in failed],
                reason=f"{len(failed)}/{total} images below quality threshold"
            )
        else:
            return GateResult(
                passed=False, action="block",
                reason=f"Image quality too low: {len(failed)}/{total} failed"
            )

    def evaluate_video_qa(self, data: dict) -> GateResult:
        """Phase 6B: Video clip QA gate."""
        video_scores = data.get("video_scores", [])
        if not video_scores:
            return GateResult(passed=True, action="continue", score=10.0)

        total = len(video_scores)
        failed = [s for s in video_scores if s.get("score", 0) < 7]
        pass_rate = (total - len(failed)) / total if total > 0 else 0

        if pass_rate >= 0.85:
            return GateResult(passed=True, action="continue", score=pass_rate * 10)
        elif pass_rate >= 0.6:
            return GateResult(
                passed=False, action="retry",
                retry_phase=JobStatus.VIDEO_REGEN.value,
                failed_items=[s.get("scene_index") for s in failed],
                reason=f"{len(failed)}/{total} video clips below quality threshold"
            )
        else:
            return GateResult(
                passed=False, action="block",
                reason=f"Video quality too low: {len(failed)}/{total} failed"
            )

    def evaluate_overlay_qa(self, data: dict) -> GateResult:
        """Phase 6C: Text overlay QA gate."""
        overall_pass = data.get("overall_pass", True)
        auto_fixable = data.get("auto_fixable", False)

        if overall_pass:
            return GateResult(passed=True, action="continue", score=10.0)
        elif auto_fixable:
            return GateResult(
                passed=False, action="retry",
                retry_phase=JobStatus.COMPOSE.value,
                reason="Overlay issues detected — auto-fixable via re-compose"
            )
        else:
            return GateResult(
                passed=False, action="block",
                reason="Overlay QA failed — manual intervention needed"
            )

    def evaluate_final_qa(self, data: dict) -> GateResult:
        """Phase 7: Final video QA gate."""
        technical = data.get("technical", {})
        content = data.get("content", {})

        # A/V sync check
        drift_ms = technical.get("av_sync_drift_ms", 0)
        if drift_ms > 100:
            return GateResult(
                passed=False, action="retry",
                retry_phase=JobStatus.COMPOSE.value,
                reason=f"A/V sync drift: {drift_ms}ms"
            )

        content_score = content.get("score", 0)
        if content_score < 7:
            return GateResult(
                passed=False, action="block",
                reason=f"Content coherence too low: {content_score}/10"
            )

        return GateResult(passed=True, action="continue", score=content_score)

    def evaluate_manual_review_needed(self, job: dict, config: dict) -> bool:
        """
        Phase 7.5: Should this job go to manual review?
        See ARCHITECTURE.md §4.3 for detailed logic.
        """
        review_config = config.get("settings", {}).get("manual_review", {})

        if not review_config.get("enabled", True) or review_config.get("mode") == "off":
            logger.critical(
                "⚠️ MANUAL REVIEW DISABLED — publishing without human verification."
            )
            return False

        if review_config.get("mode") == "all":
            return True

        # Mode: selective
        always_review_categories = [
            "politics", "political_analysis", "geopolitics",
            "religion", "islamic", "sectarian",
            "war", "military_conflict", "terrorism",
            "legal", "crime", "human_rights",
            "biography_living_person",
        ]
        if job.get("topic_region") in always_review_categories:
            return True

        min_score = review_config.get("auto_publish_min_score", 8.5)
        # In real implementation, check rubric stats, channel maturity, etc.
        # For now, default to requiring review
        return True
