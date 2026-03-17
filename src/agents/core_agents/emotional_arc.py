"""
Emotional Arc Agent — Script emotion mapping.
Analyzes narration and assigns emotion curves (calm→tense→dramatic→reflective).
Maps to voice_emotion and music_mood per scene.
"""

import json
import logging
from typing import Optional

from src.core.database import FactoryDB
from src.core import llm

logger = logging.getLogger(__name__)

# Emotion progression templates
EMOTION_CURVES = {
    "classic_documentary": ["calm", "curious", "tense", "dramatic", "reflective", "calm"],
    "investigative": ["mysterious", "curious", "tense", "shocking", "reflective", "urgent"],
    "storytelling": ["calm", "warm", "dramatic", "emotional", "hopeful", "reflective"],
    "explainer": ["calm", "curious", "engaged", "surprised", "confident", "calm"],
    "dramatic_reconstruction": ["tense", "urgent", "dramatic", "shocking", "somber", "reflective"],
}

# Map emotions to voice and music parameters
EMOTION_VOICE_MAP = {
    "calm": {"voice_emotion": "calm", "music_mood": "calm"},
    "curious": {"voice_emotion": "curious", "music_mood": "mysterious"},
    "tense": {"voice_emotion": "tense", "music_mood": "tense"},
    "dramatic": {"voice_emotion": "dramatic", "music_mood": "dramatic"},
    "reflective": {"voice_emotion": "reflective", "music_mood": "melancholic"},
    "mysterious": {"voice_emotion": "mysterious", "music_mood": "mysterious"},
    "shocking": {"voice_emotion": "urgent", "music_mood": "dramatic"},
    "warm": {"voice_emotion": "warm", "music_mood": "hopeful"},
    "emotional": {"voice_emotion": "emotional", "music_mood": "melancholic"},
    "hopeful": {"voice_emotion": "hopeful", "music_mood": "hopeful"},
    "urgent": {"voice_emotion": "urgent", "music_mood": "tense"},
    "confident": {"voice_emotion": "confident", "music_mood": "epic"},
    "somber": {"voice_emotion": "somber", "music_mood": "melancholic"},
    "surprised": {"voice_emotion": "surprised", "music_mood": "dramatic"},
    "engaged": {"voice_emotion": "engaged", "music_mood": "calm"},
}


