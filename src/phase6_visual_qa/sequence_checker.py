"""
Phase 6A — Sequence Checker: Visual flow and continuity verification.

Ensures scenes have visual coherence, consistent style, and logical
flow across the video. Detects jarring visual jumps between adjacent scenes.

Two-layer approach:
  1. Deterministic: color histogram similarity, brightness continuity,
     dominant color tracking across sequential frames.
  2. Vision LLM: semantic flow check — do adjacent scenes feel like
     they belong in the same video?
"""

import base64
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import cv2
except ImportError:
    cv2 = None
try:
    import numpy as np
except ImportError:
    np = None
try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger(__name__)

OLLAMA_HOST = "http://localhost:11434"
VISION_MODEL = "qwen3.5:27b"

# ════════════════════════════════════════════════════════════════
# THRESHOLDS
# ════════════════════════════════════════════════════════════════

HISTOGRAM_JUMP_THRESHOLD = 0.35    # Correlation below this = jarring jump
BRIGHTNESS_JUMP_MAX = 60.0         # Max brightness delta between adjacent scenes
COLOR_TEMP_JUMP_MAX = 40.0         # Max color temperature shift
FLOW_PASS_SCORE = 7.0


@dataclass
class PairResult:
    """Continuity check result for an adjacent scene pair."""
    scene_a: int = 0
    scene_b: int = 0
    histogram_similarity: float = 1.0
    brightness_delta: float = 0.0
    color_temp_delta: float = 0.0
    visual_jump: bool = False
    vision_flow_score: float = 10.0
    vision_notes: str = ""


@dataclass
class SequenceResult:
    """Full sequence continuity check result."""
    pair_results: list[PairResult] = field(default_factory=list)
    overall_score: float = 10.0
    jarring_transitions: list[int] = field(default_factory=list)
    verdict: str = "pass"           # pass | flag_human
    details: dict = field(default_factory=dict)


