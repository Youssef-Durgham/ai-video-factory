"""
Algo Tracker Agent — YouTube algorithm pattern monitoring.
Tracks changes in how YouTube promotes content and adapts strategy.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from src.core.database import FactoryDB
from src.core import llm

logger = logging.getLogger(__name__)


class AlgoTracker:
    """
    Monitors YouTube algorithm behavior patterns by tracking
    impressions, CTR, and browse/search/suggested traffic sources.
    """

    def __init__(self, db: FactoryDB):
        self.db = db

    def run(self, channel_id: str) -> dict:
        """
        Analyze algorithm patterns and generate insights.

        Returns: {
            "traffic_trends": {...},
            "ctr_trends": {...},
            "impression_trends": {...},
            "algo_signals": [...],
            "recommendations": [...],
        }
        """
        analytics = self._get_analytics(channel_id)
        if not analytics:
            return {"status": "no_data"}

        traffic = self._analyze_traffic_sources(analytics)
        ctr = self._analyze_ctr_trends(analytics)
        impressions = self._analyze_impression_trends(analytics)

        signals = self._detect_algo_shifts(traffic, ctr, impressions)
        recommendations = self._generate_recommendations(channel_id, signals)

        self._save_signals(channel_id, signals)

        return {
            "traffic_trends": traffic,
            "ctr_trends": ctr,
            "impression_trends": impressions,
            "algo_signals": signals,
            "recommendations": recommendations,
        }

    def _analyze_traffic_sources(self, analytics: list) -> dict:
        """Analyze traffic source distribution trends."""
        recent = analytics[:10]
        older = analytics[10:20]

        def avg_sources(data):
            if not data:
                return {}
            sources = {}
            for d in data:
                for src, pct in (d.get("traffic_sources") or {}).items():
                    sources.setdefault(src, []).append(pct)
            return {k: round(sum(v)/len(v), 1) for k, v in sources.items()}

        return {
            "recent": avg_sources(recent),
            "previous": avg_sources(older),
        }

    def _analyze_ctr_trends(self, analytics: list) -> dict:
        """Track CTR trends over time."""
        ctrs = [(d.get("published_at", ""), d.get("ctr", 0)) for d in analytics if d.get("ctr")]
        if len(ctrs) < 4:
            return {"trend": "insufficient_data"}

        recent_avg = sum(c for _, c in ctrs[:5]) / min(5, len(ctrs))
        older_avg = sum(c for _, c in ctrs[5:10]) / max(1, min(5, len(ctrs) - 5))

        trend = "stable"
        if recent_avg > older_avg * 1.1:
            trend = "improving"
        elif recent_avg < older_avg * 0.9:
            trend = "declining"

        return {
            "recent_avg_ctr": round(recent_avg, 2),
            "previous_avg_ctr": round(older_avg, 2),
            "trend": trend,
        }

    def _analyze_impression_trends(self, analytics: list) -> dict:
        """Track impression volume trends."""
        impressions = [d.get("impressions", 0) for d in analytics if d.get("impressions")]
        if len(impressions) < 4:
            return {"trend": "insufficient_data"}

        recent = sum(impressions[:5]) / min(5, len(impressions))
        older = sum(impressions[5:10]) / max(1, min(5, len(impressions) - 5))

        trend = "stable"
        if recent > older * 1.2:
            trend = "growing"
        elif recent < older * 0.8:
            trend = "shrinking"

        return {"recent_avg": int(recent), "previous_avg": int(older), "trend": trend}

    def _detect_algo_shifts(self, traffic: dict, ctr: dict, impressions: dict) -> list[str]:
        """Detect significant algorithm behavior changes."""
        signals = []

        # Check if suggested traffic changed significantly
        recent_suggested = traffic.get("recent", {}).get("suggested", 0)
        prev_suggested = traffic.get("previous", {}).get("suggested", 0)
        if prev_suggested and recent_suggested > prev_suggested * 1.3:
            signals.append("suggested_traffic_increase")
        elif prev_suggested and recent_suggested < prev_suggested * 0.7:
            signals.append("suggested_traffic_decrease")

        if ctr.get("trend") == "declining":
            signals.append("ctr_declining")
        if impressions.get("trend") == "shrinking":
            signals.append("impressions_declining")
        if impressions.get("trend") == "growing":
            signals.append("impressions_growing")

        return signals

    def _generate_recommendations(self, channel_id: str, signals: list[str]) -> list[str]:
        """Generate actionable recommendations based on detected signals."""
        recs = []
        if "ctr_declining" in signals:
            recs.append("CTR declining — test more compelling thumbnails and titles")
        if "impressions_declining" in signals:
            recs.append("Impressions declining — algorithm may be deprioritizing; increase upload frequency")
        if "suggested_traffic_decrease" in signals:
            recs.append("Suggested traffic dropping — improve end screens and video series linking")
        if "impressions_growing" in signals:
            recs.append("Impressions growing — algorithm is promoting more; maintain current strategy")
        if "suggested_traffic_increase" in signals:
            recs.append("Suggested traffic increasing — content is being recommended more widely")
        if not signals:
            recs.append("Algorithm behavior stable — no significant changes detected")
        return recs

    def _get_analytics(self, channel_id: str) -> list[dict]:
        """Fetch analytics data from DB."""
        try:
            rows = self.db.conn.execute("""
                SELECT j.id as job_id, j.topic, j.created_at as published_at,
                       a.ctr, a.impressions, a.traffic_sources, a.views_48h
                FROM job_analytics a
                JOIN jobs j ON j.id = a.job_id
                WHERE j.channel_id = ?
                ORDER BY j.created_at DESC LIMIT 30
            """, (channel_id,)).fetchall()
            results = []
            for r in rows:
                d = dict(r)
                if d.get("traffic_sources"):
                    try:
                        d["traffic_sources"] = json.loads(d["traffic_sources"])
                    except (json.JSONDecodeError, TypeError):
                        d["traffic_sources"] = {}
                results.append(d)
            return results
        except Exception:
            return []

    def _save_signals(self, channel_id: str, signals: list[str]):
        """Save detected algorithm signals to DB."""
        if not signals:
            return
        try:
            self.db.conn.execute("""
                INSERT INTO algo_signals (channel_id, signals, detected_at)
                VALUES (?, ?, ?)
            """, (channel_id, json.dumps(signals), datetime.now().isoformat()))
            self.db.conn.commit()
        except Exception as e:
            logger.warning(f"Failed to save algo signals: {e}")
