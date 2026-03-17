"""
Phase 6B — Video-Script Verifier: Verify LTX video clips against script.

Method: Extract 5 keyframes → deterministic checks + vision rubric.

Layer 1: Deterministic (optical flow, SSIM, OCR, black frames, duration, FPS)
Layer 2: Vision LLM rubric via Qwen 3.5-27B (5 axes:
         motion_plausibility, script_match, temporal_coherence,
         artifact_severity, source_fidelity)
Layer 3: Combined verdict with fallback logic:
         pass / regen_video / regen_image / ken_burns / flag_human
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

from src.phase6_visual_qa.video_keyframe_extractor import VideoKeyframeExtractor
from src.phase6_visual_qa.keyframe_extractor import get_video_info

logger = logging.getLogger(__name__)

OLLAMA_HOST = "http://localhost:11434"
VISION_MODEL = "qwen3.5:27b"

# ═══ Deterministic Thresholds ═══
SSIM_GLITCH_THRESHOLD = 0.3       # SSIM drop > this between adjacent frames = glitch
FROZEN_FLOW_THRESHOLD = 0.5       # Optical flow magnitude below this = frozen
FLOW_SPIKE_THRESHOLD = 50.0       # Flow magnitude above this = sudden jump
OCR_TEXT_MAX_CHARS = 20
BLACK_FRAME_THRESHOLD = 10
WHITE_FRAME_THRESHOLD = 245
FROZEN_FRAME_RATIO_FAIL = 0.30    # >30% frozen frames = fail

# ═══ Rubric Weights ═══
VIDEO_RUBRIC_WEIGHTS = {
    "motion_plausibility": 0.25,
    "script_match": 0.25,
    "temporal_coherence": 0.20,
    "artifact_severity": 0.20,
    "source_fidelity": 0.10,
}

PASS_THRESHOLD = 7.0


@dataclass
class VideoVerification:
    """Full verification result for a video clip against its script scene."""
    scene_index: int = 0

    # Deterministic
    text_detected: bool = False
    frozen_frames: int = 0
    total_frames_checked: int = 0
    ssim_glitches: int = 0
    optical_flow_anomalies: list[str] = field(default_factory=list)
    black_frames: int = 0
    duration_ok: bool = True
    fps_ok: bool = True

    # Vision rubric (5 axes)
    rubric: dict = field(default_factory=dict)

    # Combined
    weighted_score: float = 0.0
    hard_fail: Optional[str] = None
    verdict: str = "pass"  # "pass"|"regen_video"|"regen_image"|"ken_burns"|"flag_human"
    fallback_reason: str = ""
    flags: list[str] = field(default_factory=list)
    inference_ms: int = 0


class VideoScriptVerifier:
    """
    Verify LTX-generated video clips against their script scene descriptions.
    Two-layer: deterministic video checks + Vision LLM rubric on keyframes.
    """

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.keyframe_extractor = VideoKeyframeExtractor()
        self._ocr_reader = None

    def verify(
        self,
        video_path: str,
        scene_index: int,
        narration_text: str = "",
        motion_prompt: str = "",
        expected_duration_sec: float = 0,
        expected_fps: float = 24.0,
        retry_count: int = 0,
    ) -> VideoVerification:
        """
        Full two-layer verification of a video clip against its script.

        Args:
            video_path: Path to the LTX-generated video clip.
            scene_index: Scene number in the video.
            narration_text: Scene narration text.
            motion_prompt: The motion description used for LTX generation.
            expected_duration_sec: Expected clip duration.
            expected_fps: Expected frame rate.
            retry_count: Number of previous regeneration attempts.

        Returns:
            VideoVerification with verdict and fallback recommendation.
        """
        result = VideoVerification(scene_index=scene_index)

        # Validate file exists
        if not Path(video_path).exists():
            result.hard_fail = "video_file_missing"
            result.verdict = "regen_video"
            result.flags.append("file_missing")
            return result

        # Extract keyframes
        try:
            keyframe_paths = self.keyframe_extractor.extract(video_path, count=5)
        except Exception as e:
            logger.error(f"Keyframe extraction failed: {e}")
            result.hard_fail = "keyframe_extraction_failed"
            result.verdict = "regen_video"
            return result

        if not keyframe_paths:
            result.hard_fail = "no_keyframes_extracted"
            result.verdict = "regen_video"
            return result

        # Get video info
        info = get_video_info(video_path)

        # ─── Layer 1: Deterministic Checks ───
        self._run_deterministic(result, keyframe_paths, info, expected_duration_sec, expected_fps)

        if result.hard_fail:
            self._determine_fallback(result, retry_count)
            return result

        # ─── Layer 2: Vision LLM Rubric ───
        t0 = time.perf_counter_ns()
        rubric = self._run_vision_rubric(keyframe_paths, narration_text, motion_prompt)
        result.inference_ms = (time.perf_counter_ns() - t0) // 1_000_000
        result.rubric = rubric

        # ─── Layer 3: Combined Verdict ───
        self._compute_verdict(result, retry_count)

        # Cleanup temp keyframes
        for kf in keyframe_paths:
            try:
                Path(kf).unlink(missing_ok=True)
            except Exception:
                pass

        return result

    # ═══════════════════════════════════════════════════════════════
    # LAYER 1: DETERMINISTIC VIDEO CHECKS
    # ═══════════════════════════════════════════════════════════════

    def _run_deterministic(
        self,
        result: VideoVerification,
        keyframe_paths: list[str],
        video_info: dict,
        expected_duration: float,
        expected_fps: float,
    ) -> None:
        """Run deterministic checks on keyframes and video metadata."""
        frames = []
        for kf_path in keyframe_paths:
            img = cv2.imread(kf_path)
            if img is not None:
                frames.append(img)

        result.total_frames_checked = len(frames)
        if not frames:
            result.hard_fail = "no_readable_frames"
            return

        # Duration check
        actual_duration = video_info.get("duration", 0)
        if expected_duration > 0 and actual_duration > 0:
            drift = abs(actual_duration - expected_duration)
            if drift > expected_duration * 0.5:
                result.duration_ok = False
                result.flags.append(f"duration_drift_{drift:.1f}s")

        # FPS check
        actual_fps = video_info.get("fps", 0)
        if actual_fps > 0 and expected_fps > 0:
            if abs(actual_fps - expected_fps) > 5:
                result.fps_ok = False
                result.flags.append(f"fps_mismatch_{actual_fps:.0f}")

        # Frame-by-frame checks
        prev_gray = None
        for i, frame in enumerate(frames):
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # Black/white frame detection
            mean_val = np.mean(gray)
            if mean_val < BLACK_FRAME_THRESHOLD:
                result.black_frames += 1
                result.flags.append(f"black_frame_{i}")
            elif mean_val > WHITE_FRAME_THRESHOLD:
                result.flags.append(f"white_frame_{i}")

            # OCR text detection
            text = self._detect_text(frame)
            if len(text) > OCR_TEXT_MAX_CHARS:
                result.text_detected = True
                result.flags.append(f"text_in_frame_{i}")

            # Inter-frame checks
            if prev_gray is not None:
                # SSIM between adjacent keyframes
                ssim_val = self._compute_ssim(prev_gray, gray)
                if ssim_val < (1.0 - SSIM_GLITCH_THRESHOLD):
                    result.ssim_glitches += 1
                    result.flags.append(f"ssim_glitch_{i}_{ssim_val:.2f}")

                # Optical flow
                flow_mag = self._compute_optical_flow(prev_gray, gray)
                if flow_mag < FROZEN_FLOW_THRESHOLD:
                    result.frozen_frames += 1
                elif flow_mag > FLOW_SPIKE_THRESHOLD:
                    result.optical_flow_anomalies.append(f"flow_spike_{i}_{flow_mag:.1f}")

            prev_gray = gray

        # Hard fail conditions
        if result.text_detected:
            result.hard_fail = "text_in_video"
        elif result.total_frames_checked > 0:
            frozen_ratio = result.frozen_frames / result.total_frames_checked
            if frozen_ratio > FROZEN_FRAME_RATIO_FAIL:
                result.hard_fail = f"frozen_frames_{frozen_ratio:.0%}"
        if result.ssim_glitches > 2:
            result.hard_fail = f"ssim_glitches_{result.ssim_glitches}"

    def _detect_text(self, img: np.ndarray) -> str:
        """OCR text detection."""
        try:
            if self._ocr_reader is None:
                import easyocr
                self._ocr_reader = easyocr.Reader(["ar", "en"], gpu=False, verbose=False)
            results = self._ocr_reader.readtext(img, detail=0)
            return " ".join(results).strip()
        except Exception:
            return ""

    def _compute_ssim(self, gray_a: np.ndarray, gray_b: np.ndarray) -> float:
        """Compute structural similarity between two grayscale frames."""
        # Resize to match if needed
        if gray_a.shape != gray_b.shape:
            h = min(gray_a.shape[0], gray_b.shape[0])
            w = min(gray_a.shape[1], gray_b.shape[1])
            gray_a = cv2.resize(gray_a, (w, h))
            gray_b = cv2.resize(gray_b, (w, h))

        c1 = (0.01 * 255) ** 2
        c2 = (0.03 * 255) ** 2

        mu_a = cv2.GaussianBlur(gray_a.astype(np.float64), (11, 11), 1.5)
        mu_b = cv2.GaussianBlur(gray_b.astype(np.float64), (11, 11), 1.5)

        mu_a_sq = mu_a ** 2
        mu_b_sq = mu_b ** 2
        mu_ab = mu_a * mu_b

        sigma_a_sq = cv2.GaussianBlur(gray_a.astype(np.float64) ** 2, (11, 11), 1.5) - mu_a_sq
        sigma_b_sq = cv2.GaussianBlur(gray_b.astype(np.float64) ** 2, (11, 11), 1.5) - mu_b_sq
        sigma_ab = cv2.GaussianBlur(
            gray_a.astype(np.float64) * gray_b.astype(np.float64), (11, 11), 1.5
        ) - mu_ab

        ssim_map = ((2 * mu_ab + c1) * (2 * sigma_ab + c2)) / (
            (mu_a_sq + mu_b_sq + c1) * (sigma_a_sq + sigma_b_sq + c2)
        )
        return float(np.mean(ssim_map))

    def _compute_optical_flow(self, gray_a: np.ndarray, gray_b: np.ndarray) -> float:
        """Compute average optical flow magnitude between two frames."""
        if gray_a.shape != gray_b.shape:
            h = min(gray_a.shape[0], gray_b.shape[0])
            w = min(gray_a.shape[1], gray_b.shape[1])
            gray_a = cv2.resize(gray_a, (w, h))
            gray_b = cv2.resize(gray_b, (w, h))

        flow = cv2.calcOpticalFlowFarneback(
            gray_a, gray_b, None,
            pyr_scale=0.5, levels=3, winsize=15,
            iterations=3, poly_n=5, poly_sigma=1.2, flags=0,
        )
        magnitude, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
        return float(np.mean(magnitude))

    # ═══════════════════════════════════════════════════════════════
    # LAYER 2: VISION LLM RUBRIC
    # ═══════════════════════════════════════════════════════════════

    def _run_vision_rubric(
        self,
        keyframe_paths: list[str],
        narration_text: str,
        motion_prompt: str,
    ) -> dict:
        """Send keyframes to Qwen 3.5-27B for structured rubric scoring."""
        images_b64 = []
        for kf_path in keyframe_paths:
            try:
                with open(kf_path, "rb") as f:
                    images_b64.append(base64.b64encode(f.read()).decode())
            except Exception:
                continue

        if not images_b64:
            return {
                axis: {"score": 5, "reasoning": "No keyframes available", "confidence": "low"}
                for axis in VIDEO_RUBRIC_WEIGHTS
            }

        prompt = f"""You are an expert video QA reviewer for AI-generated documentary clips.

