"""
Phase 6B — Telegram Video Gallery.

Sends video clips + script as Telegram videos for human review.
Each clip captioned with scene info, motion description, and vision score.
Summary message with approve/reject inline buttons.
"""

import json
import logging
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}"
MAX_CAPTION_LEN = 1024
TELEGRAM_VIDEO_SIZE_LIMIT_MB = 50


class TelegramVideoGallery:
    """Send video QA results as Telegram videos with inline buttons."""

    def __init__(self, bot_token: str = "", chat_id: str = ""):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send_gallery(
        self,
        job_id: str,
        scenes: list[dict],
        video_paths: list[str],
        verifications: list = None,
    ) -> None:
        """
        Send all video clips to Telegram with QA captions.

        Args:
            job_id: Pipeline job identifier.
            scenes: List of scene dicts.
            video_paths: List of video clip file paths.
            verifications: List of VideoVerification results.
        """
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram credentials not configured, skipping video gallery")
            return

        verifications = verifications or []
        total = len(scenes)

        logger.info(f"[{job_id}] Sending video gallery to Telegram ({total} clips)")

        # Send each video individually (Telegram albums support videos but
        # individual sends give better caption visibility)
        for i in range(total):
            video_path = video_paths[i] if i < len(video_paths) else ""
            if not video_path or not Path(video_path).exists():
                logger.warning(f"Video {i} missing: {video_path}")
                continue

            # Check file size
            file_size_mb = Path(video_path).stat().st_size / (1024 * 1024)
            if file_size_mb > TELEGRAM_VIDEO_SIZE_LIMIT_MB:
                logger.warning(f"Video {i} too large for Telegram: {file_size_mb:.1f}MB")
                self._send_size_warning(i, total, file_size_mb)
                continue

            scene = scenes[i] if i < len(scenes) else {}
            verification = verifications[i] if i < len(verifications) else None

            self._send_video(i, total, video_path, scene, verification)

        # Summary
        self._send_summary(job_id, scenes, verifications)

    def _send_video(
        self,
        scene_index: int,
        total: int,
        video_path: str,
        scene: dict,
        verification,
    ) -> None:
        """Send a single video clip to Telegram."""
        caption = self._build_caption(scene_index, total, scene, verification)

        try:
            url = f"{TELEGRAM_API.format(token=self.bot_token)}/sendVideo"
            with open(video_path, "rb") as f:
                resp = requests.post(
                    url,
                    data={
                        "chat_id": self.chat_id,
                        "caption": caption,
                        "parse_mode": "HTML",
                        "supports_streaming": "true",
                    },
                    files={"video": (Path(video_path).name, f, "video/mp4")},
                    timeout=120,
                )
                resp.raise_for_status()
                logger.debug(f"Sent video {scene_index}")
        except Exception as e:
            logger.error(f"Failed to send video {scene_index}: {e}")

    def _build_caption(
        self,
        scene_index: int,
        total: int,
        scene: dict,
        verification,
    ) -> str:
        """Build caption for a video clip."""
        narration = scene.get("narration_text", "")[:150]
        motion = scene.get("motion_prompt", scene.get("motion_description", ""))[:100]
        score = verification.weighted_score if verification else 0.0
        verdict = verification.verdict if verification else "unknown"

        # Verdict emoji
        verdict_map = {
            "pass": "✅",
            "regen_video": "🔄",
            "regen_image": "🖼",
            "ken_burns": "📷",
            "flag_human": "👁",
        }
        verdict_icon = verdict_map.get(verdict, "❌")

        lines = [
            f"🎬 <b>Scene {scene_index + 1}/{total} — Video Clip</b> {verdict_icon}",
            f'📝 "{narration}"' if narration else "",
            f'🎥 Motion: "{motion}"' if motion else "",
            f"🎯 Vision Score: <b>{score:.1f}/10</b>",
        ]

        # Show issues
        if verification:
            if verification.flags:
                flags_str = ", ".join(verification.flags[:3])
                lines.append(f"⚠️ {flags_str}")
            if verification.fallback_reason:
                lines.append(f"💡 {verification.fallback_reason[:100]}")
            if verification.frozen_frames > 0:
                lines.append(f"🧊 Frozen frames: {verification.frozen_frames}")

        caption = "\n".join(line for line in lines if line)
        return caption[:MAX_CAPTION_LEN]

    def _send_size_warning(self, scene_index: int, total: int, size_mb: float) -> None:
        """Send a text message warning about oversized video."""
        try:
            url = f"{TELEGRAM_API.format(token=self.bot_token)}/sendMessage"
            requests.post(
                url,
                json={
                    "chat_id": self.chat_id,
                    "text": f"⚠️ Scene {scene_index + 1}/{total} video too large ({size_mb:.1f}MB) for Telegram",
                },
                timeout=15,
            )
        except Exception:
            pass

    def _send_summary(
        self,
        job_id: str,
        scenes: list[dict],
        verifications: list,
    ) -> None:
        """Send summary with inline approve/reject buttons."""
        total = len(scenes)
        passed = sum(1 for v in verifications if v and v.verdict == "pass")
        regen_video = sum(1 for v in verifications if v and v.verdict == "regen_video")
        ken_burns = sum(1 for v in verifications if v and v.verdict == "ken_burns")
        flagged = sum(1 for v in verifications if v and v.verdict == "flag_human")

        scores = [v.weighted_score for v in verifications if v]
        avg_score = sum(scores) / len(scores) if scores else 0.0

        flagged_scenes = [
            str(i + 1) for i, v in enumerate(verifications)
            if v and v.verdict in ("flag_human", "regen_image")
        ]

        text = (
            f"🎬 <b>Video Clips Review — {job_id}</b>\n\n"
            f"✅ {passed}/{total} clips passed\n"
        )
        if regen_video:
            text += f"🔄 {regen_video} clips regenerated\n"
        if ken_burns:
            text += f"📷 {ken_burns} clips using Ken Burns fallback\n"
        if flagged:
            text += f"👁 {flagged} clips need manual review: Scene {', '.join(flagged_scenes)}\n"
        text += f"📊 Average score: {avg_score:.1f}/10\n"

        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "✅ Approve All", "callback_data": f"vid_approve_{job_id}"},
                    {"text": "👁 View Flagged", "callback_data": f"vid_flagged_{job_id}"},
                ],
                [
                    {"text": "❌ Reject & Regen", "callback_data": f"vid_reject_{job_id}"},
                ],
            ]
        }

        try:
            url = f"{TELEGRAM_API.format(token=self.bot_token)}/sendMessage"
            resp = requests.post(
                url,
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "reply_markup": keyboard,
                },
                timeout=30,
            )
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to send video summary: {e}")
