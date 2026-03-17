"""
Phase 6A — Image QA: Two-layer image verification.
Layer 1: Deterministic checks (OCR, blur, NSFW, artifacts, integrity)
Layer 2: Vision LLM rubric (7 axes via Qwen 3.5-27B / Ollama)
Layer 3: Combined scoring with hard-fail overrides
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

# ═══ Thresholds ═══
BLUR_THRESHOLD = 100.0          # Laplacian variance below this = blurry
ARTIFACT_THRESHOLD = 0.15       # Fraction of high-frequency anomaly pixels
NSFW_SKIN_THRESHOLD = 0.40      # Skin pixel ratio above this = flag
OCR_TEXT_MAX_CHARS = 20         # More than this = "text in image" fail
PASS_SCORE = 7.0
HARD_FAIL_SCORE = 0.0

# ═══ Rubric axis weights ═══
RUBRIC_WEIGHTS = {
    "semantic_match":     0.25,
    "element_presence":   0.20,
    "composition":        0.10,
    "style_fit":          0.10,
    "artifact_severity":  0.15,
    "cultural":           0.10,
    "emotion":            0.10,
}


@dataclass
class DeterministicResult:
    passed: bool = True
    hard_fail: Optional[str] = None
    blur_score: float = 0.0
    has_text: bool = False
    text_detected: str = ""
    nsfw_flag: bool = False
    artifact_score: float = 0.0
    file_valid: bool = True
    details: dict = field(default_factory=dict)


@dataclass
class ImageQAResult:
    scene_index: int
    score: float
    verdict: str           # "pass" | "regen" | "flag_human"
    deterministic: DeterministicResult = field(default_factory=DeterministicResult)
    rubric_scores: dict = field(default_factory=dict)
    hard_fail: Optional[str] = None
    inference_ms: int = 0


class ImageChecker:
    """Two-layer image QA: deterministic + vision LLM rubric."""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self._ocr_reader = None

    # ─── Public API ───────────────────────────────────────────

    def check_image(
        self,
        image_path: str,
        scene_index: int,
        visual_prompt: str = "",
        expected_elements: list[str] = None,
        style_description: str = "",
        scene_mood: str = "",
    ) -> ImageQAResult:
        """
        Full two-layer check on a single image.
        Returns ImageQAResult with combined score.
        """
        expected_elements = expected_elements or []

        # Layer 1: Deterministic
        det = self._deterministic_checks(image_path)

        # If hard fail, skip vision LLM
        if det.hard_fail:
            return ImageQAResult(
                scene_index=scene_index,
                score=HARD_FAIL_SCORE,
                verdict="regen",
                deterministic=det,
                hard_fail=det.hard_fail,
            )

        # Layer 2: Vision LLM rubric
        t0 = time.perf_counter_ns()
        rubric = self._vision_rubric(
            image_path, visual_prompt, expected_elements,
            style_description, scene_mood,
        )
        inference_ms = (time.perf_counter_ns() - t0) // 1_000_000

        # Layer 3: Combined score
        weighted = sum(
            rubric.get(axis, {}).get("score", 5) * weight
            for axis, weight in RUBRIC_WEIGHTS.items()
        )
        # Scale to 0-10
        final_score = round(weighted, 2)

        # Deterministic penalties
        if det.has_text:
            final_score = min(final_score, 6.0)
        if det.blur_score < BLUR_THRESHOLD:
            final_score *= 0.8
        if det.nsfw_flag:
            final_score = min(final_score, 3.0)

        verdict = "pass" if final_score >= PASS_SCORE else "regen"
        if det.nsfw_flag:
            verdict = "flag_human"

        return ImageQAResult(
            scene_index=scene_index,
            score=final_score,
            verdict=verdict,
            deterministic=det,
            rubric_scores=rubric,
            hard_fail=None,
            inference_ms=inference_ms,
        )

    # ─── Layer 1: Deterministic ──────────────────────────────

    def _deterministic_checks(self, image_path: str) -> DeterministicResult:
        result = DeterministicResult()

        # File integrity
        path = Path(image_path)
        if not path.exists() or path.stat().st_size < 1024:
            result.passed = False
            result.file_valid = False
            result.hard_fail = "file_missing_or_corrupt"
            return result

        # Load image
        img = cv2.imread(str(path))
        if img is None:
            result.passed = False
            result.file_valid = False
            result.hard_fail = "unreadable_image"
            return result

        # Blur detection (Laplacian variance)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        result.blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
        if result.blur_score < BLUR_THRESHOLD:
            result.details["blur"] = f"Laplacian variance {result.blur_score:.1f} < {BLUR_THRESHOLD}"

        # NSFW check (skin color ratio heuristic)
        result.nsfw_flag = self._check_nsfw(img)

        # OCR text detection
        text = self._detect_text(img)
        result.text_detected = text
        result.has_text = len(text) > OCR_TEXT_MAX_CHARS

        # AI artifact detection (high-frequency anomalies)
        result.artifact_score = self._detect_artifacts(gray)
        if result.artifact_score > ARTIFACT_THRESHOLD:
            result.details["artifacts"] = f"Artifact score {result.artifact_score:.3f}"

        result.passed = result.hard_fail is None
        return result

    def _check_nsfw(self, img: np.ndarray) -> bool:
        """Skin-color ratio heuristic for NSFW flagging."""
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        # Skin tone range in HSV
        lower = np.array([0, 48, 80], dtype=np.uint8)
        upper = np.array([20, 255, 255], dtype=np.uint8)
        mask = cv2.inRange(hsv, lower, upper)
        ratio = np.sum(mask > 0) / mask.size
        return ratio > NSFW_SKIN_THRESHOLD

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
        # Apply high-pass filter
        blur = cv2.GaussianBlur(gray, (21, 21), 0)
        highpass = cv2.absdiff(gray, blur)
        # Look for anomalous patterns (repeated textures, grid artifacts)
        _, binary = cv2.threshold(highpass, 30, 255, cv2.THRESH_BINARY)
        return np.sum(binary > 0) / binary.size

    # ─── Layer 2: Vision LLM Rubric ─────────────────────────

    def _vision_rubric(
        self,
        image_path: str,
        visual_prompt: str,
        expected_elements: list[str],
        style_description: str,
        scene_mood: str,
    ) -> dict:
        """
        Send image to Qwen 3.5-27B via Ollama vision API.
        Returns dict of 7 axes, each with score/reasoning/confidence.
        """
        # Encode image to base64
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()

        elements_str = ", ".join(expected_elements) if expected_elements else "none specified"

        prompt = f"""You are an expert visual QA reviewer for AI-generated documentary images.

