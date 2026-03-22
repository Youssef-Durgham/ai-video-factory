"""
Video QA — deterministic checks + Vision LLM rubric on keyframes.

Layer 1: Duration, FPS, file integrity, black frame detection
Layer 2: Extract keyframes → Ollama Qwen vision rubric (motion, fidelity, artifacts)
Layer 3: Weighted verdict → PASS / REGEN
"""

import base64
import json
import logging
import subprocess
import tempfile
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

# Thresholds
MIN_DURATION = 2.5
MAX_DURATION = 8.0
TARGET_FPS = 24
FPS_TOLERANCE = 5
BLACK_MEAN_THRESHOLD = 15.0

# Rubric weights
WEIGHTS = {"motion": 0.35, "fidelity": 0.35, "artifacts": 0.30}
PASS_THRESHOLD = 6.0


@dataclass
class VideoDeterministicResult:
    passed: bool
    duration_sec: float = 0.0
    fps: float = 0.0
    width: int = 0
    height: int = 0
    file_ok: bool = True
    duration_ok: bool = True
    fps_ok: bool = True
    has_black_frames: bool = False
    fail_reasons: list = field(default_factory=list)


@dataclass
class VideoRubricResult:
    motion_plausibility: float = 5.0
    source_fidelity: float = 5.0
    artifact_severity: float = 5.0
    weighted_score: float = 5.0
    raw_response: str = ""


@dataclass
class VideoQAResult:
    scene_index: int
    video_path: str
    deterministic: VideoDeterministicResult
    rubric: Optional[VideoRubricResult] = None
    weighted_score: float = 0.0
    verdict: str = "REGEN"  # PASS / REGEN
    error: Optional[str] = None


