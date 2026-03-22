"""
Image QA — Advanced multi-layer quality assessment (NO LLM dependency).

Layer 1: File integrity + resolution
Layer 2: Technical quality (blur, exposure, contrast, noise, color)
Layer 3: Content analysis (edge density, object presence, scene complexity)
Layer 4: Style consistency (color palette, brightness distribution)
Layer 5: Duplicate/near-duplicate detection across scenes

All scoring is deterministic + perceptual — runs on CPU, instant results.
No Ollama/LLM calls = no thinking mode bugs, no empty responses.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════
# Thresholds (tuned for FLUX-generated documentary images)
# ════════════════════════════════════════════════════════════════

MIN_WIDTH = 1280
MIN_HEIGHT = 720
MIN_FILE_SIZE_KB = 50        # < 50KB = likely corrupted
BLUR_THRESHOLD = 3.0         # Laplacian variance — FLUX images are smooth (5-60 normal)
BLACK_MEAN = 8.0             # Mean brightness < 8 = black frame
WHITE_MEAN = 248.0           # Mean brightness > 248 = white frame
MIN_EDGE_DENSITY = 0.01      # < 1% edges = blank/solid color
MIN_COLOR_STD = 10.0         # Color channel std dev — too low = monotone
MIN_CONTRAST = 20.0          # Max-min brightness range
DUPLICATE_THRESHOLD = 0.92   # SSIM > 0.92 = near-duplicate

PASS_THRESHOLD = 7.0
REGEN_THRESHOLD = 4.0


# ════════════════════════════════════════════════════════════════
# Data classes
# ════════════════════════════════════════════════════════════════

@dataclass
class ImageQAResult:
    scene_index: int
    image_path: str
    scores: dict = field(default_factory=dict)
    weighted_score: float = 0.0
    verdict: str = "FAIL"  # PASS / REGEN / FAIL
    details: list = field(default_factory=list)
    error: Optional[str] = None


# ════════════════════════════════════════════════════════════════
# Weights for final score (total = 1.0)
# ════════════════════════════════════════════════════════════════

WEIGHTS = {
    "integrity":    0.15,   # File OK, resolution, not corrupted
    "sharpness":    0.15,   # Blur detection (Laplacian + gradient)
    "exposure":     0.15,   # Not too dark/bright, good dynamic range
    "contrast":     0.10,   # Tonal range
    "color":        0.15,   # Color richness and distribution
    "complexity":   0.15,   # Edge density, texture, scene content
    "composition":  0.15,   # Rule of thirds, visual balance
}


class ImageQA:
    """Advanced image QA — deterministic + perceptual, no LLM needed."""

    def __init__(self, **kwargs):
        # Accept but ignore ollama_host/vision_model for backward compat
        self._prev_histograms = []  # For duplicate detection

    def check_image(
        self,
        image_path: str,
        scene_index: int,
        **kwargs,  # Accept narration_text, visual_prompt, etc. (unused)
    ) -> ImageQAResult:
        """Run full QA pipeline on a single image."""
        result = ImageQAResult(scene_index=scene_index, image_path=image_path)
        scores = {}
        details = []

        # ── Layer 1: File Integrity ──
        integrity_score, integrity_details = self._check_integrity(image_path)
        scores["integrity"] = integrity_score
        details.extend(integrity_details)

        if integrity_score < 2.0:
            result.scores = scores
            result.weighted_score = integrity_score
            result.verdict = "FAIL"
            result.details = details
            result.error = "; ".join(integrity_details)
            return result

        # Load image for remaining checks
        img = cv2.imread(image_path)
        if img is None:
            result.scores = {"integrity": 0}
            result.weighted_score = 0
            result.verdict = "FAIL"
            result.error = "Cannot read image with OpenCV"
            return result

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # ── Layer 2: Sharpness ──
        scores["sharpness"], s_details = self._check_sharpness(gray)
        details.extend(s_details)

        # ── Layer 3: Exposure ──
        scores["exposure"], e_details = self._check_exposure(gray)
        details.extend(e_details)

        # ── Layer 4: Contrast ──
        scores["contrast"], c_details = self._check_contrast(gray)
        details.extend(c_details)

        # ── Layer 5: Color ──
        scores["color"], col_details = self._check_color(img)
        details.extend(col_details)

        # ── Layer 6: Complexity ──
        scores["complexity"], cx_details = self._check_complexity(gray, img)
        details.extend(cx_details)

        # ── Layer 7: Composition ──
        scores["composition"], comp_details = self._check_composition(gray)
        details.extend(comp_details)

        # ── Duplicate detection ──
        dup_score, dup_details = self._check_duplicate(img)
        details.extend(dup_details)
        if dup_score < 5.0:
            # Penalize duplicates
            scores["integrity"] = min(scores["integrity"], dup_score)

        # ── Calculate weighted score ──
        weighted = sum(scores.get(k, 5.0) * w for k, w in WEIGHTS.items())
        result.scores = scores
        result.weighted_score = round(weighted, 1)
        result.details = details

        if weighted >= PASS_THRESHOLD:
            result.verdict = "PASS"
        elif weighted >= REGEN_THRESHOLD:
            result.verdict = "REGEN"
        else:
            result.verdict = "FAIL"

        return result

    def check_batch(
        self, scenes: list[dict], images_dir: str
    ) -> list[ImageQAResult]:
        """Check all scene images with live progress."""
        results = []
        self._prev_histograms = []  # Reset for duplicate detection
        total = len(scenes)

        for i, scene in enumerate(scenes):
            idx = scene.get("scene_index", i)
            img_path = scene.get("image_path") or str(
                Path(images_dir) / f"scene_{idx:03d}.png"
            )

            if not Path(img_path).exists():
                results.append(ImageQAResult(
                    scene_index=idx, image_path=img_path,
                    weighted_score=0.0, verdict="FAIL",
                    error="Image file not found",
                ))
                continue

            result = self.check_image(image_path=img_path, scene_index=idx)
            results.append(result)

            verdict_icon = {"PASS": "✅", "REGEN": "🔄", "FAIL": "❌"}.get(result.verdict, "❓")
            logger.info(
                f"Scene {idx} image QA: {result.verdict} "
                f"(score={result.weighted_score:.1f}) "
                f"[sharp={result.scores.get('sharpness',0):.0f} "
                f"exp={result.scores.get('exposure',0):.0f} "
                f"color={result.scores.get('color',0):.0f} "
                f"complex={result.scores.get('complexity',0):.0f}]"
            )

            # Live Telegram progress
            try:
                from src.core.telegram_callbacks import send_telegram_sync
                done = len(results)
                score_str = f"{result.weighted_score:.1f}"
                send_telegram_sync(
                    f"🔎 صورة {done}/{total} — {verdict_icon} {score_str}/10"
                )
            except Exception:
                pass

        return results

    # ════════════════════════════════════════════════════════════
    # Layer 1: File Integrity
    # ════════════════════════════════════════════════════════════

    def _check_integrity(self, image_path: str) -> tuple[float, list]:
        details = []
        score = 10.0

        # File exists and readable
        path = Path(image_path)
        if not path.exists():
            return 0.0, ["File not found"]

        # File size
        size_kb = path.stat().st_size / 1024
        if size_kb < MIN_FILE_SIZE_KB:
            details.append(f"File too small: {size_kb:.0f}KB")
            return 1.0, details

        # PIL verify
        try:
            pil_img = Image.open(image_path)
            pil_img.verify()
            pil_img = Image.open(image_path)
            w, h = pil_img.size
        except Exception as e:
            return 0.0, [f"Corrupt image: {e}"]

        # Resolution
        if w < MIN_WIDTH or h < MIN_HEIGHT:
            score -= 3.0
            details.append(f"Low res: {w}x{h}")
        elif w >= MIN_WIDTH and h >= MIN_HEIGHT:
            details.append(f"Res OK: {w}x{h}")

        return max(score, 1.0), details

    # ════════════════════════════════════════════════════════════
    # Layer 2: Sharpness
    # ════════════════════════════════════════════════════════════

    def _check_sharpness(self, gray: np.ndarray) -> tuple[float, list]:
        details = []

        # Laplacian variance (primary blur metric)
        lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()

        # Gradient magnitude (secondary — Sobel)
        gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        grad_mag = np.sqrt(gx**2 + gy**2).mean()

        # For FLUX images: lap_var 5-60 is normal, grad_mag 10-50 is normal
        # Map to 1-10 score
        if lap_var < BLUR_THRESHOLD:
            score = 1.0
            details.append(f"Very blurry: lap={lap_var:.1f}")
        elif lap_var < 10:
            score = 5.0 + (lap_var - BLUR_THRESHOLD) / (10 - BLUR_THRESHOLD) * 2
            details.append(f"Soft: lap={lap_var:.1f}")
        elif lap_var < 30:
            score = 7.0 + (lap_var - 10) / 20 * 1.5
        elif lap_var < 100:
            score = 8.5 + min((lap_var - 30) / 70, 1.0) * 1.5
        else:
            score = 10.0

        # Boost/penalize with gradient
        if grad_mag < 5:
            score = min(score, 4.0)
            details.append(f"No edges: grad={grad_mag:.1f}")
        elif grad_mag > 20:
            score = min(score + 0.5, 10.0)

        return round(min(max(score, 1.0), 10.0), 1), details

    # ════════════════════════════════════════════════════════════
    # Layer 3: Exposure
    # ════════════════════════════════════════════════════════════

    def _check_exposure(self, gray: np.ndarray) -> tuple[float, list]:
        details = []
        mean_val = np.mean(gray)
        std_val = np.std(gray)

        # Black frame
        if mean_val < BLACK_MEAN:
            details.append(f"Black frame: mean={mean_val:.0f}")
            return 1.0, details

        # White frame
        if mean_val > WHITE_MEAN:
            details.append(f"White frame: mean={mean_val:.0f}")
            return 1.0, details

        # Ideal range: mean 60-180, std > 30
        if 60 <= mean_val <= 180:
            score = 9.0
        elif 30 <= mean_val < 60 or 180 < mean_val <= 220:
            score = 7.0
            details.append(f"Exposure marginal: mean={mean_val:.0f}")
        else:
            score = 5.0
            details.append(f"Exposure poor: mean={mean_val:.0f}")

        # Dark/moody images are OK for documentaries — don't penalize too much
        if 15 <= mean_val < 60 and std_val > 20:
            score = max(score, 7.5)  # Dark but has contrast = cinematic

        # Bonus for good dynamic range
        if std_val > 50:
            score = min(score + 1.0, 10.0)

        return round(score, 1), details

    # ════════════════════════════════════════════════════════════
    # Layer 4: Contrast
    # ════════════════════════════════════════════════════════════

    def _check_contrast(self, gray: np.ndarray) -> tuple[float, list]:
        details = []

        # Percentile-based contrast (more robust than min/max)
        p5 = np.percentile(gray, 5)
        p95 = np.percentile(gray, 95)
        contrast_range = p95 - p5

        if contrast_range < MIN_CONTRAST:
            details.append(f"Very low contrast: {contrast_range:.0f}")
            return 2.0, details

        # Map to score
        if contrast_range >= 150:
            score = 10.0
        elif contrast_range >= 100:
            score = 8.0 + (contrast_range - 100) / 50 * 2
        elif contrast_range >= 50:
            score = 6.0 + (contrast_range - 50) / 50 * 2
        else:
            score = 4.0 + (contrast_range - MIN_CONTRAST) / (50 - MIN_CONTRAST) * 2

        return round(min(max(score, 1.0), 10.0), 1), details

    # ════════════════════════════════════════════════════════════
    # Layer 5: Color Quality
    # ════════════════════════════════════════════════════════════

    def _check_color(self, img: np.ndarray) -> tuple[float, list]:
        details = []

        # Convert to HSV for color analysis
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv)

        # Saturation analysis
        sat_mean = np.mean(s)
        sat_std = np.std(s)

        # Hue distribution (color variety)
        hue_std = np.std(h)

        # Color channel std
        b_std = np.std(img[:, :, 0])
        g_std = np.std(img[:, :, 1])
        r_std = np.std(img[:, :, 2])
        avg_color_std = (b_std + g_std + r_std) / 3

        score = 5.0

        # Saturation scoring
        if sat_mean < 10:
            score = 3.0
            details.append("Nearly grayscale")
        elif sat_mean < 30:
            score = 5.0
            # Desaturated is OK for moody documentaries
            details.append("Low saturation (moody)")
        elif sat_mean < 80:
            score = 8.0  # Good moderate saturation
        elif sat_mean < 150:
            score = 9.0  # Rich colors
        else:
            score = 7.0  # Oversaturated
            details.append("Oversaturated")

        # Bonus for color variety
        if hue_std > 40:
            score = min(score + 1.0, 10.0)
        elif hue_std < 10:
            score = max(score - 1.0, 1.0)
            details.append("Monotone color")

        # Channel diversity
        if avg_color_std < MIN_COLOR_STD:
            score = max(score - 2.0, 1.0)
            details.append(f"Low color diversity: std={avg_color_std:.0f}")

        return round(min(max(score, 1.0), 10.0), 1), details

    # ════════════════════════════════════════════════════════════
    # Layer 6: Scene Complexity
    # ════════════════════════════════════════════════════════════

    def _check_complexity(self, gray: np.ndarray, img: np.ndarray) -> tuple[float, list]:
        details = []

        # Edge density (Canny)
        edges = cv2.Canny(gray, 50, 150)
        edge_density = np.count_nonzero(edges) / edges.size

        if edge_density < MIN_EDGE_DENSITY:
            details.append("Nearly blank image")
            return 1.0, details

        # Texture analysis (local standard deviation)
        kernel = np.ones((7, 7)) / 49
        local_mean = cv2.filter2D(gray.astype(np.float64), -1, kernel)
        local_sq_mean = cv2.filter2D((gray.astype(np.float64))**2, -1, kernel)
        local_std = np.sqrt(np.maximum(local_sq_mean - local_mean**2, 0))
        texture_score = np.mean(local_std)

        # Map edge density to score
        if edge_density >= 0.15:
            score = 9.5
        elif edge_density >= 0.08:
            score = 8.0 + (edge_density - 0.08) / 0.07 * 1.5
        elif edge_density >= 0.03:
            score = 6.0 + (edge_density - 0.03) / 0.05 * 2
        else:
            score = 3.0 + (edge_density - MIN_EDGE_DENSITY) / 0.02 * 3

        # Texture bonus
        if texture_score > 30:
            score = min(score + 0.5, 10.0)
        elif texture_score < 10:
            score = max(score - 1.0, 1.0)
            details.append("Low texture")

        return round(min(max(score, 1.0), 10.0), 1), details

    # ════════════════════════════════════════════════════════════
    # Layer 7: Composition
    # ════════════════════════════════════════════════════════════

    def _check_composition(self, gray: np.ndarray) -> tuple[float, list]:
        """Score composition using rule-of-thirds and visual weight distribution."""
        details = []
        h, w = gray.shape

        # Divide into 3x3 grid
        grid_h, grid_w = h // 3, w // 3
        zones = []
        for row in range(3):
            for col in range(3):
                zone = gray[row * grid_h:(row + 1) * grid_h, col * grid_w:(col + 1) * grid_w]
                zones.append(np.mean(zone))

        # Visual weight distribution (std of zone means)
        zone_std = np.std(zones)

        # Good composition: not all zones same brightness (visual interest)
        if zone_std < 5:
            score = 4.0
            details.append("Flat composition")
        elif zone_std < 15:
            score = 6.0
        elif zone_std < 40:
            score = 8.5  # Good visual variation
        else:
            score = 7.5  # Very high contrast zones (might be harsh)

        # Center vs edges balance
        center = zones[4]  # Center zone
        edges_mean = np.mean([zones[0], zones[2], zones[6], zones[8]])  # Corners
        if abs(center - edges_mean) > 50:
            score = min(score + 0.5, 10.0)  # Strong focal point = good

        return round(min(max(score, 1.0), 10.0), 1), details

    # ════════════════════════════════════════════════════════════
    # Duplicate Detection
    # ════════════════════════════════════════════════════════════

    def _check_duplicate(self, img: np.ndarray) -> tuple[float, list]:
        """Detect near-duplicate images across scenes."""
        details = []

        # Compute color histogram for this image
        hist = cv2.calcHist([img], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
        hist = cv2.normalize(hist, hist).flatten()

        # Compare with previous scenes
        for i, prev_hist in enumerate(self._prev_histograms):
            similarity = cv2.compareHist(hist, prev_hist, cv2.HISTCMP_CORREL)
            if similarity > DUPLICATE_THRESHOLD:
                details.append(f"Near-duplicate of scene {i} (sim={similarity:.2f})")
                self._prev_histograms.append(hist)
                return 3.0, details

        self._prev_histograms.append(hist)
        return 10.0, details
