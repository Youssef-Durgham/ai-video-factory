"""
PipelineRunner — the THIN orchestrator.
Does NOT contain phase logic. Only coordinates the other components.

Responsibilities:
1. Get next status from StateMachine
2. Ask PhaseExecutor to run the phase
3. Ask GateEvaluator to evaluate gates
4. Emit events via EventBus
5. Handle errors gracefully
"""

import logging
from typing import Optional

from src.core.config import load_config
from src.core.database import FactoryDB
from src.core.job_state_machine import (
    JobStateMachine, JobStatus, StateError,
    TERMINAL_STATES, PAUSE_STATES,
)
from src.core.gate_evaluator import GateEvaluator
from src.core.phase_executor import PhaseExecutor
from src.core.event_bus import EventBus, Event, EventType

logger = logging.getLogger(__name__)


class PipelineRunner:
    """
    Thin coordinator. Runs a job through the pipeline
    by delegating to specialized components.

    No phase logic here. No GPU management here.
    No gate evaluation logic here. Just coordination.
    """

    def __init__(self, config: Optional[dict] = None, db: Optional[FactoryDB] = None):
        self.config = config or load_config()
        db_path = self.config.get("settings", {}).get("database", {}).get("path", "data/factory.db")
        self.db = db or FactoryDB(db_path)

        self.state = JobStateMachine(self.db)
        self.gates = GateEvaluator(self.config)
        self.executor = PhaseExecutor(self.config, self.db)
        self.events = EventBus()

        # Wire up event subscribers (telegram, event store, etc. added externally)
        self.events.subscribe(EventType.JOB_BLOCKED, self._on_blocked)
        self.events.subscribe(EventType.JOB_PUBLISHED, self._on_published)

    def run_job(self, job_id: str) -> str:
        """
        Run a job through all phases until completion, pause, or error.
        Returns: "completed" | "paused" | "blocked" | "error"
        """
        logger.info(f"Pipeline starting for job: {job_id}")

        try:
            while True:
                job = self.db.get_job(job_id)
                if not job:
                    logger.error(f"Job not found: {job_id}")
                    return "error"

                current = JobStatus(job["status"])

                # Terminal states — done
                if current in TERMINAL_STATES:
                    logger.info(f"Job {job_id} reached terminal state: {current.value}")
                    return "completed"

                # Pause states — waiting for external input
                if current in PAUSE_STATES:
                    logger.info(f"Job {job_id} paused in state: {current.value}")
                    return "paused" if current == JobStatus.MANUAL_REVIEW else "blocked"

                # 1. Execute the phase
                self.events.emit(Event(
                    EventType.PHASE_STARTED, job_id,
                    {"phase": current.value}
                ))

                result = self.executor.execute(current, job_id)

                self.events.emit(Event(
                    EventType.PHASE_COMPLETED, job_id,
                    {"phase": current.value, "score": result.score, "success": result.success}
                ))

                if not result.success:
                    if result.blocked:
                        self.state.transition(job_id, JobStatus.BLOCKED)
                        self.db.block_job(job_id, current.value, result.reason)
                        self.events.emit(Event(
                            EventType.JOB_BLOCKED, job_id,
                            {"phase": current.value, "reason": result.reason}
                        ))
                        return "blocked"
                    # Non-blocking failure — try to continue
                    logger.warning(f"Phase {current.value} failed but not blocking: {result.reason}")

                # 2. Evaluate gate (if this phase has one)
                if result.is_gate:
                    gate_result = self.gates.evaluate(current, result)

                    if gate_result.action == "block":
                        self.state.transition(job_id, JobStatus.BLOCKED)
                        self.db.block_job(job_id, current.value, gate_result.reason)
                        self.events.emit(Event(
                            EventType.GATE_BLOCKED, job_id,
                            {"phase": current.value, "reason": gate_result.reason}
                        ))
                        return "blocked"

                    elif gate_result.action == "retry":
                        retry_status = JobStatus(gate_result.retry_phase)
                        self.state.transition(job_id, retry_status)
                        logger.info(f"Gate retry: {current.value} → {retry_status.value}")
                        continue

                    elif gate_result.action == "manual_review":
                        self.state.transition(job_id, JobStatus.MANUAL_REVIEW)
                        self.events.emit(Event(
                            EventType.MANUAL_REVIEW_REQUESTED, job_id
                        ))
                        return "paused"

                # 3. Check if manual review is needed (Phase 7 → 7.5)
                if current == JobStatus.FINAL_QA:
                    job = self.db.get_job(job_id)
                    if self.gates.evaluate_manual_review_needed(job, self.config):
                        self.state.transition(job_id, JobStatus.MANUAL_REVIEW)
                        self.events.emit(Event(
                            EventType.MANUAL_REVIEW_REQUESTED, job_id
                        ))
                        return "paused"

                # 4. Transition to next state
                next_status = self.state.get_next_status(current)
                if next_status:
                    self.state.transition(job_id, next_status)
                else:
                    logger.info(f"Job {job_id}: no next state from {current.value}")
                    return "completed"

        except StateError as e:
            logger.error(f"State machine error for job {job_id}: {e}")
            self.events.emit(Event(
                EventType.PHASE_FAILED, job_id, {"error": str(e)}
            ))
            return "error"

        except Exception as e:
            logger.error(f"Pipeline error for job {job_id}: {e}", exc_info=True)
            self.events.emit(Event(
                EventType.PHASE_FAILED, job_id, {"error": str(e)}
            ))
            return "error"

    def resume_job(self, job_id: str) -> str:
        """Resume a paused/blocked job."""
        resume_status = self.state.get_resume_status(job_id)
        logger.info(f"Resuming job {job_id} from {resume_status.value}")
        return self.run_job(job_id)

    def resume_all(self):
        """Resume all interrupted jobs after crash."""
        active_jobs = self.db.get_active_jobs()
        results = {}
        for job in active_jobs:
            job_id = job["id"]
            logger.info(f"Resuming {job_id} from {job['status']}")
            results[job_id] = self.run_job(job_id)
        return results

    def create_and_run(self, channel_id: str, topic: str, **kwargs) -> str:
        """Create a new job and run it through the pipeline."""
        job_id = self.db.create_job(channel_id, topic, **kwargs)
        self.events.emit(Event(EventType.JOB_CREATED, job_id, {
            "channel_id": channel_id, "topic": topic
        }))
        # Transition from PENDING → RESEARCH
        self.state.transition(job_id, JobStatus.RESEARCH)
        return self.run_job(job_id)

    # ─── Event Handlers ────────────────────────────────

    def _on_blocked(self, event: Event):
        logger.warning(f"⚠️ Job blocked: {event.job_id} — {event.data.get('reason', '')}")

    def _on_published(self, event: Event):
        logger.info(f"✅ Published: {event.job_id} — {event.data.get('topic', '')}")
