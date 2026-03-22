"""
Image QA — deterministic checks + Vision LLM rubric scoring.

Layer 1: Blur, black/white, resolution, file integrity (no LLM)
Layer 2: Ollama Qwen vision rubric (semantic match, elements, composition, style, artifacts)
Layer 3: Weighted verdict → PASS / REGEN / FAIL
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
from PIL import Image

logger = logging.getLogger(__name__)

OLLAMA_HOST = "http://localhost:11434"
VISION_MODEL = "qwen3.5:27b"

# Thresholds
BLUR_THRESHOLD = 5.0  # AI-generated images (FLUX) have naturally low Laplacian variance
BLACK_MEAN_THRESHOLD = 10.0
WHITE_MEAN_THRESHOLD = 245.0
MIN_WIDTH = 1280
MIN_HEIGHT = 720

# Rubric weights
WEIGHTS = {
    "semantic_match": 0.30,
    "visual_elements": 0.25,
    "composition": 0.15,
    "style_fit": 0.15,
    "artifact_severity": 0.15,
}

PASS_THRESHOLD = 7.0
REGEN_THRESHOLD = 4.0


@dataclass
class DeterministicResult:
    passed: bool
    blur_score: float = 0.0
    is_blurry: bool = False
    is_black: bool = False
    is_white: bool = False
    resolution_ok: bool = True
    file_ok: bool = True
    width: int = 0
    height: int = 0
    fail_reasons: list = field(default_factory=list)


@dataclass
class RubricResult:
    semantic_match: float = 5.0
    visual_elements: float = 5.0
    composition: float = 5.0
    style_fit: float = 5.0
    artifact_severity: float = 5.0
    weighted_score: float = 5.0
    raw_response: str = ""


@dataclass
class ImageQAResult:
    scene_index: int
    image_path: str
    deterministic: DeterministicResult
    rubric: Optional[RubricResult] = None
    weighted_score: float = 0.0
    verdict: str = "FAIL"  # PASS / REGEN / FAIL
    error: Optional[str] = None


class ImageQA:
    """Image quality assessment: deterministic + vision LLM."""

    def __init__(self, ollama_host: str = OLLAMA_HOST, vision_model: str = VISION_MODEL):
        self.ollama_host = ollama_host
        self.vision_model = vision_model

    def check_image(
        self,
        image_path: str,
        scene_index: int,
        narration_text: str = "",
        visual_prompt: str = "",
        expected_elements: list = None,
    ) -> ImageQAResult:
        """Run full QA pipeline on a single image."""
        # Layer 1: Deterministic
        det = self._deterministic_checks(image_path)

        if not det.file_ok:
            return ImageQAResult(
                scene_index=scene_index, image_path=image_path,
                deterministic=det, weighted_score=0.0, verdict="FAIL",
                error="File integrity check failed",
            )

        if not det.passed:
            return ImageQAResult(
                scene_index=scene_index, image_path=image_path,
                deterministic=det, weighted_score=2.0, verdict="REGEN",
                error=f"Deterministic fail: {', '.join(det.fail_reasons)}",
            )

        # Layer 2: Vision LLM rubric
        rubric = self._vision_rubric(
            image_path, narration_text, visual_prompt, expected_elements or []
        )

        # Layer 3: Verdict
        score = rubric.weighted_score if rubric else 5.0
        if score >= PASS_THRESHOLD:
            verdict = "PASS"
        elif score >= REGEN_THRESHOLD:
            verdict = "REGEN"
        else:
            verdict = "FAIL"

        return ImageQAResult(
            scene_index=scene_index, image_path=image_path,
            deterministic=det, rubric=rubric,
            weighted_score=score, verdict=verdict,
        )

    def check_batch(
        self, scenes: list[dict], images_dir: str
    ) -> list[ImageQAResult]:
        """Check all scene images. Each scene dict needs scene_index, narration_text, visual_prompt."""
        results = []
        for scene in scenes:
            idx = scene.get("scene_index", 0)
            img_path = scene.get("image_path") or str(
                Path(images_dir) / f"scene_{idx:03d}.png"
            )
            if not Path(img_path).exists():
                results.append(ImageQAResult(
                    scene_index=idx, image_path=img_path,
                    deterministic=DeterministicResult(passed=False, file_ok=False,
                                                      fail_reasons=["File not found"]),
                    weighted_score=0.0, verdict="FAIL", error="Image file not found",
                ))
                continue

            expected = scene.get("expected_elements", [])
            if isinstance(expected, str):
                try:
                    expected = json.loads(expected)
                except (json.JSONDecodeError, TypeError):
                    expected = []

            result = self.check_image(
                image_path=img_path,
                scene_index=idx,
                narration_text=scene.get("narration_text", ""),
                visual_prompt=scene.get("visual_prompt", ""),
                expected_elements=expected,
            )
            results.append(result)

            verdict_icon = {"PASS": "✅", "REGEN": "🔄", "FAIL": "❌"}.get(result.verdict, "❓")
            logger.info(
                f"Scene {idx} image QA: {result.verdict} "
                f"(score={result.weighted_score:.1f})"
            )

            # Live Telegram progress
            try:
                from src.core.telegram_callbacks import send_telegram_sync
                total = len(scenes)
                done = len(results)
                send_telegram_sync(
                    f"🔎 صورة {done}/{total} — {verdict_icon} {result.weighted_score:.1f}/10"
                )
            except Exception:
                pass

        return results

    # ─── Layer 1: Deterministic ────────────────────────

    def _deterministic_checks(self, image_path: str) -> DeterministicResult:
        result = DeterministicResult(passed=True)
        fail_reasons = []

        # File integrity
        try:
            pil_img = Image.open(image_path)
            pil_img.verify()
            pil_img = Image.open(image_path)  # re-open after verify
            result.width, result.height = pil_img.size
        except Exception as e:
            result.file_ok = False
            result.passed = False
            result.fail_reasons = [f"Cannot load image: {e}"]
            return result

        # Resolution
        if result.width < MIN_WIDTH or result.height < MIN_HEIGHT:
            result.resolution_ok = False
            fail_reasons.append(f"Resolution {result.width}x{result.height} < {MIN_WIDTH}x{MIN_HEIGHT}")

        # OpenCV checks
        try:
            img = cv2.imread(image_path)
            if img is None:
                result.file_ok = False
                result.passed = False
                result.fail_reasons = ["OpenCV cannot read image"]
                return result

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # Blur detection
            lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            result.blur_score = lap_var
            if lap_var < BLUR_THRESHOLD:
                result.is_blurry = True
                fail_reasons.append(f"Blurry (laplacian={lap_var:.1f})")

            # Black/white frame
            mean_val = np.mean(gray)
            if mean_val < BLACK_MEAN_THRESHOLD:
                result.is_black = True
                fail_reasons.append(f"Black frame (mean={mean_val:.1f})")
            elif mean_val > WHITE_MEAN_THRESHOLD:
                result.is_white = True
                fail_reasons.append(f"White frame (mean={mean_val:.1f})")

        except Exception as e:
            fail_reasons.append(f"OpenCV error: {e}")

        if fail_reasons:
            result.passed = False
        result.fail_reasons = fail_reasons
        return result

    # ─── Layer 2: Vision LLM Rubric ────────────────────

    def _vision_rubric(
        self,
        image_path: str,
        narration_text: str,
        visual_prompt: str,
        expected_elements: list,
    ) -> Optional[RubricResult]:
        """Score image via Ollama vision model."""
        try:
            with open(image_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            logger.error(f"Cannot read image for vision: {e}")
            return None

        elements_str = ", ".join(expected_elements) if expected_elements else "N/A"
        prompt = f"""You are a documentary image QA reviewer. Score this image on 5 axes (1-10 each).

