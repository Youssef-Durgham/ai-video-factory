"""
Phase 7B — Content QA: Extract keyframes from final video, verify with vision LLM.
Checks narration-visual match, text overlay readability, intro/outro presence, flow.
Uses Qwen 3.5-27B via Ollama vision API.
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

import requests

logger = logging.getLogger(__name__)

OLLAMA_HOST = "http://localhost:11434"
VISION_MODEL = "qwen3.5:27b"

CONTENT_PASS_SCORE = 7.0


@dataclass
class ContentCheckResult:
    """Result from content verification against scenes."""
    passed: bool = True
    score: float = 10.0
    scene_scores: list[dict] = field(default_factory=list)
    intro_present: bool = True
    outro_present: bool = True
    flow_score: float = 10.0
    issues: list[str] = field(default_factory=list)
    inference_ms: int = 0


class ContentChecker:
    """Vision LLM content verification on final composed video."""

    def __init__(self, config: dict = None):
        self.config = config or {}

    def check(
        self,
        video_path: str,
        scenes: list[dict],
    ) -> ContentCheckResult:
        """
        Extract one keyframe per scene from the final video,
        send to vision LLM for content verification.
        """
        result = ContentCheckResult()

        # Extract keyframes
        keyframes = self._extract_keyframes(video_path, scenes)
        if not keyframes:
            result.passed = False
            result.score = 0.0
            result.issues.append("Failed to extract keyframes from video")
            return result

        # Build vision prompt with all frames
        t0 = time.perf_counter_ns()
        llm_result = self._vision_check(keyframes, scenes)
        result.inference_ms = (time.perf_counter_ns() - t0) // 1_000_000

        if llm_result is None:
            # Fallback: neutral score if LLM unavailable
            result.score = 5.0
            result.passed = False
            result.issues.append("Vision LLM unavailable — manual review required")
            return result

        # Parse LLM results
        result.scene_scores = llm_result.get("scene_scores", [])
        result.intro_present = llm_result.get("intro_present", True)
        result.outro_present = llm_result.get("outro_present", True)
        result.flow_score = float(llm_result.get("flow_score", 5.0))

        # Collect issues
        flagged = llm_result.get("flagged_scenes", [])
        for item in flagged:
            idx = item.get("scene_index", "?")
            reason = item.get("reason", "unknown")
            result.issues.append(f"Scene {idx}: {reason}")

        if not result.intro_present:
            result.issues.append("Intro not detected in video")
        if not result.outro_present:
            result.issues.append("Outro not detected in video")

        # Calculate aggregate score
        scene_avg = 5.0
        if result.scene_scores:
            scores = [s.get("score", 5.0) for s in result.scene_scores]
            scene_avg = sum(scores) / len(scores)

        # Weighted: 50% scene match, 20% flow, 15% intro, 15% outro
        intro_val = 10.0 if result.intro_present else 2.0
        outro_val = 10.0 if result.outro_present else 2.0
        result.score = round(
            scene_avg * 0.50
            + result.flow_score * 0.20
            + intro_val * 0.15
            + outro_val * 0.15,
            2,
        )
        result.passed = result.score >= CONTENT_PASS_SCORE

        logger.info(
            "Content QA: score=%.1f passed=%s scenes=%d issues=%d",
            result.score, result.passed, len(result.scene_scores), len(result.issues),
        )

        # Cleanup temp frames
        for kf in keyframes:
            try:
                Path(kf["path"]).unlink(missing_ok=True)
            except Exception:
                pass

        return result

    # ─── Keyframe Extraction ─────────────────────────────

    def _extract_keyframes(
        self,
        video_path: str,
        scenes: list[dict],
    ) -> list[dict]:
        """
        Extract one frame per scene at the midpoint of each scene's time range.
        Returns list of {"scene_index": int, "path": str, "timestamp": float}.
        """
        keyframes = []
        tmp_dir = Path(tempfile.mkdtemp(prefix="phase7_frames_"))

        for scene in scenes:
            idx = scene.get("scene_index", 0)
            start = float(scene.get("start_time_sec", 0) or 0)
            end = float(scene.get("end_time_sec", 0) or 0)
            duration = float(scene.get("duration_sec", 10) or 10)

            # Calculate midpoint timestamp
            if end > start:
                ts = start + (end - start) / 2
            else:
                ts = start + duration / 2

            out_path = tmp_dir / f"scene_{idx:03d}.jpg"
            try:
                cmd = [
                    "ffmpeg", "-y",
                    "-ss", f"{ts:.2f}",
                    "-i", str(video_path),
                    "-frames:v", "1",
                    "-q:v", "2",
                    str(out_path),
                ]
                proc = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=15,
                )
                if proc.returncode == 0 and out_path.exists():
                    keyframes.append({
                        "scene_index": idx,
                        "path": str(out_path),
                        "timestamp": ts,
                    })
                else:
                    logger.warning("Failed to extract frame for scene %d at %.1fs", idx, ts)
            except Exception as e:
                logger.warning("Frame extraction error for scene %d: %s", idx, e)

        logger.info("Extracted %d/%d keyframes", len(keyframes), len(scenes))
        return keyframes

    # ─── Vision LLM Check ────────────────────────────────

    def _vision_check(
        self,
        keyframes: list[dict],
        scenes: list[dict],
    ) -> Optional[dict]:
        """
        Send keyframes + narration to vision LLM for content verification.
        Processes frames in batches if >5 (Ollama vision limit).
        """
        # Build scene narration map
        narration_map = {}
        for scene in scenes:
            idx = scene.get("scene_index", 0)
            narration_map[idx] = scene.get("narration_text", "")

        # Process in batches of 4 frames (vision models have image limits)
        batch_size = 4
        all_scene_scores = []
        flagged_scenes = []
        intro_present = True
        outro_present = True
        flow_scores = []

        for batch_start in range(0, len(keyframes), batch_size):
            batch = keyframes[batch_start:batch_start + batch_size]
            is_first_batch = batch_start == 0
            is_last_batch = batch_start + batch_size >= len(keyframes)

            images_b64 = []
            scene_descriptions = []
            for kf in batch:
                idx = kf["scene_index"]
                narration = narration_map.get(idx, "No narration")
                scene_descriptions.append(
                    f"Scene {idx} (at {kf['timestamp']:.1f}s): \"{narration}\""
                )
                with open(kf["path"], "rb") as f:
                    images_b64.append(base64.b64encode(f.read()).decode())

            scenes_text = "\n".join(scene_descriptions)

            intro_check = ""
            if is_first_batch:
                intro_check = "\n5. Is an intro/title sequence visible in the first frame?"
            outro_check = ""
            if is_last_batch:
                outro_check = "\n6. Is an outro/end card visible in the last frame?"

            prompt = f"""You are a video QA reviewer for a documentary production pipeline.
