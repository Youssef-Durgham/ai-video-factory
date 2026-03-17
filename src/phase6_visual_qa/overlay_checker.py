"""
Phase 6C — Overlay Checker: Arabic text overlay QA.

Verifies that Arabic text overlays are:
  1. Readable (not too small, sufficient contrast)
  2. Positioned correctly (safe zones, no edge clipping)
  3. Not occluded by visual elements
  4. RTL rendered properly (no reversed characters)

Uses Vision LLM (Qwen 3.5-27B via Ollama) for semantic verification
and deterministic checks for technical validation.
"""

import base64
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import requests

logger = logging.getLogger(__name__)

OLLAMA_HOST = "http://localhost:11434"
VISION_MODEL = "qwen3.5:27b"

# ════════════════════════════════════════════════════════════════
# THRESHOLDS
# ════════════════════════════════════════════════════════════════

MIN_TEXT_HEIGHT_PX = 24            # Minimum readable text height at 1080p
SAFE_ZONE_MARGIN = 0.05           # 5% from edges = safe zone
MIN_CONTRAST_RATIO = 4.5          # WCAG AA standard
MAX_TEXT_AREA_RATIO = 0.30        # Text shouldn't cover >30% of frame


@dataclass
class OverlayCheckResult:
    """Result of overlay quality check for a single frame."""
    scene_index: int = 0
    readable: bool = True
    positioned_correctly: bool = True
    no_occlusion: bool = True
    rtl_correct: bool = True
    contrast_ratio: float = 0.0
    text_height_px: int = 0
    in_safe_zone: bool = True
    text_area_ratio: float = 0.0
    vision_assessment: dict = field(default_factory=dict)
    overall_score: float = 10.0
    verdict: str = "pass"           # pass | regen | flag_human
    details: dict = field(default_factory=dict)


@dataclass
class OverlayQAResult:
    """Aggregated overlay QA result for all scenes."""
    scene_results: list[OverlayCheckResult] = field(default_factory=list)
    overall_score: float = 10.0
    failed_scenes: list[int] = field(default_factory=list)
    verdict: str = "pass"


