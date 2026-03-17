"""
Trending Hijack Agent — Breaking news fast-track pipeline (P0 priority).
Detects breaking/viral topics and fast-tracks them through production.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from src.core.database import FactoryDB
from src.core import llm

logger = logging.getLogger(__name__)

# Virality score thresholds
HIJACK_THRESHOLD = 80  # Score 80+ = worth hijacking
URGENCY_WINDOW_HOURS = 6  # Must publish within 6h of detection


class TrendingHijack:
    """
    Monitors for breaking/trending topics and creates P0 priority jobs
    that bypass normal queue ordering for fast-track production.
    """

    def __init__(self, db: FactoryDB, telegram_bot=None):
        self.db = db
        self.telegram = telegram_bot

    def run(self, channel_id: str, trending_topics: Optional[list] = None) -> Optional[dict]:
        """
        Check for hijack-worthy trending topics.

        Args:
            channel_id: Target channel.
            trending_topics: Pre-fetched trending data (or fetched from DB).

        Returns: Job dict if hijack triggered, None otherwise.
        """
        if trending_topics is None:
            trending_topics = self._get_trending(channel_id)

        if not trending_topics:
            return None

        # Score each topic for hijack worthiness
        scored = self._score_topics(trending_topics, channel_id)

        # Find best candidate
        best = max(scored, key=lambda x: x.get("hijack_score", 0)) if scored else None
        if not best or best.get("hijack_score", 0) < HIJACK_THRESHOLD:
            logger.debug(f"No hijack-worthy topics for {channel_id}")
            return None

        # Check we haven't already hijacked this topic
        if self._already_hijacked(best.get("topic", ""), channel_id):
            logger.info(f"Already hijacked topic: {best['topic'][:50]}")
            return None

        # Create P0 job
        job = self._create_p0_job(channel_id, best)

        # Notify
        self._notify_hijack(channel_id, best, job)

        logger.info(f"🚨 Trending hijack: '{best['topic'][:50]}' → P0 job {job.get('id')}")
        return job

    def _score_topics(self, topics: list, channel_id: str) -> list[dict]:
        """Score topics for hijack worthiness using LLM."""
        topics_str = "\n".join(
            f"- {t.get('topic', t.get('title', '?'))}: "
            f"trend_score={t.get('trend_score', '?')}, "
            f"search_volume={t.get('search_volume', '?')}"
            for t in topics[:10]
        )

        prompt = f"""You are a YouTube trending analyst for Arabic documentary channels.

Evaluate these trending topics for "hijack" potential — creating a fast-track video to capitalize on the trend.

Topics:
{topics_str}

For each topic, score (0-100) based on:
1. Time sensitivity (will it be relevant in 24h?)
2. Documentary potential (can we make quality content, not clickbait?)
3. Audience match (Arabic documentary viewers)
4. Competition gap (are established channels already covering it?)
5. Search demand (is this being searched for?)

Return JSON array: [{{
    "topic": "topic text",
    "hijack_score": 0-100,
    "time_sensitivity": "hours|days|weeks",
    "approach": "brief description of angle to take",
    "estimated_length_min": N
}}]

Only return topics scoring 60+."""

        try:
            result = llm.generate_json(prompt, temperature=0.3)
            if isinstance(result, dict):
                result = result.get("topics", [result])
            return result if isinstance(result, list) else [result]
        except Exception as e:
            logger.warning(f"Topic scoring failed: {e}")
            return []

    def _create_p0_job(self, channel_id: str, topic_data: dict) -> dict:
        """Create a P0 priority job for the trending topic."""
        import uuid
        job_id = f"hijack_{uuid.uuid4().hex[:8]}"

        job = {
            "id": job_id,
            "channel_id": channel_id,
            "topic": topic_data.get("topic", ""),
            "priority": "P0",
            "source": "trending_hijack",
            "narrative_style": "explainer",  # Fast style for quick production
            "target_length_min": topic_data.get("estimated_length_min", 8),
            "urgency_deadline": datetime.now().isoformat(),
            "hijack_approach": topic_data.get("approach", ""),
        }

        try:
            self.db.conn.execute("""
                INSERT INTO jobs (id, channel_id, topic, priority, status, source,
                                  narrative_style, target_length_min, created_at)
                VALUES (?, ?, ?, ?, 'queued', ?, ?, ?, ?)
            """, (
                job_id, channel_id, job["topic"], "P0", "trending_hijack",
                job["narrative_style"], job["target_length_min"],
                datetime.now().isoformat(),
            ))
            self.db.conn.commit()
            logger.info(f"Created P0 job {job_id} for trending hijack")
        except Exception as e:
            logger.error(f"Failed to create P0 job: {e}")

        return job

    def _already_hijacked(self, topic: str, channel_id: str) -> bool:
        """Check if we already have a job for this trending topic."""
        try:
            row = self.db.conn.execute("""
                SELECT 1 FROM jobs
                WHERE channel_id = ? AND source = 'trending_hijack'
                AND topic LIKE ? AND created_at > datetime('now', '-48 hours')
            """, (channel_id, f"%{topic[:30]}%")).fetchone()
            return row is not None
        except Exception:
            return False

    def _get_trending(self, channel_id: str) -> list[dict]:
        """Get trending topics from DB cache."""
        try:
            rows = self.db.conn.execute("""
                SELECT topic, trend_score, search_volume, source
                FROM trending_topics
                WHERE detected_at > datetime('now', '-12 hours')
                ORDER BY trend_score DESC LIMIT 15
            """).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def _notify_hijack(self, channel_id: str, topic_data: dict, job: dict):
        """Notify via Telegram about trending hijack."""
        if not self.telegram:
            return

        text = (
            f"🚨 <b>TRENDING HIJACK — P0</b>\n\n"
            f"📋 {topic_data.get('topic', '?')}\n"
            f"📊 Score: {topic_data.get('hijack_score', '?')}/100\n"
            f"⏱ Urgency: {topic_data.get('time_sensitivity', '?')}\n"
            f"🎯 Approach: {topic_data.get('approach', '?')}\n"
            f"🆔 Job: {job.get('id', '?')}\n\n"
            f"Production will start immediately."
        )

        try:
            import asyncio
            asyncio.get_event_loop().run_until_complete(self.telegram.send(text))
        except Exception as e:
            logger.warning(f"Hijack notification failed: {e}")
