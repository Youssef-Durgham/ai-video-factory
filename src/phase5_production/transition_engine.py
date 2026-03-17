"""
Phase 5 — AI-Driven Transition Engine.

Selects optimal transitions between scenes using Qwen 3.5 analysis
of adjacent scene pairs (mood, topic relationship, pacing).
Falls back to deterministic rules if LLM is unavailable.

Runs during Phase 3 (Script) to assign transitions, consumed by Composer in Phase 5.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

import requests

logger = logging.getLogger(__name__)

OLLAMA_HOST = "http://localhost:11434"
LLM_MODEL = "qwen3.5:27b"

# ════════════════════════════════════════════════════════════════
# TRANSITION LIBRARY
# ════════════════════════════════════════════════════════════════

TRANSITIONS: dict[str, dict] = {
    # ─── Hard cuts ───
    "cut": {
        "ffmpeg": "-filter_complex '[0][1]concat=n=2:v=1:a=0'",
        "duration": 0.0,
        "when": "same location, continuous action, tension",
    },
    "smash_cut": {
        "ffmpeg": "instant cut + audio spike",
        "duration": 0.0,
        "when": "sudden contrast, shock, humor",
    },

    # ─── Soft transitions ───
    "crossfade": {
        "ffmpeg": "xfade=transition=fade:duration={dur}",
        "duration": 0.5,
        "when": "gentle scene change, related topics",
    },
    "dissolve": {
        "ffmpeg": "xfade=transition=dissolve:duration={dur}",
        "duration": 1.0,
        "when": "time passing, dream-like, memory",
    },

    # ─── Directional ───
    "wipe_left": {
        "ffmpeg": "xfade=transition=wipeleft:duration={dur}",
        "duration": 0.5,
        "when": "geographic movement, timeline progression",
    },
    "wipe_right": {
        "ffmpeg": "xfade=transition=wiperight:duration={dur}",
        "duration": 0.5,
        "when": "returning, going back in time",
    },
    "slide_up": {
        "ffmpeg": "xfade=transition=slideup:duration={dur}",
        "duration": 0.4,
        "when": "escalation, revelation, new chapter",
    },
    "slide_down": {
        "ffmpeg": "xfade=transition=slidedown:duration={dur}",
        "duration": 0.4,
        "when": "de-escalation, settling, grounding",
    },

    # ─── Dramatic ───
    "fade_black": {
        "ffmpeg": "fade=out → black 1s → fade=in",
        "duration": 1.5,
        "when": "major time skip, chapter break, death/ending",
    },
    "fade_white": {
        "ffmpeg": "fade=out:color=white → fade=in",
        "duration": 1.0,
        "when": "flashback, divine/spiritual, revelation",
    },

    # ─── Modern/Dynamic ───
    "zoom_in": {
        "ffmpeg": "zoompan + xfade",
        "duration": 0.6,
        "when": "focusing on detail, narrowing scope",
    },
    "zoom_out": {
        "ffmpeg": "zoompan reverse + xfade",
        "duration": 0.6,
        "when": "revealing bigger picture, broadening scope",
    },
    "glitch_cut": {
        "ffmpeg": "RGB shift frames + cut",
        "duration": 0.3,
        "when": "tech content, conspiracy, digital theme",
    },
}

# Available transition names for LLM prompt
TRANSITION_NAMES = list(TRANSITIONS.keys())


@dataclass
class TransitionChoice:
    """Result of transition selection for a scene pair."""
    transition_type: str = "crossfade"
    duration: float = 0.5
    reasoning: str = ""
    confidence: float = 0.0
    from_llm: bool = False


# ════════════════════════════════════════════════════════════════
# FALLBACK RULES
# ════════════════════════════════════════════════════════════════

# Mood-pair → transition mapping for deterministic fallback
MOOD_FALLBACK_RULES: dict[tuple[str, str], tuple[str, float]] = {
    # (from_mood, to_mood) → (transition, duration)
}

# General fallback rules based on relationship
RELATIONSHIP_FALLBACK: dict[str, tuple[str, float]] = {
    "same_topic":   ("crossfade", 0.5),
    "new_topic":    ("dissolve", 1.0),
    "time_skip":    ("fade_black", 1.5),
    "flashback":    ("fade_white", 1.0),
    "contrast":     ("cut", 0.0),
    "escalation":   ("cut", 0.0),
    "chapter_break": ("fade_black", 2.0),
}


def _fallback_transition(
    mood_from: str,
    mood_to: str,
    relationship: str = "",
) -> TransitionChoice:
    """Deterministic fallback when LLM is unavailable."""
    # Try relationship-based first
    if relationship in RELATIONSHIP_FALLBACK:
        t, d = RELATIONSHIP_FALLBACK[relationship]
        return TransitionChoice(
            transition_type=t,
            duration=d,
            reasoning=f"Fallback rule: relationship={relationship}",
            confidence=0.6,
            from_llm=False,
        )

    # Mood-based fallback
    if mood_from == mood_to:
        return TransitionChoice(
            transition_type="crossfade",
            duration=0.5,
            reasoning="Same mood → gentle crossfade",
            confidence=0.5,
            from_llm=False,
        )
    else:
        return TransitionChoice(
            transition_type="dissolve",
            duration=1.0,
            reasoning="Mood change → dissolve",
            confidence=0.5,
            from_llm=False,
        )


class TransitionSelector:
    """
    AI-driven transition selection between scenes.

    Uses Qwen 3.5 to analyze adjacent scene pairs and pick the
    best transition type + duration. Falls back to deterministic
    rules if LLM is unavailable or returns invalid output.
    """

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.ollama_host = self.config.get("ollama_host", OLLAMA_HOST)
        self.model = self.config.get("llm_model", LLM_MODEL)

    # ─── Public API ───────────────────────────────────────────

    def select_transition(
        self,
        scene_a: dict,
        scene_b: dict,
    ) -> TransitionChoice:
        """
        Select optimal transition between two adjacent scenes.

        Args:
            scene_a: Dict with keys: index, narration_summary, mood, scene_type
            scene_b: Same structure for the next scene.

        Returns:
            TransitionChoice with type, duration, and reasoning.
        """
        mood_a = scene_a.get("mood", "neutral")
        mood_b = scene_b.get("mood", "neutral")

        try:
            return self._llm_select(scene_a, scene_b)
        except Exception as e:
            logger.warning("LLM transition selection failed: %s — using fallback", e)
            return _fallback_transition(mood_a, mood_b)

    def select_all_transitions(
        self,
        scenes: list[dict],
    ) -> list[TransitionChoice]:
        """
        Select transitions for all adjacent scene pairs in a video.

        Args:
            scenes: Ordered list of scene dicts.

        Returns:
            List of TransitionChoice (length = len(scenes) - 1).
        """
        if len(scenes) < 2:
            return []

        transitions: list[TransitionChoice] = []
        for i in range(len(scenes) - 1):
            choice = self.select_transition(scenes[i], scenes[i + 1])
            logger.info(
                "Scene %d→%d: %s (%.1fs) — %s",
                i + 1, i + 2,
                choice.transition_type,
                choice.duration,
                choice.reasoning[:60],
            )
            transitions.append(choice)
        return transitions

    # ─── LLM Selection ───────────────────────────────────────

    def _llm_select(
        self,
        scene_a: dict,
        scene_b: dict,
    ) -> TransitionChoice:
        """Use Qwen 3.5 to select transition for a scene pair."""
        transition_hints = "\n".join(
            f"  - {name}: {t['when']}"
            for name, t in TRANSITIONS.items()
        )

        prompt = f"""You are a video editor selecting transitions for an Arabic documentary.

