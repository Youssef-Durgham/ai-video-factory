"""
Watch Optimizer Agent — Retention analysis → script feedback loop.
Reads YouTube retention data, identifies drop-off points, generates rules.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from src.core.database import FactoryDB
from src.core import llm

logger = logging.getLogger(__name__)

# Retention thresholds
GOOD_RETENTION_PCT = 55
EXCELLENT_RETENTION_PCT = 70
DROP_OFF_THRESHOLD = 0.10  # 10% drop between adjacent segments = significant


class WatchOptimizer:
    """
    Analyzes YouTube audience retention data to improve future scripts.
    Generates actionable rules fed back to script writer.
    """

    def __init__(self, db: FactoryDB):
        self.db = db

    def run(self, channel_id: str) -> list[dict]:
        """
        Analyze retention across recent videos and generate optimization rules.

        Returns: List of rule dicts to store in performance_rules table.
        """
        # Get retention data for recent videos
        videos = self._get_retention_data(channel_id, limit=20)
        if not videos:
            logger.info(f"No retention data for {channel_id}")
            return []

        # Identify patterns
        drop_offs = self._find_drop_off_patterns(videos)
        high_retention = self._find_high_retention_patterns(videos)

        # Generate rules via LLM
        rules = self._generate_rules(channel_id, drop_offs, high_retention)

        # Save rules to DB
        self._save_rules(channel_id, rules)

        logger.info(f"Watch optimizer: {len(rules)} rules generated for {channel_id}")
        return rules

    def analyze_video(self, job_id: str) -> dict:
        """Analyze a single video's retention data in detail."""
        data = self._get_video_retention(job_id)
        if not data:
            return {"status": "no_data"}

        segments = data.get("retention_curve", [])
        drop_points = []
        for i in range(1, len(segments)):
            drop = segments[i - 1] - segments[i]
            if drop > DROP_OFF_THRESHOLD:
                timestamp_sec = i * (data.get("duration_sec", 600) / len(segments))
                drop_points.append({
                    "timestamp_sec": int(timestamp_sec),
                    "drop_pct": round(drop * 100, 1),
                    "segment_index": i,
                })

        return {
            "job_id": job_id,
            "avg_retention_pct": round(sum(segments) / len(segments) * 100, 1) if segments else 0,
            "drop_off_points": drop_points,
            "best_segment": max(range(len(segments)), key=lambda i: segments[i]) if segments else 0,
            "worst_segment": min(range(len(segments)), key=lambda i: segments[i]) if segments else 0,
        }

    def _find_drop_off_patterns(self, videos: list) -> list[dict]:
        """Find common drop-off patterns across videos."""
        patterns = []
        for video in videos:
            curve = video.get("retention_curve", [])
            duration = video.get("duration_sec", 600)
            if not curve:
                continue

            for i in range(1, len(curve)):
                drop = curve[i - 1] - curve[i]
                if drop > DROP_OFF_THRESHOLD:
                    time_pct = i / len(curve)
                    patterns.append({
                        "job_id": video.get("job_id"),
                        "time_pct": round(time_pct, 2),
                        "drop_pct": round(drop * 100, 1),
                        "narrative_style": video.get("narrative_style"),
                        "scene_type": self._identify_scene_type(video, i, len(curve)),
                    })

        return patterns

    def _find_high_retention_patterns(self, videos: list) -> list[dict]:
        """Find segments with above-average retention."""
        patterns = []
        for video in videos:
            curve = video.get("retention_curve", [])
            if not curve:
                continue
            avg = sum(curve) / len(curve)
            for i, val in enumerate(curve):
                if val > avg * 1.15:  # 15% above average
                    patterns.append({
                        "job_id": video.get("job_id"),
                        "time_pct": round(i / len(curve), 2),
                        "retention_pct": round(val * 100, 1),
                        "narrative_style": video.get("narrative_style"),
                    })
        return patterns

    def _generate_rules(self, channel_id: str, drop_offs: list, high_retention: list) -> list[dict]:
        """Use LLM to generate actionable rules from retention patterns."""
        drops_summary = json.dumps(drop_offs[:15], ensure_ascii=False) if drop_offs else "No significant drops"
        highs_summary = json.dumps(high_retention[:15], ensure_ascii=False) if high_retention else "No standout segments"

        prompt = f"""You are a YouTube retention optimization expert for Arabic documentary channels.

DROP-OFF PATTERNS (where viewers leave):
{drops_summary}

HIGH-RETENTION PATTERNS (where viewers stay):
{highs_summary}

Generate 3-5 actionable rules for improving audience retention.
Each rule should be specific and implementable by a script writer.

Return JSON array of objects: [{{
    "rule_name": "short English identifier",
    "rule_text": "Specific Arabic instruction for the script writer",
    "category": "retention",
    "confidence": 0.0-1.0,
    "reason": "English explanation of why"
}}]"""

        try:
            rules = llm.generate_json(prompt, temperature=0.4)
            if isinstance(rules, dict):
                rules = rules.get("rules", [rules])
            if not isinstance(rules, list):
                rules = [rules]
            return rules[:5]
        except Exception as e:
            logger.warning(f"Rule generation failed: {e}")
            return []

    def _identify_scene_type(self, video: dict, segment_idx: int, total_segments: int) -> str:
        """Identify what type of content is at a specific segment."""
        pct = segment_idx / total_segments
        if pct < 0.05:
            return "hook"
        elif pct < 0.15:
            return "intro"
        elif pct > 0.90:
            return "outro"
        elif pct > 0.75:
            return "conclusion"
        else:
            return "body"

    def _get_retention_data(self, channel_id: str, limit: int = 20) -> list[dict]:
        """Fetch retention data from DB."""
        try:
            rows = self.db.conn.execute("""
                SELECT j.id as job_id, j.narrative_style, j.topic,
                       a.retention_curve, a.duration_sec, a.avg_view_duration_sec
                FROM job_analytics a
                JOIN jobs j ON j.id = a.job_id
                WHERE j.channel_id = ? AND a.retention_curve IS NOT NULL
                ORDER BY j.created_at DESC LIMIT ?
            """, (channel_id, limit)).fetchall()
            results = []
            for r in rows:
                d = dict(r)
                if d.get("retention_curve"):
                    try:
                        d["retention_curve"] = json.loads(d["retention_curve"])
                    except (json.JSONDecodeError, TypeError):
                        d["retention_curve"] = []
                results.append(d)
            return results
        except Exception:
            return []

    def _get_video_retention(self, job_id: str) -> Optional[dict]:
        """Get retention data for a single video."""
        try:
            row = self.db.conn.execute(
                "SELECT retention_curve, duration_sec FROM job_analytics WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if row:
                d = dict(row)
                if d.get("retention_curve"):
                    d["retention_curve"] = json.loads(d["retention_curve"])
                return d
        except Exception:
            pass
        return None

    def _save_rules(self, channel_id: str, rules: list[dict]):
        """Save generated rules to performance_rules table."""
        for rule in rules:
            try:
                self.db.conn.execute("""
                    INSERT INTO performance_rules
                        (channel_id, rule_name, rule_text, category, confidence, reason, active, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                """, (
                    channel_id,
                    rule.get("rule_name", "unnamed"),
                    rule.get("rule_text", ""),
                    rule.get("category", "retention"),
                    rule.get("confidence", 0.5),
                    rule.get("reason", ""),
                    datetime.now().isoformat(),
                ))
            except Exception as e:
                logger.warning(f"Failed to save rule: {e}")
        try:
            self.db.conn.commit()
        except Exception:
            pass
