"""
Phase 8 — Shorts Generator: Extract best moments → crop 9:16 → add subtitles.

Analyzes scenes to find the most engaging 30-60s segments,
crops to vertical (9:16), burns in styled subtitles, and
produces YouTube Shorts-ready clips.
"""

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Shorts constraints
MIN_DURATION_SEC = 15
MAX_DURATION_SEC = 60
TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920
TARGET_FPS = 30


@dataclass
class ShortClip:
    """A single Short candidate."""
    start_scene: int
    end_scene: int
    start_sec: float
    end_sec: float
    duration_sec: float
    title: str = ""
    tags: list[str] = field(default_factory=list)
    engagement_score: float = 0.0
    file_path: Optional[str] = None


class ShortsGenerator:
    """
    Generates YouTube Shorts from a full-length video by:
    1. Scoring scenes for engagement potential
    2. Selecting 3-5 best continuous segments (30-60s)
    3. Cropping to 9:16 with smart framing
    4. Burning in styled subtitles
    """

    def __init__(self, config: dict, db):
        self.config = config
        self.db = db
        self.output_base = Path(config["settings"].get("output_dir", "output"))
        self.target_shorts = config["settings"].get("pipeline", {}).get(
            "shorts_per_video", 3
        )

    def generate_shorts(self, job_id: str, video_path: str) -> list[ShortClip]:
        """
        Generate YouTube Shorts from a full video.

        Args:
            job_id: The parent job.
            video_path: Path to the full-length video.

        Returns:
            List of ShortClip objects with file paths.
        """
        if not Path(video_path).exists():
            logger.error(f"Video not found: {video_path}")
            return []

        scenes = self.db.get_scenes(job_id)
        if not scenes:
            logger.warning(f"No scenes for {job_id}")
            return []

        # 1. Score scenes for engagement
        scored = self._score_scenes(scenes)

        # 2. Select best contiguous segments
        candidates = self._select_segments(scored)

        # 3. Generate each Short
        shorts_dir = self.output_base / job_id / "shorts"
        shorts_dir.mkdir(parents=True, exist_ok=True)

        # Get subtitle file if available
        sub_row = self.db.conn.execute(
            "SELECT srt_path FROM subtitles WHERE job_id = ? LIMIT 1",
            (job_id,),
        ).fetchone()
        ass_path = None
        if sub_row:
            srt_path = dict(sub_row).get("srt_path", "")
            ass_candidate = Path(srt_path).with_suffix(".ass")
            if ass_candidate.exists():
                ass_path = str(ass_candidate)

        results = []
        for i, clip in enumerate(candidates):
            output_path = shorts_dir / f"short_{i + 1}.mp4"
            success = self._render_short(
                video_path, str(output_path), clip, ass_path
            )
            if success:
                clip.file_path = str(output_path)
                self._save_short(job_id, clip, i + 1)
                results.append(clip)

        logger.info(f"Generated {len(results)} Shorts for {job_id}")
        return results

    def _score_scenes(self, scenes: list[dict]) -> list[dict]:
        """Score each scene for Short-worthiness based on engagement signals."""
        scored = []
        for scene in scenes:
            score = 0.0
            narration = scene.get("narration_text", "")

            # Hook-like text (questions, exclamations)
            if "؟" in narration or "?" in narration:
                score += 2.0
            if "!" in narration or "!" in narration:
                score += 1.0

            # Scene with voice emotion
            emotion = scene.get("voice_emotion", "calm")
            emotion_boost = {
                "dramatic": 2.5, "excited": 2.0, "suspenseful": 2.0,
                "passionate": 1.5, "urgent": 1.5, "calm": 0.0,
            }
            score += emotion_boost.get(emotion, 0.5)

            # Duration fit (prefer scenes that fit in Shorts range)
            duration = scene.get("duration_sec", 10)
            if MIN_DURATION_SEC <= duration <= MAX_DURATION_SEC:
                score += 1.5

            # Visual dynamism (camera movement)
            camera = scene.get("camera_movement", "")
            if camera and camera not in ("static", "none", ""):
                score += 1.0

            # SFX presence = something interesting
            sfx = json.loads(scene.get("sfx_tags") or "[]")
            if sfx:
                score += 0.5

            # Image QA score (if available)
            img_score = scene.get("image_score")
            if img_score and img_score > 7.0:
                score += 1.0

            scored.append({**scene, "_engagement_score": score})

        return sorted(scored, key=lambda s: s["_engagement_score"], reverse=True)

    def _select_segments(self, scored_scenes: list[dict]) -> list[ShortClip]:
        """Select 3-5 best contiguous segments for Shorts."""
        if not scored_scenes:
            return []

        candidates = []
        used_indices = set()

        for scene in scored_scenes:
            idx = scene["scene_index"]
            if idx in used_indices:
                continue

            start_sec = scene.get("start_time_sec", 0) or 0
            end_sec = scene.get("end_time_sec") or (start_sec + (scene.get("duration_sec") or 10))
            duration = end_sec - start_sec

            # Try to extend with adjacent scenes to fill 30-60s
            segment_start = idx
            segment_end = idx
            total = duration

            # Extend forward
            all_scenes = {s["scene_index"]: s for s in scored_scenes}
            next_idx = idx + 1
            while total < MAX_DURATION_SEC and next_idx in all_scenes:
                next_scene = all_scenes[next_idx]
                next_dur = (next_scene.get("end_time_sec") or 0) - (next_scene.get("start_time_sec") or 0)
                if next_dur <= 0:
                    next_dur = next_scene.get("duration_sec", 10)
                if total + next_dur > MAX_DURATION_SEC:
                    break
                total += next_dur
                segment_end = next_idx
                next_idx += 1

            if total < MIN_DURATION_SEC:
                continue

            # Clip to max duration
            clip_end_sec = start_sec + min(total, MAX_DURATION_SEC)

            clip = ShortClip(
                start_scene=segment_start,
                end_scene=segment_end,
                start_sec=start_sec,
                end_sec=clip_end_sec,
                duration_sec=clip_end_sec - start_sec,
                engagement_score=scene["_engagement_score"],
                title=scene.get("narration_text", "")[:80],
            )
            candidates.append(clip)

            # Mark scenes as used
            for i in range(segment_start, segment_end + 1):
                used_indices.add(i)

            if len(candidates) >= self.target_shorts:
                break

        return candidates

    def _render_short(
        self,
        video_path: str,
        output_path: str,
        clip: ShortClip,
        ass_path: Optional[str],
    ) -> bool:
        """Render a Short using FFmpeg: crop 9:16 + burn subtitles."""
        try:
            # Build FFmpeg filter chain
            filters = []

            # Crop to 9:16 from center
            filters.append(
                f"crop=ih*9/16:ih:(iw-ih*9/16)/2:0"
            )

            # Scale to target resolution
            filters.append(f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}")

            # Burn subtitles if available
            if ass_path:
                # Escape path for FFmpeg on Windows
                escaped_ass = ass_path.replace("\\", "/").replace(":", "\\\\:")
                filters.append(f"ass='{escaped_ass}'")

            filter_chain = ",".join(filters)

            cmd = [
                "ffmpeg", "-y",
                "-ss", str(clip.start_sec),
                "-i", video_path,
                "-t", str(clip.duration_sec),
                "-vf", filter_chain,
                "-r", str(TARGET_FPS),
                "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart",
                output_path,
            ]

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300
            )

            if result.returncode != 0:
                logger.error(f"FFmpeg Short render failed: {result.stderr[:500]}")
                return False

            logger.info(f"Short rendered: {output_path} ({clip.duration_sec:.1f}s)")
            return True

        except subprocess.TimeoutExpired:
            logger.error(f"Short render timed out for {output_path}")
            return False
        except Exception as e:
            logger.error(f"Short render error: {e}")
            return False

    def _save_short(self, job_id: str, clip: ShortClip, index: int):
        """Save Short metadata to DB."""
        self.db.conn.execute(
            """INSERT INTO shorts (parent_job_id, source_scene_start, source_scene_end,
               title, tags, file_path, duration_sec)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                job_id, clip.start_scene, clip.end_scene,
                clip.title, json.dumps(clip.tags),
                clip.file_path, clip.duration_sec,
            ),
        )
        self.db.conn.commit()
