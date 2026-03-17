"""
Anti-Repetition Agent — Tracks patterns across recent videos and enforces diversity.
Prevents audience fatigue from repetitive hooks, titles, palettes, and music.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from src.core.database import FactoryDB
from src.core import llm

logger = logging.getLogger(__name__)

# Maximum allowed repetitions within the lookback window
DIVERSITY_RULES = {
    "hook_style": {"max_repeat": 2, "window": 10},
    "title_structure": {"max_repeat": 2, "window": 7},
    "visual_palette": {"max_repeat": 3, "window": 10},
    "music_mood": {"max_repeat": 3, "window": 10},
    "narrative_style": {"max_repeat": 2, "window": 7},
}


class AntiRepetitionAgent:
    """
    Tracks content patterns across published videos and generates
    diversity constraints for the script writer and production pipeline.
    """

    def __init__(self, db: FactoryDB):
        self.db = db

    # ─── Main Entry Points ─────────────────────────────

    def run(self, channel_id: str) -> dict:
        """
        Analyze recent patterns for a channel and return diversity constraints.
        Called before Phase 3 (Script) to feed constraints to the writer.

        Returns: {
            "blocked_hooks": ["question", ...],
            "blocked_titles": ["كيف...؟", ...],
            "blocked_palettes": ["dark_cinematic", ...],
            "blocked_music": ["dramatic", ...],
            "blocked_styles": ["investigative", ...],
            "suggestions": "Use a storytelling hook with warm visuals...",
        }
        """
        patterns = self.db.get_recent_patterns(channel_id, last_n=10)
        if not patterns:
            logger.info(f"No prior patterns for {channel_id} — no constraints.")
            return self._empty_constraints()

        constraints = {}
        for field, rule in DIVERSITY_RULES.items():
            window = patterns[: rule["window"]]
            values = [p.get(field) for p in window if p.get(field)]
            blocked = self._find_overused(values, rule["max_repeat"])
            constraints[f"blocked_{field}s" if not field.endswith("s") else f"blocked_{field}"] = blocked

        # Ask LLM for creative suggestion based on what's blocked
        constraints["suggestions"] = self._generate_suggestion(channel_id, constraints, patterns)

        logger.info(f"Anti-repetition constraints for {channel_id}: {json.dumps(constraints, ensure_ascii=False)[:300]}")
        return constraints

    def log_patterns(self, job_id: str, channel_id: str, patterns: dict):
        """
        Record the patterns used in a published video.
        Called after Phase 8 (Publish).
        """
        self.db.conn.execute("""
            INSERT INTO anti_repetition
                (job_id, channel_id, hook_style, title_structure,
                 visual_palette, music_mood, narrative_style, published_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_id, channel_id,
            patterns.get("hook_style"),
            patterns.get("title_structure"),
            patterns.get("visual_palette"),
            patterns.get("music_mood"),
            patterns.get("narrative_style"),
            datetime.now().isoformat(),
        ))
        self.db.conn.commit()
        logger.info(f"Logged patterns for {job_id}")

    def extract_patterns(self, job_id: str) -> dict:
        """
        Extract pattern fingerprint from a completed job using LLM analysis.
        Called during/after Phase 3 to identify the patterns being used.
        """
        job = self.db.get_job(job_id)
        if not job:
            return {}

        scripts = self.db.conn.execute(
            "SELECT full_text, hook_text FROM scripts WHERE job_id = ? ORDER BY version DESC LIMIT 1",
            (job_id,)
        ).fetchone()

        if not scripts:
            return {}

        prompt = f"""Analyze this Arabic documentary script and identify its patterns.

Title: {job.get('topic', '')}
Hook: {scripts['hook_text'] or scripts['full_text'][:200]}
Narrative style: {job.get('narrative_style', 'unknown')}

Classify:
1. hook_style: one of [question, shocking_fact, mystery, narrative, counter_intuitive, statistic, quote]
2. title_structure: the Arabic title pattern (e.g., "كيف...؟", "لماذا...؟", "الحقيقة وراء...", "أسرار...")
3. visual_palette: one of [dark_cinematic, warm_golden, cool_blue, earth_tones, high_contrast, muted_documentary]
4. music_mood: one of [dramatic, tense, hopeful, calm, epic, mysterious, melancholic]

Return JSON with these 4 keys."""

        try:
            result = llm.generate_json(prompt, temperature=0.3)
            result["narrative_style"] = job.get("narrative_style", "unknown")
            return result
        except Exception as e:
            logger.warning(f"Pattern extraction failed: {e}")
            return {
                "hook_style": "unknown",
                "title_structure": "unknown",
                "visual_palette": "unknown",
                "music_mood": job.get("narrative_style", "unknown"),
                "narrative_style": job.get("narrative_style", "unknown"),
            }

    # ─── Constraint Formatting ─────────────────────────

    def format_constraints_for_prompt(self, constraints: dict) -> str:
        """Format constraints as Arabic text for injection into script writer prompt."""
        if not any(v for k, v in constraints.items() if k.startswith("blocked_")):
            return ""

        lines = ["قواعد التنوع (يجب تجنب التكرار):"]

        blocked_hooks = constraints.get("blocked_hook_styles", [])
        if blocked_hooks:
            lines.append(f"- لا تستخدم هذه المقدمات: {', '.join(blocked_hooks)}")

        blocked_titles = constraints.get("blocked_title_structures", [])
        if blocked_titles:
            lines.append(f"- لا تستخدم هذه الأنماط في العنوان: {', '.join(blocked_titles)}")

        blocked_palettes = constraints.get("blocked_visual_palettes", [])
        if blocked_palettes:
            lines.append(f"- تجنب هذه الألوان البصرية: {', '.join(blocked_palettes)}")

        blocked_music = constraints.get("blocked_music_moods", [])
        if blocked_music:
            lines.append(f"- تجنب هذه الأجواء الموسيقية: {', '.join(blocked_music)}")

        suggestions = constraints.get("suggestions", "")
        if suggestions:
            lines.append(f"\nاقتراح إبداعي: {suggestions}")

        return "\n".join(lines)

    # ─── Internal Helpers ──────────────────────────────

    def _find_overused(self, values: list, max_repeat: int) -> list:
        """Find values that appear more than max_repeat times."""
        from collections import Counter
        counts = Counter(v for v in values if v and v != "unknown")
        return [val for val, count in counts.items() if count >= max_repeat]

    def _generate_suggestion(self, channel_id: str, constraints: dict, patterns: list) -> str:
        """Use LLM to suggest a creative direction that avoids blocked patterns."""
        blocked_items = []
        for k, v in constraints.items():
            if k.startswith("blocked_") and v:
                blocked_items.extend(v)

        if not blocked_items:
            return ""

        recent_topics = [p.get("hook_style", "") for p in patterns[:5]]

        prompt = f"""You are a creative director for an Arabic YouTube documentary channel.

Recent videos used these patterns: {', '.join(recent_topics)}
These are now BLOCKED (overused): {', '.join(blocked_items)}

Suggest a fresh creative direction for the next video in 1-2 sentences (Arabic).
Focus on: hook style, visual mood, and narrative approach that would feel fresh."""

        try:
            return llm.generate(prompt, temperature=0.8, max_tokens=200).strip()
        except Exception:
            return ""

    def _empty_constraints(self) -> dict:
        return {
            "blocked_hook_styles": [],
            "blocked_title_structures": [],
            "blocked_visual_palettes": [],
            "blocked_music_moods": [],
            "blocked_narrative_styles": [],
            "suggestions": "",
        }
