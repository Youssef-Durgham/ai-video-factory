"""
Narrative Styles Agent — Style library + selection.
Defines narrative approaches with rules for each. Qwen selects best style for topic.
"""

import json
import logging
from typing import Optional

from src.core.database import FactoryDB
from src.core import llm

logger = logging.getLogger(__name__)

# Style library with detailed rules for each approach
NARRATIVE_STYLES = {
    "investigative": {
        "name_ar": "تحقيقي",
        "description": "Deep-dive investigation revealing hidden truths",
        "hook_types": ["mystery", "shocking_fact", "counter_intuitive"],
        "structure": ["hook", "context", "evidence_1", "counter_evidence", "evidence_2", "revelation", "implications", "conclusion"],
        "tone": "serious, authoritative, probing",
        "pacing": "slow_build",
        "voice_style": "authoritative",
        "visual_mood": "dark_cinematic",
        "music_mood": "mysterious",
        "ideal_length_min": [12, 20],
        "best_for": ["corruption", "mysteries", "conspiracies", "historical_secrets", "scandals"],
        "rules": [
            "Present multiple perspectives before revealing conclusion",
            "Use evidence-based language: 'الأدلة تشير إلى', 'وفقاً للوثائق'",
            "Build suspense gradually — don't reveal the answer in the hook",
            "Include at least 3 verified sources per major claim",
            "End with open questions to provoke thought",
        ],
    },
    "storytelling": {
        "name_ar": "سردي قصصي",
        "description": "Narrative-driven story with characters and arc",
        "hook_types": ["narrative", "quote", "mystery"],
        "structure": ["hook", "setup", "rising_action", "climax", "falling_action", "resolution", "reflection"],
        "tone": "warm, engaging, empathetic",
        "pacing": "dynamic",
        "voice_style": "warm",
        "visual_mood": "warm_golden",
        "music_mood": "dramatic",
        "ideal_length_min": [10, 18],
        "best_for": ["biographies", "historical_events", "human_stories", "cultural_topics"],
        "rules": [
            "Center the story around a person or event",
            "Use sensory details: describe sights, sounds, feelings",
            "Create emotional connection with the subject",
            "Build tension through conflict and resolution",
            "Use time markers: 'في صباح ذلك اليوم', 'بعد مرور ثلاث سنوات'",
        ],
    },
    "explainer": {
        "name_ar": "شرح وتوضيح",
        "description": "Clear explanation of complex topics",
        "hook_types": ["question", "statistic", "counter_intuitive"],
        "structure": ["hook", "overview", "point_1", "point_2", "point_3", "synthesis", "takeaway"],
        "tone": "clear, educational, accessible",
        "pacing": "steady",
        "voice_style": "educational",
        "visual_mood": "cool_blue",
        "music_mood": "calm",
        "ideal_length_min": [8, 14],
        "best_for": ["science", "economics", "technology", "geopolitics", "education"],
        "rules": [
            "Start with what the audience already knows, build from there",
            "Use analogies to simplify: 'تخيل أن...'",
            "Break complex topics into 3-5 digestible points",
            "Include visual aids descriptions in scene prompts",
            "End with a clear takeaway the viewer can remember",
        ],
    },
    "dramatic_reconstruction": {
        "name_ar": "إعادة بناء درامية",
        "description": "Dramatic recreation of real events",
        "hook_types": ["narrative", "shocking_fact", "mystery"],
        "structure": ["cold_open", "context", "act_1", "turning_point", "act_2", "climax", "aftermath", "epilogue"],
        "tone": "intense, cinematic, immersive",
        "pacing": "cinematic",
        "voice_style": "dramatic",
        "visual_mood": "high_contrast",
        "music_mood": "epic",
        "ideal_length_min": [15, 25],
        "best_for": ["wars", "disasters", "heists", "escapes", "military_operations"],
        "rules": [
            "Open in the middle of the action (in medias res)",
            "Use present tense for dramatic scenes: 'يدخل القائد الغرفة'",
            "Alternate between wide context and intimate detail",
            "Include precise time and place markers",
            "Balance drama with factual accuracy — label speculation clearly",
        ],
    },
    "countdown": {
        "name_ar": "عد تنازلي",
        "description": "Ranked list format with escalating interest",
        "hook_types": ["question", "shocking_fact", "statistic"],
        "structure": ["hook", "item_n", "...", "item_2", "honorable_mentions", "item_1", "conclusion"],
        "tone": "energetic, engaging, suspenseful",
        "pacing": "escalating",
        "voice_style": "energetic",
        "visual_mood": "high_contrast",
        "music_mood": "epic",
        "ideal_length_min": [10, 16],
        "best_for": ["rankings", "comparisons", "lists", "best_of", "worst_of"],
        "rules": [
            "Save the most interesting item for last",
            "Each item must have a mini-hook before revealing",
            "Use transition phrases: 'لكن هذا ليس الأغرب...', 'والمركز الأول...'",
            "Include at least one surprise/unexpected entry",
            "Keep items roughly equal in coverage time",
        ],
    },
    "debate": {
        "name_ar": "نقاش ومناظرة",
        "description": "Balanced exploration of opposing viewpoints",
        "hook_types": ["question", "counter_intuitive", "statistic"],
        "structure": ["hook", "context", "side_a", "side_b", "evidence", "counter_arguments", "synthesis", "viewer_question"],
        "tone": "balanced, thoughtful, respectful",
        "pacing": "measured",
        "voice_style": "authoritative",
        "visual_mood": "muted_documentary",
        "music_mood": "calm",
        "ideal_length_min": [12, 18],
        "best_for": ["politics", "social_issues", "ethics", "controversial_topics"],
        "rules": [
            "Present both sides with equal weight and respect",
            "Use evidence for both perspectives",
            "Don't take a side — let the viewer decide",
            "Include real quotes from both sides",
            "End with a thought-provoking question, not a verdict",
        ],
    },
}


