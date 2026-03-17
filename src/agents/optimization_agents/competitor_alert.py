"""
Competitor Alert Agent — Real-time competitor monitoring.
Tracks competitor channels for viral content, trending topics, and strategy shifts.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from src.core.database import FactoryDB

logger = logging.getLogger(__name__)

VIRAL_VIEW_THRESHOLD = 100_000  # Views in 48h = viral
RAPID_GROWTH_THRESHOLD = 2.0  # 2x normal view rate


class CompetitorAlert:
    """
    Monitors competitor YouTube channels and alerts on significant events:
    viral videos, trending topics, strategy changes.
    """

    def __init__(self, db: FactoryDB, youtube_api=None, telegram_bot=None):
        self.db = db
        self.youtube = youtube_api
        self.telegram = telegram_bot

    def run(self, channel_id: str) -> list[dict]:
        """
        Check all tracked competitors for a channel.

        Returns: List of alert dicts.
        """
        competitors = self._get_competitors(channel_id)
        if not competitors:
            logger.info(f"No competitors tracked for {channel_id}")
            return []

        alerts = []
        for comp in competitors:
            comp_alerts = self._check_competitor(comp)
            alerts.extend(comp_alerts)

        # Save alerts
        self._save_alerts(channel_id, alerts)

        # Notify if significant
        if alerts:
            self._notify(channel_id, alerts)

        logger.info(f"Competitor check for {channel_id}: {len(alerts)} alerts from {len(competitors)} competitors")
        return alerts

    def _check_competitor(self, competitor: dict) -> list[dict]:
        """Check a single competitor for notable activity."""
        comp_id = competitor.get("youtube_channel_id", "")
        comp_name = competitor.get("name", comp_id)
        alerts = []

        # Get recent videos
        recent_videos = self._fetch_recent_videos(comp_id)
        if not recent_videos:
            return []

        for video in recent_videos:
            views = video.get("views", 0)
            published = video.get("published_at", "")
            title = video.get("title", "")

            # Check for viral content
            if views >= VIRAL_VIEW_THRESHOLD:
                alerts.append({
                    "type": "viral_video",
                    "competitor": comp_name,
                    "competitor_id": comp_id,
                    "video_title": title,
                    "video_id": video.get("video_id", ""),
                    "views": views,
                    "published_at": published,
                    "priority": "high",
                })

            # Check for topic overlap with our planned content
            if self._is_topic_overlap(title):
                alerts.append({
                    "type": "topic_overlap",
                    "competitor": comp_name,
                    "video_title": title,
                    "views": views,
                    "priority": "medium",
                })

        # Check upload frequency changes
        freq_alert = self._check_frequency_change(comp_id, comp_name, recent_videos)
        if freq_alert:
            alerts.append(freq_alert)

        return alerts

    def _fetch_recent_videos(self, channel_id: str) -> list[dict]:
        """Fetch recent videos from a competitor channel."""
        if not self.youtube:
            # Return cached data from DB
            try:
                rows = self.db.conn.execute("""
                    SELECT video_id, title, views, published_at
                    FROM competitor_videos
                    WHERE competitor_channel_id = ?
                    ORDER BY published_at DESC LIMIT 10
                """, (channel_id,)).fetchall()
                return [dict(r) for r in rows]
            except Exception:
                return []

        try:
            response = self.youtube.search().list(
                part="snippet",
                channelId=channel_id,
                order="date",
                maxResults=10,
                type="video",
                publishedAfter=(datetime.utcnow() - timedelta(days=7)).isoformat() + "Z",
            ).execute()

            videos = []
            for item in response.get("items", []):
                vid_id = item["id"]["videoId"]
                # Get view count
                stats = self.youtube.videos().list(
                    part="statistics", id=vid_id
                ).execute()
                view_count = int(stats["items"][0]["statistics"].get("viewCount", 0)) if stats.get("items") else 0

                videos.append({
                    "video_id": vid_id,
                    "title": item["snippet"]["title"],
                    "views": view_count,
                    "published_at": item["snippet"]["publishedAt"],
                })

                # Cache to DB
                self._cache_video(channel_id, videos[-1])

            return videos
        except Exception as e:
            logger.error(f"Failed to fetch competitor videos: {e}")
            return []

    def _is_topic_overlap(self, title: str) -> bool:
        """Check if competitor video topic overlaps with planned content."""
        try:
            rows = self.db.conn.execute(
                "SELECT topic FROM content_calendar WHERE status IN ('planned', 'approved')"
            ).fetchall()
            planned_topics = [r["topic"].lower() for r in rows if r["topic"]]
            title_lower = title.lower()
            return any(
                topic in title_lower or title_lower in topic
                for topic in planned_topics
            )
        except Exception:
            return False

    def _check_frequency_change(self, comp_id: str, comp_name: str,
                                recent_videos: list) -> Optional[dict]:
        """Detect if competitor changed upload frequency."""
        if len(recent_videos) < 3:
            return None
        # Simple check: count videos in last 7 days vs historical average
        try:
            row = self.db.conn.execute(
                "SELECT avg_weekly_uploads FROM competitors WHERE youtube_channel_id = ?",
                (comp_id,),
            ).fetchone()
            if row and row["avg_weekly_uploads"]:
                current_rate = len(recent_videos)
                avg_rate = row["avg_weekly_uploads"]
                if current_rate > avg_rate * RAPID_GROWTH_THRESHOLD:
                    return {
                        "type": "frequency_increase",
                        "competitor": comp_name,
                        "current_weekly": current_rate,
                        "avg_weekly": avg_rate,
                        "priority": "low",
                    }
        except Exception:
            pass
        return None

    def _get_competitors(self, channel_id: str) -> list[dict]:
        """Get tracked competitors for a channel."""
        try:
            rows = self.db.conn.execute(
                "SELECT name, youtube_channel_id FROM competitors WHERE our_channel_id = ? AND active = 1",
                (channel_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def _cache_video(self, competitor_channel_id: str, video: dict):
        """Cache competitor video data."""
        try:
            self.db.conn.execute("""
                INSERT OR REPLACE INTO competitor_videos
                    (competitor_channel_id, video_id, title, views, published_at, cached_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                competitor_channel_id, video.get("video_id"), video.get("title"),
                video.get("views"), video.get("published_at"), datetime.now().isoformat(),
            ))
            self.db.conn.commit()
        except Exception:
            pass

    def _save_alerts(self, channel_id: str, alerts: list[dict]):
        """Save alerts to DB."""
        for alert in alerts:
            try:
                self.db.conn.execute("""
                    INSERT INTO competitor_alerts
                        (channel_id, alert_type, competitor, data, priority, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    channel_id, alert.get("type"), alert.get("competitor"),
                    json.dumps(alert, ensure_ascii=False),
                    alert.get("priority", "low"), datetime.now().isoformat(),
                ))
            except Exception:
                pass
        try:
            self.db.conn.commit()
        except Exception:
            pass

    def _notify(self, channel_id: str, alerts: list[dict]):
        """Send alerts to Telegram."""
        if not self.telegram:
            return

        high_alerts = [a for a in alerts if a.get("priority") == "high"]
        if not high_alerts:
            return

        lines = ["🔔 <b>تنبيه المنافسين</b>\n"]
        for alert in high_alerts[:5]:
            if alert["type"] == "viral_video":
                lines.append(
                    f"🔥 <b>{alert['competitor']}</b> — فيديو viral\n"
                    f"   {alert.get('video_title', '?')}\n"
                    f"   👁 {alert.get('views', 0):,} مشاهدة\n"
                )
            elif alert["type"] == "topic_overlap":
                lines.append(
                    f"⚠️ <b>{alert['competitor']}</b> — موضوع مشابه\n"
                    f"   {alert.get('video_title', '?')}\n"
                )

        try:
            import asyncio
            asyncio.get_event_loop().run_until_complete(
                self.telegram.send("\n".join(lines))
            )
        except Exception as e:
            logger.warning(f"Telegram alert failed: {e}")
