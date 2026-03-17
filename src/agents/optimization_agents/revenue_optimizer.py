"""
Revenue Optimizer Agent — RPM tracking + mid-roll placement suggestions.
Analyzes revenue patterns to maximize earnings.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from src.core.database import FactoryDB
from src.core import llm

logger = logging.getLogger(__name__)


class RevenueOptimizer:
    """
    Tracks RPM (Revenue Per Mille) patterns and generates
    content strategy adjustments to maximize revenue.
    """

    def __init__(self, db: FactoryDB):
        self.db = db

    def run(self, channel_id: str) -> dict:
        """
        Analyze revenue patterns and generate optimization suggestions.

        Returns: {
            "avg_rpm": float,
            "best_topics": [...],
            "best_length_range": [min, max],
            "best_publish_times": [...],
            "mid_roll_suggestions": {...},
            "rules": [...],
        }
        """
        revenue_data = self._get_revenue_data(channel_id)
        if not revenue_data:
            logger.info(f"No revenue data for {channel_id}")
            return {"status": "no_data"}

        # Analyze by topic category
        topic_rpm = self._analyze_by_topic(revenue_data)

        # Analyze by video length
        length_rpm = self._analyze_by_length(revenue_data)

        # Analyze by publish time
        time_rpm = self._analyze_by_time(revenue_data)

        # Generate mid-roll suggestions
        mid_roll = self._suggest_mid_rolls(revenue_data)

        # Generate rules
        rules = self._generate_rules(channel_id, topic_rpm, length_rpm, time_rpm)
        self._save_rules(channel_id, rules)

        return {
            "avg_rpm": self._calc_avg_rpm(revenue_data),
            "best_topics": topic_rpm[:5],
            "best_length_range": length_rpm.get("best_range", [10, 15]),
            "best_publish_times": time_rpm[:3],
            "mid_roll_suggestions": mid_roll,
            "rules": rules,
        }

    def _analyze_by_topic(self, data: list) -> list[dict]:
        """Group RPM by topic category."""
        by_topic = {}
        for d in data:
            cat = d.get("topic_category", "unknown")
            if cat not in by_topic:
                by_topic[cat] = []
            by_topic[cat].append(d.get("rpm", 0))

        results = []
        for cat, rpms in by_topic.items():
            results.append({
                "category": cat,
                "avg_rpm": round(sum(rpms) / len(rpms), 2),
                "count": len(rpms),
            })
        return sorted(results, key=lambda x: x["avg_rpm"], reverse=True)

    def _analyze_by_length(self, data: list) -> dict:
        """Find optimal video length for RPM."""
        buckets = {}
        for d in data:
            length = d.get("duration_min", 10)
            bucket = f"{(length // 5) * 5}-{(length // 5) * 5 + 5}"
            if bucket not in buckets:
                buckets[bucket] = []
            buckets[bucket].append(d.get("rpm", 0))

        best = None
        best_rpm = 0
        for bucket, rpms in buckets.items():
            avg = sum(rpms) / len(rpms)
            if avg > best_rpm and len(rpms) >= 2:
                best_rpm = avg
                best = bucket

        return {
            "best_range": [int(x) for x in best.split("-")] if best else [10, 15],
            "best_rpm": round(best_rpm, 2),
            "all_buckets": {k: round(sum(v)/len(v), 2) for k, v in buckets.items()},
        }

    def _analyze_by_time(self, data: list) -> list[dict]:
        """Find best publish times for RPM."""
        by_hour = {}
        for d in data:
            hour = d.get("publish_hour", 12)
            if hour not in by_hour:
                by_hour[hour] = []
            by_hour[hour].append(d.get("rpm", 0))

        results = []
        for hour, rpms in by_hour.items():
            results.append({
                "hour": hour,
                "avg_rpm": round(sum(rpms) / len(rpms), 2),
                "count": len(rpms),
            })
        return sorted(results, key=lambda x: x["avg_rpm"], reverse=True)

    def _suggest_mid_rolls(self, data: list) -> dict:
        """Suggest optimal mid-roll ad positions."""
        return {
            "min_video_length_for_midrolls": 8,
            "first_midroll_min": 3,
            "interval_min": 4,
            "avoid_first_seconds": 30,
            "prefer_natural_pauses": True,
            "note": "Place mid-rolls at scene transitions, never mid-sentence",
        }

    def _calc_avg_rpm(self, data: list) -> float:
        rpms = [d.get("rpm", 0) for d in data if d.get("rpm")]
        return round(sum(rpms) / len(rpms), 2) if rpms else 0.0

    def _generate_rules(self, channel_id: str, topic_rpm: list,
                        length_rpm: dict, time_rpm: list) -> list[dict]:
        """Generate revenue optimization rules."""
        rules = []
        if topic_rpm:
            best = topic_rpm[0]
            rules.append({
                "rule_name": "high_rpm_topics",
                "rule_text": f"المواضيع ذات أعلى عائد: {best['category']} (RPM: ${best['avg_rpm']})",
                "category": "revenue",
                "confidence": 0.7,
                "reason": f"Category '{best['category']}' has highest average RPM",
            })

        best_range = length_rpm.get("best_range", [10, 15])
        rules.append({
            "rule_name": "optimal_length_revenue",
            "rule_text": f"الطول الأمثل للعائد: {best_range[0]}-{best_range[1]} دقيقة",
            "category": "revenue",
            "confidence": 0.6,
            "reason": f"Videos {best_range[0]}-{best_range[1]} min have highest RPM",
        })

        return rules

    def _get_revenue_data(self, channel_id: str) -> list[dict]:
        """Fetch revenue analytics from DB."""
        try:
            rows = self.db.conn.execute("""
                SELECT j.id, j.topic, a.rpm, a.revenue_usd, a.duration_min,
                       a.publish_hour, a.topic_category
                FROM job_analytics a
                JOIN jobs j ON j.id = a.job_id
                WHERE j.channel_id = ? AND a.rpm IS NOT NULL
                ORDER BY j.created_at DESC LIMIT 50
            """, (channel_id,)).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def _save_rules(self, channel_id: str, rules: list[dict]):
        """Save rules to performance_rules table."""
        for rule in rules:
            try:
                self.db.conn.execute("""
                    INSERT INTO performance_rules
                        (channel_id, rule_name, rule_text, category, confidence, reason, active, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                """, (
                    channel_id, rule.get("rule_name", ""), rule.get("rule_text", ""),
                    rule.get("category", "revenue"), rule.get("confidence", 0.5),
                    rule.get("reason", ""), datetime.now().isoformat(),
                ))
            except Exception as e:
                logger.warning(f"Failed to save revenue rule: {e}")
        try:
            self.db.conn.commit()
        except Exception:
            pass
