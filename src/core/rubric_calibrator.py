"""
Vision QA Rubric Calibration System.

Problem: Rubric weights (semantic_match * 0.25, etc.) are initially arbitrary.
Solution: After enough Phase 9 data, auto-calibrate weights based on real performance.

Calibration loop:
  Phase 6 QA rubric scores ──┐
                              ├──→ Correlation Analysis (after 20+ videos)
  Phase 9 YouTube metrics ───┘
  (CTR, retention, watch time)

Questions answered:
  - Which rubric axes correlate with HIGH retention? → Increase weight
  - Which axes don't correlate? → Decrease weight
  - Is threshold (7.0) too high or too low?
  - Are regen decisions correct?
"""

import json
import logging
import math
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.database import FactoryDB

logger = logging.getLogger(__name__)


# Default rubric weights
DEFAULT_IMAGE_WEIGHTS = {
    "semantic_match": 0.25,
    "element_presence": 0.20,
    "composition": 0.15,
    "style_fit": 0.10,
    "artifact_severity": 0.15,
    "cultural": 0.05,
    "emotion": 0.10,
}

DEFAULT_THRESHOLD = 7.0
MIN_VIDEOS_FOR_CALIBRATION = 20


@dataclass
class CalibrationResult:
    """Result of a calibration run."""
    calibration_type: str  # 'image' | 'video' | 'thumbnail'
    videos_analyzed: int
    old_weights: Dict[str, float]
    new_weights: Dict[str, float]
    old_threshold: float
    new_threshold: float
    correlations: Dict[str, float]  # {axis: pearson_r}
    confidence: float  # Overall calibration confidence (0-1)
    notes: str = ""


