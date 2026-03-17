"""
Phase 5 — Smart Voice Selection.

Selects the optimal voice for a video based on:
  1. Channel default voice
  2. Content/topic match
  3. Emotion range compatibility
  4. Quality score

Returns (voice_id, embedding_path) tuple.
"""

import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════
# CONTENT → VOICE STYLE MAPPING
# ════════════════════════════════════════════════════════════════

CONTENT_VOICE_MAP: dict[str, list[str]] = {
    # topic_category → preferred voice styles (ordered by priority)
    "documentary":   ["authoritative", "narrator", "calm"],
    "historical":    ["narrator", "authoritative", "dramatic"],
    "military":      ["authoritative", "dramatic", "narrator"],
    "political":     ["authoritative", "calm", "narrator"],
    "scientific":    ["educational", "calm", "narrator"],
    "technology":    ["energetic", "educational", "calm"],
    "crime":         ["dramatic", "mysterious", "narrator"],
    "mystery":       ["mysterious", "dramatic", "narrator"],
    "islamic":       ["calm", "narrator", "authoritative"],
    "biography":     ["narrator", "calm", "dramatic"],
    "economic":      ["authoritative", "educational", "calm"],
    "social":        ["calm", "educational", "narrator"],
    "entertainment": ["energetic", "narrator", "dramatic"],
}

# Emotion range requirements per voice style
VOICE_EMOTION_RANGES: dict[str, list[str]] = {
    "authoritative": ["calm", "dramatic", "tense", "hopeful"],
    "narrator":      ["calm", "reflective", "hopeful", "somber"],
    "dramatic":      ["dramatic", "tense", "urgent", "mysterious"],
    "mysterious":    ["mysterious", "tense", "whisper", "somber"],
    "educational":   ["calm", "hopeful", "reflective", "excited"],
    "energetic":     ["excited", "urgent", "hopeful", "dramatic"],
    "calm":          ["calm", "reflective", "hopeful", "somber"],
}


@dataclass
class VoiceProfile:
    """Profile for a cloned voice."""
    voice_id: str
    embedding_path: str
    name: str = ""
    gender: str = "male"
    style: str = "narrator"
    quality_score: float = 0.0
    emotion_range: list[str] = None

    def __post_init__(self):
        if self.emotion_range is None:
            self.emotion_range = VOICE_EMOTION_RANGES.get(self.style, ["calm"])


class VoiceSelector:
    """
    Smart voice selection for video narration.

    Priority:
    1. Channel default voice (if configured)
    2. Content/topic match (best style for the topic)
    3. Emotion range compatibility (voice can handle script emotions)
    4. Quality score (highest quality clone)
    """

    def __init__(self, db=None, voices_dir: str = "config/voices"):
        self.db = db
        self.voices_dir = Path(voices_dir)
        self._voice_library: Optional[dict] = None

    def select_voice(
        self,
        job: dict,
        channel: dict,
    ) -> tuple[str, str]:
        """
        Select the optimal voice for a job.

        Args:
            job: Job dict with topic_category, script emotions, etc.
            channel: Channel config dict with optional default_voice_id.

        Returns:
            Tuple of (voice_id, embedding_path).

        Raises:
            ValueError: If no suitable voice is found.
        """
        library = self._load_voice_library()
        if not library:
            raise ValueError("No voices available in voice library")

        # 1. Channel default
        channel_voice = channel.get("default_voice_id")
        if channel_voice and channel_voice in library:
            voice = library[channel_voice]
            logger.info(f"Using channel default voice: {channel_voice}")
            return channel_voice, voice["embedding_path"]

        # 2. Content match
        topic = job.get("topic_category", "documentary")
        preferred_styles = CONTENT_VOICE_MAP.get(topic, ["narrator", "calm"])

        # 3. Score all voices
        candidates = []
        for vid, vdata in library.items():
            score = self._score_voice(vdata, preferred_styles, job)
            candidates.append((vid, vdata, score))

        # Sort by score descending
        candidates.sort(key=lambda x: x[2], reverse=True)

        if candidates:
            best_id, best_data, best_score = candidates[0]
            logger.info(
                f"Selected voice: {best_id} (score={best_score:.1f}, "
                f"style={best_data.get('style', 'unknown')})"
            )
            return best_id, best_data["embedding_path"]

        raise ValueError("No suitable voice found")

    def _score_voice(
        self,
        voice_data: dict,
        preferred_styles: list[str],
        job: dict,
    ) -> float:
        """
        Score a voice for suitability.

        Factors:
        - Style match with topic (0-4 points)
        - Emotion range coverage (0-3 points)
        - Clone quality (0-3 points)
        """
        score = 0.0
        style = voice_data.get("style", "")

        # Style match (4 points max)
        if style in preferred_styles:
            position = preferred_styles.index(style)
            score += 4.0 - position  # First choice = 4, second = 3, etc.

        # Emotion range coverage (3 points max)
        voice_emotions = VOICE_EMOTION_RANGES.get(style, [])
        script_emotions = set()
        scenes = job.get("scenes", [])
        if isinstance(scenes, list):
            for s in scenes:
                em = s.get("voice_emotion", "calm") if isinstance(s, dict) else "calm"
                script_emotions.add(em)

        if script_emotions and voice_emotions:
            coverage = len(script_emotions & set(voice_emotions)) / len(script_emotions)
            score += coverage * 3.0

        # Quality score (3 points max, scaled from 0-10 → 0-3)
        quality = voice_data.get("quality_score", 5.0)
        score += (quality / 10.0) * 3.0

        return score

    def _load_voice_library(self) -> dict:
        """Load voice library from YAML config."""
        if self._voice_library is not None:
            return self._voice_library

        import yaml

        library_path = self.voices_dir / "voice_library.yaml"
        if not library_path.exists():
            # Fall back to scanning embeddings directory
            return self._scan_embeddings()

        with open(library_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        self._voice_library = data.get("voices", {})
        return self._voice_library

    def _scan_embeddings(self) -> dict:
        """Scan embeddings directory for .pt files as fallback."""
        embeddings_dir = self.voices_dir / "embeddings"
        if not embeddings_dir.exists():
            return {}

        library = {}
        for pt_file in embeddings_dir.glob("*.pt"):
            voice_id = pt_file.stem
            library[voice_id] = {
                "embedding_path": str(pt_file),
                "style": "narrator",
                "quality_score": 5.0,
            }

        self._voice_library = library
        return library

    def get_available_voices(self) -> list[dict]:
        """Return list of all available voices with metadata."""
        library = self._load_voice_library()
        return [
            {"voice_id": vid, **vdata}
            for vid, vdata in library.items()
        ]
