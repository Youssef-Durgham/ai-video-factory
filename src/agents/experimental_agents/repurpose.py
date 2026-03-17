"""
Repurpose Agent — Multi-platform content repurposing.
Creates TikTok, Instagram Reels, and Twitter/X clips from long-form video.
Identifies highlight moments and generates platform-optimized shorts.
"""

import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

from src.core.database import FactoryDB

logger = logging.getLogger(__name__)

PLATFORM_SPECS = {
    "tiktok": {"max_duration": 60, "aspect": "9:16", "resolution": "1080x1920"},
    "reels": {"max_duration": 90, "aspect": "9:16", "resolution": "1080x1920"},
    "twitter": {"max_duration": 140, "aspect": "16:9", "resolution": "1280x720"},
    "shorts": {"max_duration": 60, "aspect": "9:16", "resolution": "1080x1920"},
}


class RepurposeAgent:
    """
    Repurposes long-form YouTube videos into platform-optimized short clips.
    Uses scene analysis to identify the most engaging moments.
    """

    def __init__(self, db: FactoryDB):
        self.db = db

    def identify_highlights(self, job_id: str) -> List[Dict[str, Any]]:
        """
        Analyze a completed video to find the best moments for short clips.

        Args:
            job_id: Pipeline job ID of the source video.

        Returns:
            List of highlight segments with timestamps and engagement scores.
        """
        # Placeholder — real version analyzes audio peaks, visual motion, and script hooks
        highlights = [
            {
                "highlight_id": f"hl_{uuid.uuid4().hex[:8]}",
                "start_sec": 15.0,
                "end_sec": 45.0,
                "duration_sec": 30.0,
                "engagement_score": 0.92,
                "type": "hook",
                "description": "Strong opening hook with visual impact",
            },
            {
                "highlight_id": f"hl_{uuid.uuid4().hex[:8]}",
                "start_sec": 120.0,
                "end_sec": 165.0,
                "duration_sec": 45.0,
                "engagement_score": 0.85,
                "type": "climax",
                "description": "Key revelation or dramatic moment",
            },
            {
                "highlight_id": f"hl_{uuid.uuid4().hex[:8]}",
                "start_sec": 200.0,
                "end_sec": 240.0,
                "duration_sec": 40.0,
                "engagement_score": 0.78,
                "type": "insight",
                "description": "Shareable fact or surprising insight",
            },
        ]

        logger.info(f"Identified {len(highlights)} highlights for job={job_id}")
        return highlights

    def create_short(
        self, job_id: str, platform: str, scene_range: Tuple[float, float]
    ) -> Dict[str, Any]:
        """
        Create a single short-form clip for a specific platform.

        Args:
            job_id: Source video job ID.
            platform: Target platform (tiktok, reels, twitter, shorts).
            scene_range: Tuple of (start_sec, end_sec) to extract.

        Returns:
            Dict with output path, platform specs, and metadata.
        """
        spec = PLATFORM_SPECS.get(platform, PLATFORM_SPECS["tiktok"])
        start, end = scene_range
        duration = end - start

        if duration > spec["max_duration"]:
            logger.warning(f"Clip duration {duration}s exceeds {platform} max {spec['max_duration']}s, trimming")
            end = start + spec["max_duration"]
            duration = spec["max_duration"]

        result = {
            "short_id": f"short_{uuid.uuid4().hex[:8]}",
            "job_id": job_id,
            "platform": platform,
            "scene_range": [start, end],
            "duration_sec": duration,
            "resolution": spec["resolution"],
            "aspect_ratio": spec["aspect"],
            "output_path": f"output/{job_id}/shorts/{platform}_{start:.0f}_{end:.0f}.mp4",
            "status": "placeholder",
        }

        logger.info(f"Created {platform} short ({duration:.0f}s) from job={job_id} [{start:.0f}s-{end:.0f}s]")
        return result

    def batch_create_shorts(self, job_id: str) -> List[Dict[str, Any]]:
        """
        Auto-create shorts for all platforms from the best highlights.

        Args:
            job_id: Source video job ID.

        Returns:
            List of created short clip results across all platforms.
        """
        highlights = self.identify_highlights(job_id)
        results = []

        for highlight in highlights[:2]:  # Top 2 highlights
            for platform in ["tiktok", "reels", "shorts"]:
                clip = self.create_short(
                    job_id, platform, (highlight["start_sec"], highlight["end_sec"])
                )
                results.append(clip)

        logger.info(f"Batch created {len(results)} shorts from job={job_id}")
        return results
