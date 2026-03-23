"""
Phase 8 — Publisher: Prepares final video for distribution.

Copies final.mp4 to publish folder, generates YouTube metadata JSON,
and optionally sends Telegram notification.
"""

import json
import logging
import os
import shutil
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class PublishResult:
    success: bool
    publish_dir: Optional[str] = None
    metadata_path: Optional[str] = None
    telegram_sent: bool = False
    error: Optional[str] = None


class Publisher:
    """Prepares and publishes the final video."""

    def __init__(self, config: dict = None):
        self.config = config or {}

    def publish(self, job_id: str, job: dict, db) -> PublishResult:
        """
        Publish the final video:
        1. Copy to publish folder
        2. Generate metadata JSON
        3. Send Telegram notification
        4. Mark job as published
        """
        base = Path(f"output/{job_id}")
        final_video = base / "final.mp4"

        if not final_video.exists():
            return PublishResult(success=False, error=f"final.mp4 not found at {final_video}")

        # 1. Create publish directory and copy
        pub_dir = base / "publish"
        pub_dir.mkdir(parents=True, exist_ok=True)
        pub_video = pub_dir / "final.mp4"
        shutil.copy2(str(final_video), str(pub_video))

        # 2. Generate metadata
        metadata = self._build_metadata(job_id, job, db)
        metadata_path = pub_dir / "metadata.json"
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # 3. Telegram notification
        tg_sent = self._notify_telegram(job_id, metadata, str(pub_video))

        # 4. Mark published in DB
        try:
            from datetime import datetime
            db.conn.execute(
                "UPDATE jobs SET status = 'published', published_at = ? WHERE id = ?",
                (datetime.now().isoformat(), job_id),
            )
            db.conn.commit()
        except Exception as e:
            logger.warning(f"Failed to update job status: {e}")

        logger.info(f"Published {job_id} to {pub_dir}")
        return PublishResult(
            success=True,
            publish_dir=str(pub_dir),
            metadata_path=str(metadata_path),
            telegram_sent=tg_sent,
        )

    def _build_metadata(self, job_id: str, job: dict, db) -> dict:
        """Build YouTube metadata from SEO data."""
        metadata = {
            "job_id": job_id,
            "title": job.get("topic", "Untitled"),
            "description": "",
            "tags": [],
            "category": "27",  # Education
            "language": "ar",
        }

        # Get SEO data
        try:
            row = db.conn.execute(
                "SELECT * FROM seo_data WHERE job_id = ? ORDER BY id DESC LIMIT 1",
                (job_id,),
            ).fetchone()
            if row:
                seo = dict(row)
                metadata["title"] = seo.get("selected_title") or metadata["title"]
                metadata["description"] = seo.get("description_template", "")
                try:
                    metadata["tags"] = json.loads(seo.get("tags", "[]"))
                except (json.JSONDecodeError, TypeError):
                    pass
                try:
                    hashtags = json.loads(seo.get("hashtags", "[]"))
                    if hashtags:
                        metadata["hashtags"] = hashtags
                except (json.JSONDecodeError, TypeError):
                    pass
        except Exception as e:
            logger.warning(f"Failed to get SEO data: {e}")

        return metadata

    def _notify_telegram(self, job_id: str, metadata: dict, video_path: str) -> bool:
        """Send Telegram notification with video and metadata."""
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if not bot_token or not chat_id:
            tg = self.config.get("settings", {}).get("telegram", {})
            bot_token = bot_token or tg.get("bot_token", "")
            chat_id = chat_id or tg.get("admin_chat_id") or tg.get("chat_id", "")

        if not bot_token or not chat_id:
            logger.warning("No Telegram credentials for publish notification")
            return False

        api = f"https://api.telegram.org/bot{bot_token}"

        # Send text message first
        title = metadata.get("title", "Untitled")
        tags = metadata.get("tags", [])
        tags_str = ", ".join(tags[:10]) if tags else "—"

        text = (
            f"🎬 <b>فيديو جاهز للنشر!</b>\n\n"
            f"📝 <b>العنوان:</b> {title}\n"
            f"🏷️ <b>Tags:</b> {tags_str}\n"
            f"🆔 <code>{job_id}</code>"
        )

        try:
            requests.post(f"{api}/sendMessage", json={
                "chat_id": chat_id, "text": text, "parse_mode": "HTML",
            }, timeout=10)
        except Exception as e:
            logger.warning(f"Telegram text message failed: {e}")

        # Send video file (if small enough for Telegram — 50MB limit)
        try:
            size_mb = Path(video_path).stat().st_size / (1024 * 1024)
            if size_mb <= 50:
                with open(video_path, "rb") as f:
                    requests.post(f"{api}/sendVideo", data={
                        "chat_id": chat_id,
                        "caption": f"📦 {title}",
                    }, files={"video": (f"final_{job_id}.mp4", f, "video/mp4")}, timeout=120)
                return True
            else:
                requests.post(f"{api}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": f"⚠️ الفيديو كبير ({size_mb:.0f}MB) — لا يمكن إرساله عبر تلغرام.",
                }, timeout=10)
                return True
        except Exception as e:
            logger.warning(f"Telegram video send failed: {e}")
            return False
