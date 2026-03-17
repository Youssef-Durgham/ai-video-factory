"""
Voice Emotion Agent — Per-scene TTS emotion control.
Maps emotional_arc output to Fish Audio emotion parameters (speed, pitch, energy).
"""

import json
import logging
from typing import Optional

from src.core.database import FactoryDB

logger = logging.getLogger(__name__)

# Fish Audio S2 Pro emotion parameter mappings
# Each emotion maps to: speed (0.5-2.0), pitch_shift (semitones), energy (0.0-1.0)
EMOTION_PARAMS = {
    "calm": {"speed": 0.9, "pitch_shift": 0, "energy": 0.4, "pause_after_ms": 400},
    "curious": {"speed": 1.0, "pitch_shift": 1, "energy": 0.5, "pause_after_ms": 300},
    "tense": {"speed": 1.05, "pitch_shift": 0, "energy": 0.7, "pause_after_ms": 200},
    "dramatic": {"speed": 0.85, "pitch_shift": -1, "energy": 0.8, "pause_after_ms": 500},
    "reflective": {"speed": 0.85, "pitch_shift": 0, "energy": 0.35, "pause_after_ms": 600},
    "mysterious": {"speed": 0.9, "pitch_shift": -1, "energy": 0.45, "pause_after_ms": 500},
    "urgent": {"speed": 1.15, "pitch_shift": 1, "energy": 0.9, "pause_after_ms": 150},
    "warm": {"speed": 0.95, "pitch_shift": 1, "energy": 0.5, "pause_after_ms": 350},
    "emotional": {"speed": 0.85, "pitch_shift": 0, "energy": 0.6, "pause_after_ms": 500},
    "hopeful": {"speed": 1.0, "pitch_shift": 2, "energy": 0.6, "pause_after_ms": 300},
    "confident": {"speed": 1.0, "pitch_shift": 0, "energy": 0.7, "pause_after_ms": 300},
    "somber": {"speed": 0.8, "pitch_shift": -2, "energy": 0.3, "pause_after_ms": 600},
    "surprised": {"speed": 1.1, "pitch_shift": 2, "energy": 0.8, "pause_after_ms": 200},
    "engaged": {"speed": 1.0, "pitch_shift": 1, "energy": 0.55, "pause_after_ms": 300},
    "authoritative": {"speed": 0.95, "pitch_shift": -1, "energy": 0.7, "pause_after_ms": 400},
    "educational": {"speed": 0.95, "pitch_shift": 0, "energy": 0.5, "pause_after_ms": 350},
    "energetic": {"speed": 1.1, "pitch_shift": 1, "energy": 0.8, "pause_after_ms": 200},
}

# Transition smoothing — when switching between emotions, blend parameters
TRANSITION_BLEND_FACTOR = 0.3  # 30% blend from previous emotion


class VoiceEmotionAgent:
    """
    Maps emotional arc to concrete Fish Audio TTS parameters per scene.
    Ensures smooth transitions and emotional delivery matching content.
    """

    def __init__(self, db: FactoryDB):
        self.db = db

    def run(self, job_id: str, scenes: list[dict]) -> list[dict]:
        """
        Process scenes and add TTS emotion parameters.

        Args:
            job_id: Job identifier.
            scenes: List of scene dicts with voice_emotion field.

        Returns:
            Updated scenes with tts_params dict per scene.
        """
        performance_rules = self._get_voice_rules()

        prev_params = None
        for i, scene in enumerate(scenes):
            emotion = scene.get("voice_emotion", "calm")
            raw_params = EMOTION_PARAMS.get(emotion, EMOTION_PARAMS["calm"]).copy()

            # Apply performance rule adjustments
            raw_params = self._apply_rules(raw_params, emotion, performance_rules)

            # Smooth transition from previous scene
            if prev_params is not None:
                raw_params = self._blend_transition(prev_params, raw_params)

            # Add sentence-level emphasis hints
            narration = scene.get("narration_text", "")
            raw_params["emphasis_words"] = self._detect_emphasis(narration)

            scene["tts_params"] = raw_params
            prev_params = raw_params

        logger.info(f"Voice emotion params set for {job_id}: {len(scenes)} scenes")
        return scenes

    def get_params(self, emotion: str) -> dict:
        """Get TTS parameters for a specific emotion."""
        return EMOTION_PARAMS.get(emotion, EMOTION_PARAMS["calm"]).copy()

    def _blend_transition(self, prev: dict, curr: dict) -> dict:
        """Blend parameters between scenes for smooth transitions."""
        blended = curr.copy()
        for key in ("speed", "energy"):
            if key in prev and key in curr:
                blended[key] = curr[key] * (1 - TRANSITION_BLEND_FACTOR) + prev[key] * TRANSITION_BLEND_FACTOR
                blended[key] = round(blended[key], 2)
        # Pitch shift doesn't blend well — keep current
        return blended

    def _detect_emphasis(self, narration: str) -> list[str]:
        """Detect words that should be emphasized in TTS delivery."""
        emphasis_markers = []
        # Numbers and statistics
        import re
        numbers = re.findall(r'\d+[\d,.]*', narration)
        emphasis_markers.extend(numbers[:3])
        # Quoted text
        quotes = re.findall(r'[""«»]([^""«»]+)[""«»]', narration)
        emphasis_markers.extend(quotes[:2])
        return emphasis_markers

    def _apply_rules(self, params: dict, emotion: str, rules: list) -> dict:
        """Apply learned performance rules to TTS parameters."""
        for rule in rules:
            # Rules are stored as JSON: {"emotion": "dramatic", "adjust": {"speed": -0.05}}
            if isinstance(rule, dict) and rule.get("emotion") == emotion:
                adjustments = rule.get("adjust", {})
                for key, delta in adjustments.items():
                    if key in params and isinstance(params[key], (int, float)):
                        params[key] = round(params[key] + delta, 2)
        return params

    def _get_voice_rules(self) -> list:
        """Fetch performance rules for voice emotion from DB."""
        try:
            rows = self.db.conn.execute(
                "SELECT rule_text FROM performance_rules WHERE category = 'voice_emotion' AND active = 1"
            ).fetchall()
            rules = []
            for r in rows:
                try:
                    rules.append(json.loads(r["rule_text"]))
                except (json.JSONDecodeError, TypeError):
                    pass
            return rules
        except Exception:
            return []