class VideoQA:
    """Video quality assessment: deterministic + vision LLM on keyframes."""

    def __init__(self, ollama_host: str = OLLAMA_HOST, vision_model: str = VISION_MODEL):
        self.ollama_host = ollama_host
        self.vision_model = vision_model

    def check_video(
        self,
        video_path: str,
        scene_index: int,
        source_image_path: str = "",
        visual_prompt: str = "",
    ) -> VideoQAResult:
        """Run full QA on a single video clip."""
        det = self._deterministic_checks(video_path)

        if not det.file_ok:
            return VideoQAResult(
                scene_index=scene_index, video_path=video_path,
                deterministic=det, weighted_score=0.0, verdict="REGEN",
                error="Video file unreadable",
            )

        if not det.passed:
            return VideoQAResult(
                scene_index=scene_index, video_path=video_path,
                deterministic=det, weighted_score=3.0, verdict="REGEN",
                error=f"Deterministic fail: {', '.join(det.fail_reasons)}",
            )

        # Layer 2: Vision rubric on keyframes
        rubric = self._vision_rubric(video_path, source_image_path, visual_prompt)
        score = rubric.weighted_score if rubric else 5.0
        verdict = "PASS" if score >= PASS_THRESHOLD else "REGEN"

        return VideoQAResult(
            scene_index=scene_index, video_path=video_path,
            deterministic=det, rubric=rubric,
            weighted_score=score, verdict=verdict,
        )

    def check_batch(
        self, scenes: list[dict], videos_dir: str, images_dir: str
    ) -> list[VideoQAResult]:
        """Check all scene videos."""
        results = []
        for scene in scenes:
            idx = scene.get("scene_index", 0)
            vid_path = scene.get("video_clip_path") or str(
                Path(videos_dir) / f"scene_{idx:03d}.mp4"
            )
            img_path = scene.get("image_path") or str(
                Path(images_dir) / f"scene_{idx:03d}.png"
            )

            if not Path(vid_path).exists():
                results.append(VideoQAResult(
                    scene_index=idx, video_path=vid_path,
                    deterministic=VideoDeterministicResult(
                        passed=False, file_ok=False, fail_reasons=["File not found"]),
                    weighted_score=0.0, verdict="REGEN", error="Video not found",
                ))
                continue

            result = self.check_video(
                video_path=vid_path, scene_index=idx,
                source_image_path=img_path,
                visual_prompt=scene.get("visual_prompt", ""),
            )
            results.append(result)
            logger.info(f"Scene {idx} video QA: {result.verdict} (score={result.weighted_score:.1f})")

        return results

    # ─── Layer 1: Deterministic ────────────────────────

    def _deterministic_checks(self, video_path: str) -> VideoDeterministicResult:
        result = VideoDeterministicResult(passed=True)
        fail_reasons = []

        # FFprobe metadata
        try:
            probe = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_format", "-show_streams", video_path],
                capture_output=True, text=True, timeout=30,
            )
            if probe.returncode != 0:
                result.file_ok = False
                result.passed = False
                result.fail_reasons = ["FFprobe failed"]
                return result

            info = json.loads(probe.stdout)
            fmt = info.get("format", {})
            result.duration_sec = float(fmt.get("duration", 0))

            # Find video stream
            for s in info.get("streams", []):
                if s.get("codec_type") == "video":
                    result.width = int(s.get("width", 0))
                    result.height = int(s.get("height", 0))
                    # Parse fps from r_frame_rate
                    r_fps = s.get("r_frame_rate", "24/1")
                    if "/" in r_fps:
                        num, den = r_fps.split("/")
                        result.fps = float(num) / max(float(den), 1)
                    else:
                        result.fps = float(r_fps)
                    break

        except Exception as e:
            result.file_ok = False
            result.passed = False
            result.fail_reasons = [f"Probe error: {e}"]
            return result

        # Duration check
        if result.duration_sec < MIN_DURATION or result.duration_sec > MAX_DURATION:
            result.duration_ok = False
            fail_reasons.append(f"Duration {result.duration_sec:.1f}s outside {MIN_DURATION}-{MAX_DURATION}s")

        # FPS check
        if abs(result.fps - TARGET_FPS) > FPS_TOLERANCE:
            result.fps_ok = False
            fail_reasons.append(f"FPS {result.fps:.1f} not near {TARGET_FPS}")

        # Black frame detection (sample 3 frames)
        try:
            cap = cv2.VideoCapture(video_path)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            black_count = 0
            for pos in [0, total_frames // 2, max(total_frames - 1, 0)]:
                cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
                ret, frame = cap.read()
                if ret:
                    mean = np.mean(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
                    if mean < BLACK_MEAN_THRESHOLD:
                        black_count += 1
            cap.release()
            if black_count >= 2:
                result.has_black_frames = True
                fail_reasons.append(f"{black_count}/3 sampled frames are black")
        except Exception as e:
            logger.warning(f"Black frame check error: {e}")

        if fail_reasons:
            result.passed = False
        result.fail_reasons = fail_reasons
        return result

    # ─── Layer 2: Vision Rubric on Keyframes ───────────

    def _extract_keyframes(self, video_path: str) -> list[str]:
        """Extract start, middle, end frames as temp PNGs."""
        tmp_dir = tempfile.mkdtemp(prefix="vqa_")
        out_pattern = str(Path(tmp_dir) / "frame_%d.png")

        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", video_path,
                 "-vf", r"select=eq(n\,0)+eq(n\,36)+eq(n\,72)",
                 "-vsync", "vfr", out_pattern],
                capture_output=True, timeout=30,
            )
        except Exception as e:
            logger.warning(f"Keyframe extraction error: {e}")

        frames = sorted(Path(tmp_dir).glob("frame_*.png"))
        return [str(f) for f in frames]

    def _vision_rubric(
        self, video_path: str, source_image_path: str, visual_prompt: str
    ) -> Optional[VideoRubricResult]:
        """Score video keyframes via Ollama vision."""
        keyframes = self._extract_keyframes(video_path)
        if not keyframes:
            logger.warning("No keyframes extracted, skipping vision rubric")
            return None

        # Encode keyframes + source image
        images_b64 = []
        for kf in keyframes[:3]:
            try:
                with open(kf, "rb") as f:
                    images_b64.append(base64.b64encode(f.read()).decode())
            except Exception:
                pass

        if source_image_path and Path(source_image_path).exists():
            try:
                with open(source_image_path, "rb") as f:
                    source_b64 = base64.b64encode(f.read()).decode()
                images_b64.append(source_b64)
                has_source = True
            except Exception:
                has_source = False
        else:
            has_source = False

        source_note = (
            "The LAST image is the source image. Compare video frames to it."
            if has_source else "No source image provided."
        )

        prompt = f"""You are a video QA reviewer for documentary production.
I'm showing you {len(keyframes)} keyframes from a video clip{' and the source image' if has_source else ''}.

{source_note}
Visual context: {visual_prompt[:400]}

Score on 3 axes (1-10):
A. Motion Plausibility — does the motion look natural and smooth? (1=frozen/glitchy, 10=smooth natural motion)
B. Source Image Fidelity — do frames look like the source image? (1=completely different, 10=faithful)
C. Artifact Severity — video quality (1=severe distortion/artifacts, 10=clean)

Reply ONLY with JSON:
{{"motion_plausibility": N, "source_fidelity": N, "artifact_severity": N}}"""

        try:
            start = time.time()
            resp = requests.post(
                f"{self.ollama_host}/api/chat",
                json={
                    "model": self.vision_model,
                    "messages": [{"role": "user", "content": prompt, "images": images_b64}],
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.3, "num_predict": 512},
                },
                timeout=180,
            )
            resp.raise_for_status()
            msg = resp.json().get("message", {})
            raw = msg.get("content", "")
            # Qwen 3.5 thinking mode fallback
            if not raw.strip():
                thinking = msg.get("thinking", "")
                if thinking:
                    import re
                    json_match = re.search(r'\{[^{}]*"motion_plausibility"[^{}]*\}', thinking)
                    if json_match:
                        raw = json_match.group(0)
            logger.debug(f"Video vision rubric took {time.time()-start:.1f}s")

            data = json.loads(raw)
            r = VideoRubricResult(
                motion_plausibility=float(data.get("motion_plausibility", 5)),
                source_fidelity=float(data.get("source_fidelity", 5)),
                artifact_severity=float(data.get("artifact_severity", 5)),
                raw_response=raw,
            )
            r.weighted_score = (
                r.motion_plausibility * WEIGHTS["motion"]
                + r.source_fidelity * WEIGHTS["fidelity"]
                + r.artifact_severity * WEIGHTS["artifacts"]
            )
            return r

        except Exception as e:
            logger.error(f"Video vision rubric failed: {e}")
            r = VideoRubricResult(raw_response=str(e))
            r.weighted_score = 5.0
            return r
        finally:
            # Cleanup temp keyframes
            for kf in keyframes:
                try:
                    Path(kf).unlink(missing_ok=True)
                except Exception:
                    pass
