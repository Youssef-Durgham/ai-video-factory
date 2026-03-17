"""
Phase 6A — Telegram Image Gallery.

Sends scene images + script info as a Telegram album for human review.
Each image captioned with scene number, narration text, QA score, and missing elements.
Summary message with approve/regenerate inline buttons.
"""

import logging
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}"
MAX_CAPTION_LEN = 1024
MAX_ALBUM_SIZE = 10  # Telegram album limit


class TelegramGallery:
    """Send image QA results as Telegram photo albums with inline buttons."""

    def __init__(self, bot_token: str = "", chat_id: str = ""):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send_gallery(
        self,
        job_id: str,
        scenes: list[dict],
        image_paths: list[str],
        verifications: list = None,
        style_outliers: list[int] = None,
    ) -> None:
        """
        Send all scene images as Telegram albums with QA captions.

        Args:
            job_id: Pipeline job identifier.
            scenes: List of scene dicts with narration_text, etc.
            image_paths: List of image file paths (parallel with scenes).
            verifications: List of ImageVerification results (parallel with scenes).
            style_outliers: Scene indices flagged as style outliers.
        """
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram credentials not configured, skipping gallery")
            return

        verifications = verifications or []
        style_outliers = style_outliers or []
        total = len(scenes)

        logger.info(f"[{job_id}] Sending image gallery to Telegram ({total} scenes)")

        # Send in batches of MAX_ALBUM_SIZE
        for batch_start in range(0, total, MAX_ALBUM_SIZE):
            batch_end = min(batch_start + MAX_ALBUM_SIZE, total)
            self._send_album_batch(
                job_id, scenes, image_paths, verifications,
                style_outliers, batch_start, batch_end, total,
            )

        # Send summary message with inline buttons
        self._send_summary(job_id, scenes, verifications, style_outliers)

    def _send_album_batch(
        self,
        job_id: str,
        scenes: list[dict],
        image_paths: list[str],
        verifications: list,
        style_outliers: list[int],
        start: int,
        end: int,
        total: int,
    ) -> None:
        """Send a batch of images as a Telegram media group (album)."""
        import json

        media = []
        files = {}

        for i in range(start, end):
            img_path = image_paths[i] if i < len(image_paths) else ""
            if not img_path or not Path(img_path).exists():
                continue

            scene = scenes[i] if i < len(scenes) else {}
            verification = verifications[i] if i < len(verifications) else None

            # Build caption
            caption = self._build_caption(i, total, scene, verification, i in style_outliers)

            file_key = f"photo_{i}"
            files[file_key] = (Path(img_path).name, open(img_path, "rb"), "image/png")

            media_item = {
                "type": "photo",
                "media": f"attach://{file_key}",
            }
            if i == start:  # Only first item in album gets caption
                media_item["caption"] = caption
                media_item["parse_mode"] = "HTML"
            media.append(media_item)

        if not media:
            return

        try:
            url = f"{TELEGRAM_API.format(token=self.bot_token)}/sendMediaGroup"
            resp = requests.post(
                url,
                data={
                    "chat_id": self.chat_id,
                    "media": json.dumps(media),
                },
                files=files,
                timeout=120,
            )
            resp.raise_for_status()
            logger.info(f"Sent album batch {start}-{end-1}")
        except Exception as e:
            logger.error(f"Failed to send album batch: {e}")
            # Fallback: send individually
            self._send_individual(scenes, image_paths, verifications, style_outliers, start, end, total)
        finally:
            for fk, fv in files.items():
                try:
                    fv[1].close()
                except Exception:
                    pass

    def _send_individual(
        self,
        scenes: list[dict],
        image_paths: list[str],
        verifications: list,
        style_outliers: list[int],
        start: int,
        end: int,
        total: int,
    ) -> None:
        """Fallback: send images one by one if album fails."""
        for i in range(start, end):
            img_path = image_paths[i] if i < len(image_paths) else ""
            if not img_path or not Path(img_path).exists():
                continue

            scene = scenes[i] if i < len(scenes) else {}
            verification = verifications[i] if i < len(verifications) else None
            caption = self._build_caption(i, total, scene, verification, i in style_outliers)

            try:
                url = f"{TELEGRAM_API.format(token=self.bot_token)}/sendPhoto"
                with open(img_path, "rb") as f:
                    resp = requests.post(
                        url,
                        data={
                            "chat_id": self.chat_id,
                            "caption": caption,
                            "parse_mode": "HTML",
                        },
                        files={"photo": f},
                        timeout=60,
                    )
                    resp.raise_for_status()
            except Exception as e:
                logger.error(f"Failed to send image {i}: {e}")

    def _build_caption(
        self,
        scene_index: int,
        total: int,
        scene: dict,
        verification,
        is_style_outlier: bool,
    ) -> str:
        """Build caption for a single scene image."""
        narration = scene.get("narration_text", "")[:200]
        score = verification.weighted_score if verification else 0.0
        verdict = verification.verdict if verification else "unknown"

        # Verdict emoji
        if verdict == "pass":
            verdict_icon = "✅"
        elif verdict == "flag_human":
            verdict_icon = "👁"
        elif verdict in ("regen_adjust", "regen_new"):
            verdict_icon = "🔄"
        else:
            verdict_icon = "❌"

        lines = [
            f"🎬 <b>Scene {scene_index + 1}/{total}</b> {verdict_icon}",
            f'📝 "{narration}"' if narration else "",
            f"🎯 Score: <b>{score:.1f}/10</b>",
        ]

        # Missing elements from rubric
        if verification and verification.rubric:
            ep = verification.rubric.get("element_presence", {})
            elements = ep.get("elements", {})
            missing = [k for k, v in elements.items() if v == "absent"] if isinstance(elements, dict) else []
            if missing:
                lines.append(f"⚠️ Missing: {', '.join(missing)}")

        # Flags
        if verification and verification.flags:
            flags_str = ", ".join(verification.flags[:3])
            lines.append(f"🚩 {flags_str}")

        if is_style_outlier:
            lines.append("🎨 <i>Style outlier — breaks consistency</i>")

        caption = "\n".join(line for line in lines if line)
        return caption[:MAX_CAPTION_LEN]

    def _send_summary(
        self,
        job_id: str,
        scenes: list[dict],
        verifications: list,
        style_outliers: list[int],
    ) -> None:
        """Send summary message with inline approve/regenerate buttons."""
        import json

        total = len(scenes)
        passed = sum(1 for v in verifications if v and v.verdict == "pass")
        flagged = sum(1 for v in verifications if v and v.verdict == "flag_human")
        regen = sum(1 for v in verifications if v and v.verdict in ("regen_adjust", "regen_new"))
        failed = total - passed - flagged - regen

        scores = [v.weighted_score for v in verifications if v]
        avg_score = sum(scores) / len(scores) if scores else 0.0

        regen_scenes = [
            str(i + 1) for i, v in enumerate(verifications)
            if v and v.verdict in ("regen_adjust", "regen_new", "fail")
        ]

        text = (
            f"📊 <b>Image QA Summary — {job_id}</b>\n\n"
            f"✅ {passed}/{total} images passed (avg {avg_score:.1f}/10)\n"
        )
        if regen:
            text += f"🔄 {regen} need regeneration: Scene {', '.join(regen_scenes)}\n"
        if flagged:
            text += f"👁 {flagged} flagged for human review\n"
        if failed:
            text += f"❌ {failed} hard failures\n"
        if style_outliers:
            text += f"🎨 Style outliers: Scene {', '.join(str(s+1) for s in style_outliers)}\n"

        # Inline keyboard
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "✅ Approve All", "callback_data": f"img_approve_{job_id}"},
                    {"text": "🔄 Regenerate Failed", "callback_data": f"img_regen_{job_id}"},
                ],
                [
                    {"text": "📋 View Details", "callback_data": f"img_details_{job_id}"},
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
            logger.error(f"Failed to send summary: {e}")