class EmotionalArcAgent:
    """
    Analyzes a script's narration scenes and assigns an emotion curve.
    Maps each scene to voice_emotion and music_mood parameters.
    """

    def __init__(self, db: FactoryDB):
        self.db = db

    def run(self, job_id: str, scenes: list[dict], narrative_style: str = "classic_documentary") -> list[dict]:
        """
        Analyze scenes and assign emotion curve.

        Args:
            job_id: Job identifier.
            scenes: List of scene dicts with narration_text.
            narrative_style: One of EMOTION_CURVES keys.

        Returns:
            Updated scenes list with voice_emotion and music_mood per scene.
        """
        performance_rules = self._get_emotion_rules()

        # Use LLM to analyze each scene's emotional content
        arc = self._analyze_arc(scenes, narrative_style, performance_rules)

        # Apply to scenes
        for i, scene in enumerate(scenes):
            if i < len(arc):
                emotion = arc[i]
                mapping = EMOTION_VOICE_MAP.get(emotion, EMOTION_VOICE_MAP["calm"])
                scene["voice_emotion"] = mapping["voice_emotion"]
                scene["music_mood"] = mapping["music_mood"]
                scene["emotion_label"] = emotion
            else:
                scene["voice_emotion"] = "calm"
                scene["music_mood"] = "calm"
                scene["emotion_label"] = "calm"

        # Validate transitions aren't too jarring
        scenes = self._smooth_transitions(scenes)

        # Save to DB
        self._save_arc(job_id, scenes)

        logger.info(f"Emotional arc for {job_id}: {[s.get('emotion_label') for s in scenes]}")
        return scenes

    def _analyze_arc(self, scenes: list[dict], narrative_style: str, rules: list) -> list[str]:
        """Use LLM to assign emotion labels to each scene."""
        narrations = []
        for i, s in enumerate(scenes):
            text = s.get("narration_text", "")[:200]
            narrations.append(f"Scene {i+1}: {text}")

        template_curve = EMOTION_CURVES.get(narrative_style, EMOTION_CURVES["classic_documentary"])
        valid_emotions = list(EMOTION_VOICE_MAP.keys())

        rules_str = "\n".join(f"- {r}" for r in rules[:5]) if rules else "No rules yet."

        prompt = f"""You are an emotional arc director for Arabic documentaries.

Narrative style: {narrative_style}
Suggested emotion curve template: {template_curve}
Valid emotions: {valid_emotions}

Performance rules from past videos:
{rules_str}

Analyze each scene's narration and assign the most fitting emotion.
Consider: content gravity, pacing, viewer engagement, and natural emotional flow.
Avoid abrupt jumps (e.g., calm→shocking without buildup).

Scenes:
{chr(10).join(narrations)}

Return a JSON array of emotion strings, one per scene. Length must equal {len(scenes)}."""

        try:
            result = llm.generate_json(prompt, temperature=0.4)
            if isinstance(result, list) and len(result) == len(scenes):
                return [e if e in valid_emotions else "calm" for e in result]
            if isinstance(result, dict) and "emotions" in result:
                emotions = result["emotions"]
                if isinstance(emotions, list):
                    return [e if e in valid_emotions else "calm" for e in emotions][:len(scenes)]
        except Exception as e:
            logger.warning(f"LLM emotion analysis failed: {e}")

        # Fallback: distribute template curve across scenes
        return self._distribute_curve(template_curve, len(scenes))

    def _distribute_curve(self, curve: list[str], num_scenes: int) -> list[str]:
        """Distribute a template curve evenly across N scenes."""
        if num_scenes <= 0:
            return []
        if num_scenes <= len(curve):
            step = len(curve) / num_scenes
            return [curve[int(i * step)] for i in range(num_scenes)]
        # More scenes than curve points — interpolate
        result = []
        for i in range(num_scenes):
            idx = int(i * len(curve) / num_scenes)
            result.append(curve[min(idx, len(curve) - 1)])
        return result

    def _smooth_transitions(self, scenes: list[dict]) -> list[dict]:
        """Ensure no jarring emotion jumps between adjacent scenes."""
        jarring_pairs = {
            ("calm", "shocking"), ("calm", "urgent"),
            ("reflective", "shocking"), ("reflective", "urgent"),
            ("hopeful", "somber"), ("warm", "tense"),
        }
        for i in range(1, len(scenes)):
            prev = scenes[i - 1].get("emotion_label", "calm")
            curr = scenes[i].get("emotion_label", "calm")
            if (prev, curr) in jarring_pairs or (curr, prev) in jarring_pairs:
                # Insert a transitional emotion
                bridge = "curious" if curr in ("shocking", "urgent", "tense") else "calm"
                scenes[i]["emotion_label"] = bridge
                mapping = EMOTION_VOICE_MAP.get(bridge, EMOTION_VOICE_MAP["calm"])
                scenes[i]["voice_emotion"] = mapping["voice_emotion"]
                scenes[i]["music_mood"] = mapping["music_mood"]
                logger.debug(f"Smoothed jarring transition at scene {i}: {prev}→{curr} → {prev}→{bridge}")
        return scenes

    def _get_emotion_rules(self) -> list[str]:
        """Fetch performance rules related to emotions from DB."""
        try:
            rows = self.db.conn.execute(
                "SELECT rule_text FROM performance_rules WHERE category = 'emotion' AND active = 1"
            ).fetchall()
            return [r["rule_text"] for r in rows]
        except Exception:
            return []

    def _save_arc(self, job_id: str, scenes: list[dict]):
        """Save emotional arc data to DB."""
        try:
            arc_data = [
                {"scene_index": i, "emotion": s.get("emotion_label"),
                 "voice_emotion": s.get("voice_emotion"), "music_mood": s.get("music_mood")}
                for i, s in enumerate(scenes)
            ]
            self.db.conn.execute(
                "UPDATE jobs SET emotional_arc = ? WHERE id = ?",
                (json.dumps(arc_data, ensure_ascii=False), job_id),
            )
            self.db.conn.commit()
        except Exception as e:
            logger.warning(f"Failed to save emotional arc: {e}")