class OverlayChecker:
    """
    Verify Arabic text overlays are readable and properly rendered.

    Two-layer approach:
      1. Deterministic: contrast ratio, text size, safe zone, area ratio
      2. Vision LLM: semantic readability, occlusion, RTL correctness
    """

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.ollama_host = self.config.get("ollama_host", OLLAMA_HOST)
        self.vision_model = self.config.get("vision_model", VISION_MODEL)

    # ─── Public API ───────────────────────────────────────────

    def check_overlay(
        self,
        frame_path: str,
        overlay_text: str = "",
        scene_index: int = 0,
    ) -> OverlayCheckResult:
        """
        Check a single frame with text overlay.

        Args:
            frame_path: Path to the rendered frame (with overlay baked in).
            overlay_text: The expected Arabic text on the overlay.
            scene_index: Scene number for reporting.

        Returns:
            OverlayCheckResult with verdict.
        """
        result = OverlayCheckResult(scene_index=scene_index)

        try:
            img = cv2.imread(frame_path)
            if img is None:
                result.verdict = "regen"
                result.details["error"] = "Cannot read image"
                return result
        except Exception as e:
            result.verdict = "regen"
            result.details["error"] = str(e)
            return result

        # Layer 1: Deterministic checks
        self._check_text_region(img, result)
        self._check_safe_zone(img, result)

        # Layer 2: Vision LLM
        self._vision_check(frame_path, overlay_text, result)

        # Compute overall
        result.overall_score = self._compute_score(result)
        result.verdict = self._compute_verdict(result)
        return result

    def check_all_overlays(
        self,
        frames: list[dict],
    ) -> OverlayQAResult:
        """
        Check all scene overlay frames.

        Args:
            frames: List of {path, text, scene_index} dicts.

        Returns:
            Aggregated OverlayQAResult.
        """
        agg = OverlayQAResult()

        for f in frames:
            r = self.check_overlay(
                frame_path=f["path"],
                overlay_text=f.get("text", ""),
                scene_index=f.get("scene_index", 0),
            )
            agg.scene_results.append(r)
            if r.verdict != "pass":
                agg.failed_scenes.append(r.scene_index)

        if agg.scene_results:
            agg.overall_score = sum(
                r.overall_score for r in agg.scene_results
            ) / len(agg.scene_results)

        if agg.failed_scenes:
            agg.verdict = "flag_human"
        else:
            agg.verdict = "pass"

        return agg

    # ─── Layer 1: Deterministic ───────────────────────────────

    def _check_text_region(self, img: np.ndarray, result: OverlayCheckResult) -> None:
        """
        Detect text region via edge/contrast analysis and check size + contrast.
        """
        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Find high-contrast regions (likely text)
        edges = cv2.Canny(gray, 100, 200)
        # Bottom third is typical overlay zone
        bottom_third = edges[int(h * 0.6):, :]
        text_pixels = np.sum(bottom_third > 0)
        total_pixels = bottom_third.size

        result.text_area_ratio = text_pixels / max(total_pixels, 1)

        # Estimate text height from connected components in bottom region
        contours, _ = cv2.findContours(
            bottom_third, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE,
        )
        if contours:
            heights = [cv2.boundingRect(c)[3] for c in contours if cv2.boundingRect(c)[3] > 5]
            if heights:
                result.text_height_px = int(np.median(heights))
                result.readable = result.text_height_px >= MIN_TEXT_HEIGHT_PX

        # Contrast: compare text region luminance vs background
        bottom_gray = gray[int(h * 0.75):, :]
        if bottom_gray.size > 0:
            mean_bright = float(np.mean(bottom_gray))
            std_bright = float(np.std(bottom_gray))
            # Higher std = more contrast (text vs background)
            result.contrast_ratio = std_bright / max(mean_bright, 1) * 21.0
            if result.contrast_ratio < MIN_CONTRAST_RATIO:
                result.readable = False

    def _check_safe_zone(self, img: np.ndarray, result: OverlayCheckResult) -> None:
        """Check that text content is within safe zone margins."""
        h, w = img.shape[:2]
        margin_x = int(w * SAFE_ZONE_MARGIN)
        margin_y = int(h * SAFE_ZONE_MARGIN)

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 100, 200)

        # Check edges for text near borders
        top = np.sum(edges[:margin_y, :] > 0)
        bottom = np.sum(edges[h - margin_y:, :] > 0)
        left = np.sum(edges[:, :margin_x] > 0)
        right = np.sum(edges[:, w - margin_x:] > 0)

        # If significant edge content near borders → out of safe zone
        threshold = margin_x * margin_y * 0.1
        if any(v > threshold for v in [top, left, right]):
            result.in_safe_zone = False
            result.positioned_correctly = False

    # ─── Layer 2: Vision LLM ─────────────────────────────────

    def _vision_check(
        self,
        frame_path: str,
        overlay_text: str,
        result: OverlayCheckResult,
    ) -> None:
        """Use Vision LLM to verify overlay readability and correctness."""
        try:
            img_b64 = self._encode_image(frame_path)
        except Exception as e:
            logger.warning("Cannot encode image for vision check: %s", e)
            return

        prompt = f"""Analyze this video frame with Arabic text overlay.

Expected text: "{overlay_text}"

Check and score (1-10) each:
1. readability: Is the Arabic text clearly readable? Good size and contrast?
2. positioning: Is the text well-positioned? Not clipped by edges?
3. occlusion: Is the text occluded by any visual elements?
4. rtl_correctness: Is the Arabic text rendered correctly (right-to-left, proper shaping)?
5. overall_quality: Overall overlay quality.

Respond in JSON only:
{{"readability": <int>, "positioning": <int>, "occlusion": <int>, "rtl_correctness": <int>, "overall_quality": <int>, "issues": ["<issue1>", ...]}}
"""

        try:
            resp = requests.post(
                f"{self.ollama_host}/api/generate",
                json={
                    "model": self.vision_model,
                    "prompt": prompt,
                    "images": [img_b64],
                    "stream": False,
                    "options": {"temperature": 0.2, "num_predict": 300},
                },
                timeout=120,
            )
            resp.raise_for_status()
            raw = resp.json().get("response", "")
            data = self._parse_json(raw)

            result.vision_assessment = data

            if data.get("readability", 10) < 5:
                result.readable = False
            if data.get("positioning", 10) < 5:
                result.positioned_correctly = False
            if data.get("occlusion", 10) < 5:
                result.no_occlusion = False
            if data.get("rtl_correctness", 10) < 5:
                result.rtl_correct = False

        except Exception as e:
            logger.warning("Vision overlay check failed: %s", e)

    # ─── Helpers ──────────────────────────────────────────────

    @staticmethod
    def _encode_image(path: str) -> str:
        """Read and base64-encode an image file."""
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    @staticmethod
    def _parse_json(raw: str) -> dict:
        """Extract JSON from LLM response."""
        text = raw.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        return json.loads(text)

    @staticmethod
    def _compute_score(r: OverlayCheckResult) -> float:
        """Compute overall score from check results."""
        score = 10.0
        if not r.readable:
            score -= 3.0
        if not r.positioned_correctly:
            score -= 2.0
        if not r.no_occlusion:
            score -= 2.0
        if not r.rtl_correct:
            score -= 3.0
        if not r.in_safe_zone:
            score -= 1.0

        # Vision assessment bonus/penalty
        va = r.vision_assessment
        if va:
            vision_avg = sum(
                va.get(k, 7) for k in
                ["readability", "positioning", "occlusion", "rtl_correctness"]
            ) / 4.0
            score = (score + vision_avg) / 2.0

        return max(0.0, min(10.0, score))

    @staticmethod
    def _compute_verdict(r: OverlayCheckResult) -> str:
        if r.overall_score >= 7.0:
            return "pass"
        elif r.overall_score >= 4.0:
            return "flag_human"
        else:
            return "regen"
