"""
Phase 7 — Video QA Coordinator: Orchestrates all QA checks on the final video.
Runs technical → content → compliance → Telegram preview.
Returns Phase7Result with aggregate gate decision.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.core.config import load_config, get_setting, resolve_path
from src.core.database import FactoryDB
from src.phase7_video_qa.technical_check import TechnicalChecker, TechnicalResult
from src.phase7_video_qa.content_check import ContentChecker, ContentCheckResult
from src.phase7_video_qa.final_compliance import ComplianceChecker, ComplianceResult
from src.phase7_video_qa.telegram_final_preview import send_final_preview

logger = logging.getLogger(__name__)

PHASE7_PASS_SCORE = 7.0


@dataclass
class Phase7Result:
    """Aggregate result from all Phase 7 QA checks."""
    passed: bool = False
    gate_decision: str = "block"  # "pass" | "block" | "manual_review"
    overall_score: float = 0.0
    technical: Optional[TechnicalResult] = None
    content: Optional[ContentCheckResult] = None
    compliance: Optional[ComplianceResult] = None
    all_issues: list[str] = field(default_factory=list)
    total_time_ms: int = 0


class VideoQACoordinator:
    """
    Orchestrates Phase 7 Video QA:
    1. Technical check (CPU — ffprobe)
    2. Content check (vision LLM — Qwen 3.5-27B)
    3. Final compliance (text LLM — Qwen 3.5)
    4. Send final preview to Telegram
    5. Return aggregate result + gate decision
    """

    def __init__(self, config: dict = None, db: FactoryDB = None):
        self.config = config or load_config()
        self.db = db or FactoryDB()
        self._technical = TechnicalChecker(self.config)
        self._content = ContentChecker(self.config)
        self._compliance = ComplianceChecker(self.config)

    def run(self, job_id: str) -> Phase7Result:
        """
        Run all Phase 7 checks on the final composed video.
        Returns Phase7Result with gate decision.
        """
        t0 = time.perf_counter_ns()
        result = Phase7Result()

        # Load job data
        job = self.db.get_job(job_id)
        if not job:
            logger.error("Job not found: %s", job_id)
            result.all_issues.append(f"Job {job_id} not found")
            return result

        # Resolve video path
        video_path = resolve_path(f"output/{job_id}/final.mp4")
        if not video_path.exists():
            logger.error("Final video not found: %s", video_path)
            result.all_issues.append("Final video file not found")
            self.db.block_job(job_id, "phase7", "Final video missing")
            return result

        # Load scenes
        scenes = self.db.get_scenes(job_id)
        if not scenes:
            logger.error("No scenes found for job %s", job_id)
            result.all_issues.append("No scenes in database")
            self.db.block_job(job_id, "phase7", "No scenes found")
            return result

        # Load script + SEO data for compliance check
        title = job.get("topic", "Untitled")
        script_text = self._get_latest_script(job_id)
        seo = self._get_seo_data(job_id)
        tags = json.loads(seo.get("tags", "[]")) if seo else []
        description = seo.get("description_template", "") if seo else ""

        logger.info("Phase 7 QA starting for job %s (%d scenes)", job_id, len(scenes))

        # ─── Step 1: Technical Check (CPU) ───
        logger.info("Step 1/4: Technical check...")
        result.technical = self._technical.check(str(video_path))
        result.all_issues.extend(result.technical.issues)

        # Save to DB
        self._save_compliance(
            job_id, "technical",
            "pass" if result.technical.passed else "fail",
            result.technical.score,
            result.technical.issues,
        )

        # If technical hard fail, skip remaining checks
        if not result.technical.file_valid:
            logger.error("Technical hard fail — skipping remaining checks")
            result.gate_decision = "block"
            result.overall_score = 0.0
            self.db.block_job(job_id, "phase7", "Technical QA hard fail")
            result.total_time_ms = (time.perf_counter_ns() - t0) // 1_000_000
            return result

        # ─── Step 2: Content Check (Vision LLM) ───
        logger.info("Step 2/4: Content check (vision LLM)...")
        result.content = self._content.check(str(video_path), scenes)
        result.all_issues.extend(result.content.issues)

        self._save_compliance(
            job_id, "content",
            "pass" if result.content.passed else "fail",
            result.content.score,
            result.content.issues,
        )

        # ─── Step 3: Final Compliance (Text LLM) ───
        logger.info("Step 3/4: Compliance check (text LLM)...")
        result.compliance = self._compliance.check(
            job_id=job_id,
            title=title,
            script_text=script_text,
            scenes=scenes,
            tags=tags,
            description=description,
        )
        result.all_issues.extend(result.compliance.issues)

        self._save_compliance(
            job_id, "compliance",
            "pass" if result.compliance.passed else "fail",
            result.compliance.score,
            result.compliance.issues,
        )

        # ─── Aggregate Score ───
        tech_weight = 0.30
        content_weight = 0.40
        compliance_weight = 0.30

        result.overall_score = round(
            result.technical.score * tech_weight
            + result.content.score * content_weight
            + result.compliance.score * compliance_weight,
            2,
        )

        # ─── Gate Decision ───
        if (
            result.technical.passed
            and result.content.passed
            and result.compliance.passed
            and result.overall_score >= PHASE7_PASS_SCORE
        ):
            result.passed = True
            result.gate_decision = "pass"
        elif result.overall_score >= 5.0:
            result.gate_decision = "manual_review"
            self.db.update_job_status(job_id, "manual_review")
        else:
            result.gate_decision = "block"
            self.db.block_job(job_id, "phase7", "; ".join(result.all_issues[:3]))

        # ─── Step 4: Telegram Preview ───
        logger.info("Step 4/4: Sending Telegram preview...")
        try:
            send_final_preview(
                job_id=job_id,
                video_path=str(video_path),
                title=title,
                duration_sec=result.technical.duration_sec,
                technical_score=result.technical.score,
                content_score=result.content.score,
                compliance_passed=result.compliance.passed,
                issues=result.all_issues,
            )
        except Exception as e:
            logger.error("Telegram preview failed (non-fatal): %s", e)

        # ─── Update Job ───
        result.total_time_ms = (time.perf_counter_ns() - t0) // 1_000_000

        self.db.conn.execute(
            "UPDATE jobs SET phase7_completed_at = ?, updated_at = ? WHERE id = ?",
            (datetime.now().isoformat(), datetime.now().isoformat(), job_id),
        )
        self.db.conn.commit()

        logger.info(
            "Phase 7 complete: job=%s score=%.1f gate=%s issues=%d time=%dms",
            job_id, result.overall_score, result.gate_decision,
            len(result.all_issues), result.total_time_ms,
        )

        return result

    # ─── Internal Helpers ────────────────────────────────

    def _get_latest_script(self, job_id: str) -> str:
        """Get the latest approved script text for a job."""
        row = self.db.conn.execute(
            "SELECT full_text FROM scripts WHERE job_id = ? "
            "ORDER BY version DESC LIMIT 1",
            (job_id,),
        ).fetchone()
        return row["full_text"] if row else ""

    def _get_seo_data(self, job_id: str) -> Optional[dict]:
        """Get SEO data for a job."""
        row = self.db.conn.execute(
            "SELECT * FROM seo_data WHERE job_id = ? ORDER BY id DESC LIMIT 1",
            (job_id,),
        ).fetchone()
        return dict(row) if row else None

    def _save_compliance(
        self,
        job_id: str,
        check_type: str,
        status: str,
        score: float,
        issues: list[str],
    ) -> None:
        """Save compliance check result to database."""
        self.db.conn.execute(
            """INSERT INTO compliance_checks
               (job_id, phase, check_type, status, score, details, flagged_items)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                job_id,
                "phase7",
                check_type,
                status,
                score,
                f"{check_type} QA check",
                json.dumps(issues),
            ),
        )
        self.db.conn.commit()