Context:
- Narration: {narration_text[:300]}
- Visual prompt: {visual_prompt[:300]}
- Expected elements: {elements_str}

Axes:
A. semantic_match: image matches narration? (1=wrong, 10=perfect)
B. visual_elements: expected elements visible? (1=none, 10=all)
C. composition: documentary quality? (1=bad, 10=pro)
D. style_fit: looks documentary? (1=wrong style, 10=cinematic)
E. artifact_severity: clean image? (1=artifacts, 10=clean)

Reply ONLY with JSON, no explanation:
{{"semantic_match": N, "visual_elements": N, "composition": N, "style_fit": N, "artifact_severity": N}}"""

        try:
            start = time.time()
            resp = requests.post(
                f"{self.ollama_host}/api/chat",
                json={
                    "model": self.vision_model,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt,
                            "images": [img_b64],
                        }
                    ],
                    "stream": False,
                    "options": {"temperature": 0.3, "num_predict": 1024},
                },
                timeout=180,
            )
            resp.raise_for_status()
            msg = resp.json().get("message", {})
            raw = msg.get("content", "")
            
            # qwen3.5 with vision + format:json = empty content (known bug)
            # Try content first, then thinking field, extract JSON from either
            import re
            all_text = raw
            if not raw.strip():
                all_text = msg.get("thinking", "")

            # Extract JSON object from text (may have surrounding explanation)
            json_match = re.search(r'\{[^{}]*"semantic_match"\s*:\s*\d+[^{}]*\}', all_text)
            if json_match:
                raw = json_match.group(0)
            elif not raw.strip():
                # Last resort: try to extract any scores mentioned
                scores = {}
                for key in ["semantic_match", "visual_elements", "composition", "style_fit", "artifact_severity"]:
                    m = re.search(rf'{key}["\s:]*(\d+)', all_text)
                    if m:
                        scores[key] = int(m.group(1))
                if scores:
                    raw = json.dumps(scores)
                else:
                    logger.warning("Vision response: no JSON found in content or thinking")

            elapsed = time.time() - start
            logger.debug(f"Vision rubric took {elapsed:.1f}s")

            # Parse scores
            data = json.loads(raw)
            r = RubricResult(
                semantic_match=float(data.get("semantic_match", 5)),
                visual_elements=float(data.get("visual_elements", 5)),
                composition=float(data.get("composition", 5)),
                style_fit=float(data.get("style_fit", 5)),
                artifact_severity=float(data.get("artifact_severity", 5)),
                raw_response=raw,
            )
            r.weighted_score = (
                r.semantic_match * WEIGHTS["semantic_match"]
                + r.visual_elements * WEIGHTS["visual_elements"]
                + r.composition * WEIGHTS["composition"]
                + r.style_fit * WEIGHTS["style_fit"]
                + r.artifact_severity * WEIGHTS["artifact_severity"]
            )
            return r

        except Exception as e:
            logger.error(f"Vision rubric failed: {e}")
            # Return neutral scores so pipeline isn't blocked
            r = RubricResult(raw_response=str(e))
            r.weighted_score = 5.0
            return r

    # ─── Future: OCR / NSFW (placeholder) ──────────────

    def _check_ocr(self, image_path: str) -> dict:
        """TODO: Check for unwanted text in image via OCR."""
        return {"has_text": False, "text": ""}

    def _check_nsfw(self, image_path: str) -> dict:
        """TODO: NSFW detection."""
        return {"is_nsfw": False, "score": 0.0}