These are {len(images_b64)} keyframes extracted in chronological order from a video clip.

Context:
- Narration: "{narration_text}"
- Motion prompt: "{motion_prompt}"

Score each axis 1-10 with brief reasoning and confidence (high/medium/low):

A. motion_plausibility: Do the keyframes show believable motion? Smooth progression, no teleporting.
B. script_match: Does the motion match "{motion_prompt}"? Do keyframes show this type of movement?
C. temporal_coherence: Logical time progression? No objects appearing/disappearing between frames.
D. artifact_severity: Rate freedom from AI artifacts (10=clean, 1=severe). List: morphing, warping, flickering, extra limbs.
E. source_fidelity: Does the video preserve source image quality? Or did generation degrade it?

Return JSON only:
{{
  "motion_plausibility": {{"score": 8, "reasoning": "...", "confidence": "high"}},
  "script_match": {{"score": 7, "reasoning": "...", "confidence": "medium"}},
  "temporal_coherence": {{"score": 8, "reasoning": "...", "confidence": "high"}},
  "artifact_severity": {{"score": 7, "reasoning": "...", "confidence": "medium"}},
  "source_fidelity": {{"score": 8, "reasoning": "...", "confidence": "high"}}
}}"""

        try:
            resp = requests.post(
                f"{OLLAMA_HOST}/api/chat",
                json={
                    "model": VISION_MODEL,
                    "messages": [{"role": "user", "content": prompt, "images": images_b64}],
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.3, "num_predict": 2048},
                },
                timeout=180,
            )
            resp.raise_for_status()
            raw = resp.json()["message"]["content"]
            return self._parse_rubric(raw)
        except Exception as e:
            logger.error(f"Video vision rubric failed: {e}")
            return {
                axis: {"score": 5, "reasoning": "Vision LLM unavailable", "confidence": "low"}
                for axis in VIDEO_RUBRIC_WEIGHTS
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
                for axis in VIDEO_RUBRIC_WEIGHTS
            }

        result = {}
        for axis in VIDEO_RUBRIC_WEIGHTS:
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

    def _compute_verdict(self, result: VideoVerification, retry_count: int) -> None:
        """Compute weighted score and verdict with fallback logic."""
        rubric = result.rubric

        weighted = sum(
            rubric.get(axis, {}).get("score", 5) * weight
            for axis, weight in VIDEO_RUBRIC_WEIGHTS.items()
        )
        result.weighted_score = round(weighted, 2)

        # Check for low confidence
        low_conf = [a for a, s in rubric.items() if s.get("confidence") == "low"]
        if low_conf:
            result.flags.append(f"low_confidence: {', '.join(low_conf)}")
            result.verdict = "flag_human"
            return

        if result.weighted_score >= PASS_THRESHOLD:
            result.verdict = "pass"
        else:
            self._determine_fallback(result, retry_count)

    def _determine_fallback(self, result: VideoVerification, retry_count: int) -> None:
        """Determine appropriate fallback action on failure."""
        rubric = result.rubric

        artifact_score = rubric.get("artifact_severity", {}).get("score", 5)
        source_score = rubric.get("source_fidelity", {}).get("score", 5)
        motion_score = rubric.get("motion_plausibility", {}).get("score", 5)

        if artifact_score < 4 and source_score > 7:
            result.verdict = "regen_video"
            result.fallback_reason = "LTX artifacts but source image OK — retry with different motion"
        elif source_score < 5:
            result.verdict = "regen_image"
            result.fallback_reason = "Source image quality too low for video generation"
        elif motion_score < 4 and retry_count >= 2:
            result.verdict = "ken_burns"
            result.fallback_reason = "LTX cannot handle this motion after 2+ retries — use Ken Burns fallback"
        else:
            result.verdict = "regen_video"
            result.fallback_reason = "Default retry — regenerate video with adjusted parameters"
