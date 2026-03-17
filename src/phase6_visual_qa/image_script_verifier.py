"""
Phase 6A — Image-Script Verifier: Verify FLUX image matches script scene description.

Two-layer verification:
  Layer 1: Deterministic checks (OCR, aspect ratio, color, blur, NSFW, artifacts)
  Layer 2: Vision LLM rubric via Qwen 3.5-27B (5 primary axes:
           semantic_match, element_presence, composition, style_fit, cultural_accuracy)

Combined verdict: deterministic formula with hard-fail overrides.
"""

import base64
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import requests

logger = logging.getLogger(__name__)

OLLAMA_HOST = "http://localhost:11434"
VISION_MODEL = "qwen3.5:27b"

# ═══ Deterministic Thresholds ═══
BLUR_THRESHOLD = 100.0
NSFW_SKIN_THRESHOLD = 0.40
OCR_TEXT_MAX_CHARS = 20
ARTIFACT_THRESHOLD = 0.15
MIN_RESOLUTION = (512, 512)

# ═══ Scoring ═══
PASS_THRESHOLD = 7.0
REGEN_ADJUST_THRESHOLD = 4.0

# ═══ Rubric Weights (5 primary axes) ═══
RUBRIC_WEIGHTS = {
    "semantic_match": 0.25,
    "element_presence": 0.20,
    "composition": 0.15,
    "style_fit": 0.10,
    "cultural_accuracy": 0.10,
    "artifact_severity": 0.10,
    "emotion": 0.10,
}


@dataclass
class RubricScore:
    """Score for a single rubric axis."""
    score: int = 5
    reasoning: str = ""
    confidence: str = "medium"  # "high" | "medium" | "low"


@dataclass
class ImageVerification:
    """Full verification result for a single image against its script scene."""
    scene_index: int = 0

    # Deterministic layer
    text_detected: bool = False
    text_content: str = ""
    nsfw_score: float = 0.0
    blur_score: float = 0.0
    artifact_flags: list[str] = field(default_factory=list)
    file_valid: bool = True
    resolution_ok: bool = True

    # Vision rubric (7 axes)
    rubric: dict = field(default_factory=dict)  # axis → RubricScore

    # Combined
    weighted_score: float = 0.0
    hard_fail: Optional[str] = None
    verdict: str = "pass"  # "pass" | "regen_adjust" | "regen_new" | "fail" | "flag_human"
    flags: list[str] = field(default_factory=list)
    inference_ms: int = 0


