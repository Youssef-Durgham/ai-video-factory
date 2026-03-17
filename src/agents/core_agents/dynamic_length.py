"""
Dynamic Length Agent — Optimal video length prediction.
Based on topic complexity, competitor analysis, historical performance data.
"""

import json
import logging
from typing import Optional

from src.core.database import FactoryDB
from src.core import llm

logger = logging.getLogger(__name__)

# Default length ranges by narrative style (minutes)
STYLE_LENGTH_DEFAULTS = {
    "investigative": (12, 20),
    "storytelling": (10, 18),
    "explainer": (8, 14),
    "dramatic_reconstruction": (15, 25),
    "countdown": (10, 16),
    "debate": (12, 18),
}

# Topic complexity multipliers
COMPLEXITY_FACTORS = {
    "simple": 0.8,
    "moderate": 1.0,
    "complex": 1.2,
    "very_complex": 1.4,
}


class DynamicLengthAgent:
    """
    Predicts optimal video length based on topic complexity,
    competitor analysis, and historical performance data.
    """

    def __init__(self, db: FactoryDB):
        self.db = db

    def run(self, topic: str, channel_id: str, narrative_style: str = "explainer",
            competitor_data: Optional[list] = None) -> dict:
        """
        Predict optimal video length.

        Returns: {
            "target_length_min": 12,
            "min_length_min": 10,
            "max_length_min": 15,
            "target_scenes": 18,
            "reasoning": "...",
        }
        """
        # Get historical performance data
        perf_data = self._get_length_performance(channel_id)
        perf_rules = self._get_length_rules()

        # Get competitor lengths
        comp_lengths = self._analyze_competitors(topic, competitor_data)

        # Get style defaults
        style_range = STYLE_LENGTH_DEFAULTS.get(narrative_style, (10, 15))

        # Use LLM for final prediction
        prediction = self._predict_length(
            topic=topic,
            narrative_style=narrative_style,
            style_range=style_range,
            perf_data=perf_data,
            perf_rules=perf_rules,
            comp_lengths=comp_lengths,
        )

        # Calculate target scenes (assuming ~40s per scene average)
        target_min = prediction["target_length_min"]
        prediction["target_scenes"] = max(8, int(target_min * 60 / 40))

        logger.info(
            f"Dynamic length for '{topic[:50]}': {target_min} min "
            f"({prediction['min_length_min']}-{prediction['max_length_min']}), "
            f"{prediction['target_scenes']} scenes"
        )
        return prediction

    def _predict_length(self, topic: str, narrative_style: str, style_range: tuple,
                        perf_data: list, perf_rules: list, comp_lengths: list) -> dict:
        """Use LLM to predict optimal length."""
        perf_str = ""
        if perf_data:
            perf_str = "Historical performance by length:\n"
            for p in perf_data[:10]:
                perf_str += f"- {p['length_bucket']} min: avg watch {p['avg_watch_pct']:.0f}%, CTR {p['avg_ctr']:.1f}%\n"

        rules_str = "\n".join(f"- {r}" for r in perf_rules[:5]) if perf_rules else ""

        comp_str = ""
        if comp_lengths:
            avg_comp = sum(comp_lengths) / len(comp_lengths)
            comp_str = f"Competitor avg length: {avg_comp:.0f} min (range: {min(comp_lengths)}-{max(comp_lengths)} min)"

        prompt = f"""You are a YouTube analytics expert for Arabic documentary channels.

Topic: {topic}
Narrative style: {narrative_style}
Style recommended range: {style_range[0]}-{style_range[1]} minutes

{perf_str}
{rules_str}
{comp_str}

Predict the OPTIMAL video length for maximum watch time and retention.

Consider:
1. Topic complexity — how much content is needed to cover it well
2. Audience attention span for this topic type
3. Historical performance data (what length works best)
4. Competitor benchmarks
5. YouTube algorithm preference (8-20 min sweet spot for mid-rolls)

Return JSON: {{
    "target_length_min": N,
    "min_length_min": N,
    "max_length_min": N,
    "complexity": "simple|moderate|complex|very_complex",
    "reasoning": "1-2 sentence explanation"
}}"""

        try:
            result = llm.generate_json(prompt, temperature=0.3)
            target = result.get("target_length_min", 12)
            # Clamp to reasonable range
            target = max(5, min(30, target))
            return {
                "target_length_min": target,
                "min_length_min": max(5, result.get("min_length_min", target - 2)),
                "max_length_min": min(30, result.get("max_length_min", target + 3)),
                "complexity": result.get("complexity", "moderate"),
                "reasoning": result.get("reasoning", ""),
            }
        except Exception as e:
            logger.warning(f"Length prediction failed: {e}")
            default = (style_range[0] + style_range[1]) // 2
            return {
                "target_length_min": default,
                "min_length_min": style_range[0],
                "max_length_min": style_range[1],
                "complexity": "moderate",
                "reasoning": "Fallback to style defaults",
            }

    def _get_length_performance(self, channel_id: str) -> list[dict]:
        """Get watch time performance grouped by video length buckets."""
        try:
            rows = self.db.conn.execute("""
                SELECT
                    CASE
                        WHEN actual_length_min < 8 THEN '5-8'
                        WHEN actual_length_min < 12 THEN '8-12'
                        WHEN actual_length_min < 16 THEN '12-16'
                        WHEN actual_length_min < 20 THEN '16-20'
                        ELSE '20+'
                    END as length_bucket,
                    AVG(watch_time_pct) as avg_watch_pct,
                    AVG(ctr) as avg_ctr,
                    COUNT(*) as count
                FROM job_analytics
                WHERE channel_id = ?
                GROUP BY length_bucket
                HAVING count >= 2
                ORDER BY avg_watch_pct DESC
            """, (channel_id,)).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def _get_length_rules(self) -> list[str]:
        """Fetch performance rules related to video length."""
        try:
            rows = self.db.conn.execute(
                "SELECT rule_text FROM performance_rules WHERE category = 'length' AND active = 1"
            ).fetchall()
            return [r["rule_text"] for r in rows]
        except Exception:
            return []

    def _analyze_competitors(self, topic: str, competitor_data: Optional[list]) -> list[float]:
        """Extract competitor video lengths for similar topics."""
        if competitor_data:
            return [c.get("duration_min", 12) for c in competitor_data if c.get("duration_min")]

        try:
            rows = self.db.conn.execute("""
                SELECT duration_min FROM competitor_videos
                WHERE topic_similarity > 0.6
                ORDER BY published_at DESC LIMIT 20
            """).fetchall()
            return [r["duration_min"] for r in rows if r["duration_min"]]
        except Exception:
            return []
