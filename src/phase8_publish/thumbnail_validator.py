"""
Phase 8 — Thumbnail Validator: 3-layer QA for thumbnails.

Layer 1: Deterministic — resolution, file size, face detection, mobile readability, dead zones
Layer 2: Vision rubric — click_appeal, relevance, mobile_readability, emotion, professionalism, differentiation
Layer 3: Ranking — weighted score, rank all 3 variants
"""

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ThumbnailScore:
    variant: str
    file_path: str
    # Layer 1 — deterministic
    resolution_ok: bool = True
    file_size_ok: bool = True
    face_detected: bool = False
    face_area_pct: float = 0.0
    mobile_readable: bool = True
    dead_zone_clear: bool = True
    deterministic_pass: bool = True
    hard_fail_reason: Optional[str] = None
    # Layer 2 — vision rubric
    click_appeal: float = 5.0
    relevance: float = 5.0
    mobile_readability: float = 5.0
    emotion: float = 5.0
    professionalism: float = 5.0
    differentiation: float = 5.0
    rubric_reasoning: dict = field(default_factory=dict)
    # Layer 3 — combined
    weighted_score: float = 0.0
    rank: int = 0


class ThumbnailValidator:
    """3-layer thumbnail QA matching the rigor of scene image verification."""

    # Weights for Layer 3 ranking
    WEIGHTS = {
        "click_appeal": 0.30,
        "relevance": 0.20,
        "mobile_readability": 0.20,
        "emotion": 0.15,
        "professionalism": 0.10,
        "differentiation": 0.05,
    }

    YOUTUBE_THUMB_WIDTH = 1280
    YOUTUBE_THUMB_HEIGHT = 720
    MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024  # 2MB YouTube limit

    def __init__(self, config: dict, db):
        self.config = config
        self.db = db
        self.ollama_host = config["settings"]["ollama"]["host"]
        self.vision_model = config["settings"]["ollama"]["models"].get("vision", "qwen3.5:27b")

    def validate_thumbnails(self, job_id: str) -> list[ThumbnailScore]:
        """
        Validate all thumbnail variants for a job.
        Returns scored and ranked list of ThumbnailScore objects.
        """
        rows = self.db.conn.execute(
            "SELECT * FROM thumbnails WHERE job_id = ? ORDER BY variant",
            (job_id,)
        ).fetchall()

        if not rows:
            logger.warning(f"No thumbnails found for {job_id}")
            return []

        job = self.db.get_job(job_id)
        seo_row = self.db.conn.execute(
            "SELECT selected_title FROM seo_data WHERE job_id = ? ORDER BY id DESC LIMIT 1",
            (job_id,)
        ).fetchone()
        title = dict(seo_row)["selected_title"] if seo_row else (job.get("topic") or "")

        scores: list[ThumbnailScore] = []
        for row in rows:
            thumb = dict(row)
            score = ThumbnailScore(
                variant=thumb["variant"],
                file_path=thumb["file_path"],
            )

            # Layer 1: Deterministic checks
            self._check_deterministic(score)

            # Layer 2: Vision rubric (skip if hard fail)
            if score.deterministic_pass:
                self._check_vision_rubric(score, title, job.get("topic", ""))

            # Layer 3: Calculate weighted score
            score.weighted_score = self._calculate_weighted_score(score)

            scores.append(score)

        # Rank by weighted score
        scores.sort(key=lambda s: s.weighted_score, reverse=True)
        for i, s in enumerate(scores):
            s.rank = i + 1

        # Save rubrics to DB
        for s in scores:
            self._save_rubric(job_id, s)

        # Update thumbnails table with scores
        for s in scores:
            self.db.conn.execute(
                "UPDATE thumbnails SET readability_score = ?, youtube_ui_overlap = ? "
                "WHERE job_id = ? AND variant = ?",
                (s.weighted_score, not s.dead_zone_clear, job_id, s.variant)
            )
        self.db.conn.commit()

        return scores

    # ─── Layer 1: Deterministic Checks ─────────────────────

    def _check_deterministic(self, score: ThumbnailScore):
        """Hard rule checks — no LLM needed."""
        path = score.file_path
        if not path or not os.path.exists(path):
            score.deterministic_pass = False
            score.hard_fail_reason = "File not found"
            return

        # Resolution check
        try:
            from PIL import Image
            img = Image.open(path)
            w, h = img.size
            score.resolution_ok = (w == self.YOUTUBE_THUMB_WIDTH and h == self.YOUTUBE_THUMB_HEIGHT)
            if not score.resolution_ok:
                # Allow close matches (within 10%)
                if abs(w - self.YOUTUBE_THUMB_WIDTH) > 128 or abs(h - self.YOUTUBE_THUMB_HEIGHT) > 72:
                    score.hard_fail_reason = f"Bad resolution: {w}x{h}"
                    score.deterministic_pass = False
                    return
        except Exception as e:
            score.hard_fail_reason = f"Cannot open image: {e}"
            score.deterministic_pass = False
            return

        # File size check
        file_size = os.path.getsize(path)
        score.file_size_ok = file_size <= self.MAX_FILE_SIZE_BYTES

        # Face detection (optional, best effort)
        try:
            self._detect_face(score, img)
        except Exception:
            pass  # Face detection is supplementary

        # Mobile readability simulation
        try:
            self._check_mobile_readability(score, img)
        except Exception:
            pass

        # YouTube dead zone check (bottom-right: duration badge)
        try:
            self._check_dead_zones(score, img)
        except Exception:
            pass

    def _detect_face(self, score: ThumbnailScore, img):
        """Detect faces using OpenCV Haar cascade (lightweight)."""
        try:
            import cv2
            import numpy as np
            arr = np.array(img.convert("RGB"))
            gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
            face_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            )
            faces = face_cascade.detectMultiScale(gray, 1.1, 4)
            if len(faces) > 0:
                score.face_detected = True
                # Largest face area as % of image
                max_area = max(w * h for (x, y, w, h) in faces)
                total_area = img.width * img.height
                score.face_area_pct = (max_area / total_area) * 100
        except ImportError:
            pass

    def _check_mobile_readability(self, score: ThumbnailScore, img):
        """Downscale to mobile thumbnail size (168x94) and check OCR readability."""
        mobile = img.resize((168, 94))
        # Simple contrast check on downscaled version
        import numpy as np
        arr = np.array(mobile.convert("L"))
        contrast = arr.std()
        score.mobile_readable = contrast > 30  # Minimum contrast threshold

    def _check_dead_zones(self, score: ThumbnailScore, img):
        """Check bottom-right corner for important content (YouTube duration badge)."""
        import numpy as np
        arr = np.array(img.convert("RGB"))
        h, w = arr.shape[:2]
        # Dead zone: bottom-right 15% width, 15% height
        dead_zone = arr[int(h * 0.85):, int(w * 0.85):]
        # Check if this region has high contrast (text/important content)
        std = dead_zone.std()
        score.dead_zone_clear = std < 60  # Low variance = no important content there

    # ─── Layer 2: Vision Rubric ────────────────────────────

    def _check_vision_rubric(self, score: ThumbnailScore, title: str, topic: str):
        """Use Qwen vision model to score thumbnail on 6 axes."""
        import base64

        try:
            with open(score.file_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode()
        except Exception as e:
            logger.error(f"Cannot read thumbnail for vision check: {e}")
            return

        prompt = f"""You are a YouTube thumbnail expert. Analyze this thumbnail for an Arabic documentary video.

Video title: "{title}"
Topic: "{topic}"

Score each axis from 1-10 with brief reasoning:

A. Click Appeal: Would viewers click this? Curiosity gap, emotional hook, visual intrigue.
B. Relevance: Does thumbnail match the title/topic? Misleading = bad.
C. Mobile Readability: At phone screen size, is everything clear?
D. Emotional Impact: What emotion does this evoke? Does it match the topic?
E. Professionalism: Does it look professionally made? Not cluttered?
F. Differentiation: Would this stand out among similar documentary videos?

Return JSON only:
{{"click_appeal": {{"score": N, "reason": "..."}}, "relevance": {{"score": N, "reason": "..."}}, "mobile_readability": {{"score": N, "reason": "..."}}, "emotion": {{"score": N, "reason": "..."}}, "professionalism": {{"score": N, "reason": "..."}}, "differentiation": {{"score": N, "reason": "..."}}}}"""

        try:
            resp = requests.post(
                f"{self.ollama_host}/api/generate",
                json={
                    "model": self.vision_model,
                    "prompt": prompt,
                    "images": [img_b64],
                    "stream": False,
                    "options": {"temperature": 0.3, "num_predict": 500},
                },
                timeout=120,
            )
            resp.raise_for_status()
            text = resp.json().get("response", "")

            # Parse JSON from response
            import re
            json_match = re.search(r"\{.*\}", text, re.DOTALL)
            if json_match:
                rubric = json.loads(json_match.group())
                for axis in ["click_appeal", "relevance", "mobile_readability",
                             "emotion", "professionalism", "differentiation"]:
                    if axis in rubric:
                        val = rubric[axis]
                        s = val.get("score", 5) if isinstance(val, dict) else val
                        setattr(score, axis, float(s))
                        if isinstance(val, dict):
                            score.rubric_reasoning[axis] = val.get("reason", "")

        except Exception as e:
            logger.warning(f"Vision rubric check failed: {e}")
            # Leave default scores (5.0)

    # ─── Layer 3: Weighted Score + Ranking ─────────────────

    def _calculate_weighted_score(self, score: ThumbnailScore) -> float:
        """Calculate final weighted score from vision rubric axes."""
        if not score.deterministic_pass:
            return 0.0

        total = 0.0
        for axis, weight in self.WEIGHTS.items():
            total += getattr(score, axis, 5.0) * weight
        return round(total, 2)

    # ─── Save to DB ────────────────────────────────────────

    def _save_rubric(self, job_id: str, score: ThumbnailScore):
        """Save thumbnail QA rubric to qa_rubrics table."""
        deterministic = {
            "resolution_ok": score.resolution_ok,
            "file_size_ok": score.file_size_ok,
            "face_detected": score.face_detected,
            "face_area_pct": score.face_area_pct,
            "mobile_readable": score.mobile_readable,
            "dead_zone_clear": score.dead_zone_clear,
        }
        rubric_scores = {
            axis: {"score": getattr(score, axis), "reasoning": score.rubric_reasoning.get(axis, "")}
            for axis in self.WEIGHTS
        }

        verdict = "pass" if score.weighted_score >= 6.0 else "regen_new"
        if score.hard_fail_reason:
            verdict = "fail"

        self.db.save_rubric(
            job_id=job_id,
            scene_index=None,
            asset_type="thumbnail",
            check_phase="phase8",
            attempt=1,
            deterministic=deterministic,
            rubric_scores=rubric_scores,
            weighted_score=score.weighted_score,
            verdict=verdict,
            flags=[],
            hard_fail=score.hard_fail_reason,
            model=self.vision_model,
        )


import requests  # noqa: E402 — needed for vision rubric