Evaluate this image against the production brief:
- Visual prompt: "{visual_prompt}"
- Expected elements: {elements_str}
- Style: {style_description or "cinematic documentary"}
- Scene mood: {scene_mood or "neutral"}

Score each axis 1-10 with brief reasoning and confidence (0.0-1.0):

1. semantic_match: Does the image match the visual prompt's intent?
2. element_presence: Are all expected elements visible?
3. composition: Is the framing, rule of thirds, visual balance good?
4. style_fit: Does the visual style match the requested style?
5. artifact_severity: Rate freedom from AI artifacts (10=clean, 1=severe artifacts)
6. cultural: Is the image culturally appropriate for Arabic/Middle Eastern audience?
7. emotion: Does the image convey the intended mood?

Return JSON only:
{{
  "semantic_match": {{"score": 8, "reasoning": "...", "confidence": 0.9}},
  "element_presence": {{"score": 7, "reasoning": "...", "confidence": 0.8}},
  ...
}}"""

        try:
            resp = requests.post(
                f"{OLLAMA_HOST}/api/chat",
                json={
                    "model": VISION_MODEL,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt,
                            "images": [img_b64],
                        }
                    ],
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
            # Fallback: neutral scores
            return {
                axis: {"score": 5, "reasoning": "Vision LLM unavailable", "confidence": 0.0}
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
                data = json.loads(raw[start:end])
            else:
                return {
                    axis: {"score": 5, "reasoning": "Parse error", "confidence": 0.0}
                    for axis in RUBRIC_WEIGHTS
                }

        # Validate and normalize
        result = {}
        for axis in RUBRIC_WEIGHTS:
            entry = data.get(axis, {})
            score = entry.get("score", 5)
            score = max(1, min(10, int(score))) if isinstance(score, (int, float)) else 5
            result[axis] = {
                "score": score,
                "reasoning": str(entry.get("reasoning", ""))[:200],
                "confidence": max(0.0, min(1.0, float(entry.get("confidence", 0.5)))),
            }
        return result
