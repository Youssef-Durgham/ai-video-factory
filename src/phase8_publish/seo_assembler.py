"""
Phase 8 — SEO Assembler: Combine title + description + tags + timestamps + hashtags.

Assembles the final YouTube metadata from SEO data, scene timing,
and channel branding into a ready-to-upload metadata dict.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# YouTube limits
MAX_TITLE_LENGTH = 100
MAX_DESCRIPTION_LENGTH = 5000
MAX_TAG_LENGTH = 500  # Total chars for all tags combined
MAX_TAGS = 30
MAX_HASHTAGS = 15


@dataclass
class SEOMetadata:
    """Assembled YouTube metadata ready for upload."""
    title: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    category_id: str = "27"  # Education default
    default_language: str = "ar"
    hashtags: list[str] = field(default_factory=list)
    timestamps: list[str] = field(default_factory=list)
    privacy_status: str = "public"


# YouTube category IDs for common types
CATEGORY_MAP = {
    "documentary": "27",     # Education
    "history": "27",
    "science": "28",         # Science & Technology
    "tech": "28",
    "news": "25",            # News & Politics
    "politics": "25",
    "entertainment": "24",
    "music": "10",
    "film": "1",
    "gaming": "20",
}


class SEOAssembler:
    """
    Assembles final YouTube SEO metadata from research data,
    scene timing, and channel configuration.
    """

    def __init__(self, config: dict, db):
        self.config = config
        self.db = db

    def assemble(self, job_id: str) -> SEOMetadata:
        """
        Assemble complete YouTube metadata for a job.

        Args:
            job_id: The job to assemble metadata for.

        Returns:
            SEOMetadata with all fields populated.
        """
        job = self.db.get_job(job_id)
        if not job:
            logger.error(f"Job not found: {job_id}")
            return SEOMetadata()

        # Fetch SEO research data
        seo_row = self.db.conn.execute(
            "SELECT * FROM seo_data WHERE job_id = ? ORDER BY id DESC LIMIT 1",
            (job_id,),
        ).fetchone()
        seo = dict(seo_row) if seo_row else {}

        # Fetch scenes for timestamps
        scenes = self.db.get_scenes(job_id)

        # Fetch channel config
        channel_id = job.get("channel_id", "")
        channel_config = self._get_channel_config(channel_id)

        metadata = SEOMetadata()

        # 1. Title
        metadata.title = self._build_title(seo, job)

        # 2. Tags
        metadata.tags = self._build_tags(seo)

        # 3. Hashtags
        metadata.hashtags = self._build_hashtags(seo)

        # 4. Timestamps
        metadata.timestamps = self._build_timestamps(scenes)

        # 5. Description (includes timestamps, hashtags, channel branding)
        metadata.description = self._build_description(
            seo, job, metadata.timestamps, metadata.hashtags, channel_config
        )

        # 6. Category
        topic_category = job.get("topic_region", "documentary")
        metadata.category_id = CATEGORY_MAP.get(topic_category, "27")

        # 7. Language
        content_config = channel_config.get("content", {})
        metadata.default_language = "ar" if content_config.get("language", "MSA") in ("MSA", "ar") else "en"

        logger.info(
            f"SEO assembled for {job_id}: title='{metadata.title[:50]}...', "
            f"{len(metadata.tags)} tags, {len(metadata.timestamps)} timestamps"
        )
        return metadata

    def _build_title(self, seo: dict, job: dict) -> str:
        """Select best title, truncated to YouTube limit."""
        title = seo.get("selected_title") or job.get("topic", "Untitled")
        if len(title) > MAX_TITLE_LENGTH:
            title = title[:MAX_TITLE_LENGTH - 3] + "..."
        return title

    def _build_tags(self, seo: dict) -> list[str]:
        """Combine primary + secondary + long-tail keywords as tags."""
        all_tags = []

        for key in ("primary_keywords", "secondary_keywords", "long_tail_keywords", "tags"):
            raw = seo.get(key)
            if raw:
                parsed = json.loads(raw) if isinstance(raw, str) else raw
                if isinstance(parsed, list):
                    all_tags.extend(parsed)

        # Deduplicate, limit
        seen = set()
        unique_tags = []
        total_chars = 0
        for tag in all_tags:
            tag = str(tag).strip()
            if tag.lower() not in seen and tag:
                if total_chars + len(tag) > MAX_TAG_LENGTH:
                    break
                if len(unique_tags) >= MAX_TAGS:
                    break
                seen.add(tag.lower())
                unique_tags.append(tag)
                total_chars += len(tag)

        return unique_tags

    def _build_hashtags(self, seo: dict) -> list[str]:
        """Extract hashtags from SEO data."""
        raw = seo.get("hashtags")
        if raw:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(parsed, list):
                # Ensure # prefix, limit count
                hashtags = []
                for h in parsed[:MAX_HASHTAGS]:
                    h = str(h).strip()
                    if not h.startswith("#"):
                        h = f"#{h}"
                    hashtags.append(h)
                return hashtags
        return []

    def _build_timestamps(self, scenes: list[dict]) -> list[str]:
        """Generate YouTube chapter timestamps from scene data."""
        if not scenes:
            return []

        timestamps = []
        for scene in scenes:
            start = scene.get("start_time_sec", 0) or 0
            narration = scene.get("narration_text", "").strip()
            if not narration:
                continue

            # Extract first sentence as chapter title
            chapter_title = narration.split(".")[0].split("،")[0].strip()
            if len(chapter_title) > 60:
                chapter_title = chapter_title[:57] + "..."

            minutes = int(start // 60)
            seconds = int(start % 60)
            timestamps.append(f"{minutes:02d}:{seconds:02d} {chapter_title}")

        # YouTube requires first timestamp at 00:00
        if timestamps and not timestamps[0].startswith("00:00"):
            timestamps[0] = "00:00 " + timestamps[0].split(" ", 1)[-1]

        return timestamps

    def _build_description(
        self,
        seo: dict,
        job: dict,
        timestamps: list[str],
        hashtags: list[str],
        channel_config: dict,
    ) -> str:
        """Build full YouTube description with timestamps and branding."""
        parts = []

        # Main description from SEO template
        desc_template = seo.get("description_template", "")
        if desc_template:
            parts.append(desc_template)
        else:
            # Fallback: use topic + unique angle
            topic = job.get("topic", "")
            angle = seo.get("unique_angle", "")
            if topic:
                parts.append(topic)
            if angle:
                parts.append(f"\n{angle}")

        # Timestamps (chapters)
        if timestamps:
            parts.append("\n⏱️ المحتويات:")
            parts.extend(timestamps)

        # Hashtags
        if hashtags:
            parts.append("\n" + " ".join(hashtags))

        # Channel branding / CTA
        brand = channel_config.get("brand", {})
        if brand:
            parts.append("\n─────────────────")
            parts.append("📺 لا تنسى الاشتراك وتفعيل الجرس! 🔔")

        description = "\n".join(parts)

        # Truncate to YouTube limit
        if len(description) > MAX_DESCRIPTION_LENGTH:
            description = description[:MAX_DESCRIPTION_LENGTH - 3] + "..."

        return description

    def _get_channel_config(self, channel_id: str) -> dict:
        """Safely get channel config."""
        try:
            from src.core.config import get_channel_config
            return get_channel_config(channel_id, self.config)
        except (ValueError, KeyError):
            return {}