class RubricCalibrator:
    """
    Auto-calibrates QA rubric weights based on real YouTube performance.

    DB table: calibration_history
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS calibration_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        calibration_type TEXT,
        videos_analyzed INTEGER,
        old_weights TEXT,
        new_weights TEXT,
        old_threshold REAL,
        new_threshold REAL,
        correlations TEXT,
        confidence REAL,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """

    def __init__(self, db: "FactoryDB", config: dict = None):
        self.db = db
        self.config = config or {}

        # Ensure table exists
        self.db.conn.executescript(self.SCHEMA)
        self.db.conn.commit()

    def should_calibrate(self) -> bool:
        """True if 20+ new videos since last calibration."""
        last = self.db.conn.execute(
            "SELECT MAX(created_at) FROM calibration_history"
        ).fetchone()[0]

        if last is None:
            # Never calibrated — check if enough videos exist
            count = self.db.conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE status = 'published'"
            ).fetchone()[0]
        else:
            count = self.db.conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE status = 'published' AND created_at > ?",
                (last,)
            ).fetchone()[0]

        return count >= MIN_VIDEOS_FOR_CALIBRATION

    def get_current_weights(self, calibration_type: str = "image") -> Dict[str, float]:
        """Return active weights (calibrated or default)."""
        # Check for most recent calibration
        row = self.db.conn.execute(
            "SELECT new_weights FROM calibration_history WHERE calibration_type = ? ORDER BY created_at DESC LIMIT 1",
            (calibration_type,)
        ).fetchone()

        if row and row[0]:
            try:
                return json.loads(row[0])
            except (json.JSONDecodeError, TypeError):
                pass

        # Fall back to config or defaults
        config_weights = (
            self.config.get("settings", {})
            .get("rubric_calibration", {})
            .get("image_weights")
        )
        return config_weights or DEFAULT_IMAGE_WEIGHTS.copy()

    def get_current_threshold(self, calibration_type: str = "image") -> float:
        """Return active threshold (calibrated or default)."""
        row = self.db.conn.execute(
            "SELECT new_threshold FROM calibration_history WHERE calibration_type = ? ORDER BY created_at DESC LIMIT 1",
            (calibration_type,)
        ).fetchone()

        if row and row[0] is not None:
            return row[0]

        return (
            self.config.get("settings", {})
            .get("rubric_calibration", {})
            .get("calibrated_threshold")
        ) or DEFAULT_THRESHOLD

    def calibrate(self, calibration_type: str = "image",
                  min_videos: int = MIN_VIDEOS_FOR_CALIBRATION) -> Optional[CalibrationResult]:
        """
        Run calibration:
        1. Pull all qa_rubrics + youtube_analytics for published videos
        2. For each rubric axis, calculate Pearson correlation with retention/CTR
        3. Normalize correlations → new weights
        4. Analyze threshold: find optimal cutoff
        5. Save to DB + calibration_history
        """
        # Gather data
        rows = self.db.conn.execute("""
            SELECT j.id, j.status,
                   qa.rubric_scores,
                   ya.avg_view_percentage, ya.ctr, ya.watch_time_hours
            FROM jobs j
            LEFT JOIN qa_rubrics qa ON j.id = qa.job_id
            LEFT JOIN youtube_analytics ya ON j.id = ya.job_id
            WHERE j.status = 'published'
              AND qa.rubric_scores IS NOT NULL
              AND ya.avg_view_percentage IS NOT NULL
            ORDER BY j.created_at DESC
        """).fetchall()

        if len(rows) < min_videos:
            logger.info(
                f"Not enough data for calibration: {len(rows)}/{min_videos} videos"
            )
            return None

        # Parse rubric scores
        data_points = []
        for row in rows:
            try:
                scores = json.loads(row[2]) if isinstance(row[2], str) else row[2]
                data_points.append({
                    "scores": scores,
                    "retention": row[3],
                    "ctr": row[4],
                    "watch_time": row[5],
                })
            except (json.JSONDecodeError, TypeError):
                continue

        if len(data_points) < min_videos:
            return None

        old_weights = self.get_current_weights(calibration_type)
        old_threshold = self.get_current_threshold(calibration_type)

        # Calculate correlations
        axes = list(old_weights.keys())
        correlations = {}

        for axis in axes:
            axis_values = [dp["scores"].get(axis, 0) for dp in data_points]
            retention_values = [dp["retention"] for dp in data_points]

            r = self._pearson_correlation(axis_values, retention_values)
            correlations[axis] = round(r, 4) if r is not None else 0.0

        # Normalize positive correlations into new weights
        positive_corrs = {k: max(v, 0.01) for k, v in correlations.items()}
        total = sum(positive_corrs.values())
        new_weights = {k: round(v / total, 4) for k, v in positive_corrs.items()}

        # Calculate confidence (average |correlation|)
        confidence = sum(abs(v) for v in correlations.values()) / len(correlations) if correlations else 0

        # Threshold optimization — simple approach
        all_scores = []
        for dp in data_points:
            weighted_score = sum(
                dp["scores"].get(axis, 0) * new_weights.get(axis, 0)
                for axis in axes
            ) * 10  # Scale to 0-10
            all_scores.append((weighted_score, dp["retention"]))

        new_threshold = self._find_optimal_threshold(all_scores, old_threshold)

        # Build notes
        weight_changes = []
        for axis in axes:
            old_w = old_weights.get(axis, 0)
            new_w = new_weights.get(axis, 0)
            if abs(new_w - old_w) > 0.02:
                direction = "↑" if new_w > old_w else "↓"
                weight_changes.append(f"{axis} {old_w:.2f}→{new_w:.2f} {direction}")

        notes = "; ".join(weight_changes) if weight_changes else "No significant changes"

        result = CalibrationResult(
            calibration_type=calibration_type,
            videos_analyzed=len(data_points),
            old_weights=old_weights,
            new_weights=new_weights,
            old_threshold=old_threshold,
            new_threshold=new_threshold,
            correlations=correlations,
            confidence=round(confidence, 4),
            notes=notes,
        )

        # Save to DB
        self.db.conn.execute("""
            INSERT INTO calibration_history
            (calibration_type, videos_analyzed, old_weights, new_weights,
             old_threshold, new_threshold, correlations, confidence, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            result.calibration_type,
            result.videos_analyzed,
            json.dumps(result.old_weights),
            json.dumps(result.new_weights),
            result.old_threshold,
            result.new_threshold,
            json.dumps(result.correlations),
            result.confidence,
            result.notes,
        ))
        self.db.conn.commit()

        logger.info(
            f"Calibration complete: {result.videos_analyzed} videos, "
            f"confidence={result.confidence:.2f}, threshold {old_threshold}→{new_threshold}"
        )

        return result

    @staticmethod
    def _pearson_correlation(x: List[float], y: List[float]) -> Optional[float]:
        """Calculate Pearson correlation coefficient."""
        n = len(x)
        if n < 3:
            return None

        mean_x = sum(x) / n
        mean_y = sum(y) / n

        num = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
        den_x = math.sqrt(sum((xi - mean_x) ** 2 for xi in x))
        den_y = math.sqrt(sum((yi - mean_y) ** 2 for yi in y))

        if den_x == 0 or den_y == 0:
            return 0.0

        return num / (den_x * den_y)

    @staticmethod
    def _find_optimal_threshold(
        scores_and_retention: List[tuple],
        default: float,
    ) -> float:
        """
        Find optimal QA threshold using simple split analysis.
        Maximize: high-performing videos pass, low-performing fail.
        """
        if not scores_and_retention:
            return default

        # Median retention as "good/bad" divider
        retentions = sorted(r for _, r in scores_and_retention)
        median_retention = retentions[len(retentions) // 2]

        best_threshold = default
        best_accuracy = 0.0

        for threshold_candidate in [t / 10.0 for t in range(50, 95)]:  # 5.0 to 9.5
            correct = 0
            for score, retention in scores_and_retention:
                passed = score >= threshold_candidate
                good_video = retention >= median_retention
                if passed == good_video:
                    correct += 1

            accuracy = correct / len(scores_and_retention)
            if accuracy > best_accuracy:
                best_accuracy = accuracy
                best_threshold = threshold_candidate

        return round(best_threshold, 1)
