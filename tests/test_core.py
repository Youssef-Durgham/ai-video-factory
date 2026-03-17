"""Core system tests — config, database, state machine, gates, pipeline."""

import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_config():
    from src.core.config import load_config
    config = load_config()
    assert config["settings"]["factory"]["name"] == "AI Video Factory"
    assert len(config["channels"]) >= 1
    print("  config OK")


def test_database():
    from src.core.database import FactoryDB
    with tempfile.TemporaryDirectory() as tmpdir:
        db = FactoryDB(os.path.join(tmpdir, "test.db"))
        tables = db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = [t[0] for t in tables]
        assert "jobs" in table_names
        assert "scenes" in table_names
        assert "qa_rubrics" in table_names
        assert "events" in table_names
        assert "asset_versions" in table_names

        # WAL mode
        mode = db.conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"

        # Foreign keys
        fk = db.conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1

        # Create job
        job_id = db.create_job("test_ch", "Test Topic")
        assert job_id.startswith("job_")
        job = db.get_job(job_id)
        assert job["status"] == "pending"
        assert job["channel_id"] == "test_ch"

        # Update status
        db.update_job_status(job_id, "research")
        job = db.get_job(job_id)
        assert job["status"] == "research"

        # Save scenes
        db.save_scenes(job_id, [
            {"narration_text": "test narration", "duration_seconds": 10,
             "visual_prompt": "test prompt"},
        ])
        scenes = db.get_scenes(job_id)
        assert len(scenes) == 1
        assert scenes[0]["narration_text"] == "test narration"

        db.close()
        print("  database OK")


def test_state_machine():
    from src.core.database import FactoryDB
    from src.core.job_state_machine import JobStateMachine, JobStatus, StateError

    with tempfile.TemporaryDirectory() as tmpdir:
        db = FactoryDB(os.path.join(tmpdir, "test.db"))
        sm = JobStateMachine(db)
        job_id = db.create_job("ch", "topic")

        # Valid transitions
        prev = sm.transition(job_id, JobStatus.RESEARCH)
        assert prev == JobStatus.PENDING

        prev = sm.transition(job_id, JobStatus.SEO)
        assert prev == JobStatus.RESEARCH

        # Invalid transition
        try:
            sm.transition(job_id, JobStatus.PUBLISH)
            assert False, "Should have raised StateError"
        except StateError:
            pass

        # Next status
        nxt = sm.get_next_status(JobStatus.SEO)
        assert nxt == JobStatus.SCRIPT

        # GPU requirements
        gpu = sm.get_required_gpu(JobStatus.IMAGES)
        assert gpu == "flux"
        assert sm.get_required_gpu(JobStatus.COMPOSE) is None

        # Batching
        assert sm.can_batch_with_next(JobStatus.RESEARCH, JobStatus.SEO)
        assert not sm.can_batch_with_next(JobStatus.IMAGES, JobStatus.VOICE)

        # Terminal/pause
        assert sm.is_terminal(JobStatus.COMPLETE)
        assert sm.is_paused(JobStatus.BLOCKED)
        assert not sm.is_terminal(JobStatus.RESEARCH)

        db.close()
        print("  state machine OK")


def test_gate_evaluator():
    from src.core.gate_evaluator import GateEvaluator
    from src.core.job_state_machine import JobStatus
    from src.models.analytics import PhaseResult

    gates = GateEvaluator()

    # Compliance pass
    result = PhaseResult(success=True, score=9, is_gate=True, gate_data={
        "checks": [{"status": "pass", "score": 9, "details": "ok"}]
    })
    gr = gates.evaluate(JobStatus.COMPLIANCE, result)
    assert gr.passed
    assert gr.action == "continue"

    # Compliance block
    result = PhaseResult(success=True, score=0, is_gate=True, gate_data={
        "checks": [{"status": "block", "score": 0, "details": "policy violation"}]
    })
    gr = gates.evaluate(JobStatus.COMPLIANCE, result)
    assert not gr.passed
    assert gr.action == "block"

    # Image QA retry
    result = PhaseResult(success=True, score=7, is_gate=True, gate_data={
        "image_scores": [
            {"scene_index": i, "score": 8 if i < 8 else 4}
            for i in range(10)
        ]
    })
    gr = gates.evaluate(JobStatus.IMAGE_QA, result)
    assert not gr.passed
    assert gr.action == "retry"
    assert len(gr.failed_items) == 2

    print("  gate evaluator OK")


def test_event_bus():
    from src.core.event_bus import EventBus, Event, EventType

    bus = EventBus()
    received = []
    bus.subscribe(EventType.JOB_CREATED, lambda e: received.append(e))
    bus.subscribe_all(lambda e: received.append(("global", e)))

    bus.emit(Event(EventType.JOB_CREATED, "job_1", {"test": True}))
    assert len(received) == 2  # global + specific
    print("  event bus OK")


def test_phase_executor():
    from src.core.phase_executor import PhaseExecutor
    from src.core.job_state_machine import JobStatus
    from src.core.database import FactoryDB

    with tempfile.TemporaryDirectory() as tmpdir:
        db = FactoryDB(os.path.join(tmpdir, "test.db"))
        config = {"settings": {}}
        executor = PhaseExecutor(config, db)

        job_id = db.create_job("ch", "topic")
        result = executor.execute(JobStatus.RESEARCH, job_id)
        assert result.success  # stub returns success
        db.close()
        print("  phase executor OK")


def test_pipeline_runner():
    from src.core.pipeline_runner import PipelineRunner
    from src.core.config import load_config
    from src.core.database import FactoryDB

    config = load_config()
    with tempfile.TemporaryDirectory() as tmpdir:
        db = FactoryDB(os.path.join(tmpdir, "test.db"))
        runner = PipelineRunner(config, db)

        # Create job
        job_id = db.create_job("documentary_ar", "Test Pipeline")
        db.update_job_status(job_id, "research")

        # Run — should go through all stub phases until completion or pause
        result = runner.run_job(job_id)
        assert result in ("completed", "paused", "blocked")

        job = db.get_job(job_id)
        print(f"  pipeline runner OK (final status: {job['status']}, result: {result})")
        db.close()


def test_models():
    from src.models import Job, Scene, Script, PhaseResult

    j = Job(id="test", channel_id="ch1", topic="topic1")
    assert j.status == "pending"

    s = Scene(scene_index=0, narration_text="text", visual_prompt="prompt",
              duration_seconds=10)
    assert s.camera_movement == "slow_zoom_in"

    pr = PhaseResult(success=True, score=8.5, is_gate=True, gate_data={"checks": []})
    assert pr.is_gate
    print("  models OK")


if __name__ == "__main__":
    print("Running core tests...")
    test_config()
    test_database()
    test_state_machine()
    test_gate_evaluator()
    test_event_bus()
    test_phase_executor()
    test_models()
    test_pipeline_runner()
    print("\n=== ALL TESTS PASSED ===")
