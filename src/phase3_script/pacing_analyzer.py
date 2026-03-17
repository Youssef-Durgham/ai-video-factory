"""
Phase 3: Scene duration optimization based on pacing best practices.
"""

import logging
import statistics
from src.core.llm import generate_json

logger = logging.getLogger(__name__)

# Scene type → duration guidelines (seconds)
DURATION_GUIDELINES = {
    "hook": (3, 5),
    "intro": (8, 12),
    "setup": (8, 12),
    "explanation": (12, 20),
    "emotional_peak": (5, 8),
    "visual_showcase": (6, 10),
    "transition_bridge": (3, 5),
    "conclusion": (10, 15),
    "cta": (5, 8),
}

CLASSIFY_PROMPT = """صنّف كل مشهد من المشاهد التالية حسب نوعه.

أنواع المشاهد المتاحة:
- hook: الخطاف الافتتاحي
- intro: المقدمة والسياق
- setup: تمهيد لنقطة رئيسية
- explanation: شرح مفصّل
- emotional_peak: لحظة درامية/عاطفية
- visual_showcase: عرض بصري
- transition_bridge: انتقال بين أقسام
- conclusion: خاتمة وتأمل
- cta: دعوة للاشتراك

المشاهد:
{scenes_text}

أجب بـ JSON:
{{
    "classifications": [
        {{"scene_index": 0, "type": "hook", "complexity": "low|medium|high", "has_data": false}},
        ...
    ]
}}"""


class PacingAnalyzer:
    """Analyze and optimize video pacing/rhythm."""

    def __init__(self, config: dict):
        self.config = config

    def analyze_and_adjust(self, scenes: list[dict]) -> list[dict]:
        """
        Classify scene types and adjust durations for optimal pacing.
        Returns scenes with updated duration_seconds + pacing_notes.
        """
        # Step 1: Classify scenes using LLM
        classifications = self._classify_scenes(scenes)

        # Step 2: Apply duration guidelines
        for scene in scenes:
            idx = scene["scene_index"]
            cls = classifications.get(idx, {"type": "explanation", "complexity": "medium"})
            scene_type = cls.get("type", "explanation")
            complexity = cls.get("complexity", "medium")

            # Get guideline range
            min_dur, max_dur = DURATION_GUIDELINES.get(scene_type, (5, 15))

            # Adjust for complexity
            if complexity == "high":
                min_dur += 3
                max_dur += 3
            elif complexity == "low":
                min_dur -= 1
                max_dur -= 2

            # Adjust for data/statistics content
            if cls.get("has_data", False):
                min_dur += 3

            # Clamp duration
            current = scene.get("duration_seconds", 10)
            adjusted = max(min_dur, min(max_dur, current))
            scene["duration_seconds"] = adjusted
            scene["_scene_type"] = scene_type
            scene["_pacing_note"] = f"{scene_type} ({min_dur}-{max_dur}s)"

        # Step 3: Apply anti-monotony rules
        scenes = self._apply_anti_monotony(scenes)

        # Step 4: Log pacing score
        durations = [s["duration_seconds"] for s in scenes]
        score = self.get_pacing_score(durations)
        logger.info(f"Pacing score: {score:.1f}/10 across {len(scenes)} scenes")

        return scenes

    def _classify_scenes(self, scenes: list[dict]) -> dict:
        """Classify each scene type using LLM."""
        scenes_text = "\n".join(
            f"[{s['scene_index']}] ({s.get('duration_seconds', 10)}s) "
            f"{s.get('narration_text', '')[:100]}"
            for s in scenes
        )

        try:
            result = generate_json(
                prompt=CLASSIFY_PROMPT.format(scenes_text=scenes_text),
                temperature=0.3,
            )
            classifications = result.get("classifications", [])
            return {c["scene_index"]: c for c in classifications}
        except Exception as e:
            logger.warning(f"Scene classification failed: {e}")
            # Fallback: heuristic classification
            return self._heuristic_classify(scenes)

    def _heuristic_classify(self, scenes: list[dict]) -> dict:
        """Fallback: classify scenes without LLM."""
        result = {}
        total = len(scenes)
        for s in scenes:
            idx = s["scene_index"]
            position = idx / max(total - 1, 1)

            if idx == 0:
                scene_type = "hook"
            elif idx == 1:
                scene_type = "intro"
            elif position > 0.9:
                scene_type = "conclusion" if idx < total - 1 else "cta"
            elif position > 0.7:
                scene_type = "emotional_peak"
            else:
                scene_type = "explanation"

            result[idx] = {"type": scene_type, "complexity": "medium", "has_data": False}
        return result

    def _apply_anti_monotony(self, scenes: list[dict]) -> list[dict]:
        """
        Anti-monotony rules:
        - No 3+ consecutive scenes with same duration (±2s)
        - Max 3:1 duration ratio between adjacent scenes
        """
        for i in range(2, len(scenes)):
            d0 = scenes[i - 2]["duration_seconds"]
            d1 = scenes[i - 1]["duration_seconds"]
            d2 = scenes[i]["duration_seconds"]

            # Check 3 consecutive similar durations
            if abs(d0 - d1) <= 2 and abs(d1 - d2) <= 2:
                # Adjust middle scene by ±3s
                if d1 < 10:
                    scenes[i - 1]["duration_seconds"] = min(15, d1 + 3)
                else:
                    scenes[i - 1]["duration_seconds"] = max(5, d1 - 3)

        # Check ratio between adjacent
        for i in range(1, len(scenes)):
            d_prev = scenes[i - 1]["duration_seconds"]
            d_curr = scenes[i]["duration_seconds"]
            if d_prev > 0 and d_curr > 0:
                ratio = max(d_prev, d_curr) / min(d_prev, d_curr)
                if ratio > 3:
                    # Smooth the transition
                    avg = (d_prev + d_curr) / 2
                    scenes[i]["duration_seconds"] = max(5, min(15, avg * 1.2))

        return scenes

    def get_pacing_score(self, durations: list[float]) -> float:
        """
        Score 0-10 for pacing quality.
        Higher variance + good rhythm = higher score.
        """
        if len(durations) < 3:
            return 5.0

        # Variance score (too uniform = boring)
        stdev = statistics.stdev(durations)
        variance_score = min(10, stdev * 2.5)  # Target stdev ~3-4

        # Rhythm score: check for pace changes
        changes = 0
        for i in range(1, len(durations)):
            if abs(durations[i] - durations[i - 1]) > 3:
                changes += 1
        rhythm_score = min(10, changes / max(len(durations) / 5, 1) * 10)

        # Anti-monotony score
        monotone_runs = 0
        for i in range(2, len(durations)):
            if abs(durations[i] - durations[i - 1]) <= 1 and abs(durations[i - 1] - durations[i - 2]) <= 1:
                monotone_runs += 1
        monotony_penalty = min(5, monotone_runs)

        score = (variance_score * 0.4 + rhythm_score * 0.4) - monotony_penalty * 0.2
        return max(0, min(10, score))