I'm showing you {len(batch)} keyframes from the final assembled video with their narration.

{scenes_text}

Evaluate each frame (images provided in order):
1. Does each frame match its narration text?
2. Are text overlays (if any) readable and correctly positioned?
3. Does the visual quality look professional?
4. Any frames that would get the video flagged on YouTube?{intro_check}{outro_check}

Also rate the visual flow/coherence between these frames (1-10).

Return JSON only:
{{
  "scene_scores": [
    {{"scene_index": 0, "score": 8.5, "match": "good", "issues": []}},
    ...
  ],
  "flow_score": 8.0,
  "intro_present": true,
  "outro_present": true,
  "flagged_scenes": [
    {{"scene_index": 2, "reason": "graphic content"}}
  ]
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
                        "options": {"temperature": 0.3, "num_predict": 4096},
                    },
                    timeout=180,
                )
                resp.raise_for_status()
                raw = resp.json()["message"]["content"]
                batch_result = self._parse_response(raw)

                all_scene_scores.extend(batch_result.get("scene_scores", []))
                flagged_scenes.extend(batch_result.get("flagged_scenes", []))
                flow_scores.append(float(batch_result.get("flow_score", 5.0)))

                if is_first_batch and "intro_present" in batch_result:
                    intro_present = batch_result["intro_present"]
                if is_last_batch and "outro_present" in batch_result:
                    outro_present = batch_result["outro_present"]

            except Exception as e:
                logger.error("Vision content check failed for batch: %s", e)
                return None

        avg_flow = sum(flow_scores) / len(flow_scores) if flow_scores else 5.0

        return {
            "scene_scores": all_scene_scores,
            "flow_score": avg_flow,
            "intro_present": intro_present,
            "outro_present": outro_present,
            "flagged_scenes": flagged_scenes,
        }

    def _parse_response(self, raw: str) -> dict:
        """Parse JSON response from vision LLM."""
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(raw[start:end])
            logger.error("Failed to parse vision LLM response: %s", raw[:300])
            return {}
