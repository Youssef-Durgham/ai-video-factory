"""
Phase 8 — Thumbnail QA: 3-layer quality assurance for thumbnails.

Orchestrates the full QA pipeline:
  Layer 1: Deterministic checks (resolution, file size, faces, dead zones, mobile)
  Layer 2: Vision rubric via Qwen (click appeal, relevance, readability, emotion, pro, diff)
  Layer 3: Ranking — weighted score, rank all 3 variants, decide best + regen if needed

Wraps ThumbnailValidator and adds the ranking/decision layer.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from src.phase8_publish.thumbnail_validator import ThumbnailValidator, ThumbnailScore

logger = logging.getLogger(__name__)


@dataclass
class ThumbnailQAResult:
    """Aggregate result of thumbnail QA across all variants."""
    scores: list[ThumbnailScore] = field(default_factory=list)
    best_variant: Optional[str] = None
    best_path: Optional[str] = None
    best_score: float = 0.0
    all_pass: bool = False
    needs_regen: bool = False
    regen_reason: Optional[str] = None
    ab_test_paths: list[str] = field(default_factory=list)

    @property
    def ranked_variants(self) -> list[str]:
        """Return variant labels in ranked order (best first)."""
        return [s.variant for s in sorted(self.scores, key=lambda s: s.weighted_score, reverse=True)]


# Minimum weighted score for a thumbnail to be considered acceptable
REGEN_THRESHOLD = 6.0


class ThumbnailQA:
    """
    Full 3-layer thumbnail QA pipeline.

    Uses ThumbnailValidator for layers 1+2, then adds:
    - Cross-variant ranking
    - Best selection for primary thumbnail
    - Regen decision if all variants score below threshold
    - A/B test candidate list
    """

    def __init__(self, config: dict, db):
        self.config = config
        self.db = db
        self.validator = ThumbnailValidator(config, db)

    def run(self, job_id: str) -> ThumbnailQAResult:
        """
        Run full 3-layer QA on all thumbnail variants for a job.

        Args:
            job_id: The job whose thumbnails to evaluate.

        Returns:
            ThumbnailQAResult with ranked scores and decisions.
        """
        logger.info(f"Starting thumbnail QA for {job_id}")

        # Run validator (layers 1 + 2 + scoring)
        scores = self.validator.validate_thumbnails(job_id)

        if not scores:
            logger.warning(f"No thumbnails to QA for {job_id}")
            return ThumbnailQAResult(needs_regen=True, regen_reason="No thumbnails generated")

        result = ThumbnailQAResult(scores=scores)

        # Layer 3: Ranking + decision
        passing = [s for s in scores if s.weighted_score >= REGEN_THRESHOLD]
        result.all_pass = len(passing) == len(scores)

        if passing:
            best = passing[0]  # Already sorted by validator
            result.best_variant = best.variant
            result.best_path = best.file_path
            result.best_score = best.weighted_score
            result.ab_test_paths = [s.file_path for s in scores if s.deterministic_pass]
        else:
            # All variants below threshold — request regeneration
            result.needs_regen = True
            top_score = scores[0].weighted_score if scores else 0
            result.regen_reason = (
                f"All thumbnails below threshold ({REGEN_THRESHOLD}). "
                f"Best score: {top_score:.1f}"
            )
            logger.warning(f"Thumbnail QA failed for {job_id}: {result.regen_reason}")

        # Update thumbnails table — mark best
        if result.best_variant:
            self.db.conn.execute(
                "UPDATE thumbnails SET is_winner = 0 WHERE job_id = ?",
                (job_id,),
            )
            self.db.conn.execute(
                "UPDATE thumbnails SET is_winner = 1 WHERE job_id = ? AND variant = ?",
                (job_id, result.best_variant),
            )
            self.db.conn.commit()

        logger.info(
            f"Thumbnail QA complete for {job_id}: "
            f"best={result.best_variant} ({result.best_score:.1f}), "
            f"regen={result.needs_regen}"
        )
        return result