class NarrativeStylesAgent:
    """
    Selects the optimal narrative style for a topic using LLM analysis
    and returns style rules for the script writer.
    """

    def __init__(self, db: FactoryDB):
        self.db = db

    def run(self, topic: str, channel_id: str, constraints: Optional[dict] = None) -> dict:
        """
        Select best narrative style for a topic.

        Args:
            topic: The video topic (Arabic).
            channel_id: Channel identifier.
            constraints: Anti-repetition constraints (blocked styles).

        Returns: {
            "style_id": "investigative",
            "style": { ... full style dict ... },
            "rules": [...],
            "reasoning": "...",
        }
        """
        # Get channel allowed styles
        channel_styles = self._get_channel_styles(channel_id)

        # Filter blocked styles
        blocked = []
        if constraints:
            blocked = constraints.get("blocked_narrative_styles", [])

        available = {k: v for k, v in NARRATIVE_STYLES.items()
                     if k in channel_styles and k not in blocked}

        if not available:
            available = {k: v for k, v in NARRATIVE_STYLES.items() if k not in blocked}

        if not available:
            available = NARRATIVE_STYLES

        # Get performance rules
        perf_rules = self._get_style_performance(channel_id)

        # Ask LLM to select
        style_id, reasoning = self._select_style(topic, available, perf_rules)

        style = NARRATIVE_STYLES.get(style_id, NARRATIVE_STYLES["explainer"])

        result = {
            "style_id": style_id,
            "style": style,
            "rules": style["rules"],
            "structure": style["structure"],
            "reasoning": reasoning,
        }

        logger.info(f"Selected style '{style_id}' for topic: {topic[:60]} — {reasoning[:100]}")
        return result

    def get_style(self, style_id: str) -> Optional[dict]:
        """Get a specific style by ID."""
        return NARRATIVE_STYLES.get(style_id)

    def list_styles(self) -> dict:
        """Return all available styles."""
        return NARRATIVE_STYLES

    def format_rules_for_prompt(self, style: dict) -> str:
        """Format style rules for injection into script writer prompt."""
        lines = [
            f"أسلوب السرد: {style.get('name_ar', '')} ({style.get('description', '')})",
            f"النبرة: {style.get('tone', '')}",
            f"الإيقاع: {style.get('pacing', '')}",
            f"البنية: {' → '.join(style.get('structure', []))}",
            "",
            "قواعد الأسلوب:",
        ]
        for rule in style.get("rules", []):
            lines.append(f"- {rule}")
        return "\n".join(lines)

    def _select_style(self, topic: str, available: dict, perf_rules: list) -> tuple[str, str]:
        """Use LLM to select the best style for this topic."""
        styles_desc = []
        for sid, style in available.items():
            styles_desc.append(
                f"- {sid} ({style['name_ar']}): {style['description']}. "
                f"Best for: {', '.join(style['best_for'])}. "
                f"Length: {style['ideal_length_min'][0]}-{style['ideal_length_min'][1]} min."
            )

        perf_str = "\n".join(f"- {r}" for r in perf_rules[:5]) if perf_rules else "No performance data yet."

        prompt = f"""You are a content strategist for an Arabic YouTube documentary channel.

Topic: {topic}

Available narrative styles:
{chr(10).join(styles_desc)}

Performance insights from past videos:
{perf_str}

Select the BEST narrative style for this topic. Consider:
1. Topic nature (matches "best_for" categories)
2. Audience engagement potential
3. Performance data from past videos

Return JSON: {{"style_id": "...", "reasoning": "1-2 sentence Arabic explanation"}}"""

        try:
            result = llm.generate_json(prompt, temperature=0.4)
            style_id = result.get("style_id", "explainer")
            reasoning = result.get("reasoning", "")
            if style_id not in available:
                style_id = list(available.keys())[0]
            return style_id, reasoning
        except Exception as e:
            logger.warning(f"Style selection LLM failed: {e}")
            return list(available.keys())[0], "Fallback selection"

    def _get_channel_styles(self, channel_id: str) -> list[str]:
        """Get allowed styles for a channel from config."""
        try:
            from src.core.config import get_channel_config
            config = get_channel_config(channel_id)
            return config.get("narrative_styles", list(NARRATIVE_STYLES.keys()))
        except Exception:
            return list(NARRATIVE_STYLES.keys())

    def _get_style_performance(self, channel_id: str) -> list[str]:
        """Get performance insights per style from DB."""
        try:
            rows = self.db.conn.execute("""
                SELECT narrative_style, AVG(watch_time_pct) as avg_watch,
                       AVG(ctr) as avg_ctr, COUNT(*) as count
                FROM job_analytics
                WHERE channel_id = ? AND narrative_style IS NOT NULL
                GROUP BY narrative_style
                HAVING count >= 2
                ORDER BY avg_watch DESC
            """, (channel_id,)).fetchall()
            return [
                f"{r['narrative_style']}: avg watch {r['avg_watch']:.0f}%, CTR {r['avg_ctr']:.1f}%, {r['count']} videos"
                for r in rows
            ]
        except Exception:
            return []
