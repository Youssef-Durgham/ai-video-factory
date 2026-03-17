"""
Phase 1: YouTube Data API v3 trending analysis.
Uses official YouTube API only — no scraping.
"""

import logging
from typing import Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class YouTubeTrends:
    """Fetch trending topics and competitor uploads via YouTube Data API v3."""

    def __init__(self, config: dict):
        from googleapiclient.discovery import build

        api_key = config["settings"]["youtube"]["api_key"]
        self.youtube = build("youtube", "v3", developerKey=api_key)
        self.quota_per_call = {
            "videos.list": 1,
            "search.list": 100,
            "channels.list": 1,
        }

    def get_trending(
        self,
        region_codes: list[str] = None,
        category_id: str = None,
        max_results: int = 50,
    ) -> list[dict]:
        """
        Get trending videos from YouTube for given regions.
        Returns list of dicts with title, views, channel, category, published_at.
        """
        if region_codes is None:
            region_codes = ["IQ", "SA", "EG"]

        all_results = []
        for region in region_codes:
            try:
                request = self.youtube.videos().list(
                    part="snippet,statistics",
                    chart="mostPopular",
                    regionCode=region,
                    maxResults=min(max_results, 50),
                    videoCategoryId=category_id or "",
                )
                response = request.execute()

                for item in response.get("items", []):
                    snippet = item["snippet"]
                    stats = item.get("statistics", {})
                    all_results.append({
                        "video_id": item["id"],
                        "title": snippet["title"],
                        "channel": snippet["channelTitle"],
                        "channel_id": snippet["channelId"],
                        "category_id": snippet.get("categoryId"),
                        "published_at": snippet["publishedAt"],
                        "views": int(stats.get("viewCount", 0)),
                        "likes": int(stats.get("likeCount", 0)),
                        "comments": int(stats.get("commentCount", 0)),
                        "region": region,
                        "source": "youtube_trending",
                    })
            except Exception as e:
                logger.warning(f"Failed to fetch trending for {region}: {e}")

        # Deduplicate by video_id
        seen = set()
        unique = []
        for r in all_results:
            if r["video_id"] not in seen:
                seen.add(r["video_id"])
                unique.append(r)

        return sorted(unique, key=lambda x: x["views"], reverse=True)

    def get_competitor_uploads(
        self,
        channel_ids: list[str],
        days: int = 7,
        max_per_channel: int = 10,
    ) -> list[dict]:
        """
        Get recent uploads from competitor channels.
        Uses search.list (100 quota units per call).
        """
        after = (datetime.utcnow() - timedelta(days=days)).strftime(
            "%Y-%m-%dT00:00:00Z"
        )
        results = []

        for channel_id in channel_ids:
            try:
                request = self.youtube.search().list(
                    part="snippet",
                    channelId=channel_id,
                    order="date",
                    publishedAfter=after,
                    maxResults=max_per_channel,
                    type="video",
                )
                response = request.execute()

                for item in response.get("items", []):
                    snippet = item["snippet"]
                    results.append({
                        "video_id": item["id"]["videoId"],
                        "title": snippet["title"],
                        "channel": snippet["channelTitle"],
                        "channel_id": channel_id,
                        "published_at": snippet["publishedAt"],
                        "description": snippet.get("description", "")[:500],
                        "source": "competitor_upload",
                    })
            except Exception as e:
                logger.warning(f"Failed to fetch uploads for {channel_id}: {e}")

        return results

    def get_video_details(self, video_ids: list[str]) -> list[dict]:
        """Get detailed stats for specific videos (1 unit per 50 videos)."""
        results = []
        # API allows up to 50 IDs per call
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i : i + 50]
            try:
                request = self.youtube.videos().list(
                    part="snippet,statistics,contentDetails",
                    id=",".join(batch),
                )
                response = request.execute()
                for item in response.get("items", []):
                    snippet = item["snippet"]
                    stats = item.get("statistics", {})
                    results.append({
                        "video_id": item["id"],
                        "title": snippet["title"],
                        "channel": snippet["channelTitle"],
                        "views": int(stats.get("viewCount", 0)),
                        "likes": int(stats.get("likeCount", 0)),
                        "comments": int(stats.get("commentCount", 0)),
                        "duration": item["contentDetails"]["duration"],
                        "tags": snippet.get("tags", []),
                        "description": snippet.get("description", ""),
                    })
            except Exception as e:
                logger.warning(f"Failed to fetch video details: {e}")

        return results