class SequenceChecker:
    """
    Check visual flow and continuity across all scene images.

    Analyzes adjacent scene pairs for visual coherence and flags
    jarring transitions that could distract viewers.
    """

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.ollama_host = self.config.get("ollama_host", OLLAMA_HOST)
        self.vision_model = self.config.get("vision_model", VISION_MODEL)

    # ─── Public API ───────────────────────────────────────────

    def check_sequence(
        self,
        image_paths: list[str],
        scene_moods: list[str] | None = None,
    ) -> SequenceResult:
        """
        Check visual flow across ordered scene images.

        Args:
            image_paths: Ordered list of scene image paths.
            scene_moods: Optional mood labels per scene.

        Returns:
            SequenceResult with pair-level and overall analysis.
        """
        if len(image_paths) < 2:
            return SequenceResult(overall_score=10.0, verdict="pass")

        result = SequenceResult()
        moods = scene_moods or [""] * len(image_paths)

        images = []
        for p in image_paths:
            img = cv2.imread(p)
            if img is None:
                logger.warning("Cannot read image: %s", p)
                images.append(None)
            else:
                images.append(img)

        # Check each adjacent pair
        for i in range(len(images) - 1):
            if images[i] is None or images[i + 1] is None:
                continue

            pair = PairResult(scene_a=i, scene_b=i + 1)

            # Layer 1: Deterministic
            self._deterministic_pair(images[i], images[i + 1], pair)

            # Layer 2: Vision LLM (only for flagged pairs or sampling)
            if pair.visual_jump or i % 3 == 0:
                self._vision_pair(
                    image_paths[i], image_paths[i + 1],
                    moods[i], moods[i + 1], pair,
                )

            result.pair_results.append(pair)

            if pair.visual_jump:
                result.jarring_transitions.append(i)

        # Overall score
        if result.pair_results:
            scores = []
            for pr in result.pair_results:
                # Combine histogram similarity and vision score
                det_score = pr.histogram_similarity * 10.0
                vis_score = pr.vision_flow_score
                combined = (det_score + vis_score) / 2.0
                scores.append(combined)
            result.overall_score = sum(scores) / len(scores)
        else:
            result.overall_score = 10.0

        result.verdict = (
            "pass" if result.overall_score >= FLOW_PASS_SCORE
            else "flag_human"
        )

        return result

    # ─── Layer 1: Deterministic ───────────────────────────────

    def _deterministic_pair(
        self,
        img_a: np.ndarray,
        img_b: np.ndarray,
        pair: PairResult,
    ) -> None:
        """Run deterministic checks on an adjacent image pair."""
        # Histogram similarity
        pair.histogram_similarity = self._histogram_similarity(img_a, img_b)

        # Brightness delta
        bright_a = float(np.mean(cv2.cvtColor(img_a, cv2.COLOR_BGR2GRAY)))
        bright_b = float(np.mean(cv2.cvtColor(img_b, cv2.COLOR_BGR2GRAY)))
        pair.brightness_delta = abs(bright_b - bright_a)

        # Color temperature (approximated via blue/red channel ratio)
        temp_a = self._color_temperature(img_a)
        temp_b = self._color_temperature(img_b)
        pair.color_temp_delta = abs(temp_b - temp_a)

        # Flag if any metric exceeds threshold
        pair.visual_jump = (
            pair.histogram_similarity < HISTOGRAM_JUMP_THRESHOLD
            or pair.brightness_delta > BRIGHTNESS_JUMP_MAX
            or pair.color_temp_delta > COLOR_TEMP_JUMP_MAX
        )

    @staticmethod
    def _histogram_similarity(img_a: np.ndarray, img_b: np.ndarray) -> float:
        """Compare color histograms using correlation."""
        hist_a = cv2.calcHist([img_a], [0, 1, 2], None, [16, 16, 16],
                              [0, 256, 0, 256, 0, 256])
        hist_b = cv2.calcHist([img_b], [0, 1, 2], None, [16, 16, 16],
                              [0, 256, 0, 256, 0, 256])
        cv2.normalize(hist_a, hist_a)
        cv2.normalize(hist_b, hist_b)
        corr = cv2.compareHist(hist_a.flatten(), hist_b.flatten(), cv2.HISTCMP_CORREL)
        return float(max(0.0, corr))

    @staticmethod
    def _color_temperature(img: np.ndarray) -> float:
        """Estimate color temperature from blue/red channel ratio."""
        b, _, r = cv2.split(img)
        mean_r = float(np.mean(r)) + 1e-10
        mean_b = float(np.mean(b)) + 1e-10
        return mean_b / mean_r * 100.0

    # ─── Layer 2: Vision LLM ─────────────────────────────────

    def _vision_pair(
        self,
        path_a: str,
        path_b: str,
        mood_a: str,
        mood_b: str,
        pair: PairResult,
    ) -> None:
        """Use Vision LLM to evaluate visual flow between two scenes."""
        try:
            img_a_b64 = self._encode_image(path_a)
            img_b_b64 = self._encode_image(path_b)
        except Exception as e:
            logger.warning("Cannot encode images for vision check: %s", e)
            return

        prompt = f"""You are reviewing two adjacent scenes from an Arabic documentary video.

Scene {pair.scene_a + 1} mood: {mood_a or 'unknown'}
Scene {pair.scene_b + 1} mood: {mood_b or 'unknown'}

Evaluate the visual flow/continuity between these two scenes:
1. Do they feel like they belong in the same video?
2. Is the style consistent (color palette, lighting, realism level)?
3. Is the transition between subjects/locations logical?
4. Any jarring visual jumps?

Score the flow from 1-10 (10 = perfect continuity).
Respond in JSON: {{"flow_score": <int>, "notes": "<brief assessment>"}}
"""

        try:
            resp = requests.post(
                f"{self.ollama_host}/api/generate",
                json={
                    "model": self.vision_model,
                    "prompt": prompt,
                    "images": [img_a_b64, img_b_b64],
                    "stream": False,
                    "options": {"temperature": 0.2, "num_predict": 200},
                },
                timeout=120,
            )
            resp.raise_for_status()
            raw = resp.json().get("response", "")
            data = self._parse_json(raw)

            pair.vision_flow_score = float(data.get("flow_score", 7))
            pair.vision_notes = data.get("notes", "")

            if pair.vision_flow_score < 5:
                pair.visual_jump = True

        except Exception as e:
            logger.warning("Vision flow check failed: %s", e)

    # ─── Helpers ──────────────────────────────────────────────

    @staticmethod
    def _encode_image(path: str) -> str:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    @staticmethod
    def _parse_json(raw: str) -> dict:
        text = raw.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        return json.loads(text)
