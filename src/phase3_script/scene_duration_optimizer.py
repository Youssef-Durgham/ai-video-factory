"""
Scene Duration Optimizer.

Adjusts individual scene durations based on visual complexity + narration length.
Companion to PacingAnalyzer — this handles per-scene optimization.

Runs AFTER voice generation (we now know exact narration duration per scene).

INPUTS:
├── Narration audio duration per scene (from Fish Audio S2 Pro)
├── Visual complexity score (from FLUX prompt analysis)
├── Scene type (action, dialogue, visual showcase, data display)
├── Text overlay amount (more text = more reading time needed)
└── Emotional weight (from emotional_arc agent)

RULES:
1. Scene duration ≥ narration duration + 0.5s (breathing room)
2. Scenes with text overlay: add (word_count / 3) seconds reading time
3. Data/statistics scenes: add 3s minimum for comprehension
4. After emotional peak: add 1-2s "landing" time
5. Visual showcase: can extend 2-3s beyond narration
6. Rapid montage: can be shorter than narration (audio continues over next)

OUTPUT:
Updated scene durations → affects:
├── LTX video clip length
├── Text overlay timing
├── Music zone durations
└── Transition timing
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.database import FactoryDB

logger = logging.getLogger(__name__)


@dataclass
class DurationAdjustment:
    """Result of duration optimization for a single scene."""
    scene_index: int
    original_duration: float
    narration_duration: float
    adjusted_duration: float
    reason: str
    adjustments: Dict[str, float]  # breakdown of time additions


class SceneDurationOptimizer:
    """
    Optimizes per-scene durations after voice generation.
    
    Uses narration audio length as the baseline, then adjusts for:
    - Text overlay reading time
    - Data comprehension time
    - Emotional weight landing time
    - Visual complexity showcase time
    - Scene type-specific padding
    """

    # Minimum padding after narration ends (breathing room)
    MIN_PADDING_SEC = 0.5

    # Reading speed: words per second for Arabic text overlays
    READING_SPEED_WPS = 3.0

    # Minimum extra time for data/statistics scenes
    DATA_SCENE_MIN_SEC = 3.0

    # Extra time after emotional peaks
    EMOTIONAL_LANDING_SEC = 1.5

    # Visual showcase extension
    VISUAL_SHOWCASE_EXTENSION = 2.5

    # Scene type multipliers
    SCENE_TYPE_MULTIPLIERS = {
        "action": 1.0,        # Fast paced
        "dialogue": 1.1,      # Needs reading time
        "visual_showcase": 1.3,  # Let the visual breathe
        "data_display": 1.4,  # Needs comprehension time
        "montage": 0.8,       # Can be shorter, audio overlaps
        "transition": 0.9,    # Brief connecting scene
        "emotional_peak": 1.2,  # Let emotions land
        "intro": 1.1,         # Hook needs breathing room
        "outro": 1.2,         # Conclusion needs weight
    }

    # Absolute limits
    MIN_SCENE_DURATION = 3.0
    MAX_SCENE_DURATION = 25.0

    def __init__(self, db: Optional["FactoryDB"] = None):
        self.db = db

    def optimize(
        self,
        scenes: List[dict],
        voice_durations: Dict[int, float],
        emotional_arc: Optional[Dict[int, float]] = None,
        target_total_duration: Optional[float] = None,
    ) -> List[DurationAdjustment]:
        """
        Optimize scene durations.

        Args:
            scenes: List of scene dicts (from splitter).
            voice_durations: {scene_index: narration_duration_seconds}.
            emotional_arc: {scene_index: emotion_intensity 0-1} from EmotionalArcAgent.
            target_total_duration: Optional target video length in seconds.

        Returns:
            List of DurationAdjustment for each scene.
        """
        emotional_arc = emotional_arc or {}
        adjustments = []

        for scene in scenes:
            idx = scene.get("scene_index", 0)
            original_dur = scene.get("duration_seconds", 8.0)
            narration_dur = voice_durations.get(idx, original_dur - self.MIN_PADDING_SEC)

            # Start from narration duration + minimum padding
            base_duration = narration_dur + self.MIN_PADDING_SEC
            adj_breakdown = {"narration": narration_dur, "base_padding": self.MIN_PADDING_SEC}

            # 1. Text overlay reading time
            text_overlay = scene.get("text_overlay")
            if text_overlay and isinstance(text_overlay, dict):
                text = text_overlay.get("text", "")
                word_count = len(text.split())
                reading_time = word_count / self.READING_SPEED_WPS
                if reading_time > 0:
                    base_duration = max(base_duration, narration_dur + reading_time + 0.3)
                    adj_breakdown["reading_time"] = reading_time

            # 2. Data/statistics scene padding
            scene_type = self._classify_scene_type(scene)
            if scene_type == "data_display":
                data_extra = max(0, self.DATA_SCENE_MIN_SEC - (base_duration - narration_dur))
                base_duration += data_extra
                adj_breakdown["data_comprehension"] = data_extra

            # 3. Emotional weight landing
            emotion_intensity = emotional_arc.get(idx, 0.0)
            if emotion_intensity > 0.7:
                landing = self.EMOTIONAL_LANDING_SEC * emotion_intensity
                base_duration += landing
                adj_breakdown["emotional_landing"] = round(landing, 2)

            # 4. Visual showcase extension
            if scene_type == "visual_showcase":
                base_duration += self.VISUAL_SHOWCASE_EXTENSION
                adj_breakdown["visual_showcase"] = self.VISUAL_SHOWCASE_EXTENSION

            # 5. Scene type multiplier
            multiplier = self.SCENE_TYPE_MULTIPLIERS.get(scene_type, 1.0)
            if multiplier != 1.0:
                before = base_duration
                base_duration *= multiplier
                adj_breakdown["type_multiplier"] = round(base_duration - before, 2)

            # 6. Enforce absolute limits
            adjusted = max(self.MIN_SCENE_DURATION, min(self.MAX_SCENE_DURATION, base_duration))

            reason_parts = []
            if adjusted > original_dur + 1:
                reason_parts.append(f"extended for {scene_type}")
            elif adjusted < original_dur - 1:
                reason_parts.append(f"shortened: {scene_type}")
            else:
                reason_parts.append("minor adjustment")

            if text_overlay:
                reason_parts.append("text overlay reading time")
            if emotion_intensity > 0.7:
                reason_parts.append(f"emotional peak ({emotion_intensity:.1f})")

            adjustments.append(DurationAdjustment(
                scene_index=idx,
                original_duration=original_dur,
                narration_duration=narration_dur,
                adjusted_duration=round(adjusted, 2),
                reason="; ".join(reason_parts),
                adjustments=adj_breakdown,
            ))

        # If target total duration is specified, scale proportionally
        if target_total_duration:
            adjustments = self._scale_to_target(adjustments, target_total_duration)

        return adjustments

    def apply_to_scenes(self, scenes: List[dict],
                        adjustments: List[DurationAdjustment]) -> List[dict]:
        """Apply duration adjustments back to scene dicts."""
        adj_map = {a.scene_index: a for a in adjustments}
        updated = []
        for scene in scenes:
            idx = scene.get("scene_index", 0)
            if idx in adj_map:
                scene = {**scene, "duration_seconds": adj_map[idx].adjusted_duration}
            updated.append(scene)
        return updated

    def _classify_scene_type(self, scene: dict) -> str:
        """Classify scene type based on content indicators."""
        text = scene.get("narration_text", "").lower()
        prompt = scene.get("visual_prompt", "").lower()
        overlay = scene.get("text_overlay")

        # Data display: numbers, statistics, percentages
        data_indicators = ["percent", "%", "billion", "million", "statistics",
                           "number", "data", "chart", "graph", "مليار", "مليون", "نسبة"]
        if any(ind in text or ind in prompt for ind in data_indicators):
            return "data_display"

        # Visual showcase: landscape, architecture, aerial
        visual_indicators = ["landscape", "aerial", "panoramic", "establishing shot",
                            "wide shot", "beauty shot", "sunset", "skyline"]
        if any(ind in prompt for ind in visual_indicators):
            return "visual_showcase"

        # Montage: quick cuts, series
        if "montage" in prompt or scene.get("transition_to_next") == "quick_cut":
            return "montage"

        # Emotional peak: based on voice_emotion
        voice_emotion = scene.get("voice_emotion", "calm")
        if voice_emotion in ("dramatic", "urgent", "emotional"):
            return "emotional_peak"

        # Intro/outro by index
        scene_idx = scene.get("scene_index", 0)
        if scene_idx == 0:
            return "intro"

        return "dialogue"  # Default

    def _scale_to_target(
        self,
        adjustments: List[DurationAdjustment],
        target: float,
    ) -> List[DurationAdjustment]:
        """Scale all durations proportionally to meet target total."""
        current_total = sum(a.adjusted_duration for a in adjustments)
        if current_total <= 0:
            return adjustments

        scale_factor = target / current_total

        scaled = []
        for a in adjustments:
            new_dur = max(
                self.MIN_SCENE_DURATION,
                min(self.MAX_SCENE_DURATION, a.adjusted_duration * scale_factor),
            )
            scaled.append(DurationAdjustment(
                scene_index=a.scene_index,
                original_duration=a.original_duration,
                narration_duration=a.narration_duration,
                adjusted_duration=round(new_dur, 2),
                reason=a.reason + f" (scaled {scale_factor:.2f}x)",
                adjustments={**a.adjustments, "scale_factor": round(scale_factor, 3)},
            ))

        return scaled