class ImageScriptVerifier:
    """
    Verify that a FLUX-generated image matches its script scene description.
    Two-layer: deterministic checks + Vision LLM rubric.
    """

    def __init__(self, config: dict = None):
        self.config = config or {}
        self._ocr_reader = None

    def verify(
        self,
        image_path: str,
        scene_index: int,
        narration_text: str = "",
        visual_prompt: str = "",
        expected_elements: list[str] = None,
        style_description: str = "",
        scene_mood: str = "",
        region: str = "arabic",
    ) -> ImageVerification:
        """
        Full two-layer verification of an image against its script scene.

        Args:
            image_path: Path to the generated image.
            scene_index: Scene number in the video.
            narration_text: The narration text for this scene.
            visual_prompt: The prompt used to generate the image.
            expected_elements: List of elements that should be visible.
            style_description: Expected visual style.
            scene_mood: Expected emotional tone.
            region: Target audience region for cultural checks.

        Returns:
            ImageVerification with full results and verdict.
        """
        expected_elements = expected_elements or []
        result = ImageVerification(scene_index=scene_index)

        # ─── Layer 1: Deterministic Checks ───
        self._run_deterministic(result, image_path)

        # If hard fail on deterministic, skip vision
        if result.hard_fail:
            result.verdict = "fail"
            result.weighted_score = 0.0
            return result

        # ─── Layer 2: Vision LLM Rubric ───
        t0 = time.perf_counter_ns()
        rubric = self._run_vision_rubric(
            image_path, narration_text, visual_prompt,
            expected_elements, style_description, scene_mood, region,
        )
        result.inference_ms = (time.perf_counter_ns() - t0) // 1_000_000
        result.rubric = rubric

        # ─── Layer 3: Combined Verdict ───
        self._compute_verdict(result)

        return result

    # ═══════════════════════════════════════════════════════════════
    # LAYER 1: DETERMINISTIC CHECKS
    # ═══════════════════════════════════════════════════════════════

    def _run_deterministic(self, result: ImageVerification, image_path: str) -> None:
        """Run all deterministic checks, populating the result."""
        path = Path(image_path)

        # File integrity
        if not path.exists() or path.stat().st_size < 1024:
            result.file_valid = False
            result.hard_fail = "file_missing_or_corrupt"
            result.flags.append("file_invalid")
            return

        img = cv2.imread(str(path))
        if img is None:
            result.file_valid = False
            result.hard_fail = "unreadable_image"
            result.flags.append("unreadable")
            return

        h, w = img.shape[:2]

        # Resolution check
        if w < MIN_RESOLUTION[0] or h < MIN_RESOLUTION[1]:
            result.resolution_ok = False
            result.flags.append(f"low_resolution_{w}x{h}")

        # Blur detection (Laplacian variance)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        result.blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
        if result.blur_score < BLUR_THRESHOLD:
            result.flags.append(f"blurry_{result.blur_score:.1f}")

        # NSFW check (skin color ratio)
        result.nsfw_score = self._check_nsfw_ratio(img)
        if result.nsfw_score > NSFW_SKIN_THRESHOLD:
            result.flags.append("nsfw_flagged")

        # OCR text detection
        text = self._detect_text(img)
        result.text_content = text
        result.text_detected = len(text) > OCR_TEXT_MAX_CHARS
        if result.text_detected:
            result.hard_fail = "text_in_image"
            result.flags.append("text_detected")

        # AI artifact detection
        artifact_score = self._detect_artifacts(gray)
        if artifact_score > ARTIFACT_THRESHOLD:
            result.artifact_flags.append(f"high_frequency_artifacts_{artifact_score:.3f}")
            result.flags.append("ai_artifacts")

        # Black/white frame detection
        mean_val = np.mean(gray)
        if mean_val < 10:
            result.hard_fail = "black_frame"
            result.flags.append("black_frame")
        elif mean_val > 245:
            result.hard_fail = "white_frame"
            result.flags.append("white_frame")

    def _check_nsfw_ratio(self, img: np.ndarray) -> float:
        """Skin-color ratio heuristic for NSFW flagging."""
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        lower = np.array([0, 48, 80], dtype=np.uint8)
        upper = np.array([20, 255, 255], dtype=np.uint8)
        mask = cv2.inRange(hsv, lower, upper)
        return float(np.sum(mask > 0) / mask.size)

    def _detect_text(self, img: np.ndarray) -> str:
        """OCR text detection using easyocr."""
        try:
            if self._ocr_reader is None:
                import easyocr
                self._ocr_reader = easyocr.Reader(["ar", "en"], gpu=False, verbose=False)
            results = self._ocr_reader.readtext(img, detail=0)
            return " ".join(results).strip()
        except Exception as e:
            logger.debug(f"OCR failed (non-fatal): {e}")
            return ""

    def _detect_artifacts(self, gray: np.ndarray) -> float:
        """Detect AI generation artifacts via high-frequency analysis."""
        blur = cv2.GaussianBlur(gray, (21, 21), 0)
        highpass = cv2.absdiff(gray, blur)
        _, binary = cv2.threshold(highpass, 30, 255, cv2.THRESH_BINARY)
        return float(np.sum(binary > 0) / binary.size)

    # ═══════════════════════════════════════════════════════════════
    # LAYER 2: VISION LLM RUBRIC
    # ═══════════════════════════════════════════════════════════════

    def _run_vision_rubric(
        self,
        image_path: str,
        narration_text: str,
        visual_prompt: str,
        expected_elements: list[str],
        style_description: str,
        scene_mood: str,
        region: str,
    ) -> dict:
        """
        Send image to Qwen 3.5-27B via Ollama for structured rubric scoring.
        Returns dict of axis_name → {score, reasoning, confidence}.
        """
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()

        elements_str = ", ".join(expected_elements) if expected_elements else "none specified"

        prompt = f"""You are an expert visual QA reviewer for AI-generated documentary images.

Scene context:
- Narration: "{narration_text}"
- Visual prompt: "{visual_prompt}"
- Expected elements: {elements_str}
- Style: {style_description or "cinematic documentary"}
- Mood: {scene_mood or "neutral"}
- Target audience region: {region}

Score each axis 1-10 with brief reasoning and confidence (high/medium/low):

A. semantic_match: Does this image convey the MEANING of the narration? (conceptual fit, not literal)
B. element_presence: Which expected elements are visible? List each as present/absent/uncertain.
C. composition: Is the image well-composed for a documentary? (lighting, framing, depth)
D. style_fit: Does this look like a {style_description or 'cinematic'} documentary frame?
E. cultural_accuracy: Is this visually appropriate for {region} audience?
F. artifact_severity: Rate freedom from AI artifacts (10=clean, 1=severe). List specific artifacts.
G. emotion: Does the visual mood match "{scene_mood or 'neutral'}"?

Return JSON only:
{{
  "semantic_match": {{"score": 8, "reasoning": "...", "confidence": "high"}},
  "element_presence": {{"score": 7, "reasoning": "...", "confidence": "medium", "elements": {{"element1": "present"}}}},
  "composition": {{"score": 8, "reasoning": "...", "confidence": "high"}},
  "style_fit": {{"score": 7, "reasoning": "...", "confidence": "medium"}},
  "cultural_accuracy": {{"score": 9, "reasoning": "...", "confidence": "high"}},
  "artifact_severity": {{"score": 8, "reasoning": "...", "confidence": "high"}},
  "emotion": {{"score": 7, "reasoning": "...", "confidence": "medium"}}
}}"""

        try:
            resp = requests.post(
                f"{OLLAMA_HOST}/api/chat",
                json={
                    "model": VISION_MODEL,
                    "messages": [{"role": "user", "content": prompt, "images": [img_b64]}],
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.3, "num_predict": 2048},
                },
                timeout=120,
            )
            resp.raise_for_status()
            raw = resp.json()["message"]["content"]
            return self._parse_rubric(raw)
        except Exception as e:
            logger.error(f"Vision rubric failed: {e}")
            return {
                axis: {"score": 5, "reasoning": "Vision LLM unavailable", "confidence": "low"}
                for axis in RUBRIC_WEIGHTS
            }

    def _parse_rubric(self, raw: str) -> dict:
        """Parse JSON rubric from LLM response."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    data = json.loads(raw[start:end])
                except json.JSONDecodeError:
                    data = {}
            else:
                data = {}

        if not data:
            return {
                axis: {"score": 5, "reasoning": "Parse error", "confidence": "low"}
                for axis in RUBRIC_WEIGHTS
            }

        result = {}
        for axis in RUBRIC_WEIGHTS:
            entry = data.get(axis, {})
            score = entry.get("score", 5)
            score = max(1, min(10, int(score))) if isinstance(score, (int, float)) else 5
            confidence = str(entry.get("confidence", "medium")).lower()
            if confidence not in ("high", "medium", "low"):
                confidence = "medium"
            result[axis] = {
                "score": score,
                "reasoning": str(entry.get("reasoning", ""))[:200],
                "confidence": confidence,
            }
        return result

    # ═══════════════════════════════════════════════════════════════
    # LAYER 3: COMBINED VERDICT
    # ═══════════════════════════════════════════════════════════════

    def _compute_verdict(self, result: ImageVerification) -> None:
        """Compute weighted score and verdict from rubric + deterministic results."""
        rubric = result.rubric

        # Weighted score
        weighted = sum(
            rubric.get(axis, {}).get("score", 5) * weight
            for axis, weight in RUBRIC_WEIGHTS.items()
        )
        result.weighted_score = round(weighted, 2)

        # Deterministic penalties
        if result.text_detected:
            result.weighted_score = min(result.weighted_score, 3.0)
        if result.nsfw_score > NSFW_SKIN_THRESHOLD:
            result.weighted_score = min(result.weighted_score, 3.0)
        if result.blur_score < BLUR_THRESHOLD and result.blur_score > 0:
            result.weighted_score *= 0.8

        # Check for low-confidence axes → flag human
        low_confidence_axes = [
            axis for axis, scores in rubric.items()
            if scores.get("confidence") == "low"
        ]
        if low_confidence_axes:
            result.flags.append(f"low_confidence: {', '.join(low_confidence_axes)}")

        # Hard fail overrides
        if result.hard_fail:
            result.verdict = "fail"
            return

        if result.nsfw_score > NSFW_SKIN_THRESHOLD:
            result.verdict = "flag_human"
            result.hard_fail = "nsfw_detected"
            return

        if low_confidence_axes:
            result.verdict = "flag_human"
            return

        # Soft thresholds
        if result.weighted_score >= PASS_THRESHOLD:
            result.verdict = "pass"
        elif result.weighted_score >= REGEN_ADJUST_THRESHOLD:
            result.verdict = "regen_adjust"
        else:
            result.verdict = "regen_new"
