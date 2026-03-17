"""
Playlist Agent — Series clustering and playlist optimization.
Groups related videos into playlists for better discoverability.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from src.core.database import FactoryDB
from src.core import llm

logger = logging.getLogger(__name__)


class PlaylistAgent:
    """
    Clusters videos into topical series and manages YouTube playlists.
    Optimizes playlist structure for algorithm recommendation.
    """

    def __init__(self, db: FactoryDB, youtube_api=None):
        self.db = db
        self.youtube = youtube_api

    def run(self, channel_id: str) -> list[dict]:
        """
        Analyze all videos and suggest playlist groupings.

        Returns: List of playlist suggestion dicts.
        """
        videos = self._get_published_videos(channel_id)
        if len(videos) < 5:
            logger.info(f"Not enough videos for playlist clustering ({len(videos)})")
            return []

        # Cluster videos by topic similarity
        clusters = self._cluster_videos(videos)

        # Check existing playlists
        existing = self._get_existing_playlists(channel_id)

        # Suggest new playlists or additions
        suggestions = self._generate_suggestions(clusters, existing, channel_id)

        logger.info(f"Playlist agent: {len(suggestions)} suggestions for {channel_id}")
        return suggestions

    def add_to_playlist(self, video_id: str, playlist_id: str):
        """Add a video to a YouTube playlist."""
        if not self.youtube:
            logger.info(f"[DRY RUN] Add {video_id} to playlist {playlist_id}")
            return

        try:
            self.youtube.playlistItems().insert(
                part="snippet",
                body={
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {"kind": "youtube#video", "videoId": video_id},
                    }
                },
            ).execute()
            logger.info(f"Added {video_id} to playlist {playlist_id}")
        except Exception as e:
            logger.error(f"Failed to add to playlist: {e}")

    def _cluster_videos(self, videos: list[dict]) -> list[dict]:
        """Use LLM to cluster videos by topic similarity."""
        video_list = "\n".join(
            f"- [{v.get('id', '?')}] {v.get('topic', '?')} (style: {v.get('narrative_style', '?')})"
            for v in videos[:40]
        )

        prompt = f"""Group these Arabic documentary videos into topical playlists (series).

Videos:
{video_list}

Create 3-7 playlist groups. Each group should have at least 3 related videos.

Return JSON array: [{{
    "playlist_name_ar": "Arabic playlist title",
    "playlist_name_en": "English title",
    "description_ar": "Arabic description",
    "video_ids": ["id1", "id2", ...],
    "theme": "what unifies these videos"
}}]"""

        try:
            clusters = llm.generate_json(prompt, temperature=0.4)
            if isinstance(clusters, dict):
                clusters = clusters.get("playlists", clusters.get("clusters", [clusters]))
            return clusters if isinstance(clusters, list) else [clusters]
        except Exception as e:
            logger.warning(f"Video clustering failed: {e}")
            return []

    def _generate_suggestions(self, clusters: list[dict], existing: list[dict],
                              channel_id: str) -> list[dict]:
        """Compare clusters with existing playlists and suggest actions."""
        existing_names = {p.get("title", "").lower() for p in existing}
        suggestions = []

        for cluster in clusters:
            name = cluster.get("playlist_name_ar", "")
            if name.lower() not in existing_names:
                suggestions.append({
                    "action": "create",
                    "name_ar": name,
                    "name_en": cluster.get("playlist_name_en", ""),
                    "description": cluster.get("description_ar", ""),
                    "video_ids": cluster.get("video_ids", []),
                    "theme": cluster.get("theme", ""),
                })
            else:
                # Check for new videos to add
                suggestions.append({
                    "action": "update",
                    "name_ar": name,
                    "new_video_ids": cluster.get("video_ids", []),
                })

        return suggestions

    def _get_published_videos(self, channel_id: str) -> list[dict]:
        """Get all published videos for a channel."""
        try:
            rows = self.db.conn.execute("""
                SELECT id, topic, narrative_style, youtube_video_id
                FROM jobs
                WHERE channel_id = ? AND status = 'published' AND youtube_video_id IS NOT NULL
                ORDER BY created_at DESC
            """, (channel_id,)).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def _get_existing_playlists(self, channel_id: str) -> list[dict]:
        """Get existing playlists from DB cache."""
        try:
            rows = self.db.conn.execute(
                "SELECT title, playlist_id, video_count FROM playlists WHERE channel_id = ?",
                (channel_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []
