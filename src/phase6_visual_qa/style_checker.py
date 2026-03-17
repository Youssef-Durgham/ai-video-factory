"""
Phase 6A — Style Consistency Checker.
Two-layer: deterministic (OpenCV histograms) + Vision LLM batch check.
Ensures all scene images share a coherent visual identity.
"""

import base64
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import requests

logger = logging.getLogger(__name__)

OLLAMA_HOST = "http://localhost:11434"
VISION_MODEL = "qwen3.5:27b"

OUTLIER_STD_THRESHOLD = 2.0
HISTOGRAM_SIMILARITY_THRESHOLD = 0.5   # correlation below this = outlier
BRIGHTNESS_STD_MAX = 40.0              # max std dev in mean brightness


@dataclass
class StyleResult:
    consistent: bool = True
    overall_score: float = 10.0
    outlier_indices: list = field(default_factory=list)
    histogram_similarities: list = field(default_factory=list)
    brightness_stats: dict = field(default_factory=dict)
    vision_assessment: dict = field(default_factory=dict)
    details: list = field(default_factory=list)


class StyleChecker:
    """Check visual style consistency across all scene images."""

    def __init__(self, config: dict = None):
        self.config = config or {}

    def check_style_consistency(
        self,
        image_paths: list[str],
        style_description: str = "",
    ) -> StyleResult:
        """
        Full style consistency check on a batch of images.
        """
        if len(image_paths) < 2:
            return StyleResult(consistent=True, overall_score=10.0)

        result = StyleResult()

        # Layer 1: Deterministic
        self._deterministic_style(image_paths, result)

        # Layer 2: Vision LLM
        self._vision_style_check(image_paths, style_description, result)

        # Combined score
        det_score = 10.0
        if result.outlier_indices:
            det_score -= len(result.outlier_indices) * 1.5
        det_score = max(0, det_score)

        vision_score = result.vision_assessment.get("consistency_score", 7.0)
        result.overall_score = round(det_score * 0.4 + vision_score * 0.6, 2)
        result.consistent = result.overall_score >= 7.0

        return result

    # ─── Layer 1: Deterministic ──────────────────────────────

    def _deterministic_style(self, image_paths: list[str], result: StyleResult):
        """OpenCV histogram comparison, brightness/contrast analysis."""
        histograms = []
        brightnesses = []
        contrasts = []

        for path in image_paths:
            img = cv2.imread(path)
            if img is None:
                continue

            # Color histogram (HSV)
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            hist = cv2.calcHist([hsv], [0, 1], None, [50, 60], [0, 180, 0, 256])
            cv2.normalize(hist, hist)
            histograms.append(hist)

            # Brightness and contrast
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            brightnesses.append(float(np.mean(gray)))
            contrasts.append(float(np.std(gray)))

        if len(histograms) < 2:
            return

        # Pairwise histogram correlation (compare each to mean histogram)
        mean_hist = np.mean(histograms, axis=0)
        similarities = []
        for i, hist in enumerate(histograms):
            sim = cv2.compareHist(hist, mean_hist.astype(np.float32), cv2.HISTCMP_CORREL)
            similarities.append(round(sim, 3))
        result.histogram_similarities = similarities

        # Outlier detection (>2 std dev from mean similarity)
        sim_arr = np.array(similarities)
        mean_sim = np.mean(sim_arr)
        std_sim = np.std(sim_arr)
        if std_sim > 0:
            for i, s in enumerate(similarities):
                if abs(s - mean_sim) > OUTLIER_STD_THRESHOLD * std_sim:
                    result.outlier_indices.append(i)
                    result.details.append(f"Scene {i}: histogram outlier (corr={s:.3f})")

        # Low absolute similarity
        for i, s in enumerate(similarities):
            if s < HISTOGRAM_SIMILARITY_THRESHOLD and i not in result.outlier_indices:
                result.outlier_indices.append(i)
                result.details.append(f"Scene {i}: low histogram similarity ({s:.3f})")

        # Brightness consistency
        bright_arr = np.array(brightnesses)
        result.brightness_stats = {
            "mean": round(float(np.mean(bright_arr)), 1),
            "std": round(float(np.std(bright_arr)), 1),
            "min": round(float(np.min(bright_arr)), 1),
            "max": round(float(np.max(bright_arr)), 1),
        }
        if np.std(bright_arr) > BRIGHTNESS_STD_MAX:
            result.details.append(
                f"Brightness inconsistent: std={np.std(bright_arr):.1f} > {BRIGHTNESS_STD_MAX}"
            )

    # ─── Layer 2: Vision LLM ────────────────────────────────

    def _vision_style_check(
        self,
        image_paths: list[str],
        style_description: str,
        result: StyleResult,
    ):
        """Send all images to vision LLM for style consistency assessment."""
        # Encode images (limit to 8 to stay within context)
        paths = image_paths[:8]
        images_b64 = []
        for p in paths:
            try:
                with open(p, "rb") as f:
                    images_b64.append(base64.b64encode(f.read()).decode())
            except Exception:
                continue

        if len(images_b64) < 2:
            return

        prompt = f"""You are a visual consistency reviewer for documentary video production.

You are given {len(images_b64)} sequential scene images from one video.
Target style: {style_description or "cinematic documentary, consistent color grading"}

Evaluate:
1. Color palette consistency (do all images share a cohesive palette?)
2. Lighting consistency (similar brightness/contrast feel?)
3. Art style consistency (same rendering style throughout?)
4. Any scene that visually "breaks" from the rest?

Return JSON:
{{
  "consistency_score": 8,
  "color_consistency": "good/mixed/poor",
  "lighting_consistency": "good/mixed/poor",
  "style_consistency": "good/mixed/poor",
  "outlier_scenes": [3, 5],
  "reasoning": "brief explanation"
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
                            "images": images_b64,
                        }
                    ],
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.3, "num_predict": 1024},
                },
                timeout=180,
            )
            resp.raise_for_status()
            raw = resp.json()["message"]["content"]
            data = json.loads(raw) if isinstance(raw, str) else raw
            result.vision_assessment = data

            # Merge vision outliers
            for idx in data.get("outlier_scenes", []):
                if isinstance(idx, int) and idx not in result.outlier_indices:
                    result.outlier_indices.append(idx)

        except Exception as e:
            logger.error(f"Vision style check failed: {e}")
            result.vision_assessment = {"consistency_score": 7.0, "error": str(e)}
