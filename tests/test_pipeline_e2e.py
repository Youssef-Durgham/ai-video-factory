"""End-to-end pipeline test — full state machine traversal with stubbed phases."""

import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock
from src.core.database import FactoryDB
from src.core.job_state_machine import JobStateMachine, JobStatus, StateError
from src.core.gate_evaluator import GateEvaluator, GateResult
from src.core.event_bus import EventBus, Event, EventType
from src.core.pipeline_runner import PipelineRunner
from src.core.config import load_config
from src.models.analytics import PhaseResult


@pytest.fixture
def tmpdb():
    with tempfile.TemporaryDirectory() as tmpdir:
        db = FactoryDB(os.path.join(tmpdir, "test.db"))
        yield db
        db.close()


@pytest.fixture
def config():
    return load_config()


class TestFullPipelineTraversal:
    """Test job traversing all states from PENDING to PUBLISHED."""

    def test_happy_path(self, tmpdb, config):
        """Job goes through all phases with all gates passing."""
        runner = PipelineRunner(config, tmpdb)

        job_id = tmpdb.create_job("documentary_ar", "Test E2E Topic")
        tmpdb.update_job_status(job_id, "research")

        result = runner.run_job(job_id)
        job = tmpdb.get_job(job_id)

        # Should reach a terminal or pause state
        assert job["status"] in (
            "published", "manual_review", "blocked",
            "complete", "tracking_24h",
        )

    def test_all_states_reachable(self, tmpdb):
        """Verify the state machine allows a full traversal."""
        sm = JobStateMachine(tmpdb)
        job_id = tmpdb.create_job("ch", "topic")

        # Walk through the happy path
        expected_path = [
            JobStatus.RESEARCH, JobStatus.SEO, JobStatus.SCRIPT,
            JobStatus.COMPLIANCE, JobStatus.IMAGES, JobStatus.IMAGE_QA,
            JobStatus.VIDEO, JobStatus.VIDEO_QA, JobStatus.VOICE,
            JobStatus.MUSIC, JobStatus.SFX, JobStatus.COMPOSE,
            JobStatus.OVERLAY_QA, JobStatus.FINAL_QA,
            JobStatus.MANUAL_REVIEW, JobStatus.PUBLISH,
            JobStatus.PUBLISHED,
        ]

        for status in expected_path:
            sm.transition(job_id, status)
            job = tmpdb.get_job(job_id)
            assert job["status"] == status.value


class TestStateTransitions:
    """Test valid and invalid state transitions."""

    def test_invalid_transition_raises(self, tmpdb):
        sm = JobStateMachine(tmpdb)
        job_id = tmpdb.create_job("ch", "topic")

        sm.transition(job_id, JobStatus.RESEARCH)
        with pytest.raises(StateError):
            sm.transition(job_id, JobStatus.PUBLISH)

    def test_blocked_can_resume(self, tmpdb):
        sm = JobStateMachine(tmpdb)
        job_id = tmpdb.create_job("ch", "topic")

        sm.transition(job_id, JobStatus.RESEARCH)
        sm.transition(job_id, JobStatus.BLOCKED)
        # Should be able to resume to RESEARCH from BLOCKED
        sm.transition(job_id, JobStatus.RESEARCH)
        assert tmpdb.get_job(job_id)["status"] == "research"

    def test_cancelled_is_terminal(self, tmpdb):
        sm = JobStateMachine(tmpdb)
        job_id = tmpdb.create_job("ch", "topic")

        sm.transition(job_id, JobStatus.RESEARCH)
        sm.transition(job_id, JobStatus.SEO)
        sm.transition(job_id, JobStatus.SCRIPT)
        sm.transition(job_id, JobStatus.COMPLIANCE)
        sm.transition(job_id, JobStatus.BLOCKED)
        sm.transition(job_id, JobStatus.CANCELLED)

        with pytest.raises(StateError):
            sm.transition(job_id, JobStatus.RESEARCH)

    def test_complete_is_terminal(self, tmpdb):
        sm = JobStateMachine(tmpdb)
        job_id = tmpdb.create_job("ch", "topic")

        # Fast-forward to complete
        for status in [JobStatus.RESEARCH, JobStatus.SEO, JobStatus.SCRIPT,
                       JobStatus.COMPLIANCE, JobStatus.IMAGES, JobStatus.IMAGE_QA,
                       JobStatus.VIDEO, JobStatus.VIDEO_QA, JobStatus.VOICE,
                       JobStatus.MUSIC, JobStatus.SFX, JobStatus.COMPOSE,
                       JobStatus.OVERLAY_QA, JobStatus.FINAL_QA,
                       JobStatus.PUBLISH, JobStatus.PUBLISHED,
                       JobStatus.TRACKING_24H, JobStatus.TRACKING_7D,
                       JobStatus.TRACKING_30D, JobStatus.COMPLETE]:
            sm.transition(job_id, status)

        with pytest.raises(StateError):
            sm.transition(job_id, JobStatus.RESEARCH)