Scene {scene_a.get('index', '?')}:
  Narration: "{scene_a.get('narration_summary', '')}"
  Mood: {scene_a.get('mood', 'neutral')}
  Type: {scene_a.get('scene_type', 'general')}

Scene {scene_b.get('index', '?')}:
  Narration: "{scene_b.get('narration_summary', '')}"
  Mood: {scene_b.get('mood', 'neutral')}
  Type: {scene_b.get('scene_type', 'general')}

Available transitions:
{transition_hints}

Respond in JSON only:
{{"transition": "<name>", "duration": <float 0.3-2.0>, "reasoning": "<brief>"}}
"""

        resp = requests.post(
            f"{self.ollama_host}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 200},
            },
            timeout=60,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "")

        return self._parse_llm_response(raw, scene_a, scene_b)

    def _parse_llm_response(
        self,
        raw: str,
        scene_a: dict,
        scene_b: dict,
    ) -> TransitionChoice:
        """Parse LLM JSON response into TransitionChoice."""
        # Extract JSON from response (handle markdown fences)
        text = raw.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        data = json.loads(text)

        t_type = data.get("transition", "crossfade")
        duration = float(data.get("duration", 0.5))
        reasoning = data.get("reasoning", "")

        # Validate transition name
        if t_type not in TRANSITIONS:
            logger.warning("LLM returned unknown transition '%s', falling back", t_type)
            return _fallback_transition(
                scene_a.get("mood", "neutral"),
                scene_b.get("mood", "neutral"),
            )

        # Clamp duration
        duration = max(0.0, min(duration, 2.5))

        return TransitionChoice(
            transition_type=t_type,
            duration=duration,
            reasoning=reasoning,
            confidence=0.85,
            from_llm=True,
        )

    # ─── FFmpeg Command Generation ────────────────────────────

    @staticmethod
    def get_ffmpeg_filter(
        transition_type: str,
        duration: float,
        offset: float,
    ) -> str:
        """
        Generate FFmpeg xfade filter string for a given transition.

        Args:
            transition_type: Key from TRANSITIONS dict.
            duration: Transition duration in seconds.
            offset: Time offset where transition starts.

        Returns:
            FFmpeg filter string ready for -filter_complex.
        """
        t = TRANSITIONS.get(transition_type)
        if not t or transition_type == "cut":
            return ""  # Hard cut = no filter needed

        if transition_type == "fade_black":
            # Two-step: fade out → black → fade in
            half = duration / 2
            return (
                f"fade=t=out:st={offset}:d={half},"
                f"fade=t=in:st={offset + half}:d={half}"
            )

        if transition_type == "fade_white":
            half = duration / 2
            return (
                f"fade=t=out:st={offset}:d={half}:color=white,"
                f"fade=t=in:st={offset + half}:d={half}:color=white"
            )

        xfade = t.get("xfade")
        if xfade:
            return f"xfade=transition={xfade}:duration={duration}:offset={offset}"

        return ""
