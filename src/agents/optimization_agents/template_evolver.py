"""
Template Evolver Agent — Script template learning from high-performing videos.
Evolves script structures based on what works best.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from src.core.database import FactoryDB
from src.core import llm

logger = logging.getLogger(__name__)

PERFORMANCE_THRESHOLD_WATCH_PCT = 55  # Videos above this are "high-performing"


class TemplateEvolver:
    """
    Learns successful script templates from high-performing videos
    and generates improved template suggestions for future scripts.
    """

    def __init__(self, db: FactoryDB):
        self.db = db

    def run(self, channel_id: str) -> list[dict]:
        """
        Analyze high-performing videos and extract/evolve templates.

        Returns: List of evolved template dicts.
        """
        # Get high-performing videos
        high_perf = self._get_high_performing(channel_id)
        if len(high_perf) < 3:
            logger.info(f"Not enough high-performing videos for template evolution ({len(high_perf)})")
            return []

        # Extract common patterns
        patterns = self._extract_patterns(high_perf)

        # Generate evolved templates
        templates = self._evolve_templates(channel_id, patterns, high_perf)

        # Save templates
        self._save_templates(channel_id, templates)

        logger.info(f"Template evolver: {len(templates)} templates evolved for {channel_id}")
        return templates

    def get_best_template(self, channel_id: str, narrative_style: str) -> Optional[dict]:
        """Get the best-performing template for a given style."""
        try:
            row = self.db.conn.execute("""
                SELECT template_data FROM script_templates
                WHERE channel_id = ? AND narrative_style = ? AND active = 1
                ORDER BY performance_score DESC LIMIT 1
            """, (channel_id, narrative_style)).fetchone()
            if row:
                return json.loads(row["template_data"])
        except Exception:
            pass
        return None

    def _get_high_performing(self, channel_id: str) -> list[dict]:
        """Fetch high-performing videos with their script structure."""
        try:
            rows = self.db.conn.execute("""
                SELECT j.id, j.topic, j.narrative_style,
                       a.watch_time_pct, a.ctr, a.views_48h,
                       s.full_text, s.hook_text, s.scene_count
                FROM jobs j
                JOIN job_analytics a ON j.id = a.job_id
                LEFT JOIN scripts s ON j.id = s.job_id
                WHERE j.channel_id = ? AND a.watch_time_pct >= ?
                ORDER BY a.watch_time_pct DESC LIMIT 20
            """, (channel_id, PERFORMANCE_THRESHOLD_WATCH_PCT)).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def _extract_patterns(self, videos: list[dict]) -> dict:
        """Extract common structural patterns from high-performing videos."""
        patterns = {
            "avg_scene_count": 0,
            "common_styles": {},
            "hook_types": [],
            "avg_watch_pct": 0,
        }

        scene_counts = [v.get("scene_count", 0) for v in videos if v.get("scene_count")]
        if scene_counts:
            patterns["avg_scene_count"] = int(sum(scene_counts) / len(scene_counts))

        for v in videos:
            style = v.get("narrative_style", "unknown")
            patterns["common_styles"][style] = patterns["common_styles"].get(style, 0) + 1

        watch_pcts = [v.get("watch_time_pct", 0) for v in videos]
        patterns["avg_watch_pct"] = round(sum(watch_pcts) / len(watch_pcts), 1)

        return patterns

    def _evolve_templates(self, channel_id: str, patterns: dict, videos: list[dict]) -> list[dict]:
        """Use LLM to generate evolved script templates."""
        video_summaries = []
        for v in videos[:5]:
            hook = (v.get("hook_text") or "")[:150]
            video_summaries.append(
                f"- {v.get('topic', '?')} (style: {v.get('narrative_style', '?')}, "
                f"watch: {v.get('watch_time_pct', 0):.0f}%, scenes: {v.get('scene_count', '?')})"
                f"\n  Hook: {hook}"
            )

        prompt = f"""Analyze these high-performing Arabic documentary videos and create improved script templates.

HIGH-PERFORMING VIDEOS:
{chr(10).join(video_summaries)}

PATTERNS:
- Average scene count: {patterns['avg_scene_count']}
- Most common styles: {json.dumps(patterns['common_styles'])}
- Average watch time: {patterns['avg_watch_pct']}%

Generate 2-3 evolved script templates. Each template should:
1. Define a clear structure (sections with purpose)
2. Include hook type and approach
3. Specify pacing rhythm
4. Note what made the originals work

Return JSON array: [{{
    "name": "template name",
    "narrative_style": "style_id",
    "structure": ["section1", "section2", ...],
    "hook_approach": "description",
    "pacing": "description",
    "scene_count_range": [min, max],
    "key_elements": ["element1", ...],
    "performance_score": 0.0-1.0
}}]"""

        try:
            templates = llm.generate_json(prompt, temperature=0.5)
            if isinstance(templates, dict):
                templates = templates.get("templates", [templates])
            return templates if isinstance(templates, list) else [templates]
        except Exception as e:
            logger.warning(f"Template evolution failed: {e}")
            return []

    def _save_templates(self, channel_id: str, templates: list[dict]):
        """Save evolved templates to DB."""
        for tmpl in templates:
            try:
                self.db.conn.execute("""
                    INSERT INTO script_templates
                        (channel_id, name, narrative_style, template_data,
                         performance_score, active, created_at)
                    VALUES (?, ?, ?, ?, ?, 1, ?)
                """, (
                    channel_id,
                    tmpl.get("name", "unnamed"),
                    tmpl.get("narrative_style", ""),
                    json.dumps(tmpl, ensure_ascii=False),
                    tmpl.get("performance_score", 0.5),
                    datetime.now().isoformat(),
                ))
            except Exception as e:
                logger.warning(f"Failed to save template: {e}")
        try:
            self.db.conn.commit()
        except Exception:
            pass