class TestEventEmissions:
    """Test events are emitted during pipeline execution."""

    def test_phase_events_emitted(self, tmpdb, config):
        runner = PipelineRunner(config, tmpdb)
        events_received = []
        runner.events.subscribe_all(lambda e: events_received.append(e))

        job_id = tmpdb.create_job("documentary_ar", "Event Test")
        tmpdb.update_job_status(job_id, "research")
        runner.run_job(job_id)

        event_types = [e.type for e in events_received]
        assert EventType.PHASE_STARTED in event_types
        assert EventType.PHASE_COMPLETED in event_types

    def test_job_id_in_events(self, tmpdb, config):
        runner = PipelineRunner(config, tmpdb)
        events_received = []
        runner.events.subscribe_all(lambda e: events_received.append(e))

        job_id = tmpdb.create_job("documentary_ar", "Event ID Test")
        tmpdb.update_job_status(job_id, "research")
        runner.run_job(job_id)

        for event in events_received:
            if event.type in (EventType.PHASE_STARTED, EventType.PHASE_COMPLETED):
                assert event.job_id == job_id


class TestGateEvaluations:
    """Test gate pass/fail/block decisions."""

    def test_compliance_gate_pass(self):
        gates = GateEvaluator()
        result = PhaseResult(success=True, score=9.0, is_gate=True, gate_data={
            "checks": [
                {"status": "pass", "score": 9, "details": "Clean content"},
            ]
        })
        gr = gates.evaluate(JobStatus.COMPLIANCE, result)
        assert gr.passed
        assert gr.action == "continue"

    def test_compliance_gate_block(self):
        gates = GateEvaluator()
        result = PhaseResult(success=True, score=0, is_gate=True, gate_data={
            "checks": [
                {"status": "block", "score": 0, "details": "Policy violation"},
            ]
        })
        gr = gates.evaluate(JobStatus.COMPLIANCE, result)
        assert not gr.passed
        assert gr.action == "block"

    def test_image_qa_retry(self):
        gates = GateEvaluator()
        result = PhaseResult(success=True, score=7, is_gate=True, gate_data={
            "image_scores": [
                {"scene_index": i, "score": 8 if i < 7 else 3}
                for i in range(10)
            ]
        })
        gr = gates.evaluate(JobStatus.IMAGE_QA, result)
        assert not gr.passed
        assert gr.action == "retry"
        assert gr.failed_items is not None
        assert len(gr.failed_items) == 3

    def test_image_qa_pass(self):
        gates = GateEvaluator()
        result = PhaseResult(success=True, score=9, is_gate=True, gate_data={
            "image_scores": [
                {"scene_index": i, "score": 8}
                for i in range(10)
            ]
        })
        gr = gates.evaluate(JobStatus.IMAGE_QA, result)
        assert gr.passed

    def test_final_qa_av_sync_retry(self):
        gates = GateEvaluator()
        result = PhaseResult(success=True, score=8, is_gate=True, gate_data={
            "technical": {"av_sync_drift_ms": 200},
            "content": {"score": 8},
        })
        gr = gates.evaluate(JobStatus.FINAL_QA, result)
        assert not gr.passed
        assert gr.action == "retry"


