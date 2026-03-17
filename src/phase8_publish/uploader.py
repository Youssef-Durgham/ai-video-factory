"""
Phase 8 — YouTube Uploader: Upload video, set metadata, add captions.

Uses google-api-python-client for YouTube Data API v3.
Handles resumable uploads, quota tracking, caption upload,
and thumbnail setting.
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import httplib2
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from src.core.config import resolve_path

logger = logging.getLogger(__name__)

# YouTube API scopes
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

# Quota costs (YouTube Data API v3)
QUOTA_UPLOAD = 1600
QUOTA_THUMBNAIL = 50
QUOTA_CAPTION = 200
QUOTA_UPDATE = 50

# Retry settings
MAX_RETRIES = 3
RETRY_BACKOFF = [5, 15, 60]  # seconds


class YouTubeUploader:
    """
    Uploads videos to YouTube via the Data API v3.
    Supports resumable upload, metadata, thumbnails, and captions.
    """

    def __init__(self, config: dict, db):
        self.config = config
        self.db = db
        self.yt_config = config["settings"].get("youtube", {})
        self.client_secrets = resolve_path(
            self.yt_config.get("client_secrets_file", "config/youtube_client_secret.json")
        )
        self.token_path = resolve_path("config/youtube_token.json")
        self.quota_daily = self.yt_config.get("quota_daily", 10000)
        self.quota_reserve = self.yt_config.get("quota_reserve", 3000)
        self._youtube = None

    @property
    def youtube(self):
        """Lazy-init authenticated YouTube API client."""
        if self._youtube is None:
            self._youtube = self._authenticate()
        return self._youtube

    def upload_video(
        self,
        job_id: str,
        video_path: str,
        title: str,
        description: str,
        tags: list[str],
        category_id: str = "27",
        privacy_status: str = "public",
        default_language: str = "ar",
        thumbnail_path: Optional[str] = None,
        srt_path: Optional[str] = None,
        scheduled_for: Optional[str] = None,
    ) -> Optional[str]:
        """
        Upload a video to YouTube with full metadata.

        Args:
            job_id: Job ID for tracking.
            video_path: Path to the video file.
            title: Video title.
            description: Video description.
            tags: List of tags.
            category_id: YouTube category ID.
            privacy_status: "public", "unlisted", or "private".
            default_language: Default language code.
            thumbnail_path: Optional path to thumbnail image.
            srt_path: Optional path to .srt caption file.
            scheduled_for: Optional ISO datetime for scheduled publishing.

        Returns:
            YouTube video ID on success, None on failure.
        """
        if not Path(video_path).exists():
            logger.error(f"Video file not found: {video_path}")
            return None

        # Check quota
        if not self._check_quota(QUOTA_UPLOAD):
            logger.error("Insufficient YouTube API quota for upload")
            self.db.block_job(job_id, "publish", "YouTube API quota exhausted")
            return None

        # If scheduled, use private + publishAt
        if scheduled_for:
            privacy_status = "private"

        body = {
            "snippet": {
                "title": title[:100],
                "description": description[:5000],
                "tags": tags[:30],
                "categoryId": category_id,
                "defaultLanguage": default_language,
                "defaultAudioLanguage": default_language,
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        }

        if scheduled_for:
            body["status"]["publishAt"] = scheduled_for

        media = MediaFileUpload(
            video_path,
            mimetype="video/mp4",
            resumable=True,
            chunksize=10 * 1024 * 1024,  # 10MB chunks
        )

        video_id = None
        for attempt in range(MAX_RETRIES):
            try:
                logger.info(f"Uploading video for {job_id} (attempt {attempt + 1})")

                request = self.youtube.videos().insert(
                    part="snippet,status",
                    body=body,
                    media_body=media,
                )

                response = self._resumable_upload(request)
                video_id = response.get("id")

                if video_id:
                    self._log_quota(job_id, "video_upload", QUOTA_UPLOAD)
                    logger.info(f"Video uploaded: {video_id} for {job_id}")
                    break

            except HttpError as e:
                logger.error(f"Upload HTTP error (attempt {attempt + 1}): {e}")
                if e.resp.status in (500, 502, 503):
                    time.sleep(RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)])
                    continue
                raise
            except Exception as e:
                logger.error(f"Upload error (attempt {attempt + 1}): {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)])
                else:
                    raise

        if not video_id:
            logger.error(f"Video upload failed after {MAX_RETRIES} attempts for {job_id}")
            return None

        # Set thumbnail
        if thumbnail_path and Path(thumbnail_path).exists():
            self._set_thumbnail(video_id, thumbnail_path, job_id)

        # Upload captions
        if srt_path and Path(srt_path).exists():
            self._upload_captions(video_id, srt_path, default_language, job_id)

        # Update job in DB
        youtube_url = f"https://www.youtube.com/watch?v={video_id}"
        self.db.conn.execute(
            "UPDATE jobs SET youtube_video_id = ?, youtube_url = ?, "
            "published_at = ?, status = 'published', "
            "phase8_completed_at = ?, updated_at = ? WHERE id = ?",
            (
                video_id, youtube_url,
                datetime.now().isoformat(),
                datetime.now().isoformat(),
                datetime.now().isoformat(),
                job_id,
            ),
        )
        self.db.conn.commit()

        logger.info(f"Upload complete for {job_id}: {youtube_url}")
        return video_id

    def _resumable_upload(self, request) -> dict:
        """Execute a resumable upload with progress logging."""
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                if pct % 25 == 0:
                    logger.info(f"Upload progress: {pct}%")
        return response

    def _set_thumbnail(self, video_id: str, thumbnail_path: str, job_id: str):
        """Set custom thumbnail for an uploaded video."""
        if not self._check_quota(QUOTA_THUMBNAIL):
            logger.warning("Insufficient quota for thumbnail — skipping")
            return

        try:
            media = MediaFileUpload(thumbnail_path, mimetype="image/png")
            self.youtube.thumbnails().set(
                videoId=video_id,
                media_body=media,
            ).execute()
            self._log_quota(job_id, "thumbnail_set", QUOTA_THUMBNAIL)
            logger.info(f"Thumbnail set for {video_id}")
        except HttpError as e:
            logger.error(f"Thumbnail upload failed: {e}")

    def _upload_captions(
        self, video_id: str, srt_path: str, language: str, job_id: str
    ):
        """Upload SRT captions to a video."""
        if not self._check_quota(QUOTA_CAPTION):
            logger.warning("Insufficient quota for captions — skipping")
            return

        try:
            body = {
                "snippet": {
                    "videoId": video_id,
                    "language": language,
                    "name": "Arabic" if language == "ar" else language,
                    "isDraft": False,
                },
            }
            media = MediaFileUpload(srt_path, mimetype="application/x-subrip")
            self.youtube.captions().insert(
                part="snippet",
                body=body,
                media_body=media,
            ).execute()
            self._log_quota(job_id, "caption_upload", QUOTA_CAPTION)

            # Update subtitles table
            self.db.conn.execute(
                "UPDATE subtitles SET uploaded_to_youtube = 1 "
                "WHERE job_id = ? AND language = ?",
                (job_id, language),
            )
            self.db.conn.commit()
            logger.info(f"Captions uploaded for {video_id}")
        except HttpError as e:
            logger.error(f"Caption upload failed: {e}")

    def _authenticate(self):
        """Authenticate with YouTube API using OAuth2."""
        creds = None

        if self.token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
            except Exception:
                pass

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                from google.auth.transport.requests import Request
                creds.refresh(Request())
            else:
                if not self.client_secrets.exists():
                    raise FileNotFoundError(
                        f"YouTube client secrets not found: {self.client_secrets}"
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.client_secrets), SCOPES
                )
                creds = flow.run_local_server(port=0)

            # Save token
            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            self.token_path.write_text(creds.to_json())

        return build("youtube", "v3", credentials=creds)

    def _check_quota(self, cost: int) -> bool:
        """Check if we have enough quota for an operation."""
        today = datetime.now().strftime("%Y-%m-%d")
        row = self.db.conn.execute(
            "SELECT COALESCE(SUM(units_used), 0) as used FROM api_quota_log WHERE date = ?",
            (today,),
        ).fetchone()
        used = row[0] if row else 0
        available = self.quota_daily - self.quota_reserve - used
        return available >= cost

    def _log_quota(self, job_id: str, operation: str, units: int):
        """Log quota usage."""
        self.db.conn.execute(
            "INSERT INTO api_quota_log (date, operation, units_used, job_id) VALUES (?, ?, ?, ?)",
            (datetime.now().strftime("%Y-%m-%d"), operation, units, job_id),
        )
        self.db.conn.commit()