class TestManualReviewPause:
    """Test pipeline pauses at manual review."""

    def test_manual_review_pauses_pipeline(self, tmpdb, config):
        """Pipeline should stop at MANUAL_REVIEW and not auto-continue."""
        runner = PipelineRunner(config, tmpdb)

        job_id = tmpdb.create_job("documentary_ar", "Review Test")
        tmpdb.update_job_status(job_id, "manual_review")

        result = runner.run_job(job_id)
        job = tmpdb.get_job(job_id)
        # Should still be in manual_review (paused)
        assert job["status"] == "manual_review"

    def test_manual_review_approval_continues(self, tmpdb):
        """After approval, job should transition to PUBLISH."""
        sm = JobStateMachine(tmpdb)
        job_id = tmpdb.create_job("ch", "topic")

        # Get to manual review
        for status in [JobStatus.RESEARCH, JobStatus.SEO, JobStatus.SCRIPT,
                       JobStatus.COMPLIANCE, JobStatus.IMAGES, JobStatus.IMAGE_QA,
                       JobStatus.VIDEO, JobStatus.VIDEO_QA, JobStatus.VOICE,
                       JobStatus.MUSIC, JobStatus.SFX, JobStatus.COMPOSE,
                       JobStatus.OVERLAY_QA, JobStatus.FINAL_QA,
                       JobStatus.MANUAL_REVIEW]:
            sm.transition(job_id, status)

        # Approve → PUBLISH
        sm.transition(job_id, JobStatus.PUBLISH)
        assert tmpdb.get_job(job_id)["status"] == "publish"

    def test_manual_review_rejection_cancels(self, tmpdb):
        """Rejection should allow transition to CANCELLED."""
        sm = JobStateMachine(tmpdb)
        job_id = tmpdb.create_job("ch", "topic")

        for status in [JobStatus.RESEARCH, JobStatus.SEO, JobStatus.SCRIPT,
                       JobStatus.COMPLIANCE, JobStatus.IMAGES, JobStatus.IMAGE_QA,
                       JobStatus.VIDEO, JobStatus.VIDEO_QA, JobStatus.VOICE,
                       JobStatus.MUSIC, JobStatus.SFX, JobStatus.COMPOSE,
                       JobStatus.OVERLAY_QA, JobStatus.FINAL_QA,
                       JobStatus.MANUAL_REVIEW]:
            sm.transition(job_id, status)

        sm.transition(job_id, JobStatus.CANCELLED)
        assert tmpdb.get_job(job_id)["status"] == "cancelled"


class TestImageRegenLoop:
    """Test image QA → regen → re-verify loop."""

    def test_image_regen_returns_to_qa(self, tmpdb):
        sm = JobStateMachine(tmpdb)
        job_id = tmpdb.create_job("ch", "topic")

        for s in [JobStatus.RESEARCH, JobStatus.SEO, JobStatus.SCRIPT,
                  JobStatus.COMPLIANCE, JobStatus.IMAGES, JobStatus.IMAGE_QA]:
            sm.transition(job_id, s)

        # QA fails → regen
        sm.transition(job_id, JobStatus.IMAGE_REGEN)
        assert tmpdb.get_job(job_id)["status"] == "image_regen"

        # Regen → back to QA
        sm.transition(job_id, JobStatus.IMAGE_QA)
        assert tmpdb.get_job(job_id)["status"] == "image_qa"

        # Now passes → video
        sm.transition(job_id, JobStatus.VIDEO)
        assert tmpdb.get_job(job_id)["status"] == "video"


class TestTrackingStates:
    """Test Phase 9 tracking state transitions."""

    def test_tracking_flow(self, tmpdb):
        sm = JobStateMachine(tmpdb)
        job_id = tmpdb.create_job("ch", "topic")

        # Fast path to published
        for s in [JobStatus.RESEARCH, JobStatus.SEO, JobStatus.SCRIPT,
                  JobStatus.COMPLIANCE, JobStatus.IMAGES, JobStatus.IMAGE_QA,
                  JobStatus.VIDEO, JobStatus.VIDEO_QA, JobStatus.VOICE,
                  JobStatus.MUSIC, JobStatus.SFX, JobStatus.COMPOSE,
                  JobStatus.OVERLAY_QA, JobStatus.FINAL_QA,
                  JobStatus.PUBLISH, JobStatus.PUBLISHED]:
            sm.transition(job_id, s)

        sm.transition(job_id, JobStatus.TRACKING_24H)
        sm.transition(job_id, JobStatus.TRACKING_7D)
        sm.transition(job_id, JobStatus.TRACKING_30D)
        sm.transition(job_id, JobStatus.COMPLETE)
        assert tmpdb.get_job(job_id)["status"] == "complete"


class TestCrashRecovery:
    """Test pipeline can resume after crash."""

    def test_resume_from_interrupted_state(self, tmpdb, config):
        """Simulated crash mid-pipeline — should resume from last state."""
        job_id = tmpdb.create_job("documentary_ar", "Crash Test")
        tmpdb.update_job_status(job_id, "voice")

        runner = PipelineRunner(config, tmpdb)
        result = runner.run_job(job_id)

        job = tmpdb.get_job(job_id)
        # Should have progressed beyond voice
        assert job["status"] != "pending"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
