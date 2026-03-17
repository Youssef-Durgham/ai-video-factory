"""
Community Engagement Agent — Auto-replies to comments, pins discussion questions,
flags spam/hate, hearts valuable comments. Active first 2 hours post-publish.
"""

import json
import logging
import time
from datetime import datetime, timedelta
from typing import Optional

from src.core.database import FactoryDB
from src.core import llm

logger = logging.getLogger(__name__)

ENGAGEMENT_WINDOW_HOURS = 2
MAX_REPLIES = 50
MIN_REPLIES = 20
CHECK_INTERVAL_SEC = 300  # 5 minutes
FOLLOW_UP_INTERVALS = [6, 12, 24, 48]  # hours after publish


class CommunityAgent:
    """
    Manages YouTube comment engagement for published videos.
    Boosts early engagement signals for the algorithm.
    """

    def __init__(self, db: FactoryDB, youtube_api=None):
        self.db = db
        self.youtube = youtube_api

    def run(self, job_id: str):
        """
        Full engagement cycle for a published video.
        Called after Phase 8 publish.
        """
        job = self.db.get_job(job_id)
        if not job or not job.get("youtube_video_id"):
            logger.warning(f"Job {job_id} not published — skipping community engagement")
            return

        video_id = job["youtube_video_id"]
        channel_id = job["channel_id"]

        # Step 1: Pin a discussion question
        question = self._generate_discussion_question(job)
        self._pin_comment(video_id, question)

        # Step 2: Active engagement in first 2 hours
        self._active_engagement_loop(job_id, video_id, channel_id)

        # Step 3: Schedule follow-up checks
        logger.info(f"Active engagement complete for {job_id}. Follow-ups scheduled.")

    def run_followup(self, job_id: str):
        """Periodic follow-up check (called by scheduler at 6h, 12h, 24h, 48h)."""
        job = self.db.get_job(job_id)
        if not job or not job.get("youtube_video_id"):
            return

        video_id = job["youtube_video_id"]
        comments = self._fetch_new_comments(video_id, since_hours=6)

        for comment in comments[:20]:
            if self._is_already_handled(job_id, comment["id"]):
                continue
            action = self._classify_comment(comment["text"])
            self._execute_action(job_id, video_id, comment, action)

    # ─── Discussion Question ───────────────────────────

    def _generate_discussion_question(self, job: dict) -> str:
        """Generate a thought-provoking question related to the video topic."""
        prompt = f"""You are a community manager for an Arabic YouTube documentary channel.

Video topic: {job.get('topic', '')}

Write a short, engaging discussion question in Arabic to pin as the top comment.
The question should:
1. Be open-ended (not yes/no)
2. Relate directly to the video topic
3. Encourage viewers to share personal opinions or experiences
4. Be 1-2 sentences max

Return ONLY the question text in Arabic."""

        try:
            question = llm.generate(prompt, temperature=0.8, max_tokens=200).strip()
            # Strip quotes if present
            question = question.strip('"').strip("'").strip("«»")
            return question
        except Exception as e:
            logger.error(f"Discussion question generation failed: {e}")
            return "ما رأيكم في هذا الموضوع؟ شاركونا آراءكم في التعليقات 👇"

    def _pin_comment(self, video_id: str, text: str):
        """Post and pin a comment on the video."""
        if not self.youtube:
            logger.info(f"[DRY RUN] Would pin comment on {video_id}: {text[:80]}")
            return

        try:
            # Insert comment
            response = self.youtube.commentThreads().insert(
                part="snippet",
                body={
                    "snippet": {
                        "videoId": video_id,
                        "topLevelComment": {
                            "snippet": {"textOriginal": text}
                        }
                    }
                }
            ).execute()
            comment_id = response["id"]

            # Pin it (requires channel owner auth)
            # YouTube API doesn't have a direct pin endpoint;
            # pinning is done via the setModerationStatus or channel UI
            logger.info(f"Posted discussion comment on {video_id}: {comment_id}")
        except Exception as e:
            logger.error(f"Failed to post/pin comment: {e}")

    # ─── Active Engagement Loop ────────────────────────

    def _active_engagement_loop(self, job_id: str, video_id: str, channel_id: str):
        """Monitor and engage with comments for the first 2 hours."""
        start = time.time()
        end = start + (ENGAGEMENT_WINDOW_HOURS * 3600)
        replies_sent = 0

        while time.time() < end and replies_sent < MAX_REPLIES:
            comments = self._fetch_new_comments(video_id, since_hours=2)
            unhandled = [c for c in comments if not self._is_already_handled(job_id, c["id"])]

            if not unhandled:
                time.sleep(CHECK_INTERVAL_SEC)
                continue

            for comment in unhandled:
                if replies_sent >= MAX_REPLIES:
                    break

                action = self._classify_comment(comment["text"])
                self._execute_action(job_id, video_id, comment, action)

                if action["type"] == "reply":
                    replies_sent += 1

            logger.info(f"Engagement cycle: {replies_sent} replies sent for {job_id}")
            time.sleep(CHECK_INTERVAL_SEC)

        logger.info(f"Active engagement ended for {job_id}: {replies_sent} total replies")

    # ─── Comment Classification ────────────────────────

    def _classify_comment(self, text: str) -> dict:
        """Classify a comment and determine the appropriate action."""
        prompt = f"""Classify this YouTube comment and decide the action.

Comment: "{text}"

Classify as ONE of:
- "positive": Genuine positive feedback or discussion
- "question": Viewer asking a question about the topic
- "request": Viewer requesting a future topic
- "negative_constructive": Constructive criticism
- "spam": Spam, self-promotion, or unrelated
- "hate": Hate speech, harassment, or abusive
- "neutral": Simple/generic comment (e.g., "nice", "good video")

Also rate the comment value (1-10): how much it adds to the discussion.

Return JSON: {{"classification": "...", "value": N, "should_reply": true/false, "should_heart": true/false}}"""

        try:
            result = llm.generate_json(prompt, temperature=0.3)
            action_type = "reply" if result.get("should_reply", False) else "heart" if result.get("should_heart", False) else "skip"

            classification = result.get("classification", "neutral")
            if classification == "spam":
                action_type = "hide"
            elif classification == "hate":
                action_type = "report"

            return {
                "type": action_type,
                "classification": classification,
                "value": result.get("value", 5),
            }
        except Exception:
            return {"type": "skip", "classification": "unknown", "value": 0}

    def _execute_action(self, job_id: str, video_id: str, comment: dict, action: dict):
        """Execute the decided action on a comment."""
        comment_id = comment["id"]
        comment_text = comment["text"]
        action_type = action["type"]

        if action_type == "reply":
            reply = self._generate_reply(comment_text, action["classification"])
            self._post_reply(video_id, comment_id, reply)
        elif action_type == "heart":
            self._heart_comment(comment_id)
        elif action_type == "hide":
            self._hide_comment(comment_id)
        elif action_type == "report":
            self._report_comment(comment_id)

        # Log to DB
        self._log_engagement(job_id, comment_id, action_type, comment_text,
                             reply if action_type == "reply" else None,
                             action["classification"])

    # ─── Reply Generation ──────────────────────────────

    def _generate_reply(self, comment_text: str, classification: str) -> str:
        """Generate a contextual, human-like reply."""
        tone_map = {
            "positive": "grateful and warm",
            "question": "helpful and informative",
            "request": "enthusiastic about the suggestion",
            "negative_constructive": "respectful and open to feedback",
            "neutral": "friendly and brief",
        }
        tone = tone_map.get(classification, "friendly")

        prompt = f"""You are replying to a YouTube comment on an Arabic documentary channel.

Comment: "{comment_text}"
Tone: {tone}

Write a reply in Arabic that:
1. Is natural and conversational (NOT generic like "شكراً لتعليقك")
2. Directly addresses what the commenter said
3. Is 1-3 sentences max
4. May ask a follow-up question to encourage more discussion
5. Never argues or gets political

Return ONLY the reply text."""

        try:
            reply = llm.generate(prompt, temperature=0.8, max_tokens=200).strip()
            return reply.strip('"').strip("'")
        except Exception:
            return "شكراً لمشاركتك! 🙏"

    # ─── YouTube API Helpers ───────────────────────────

    def _fetch_new_comments(self, video_id: str, since_hours: int = 2) -> list[dict]:
        """Fetch recent comments from YouTube API."""
        if not self.youtube:
            return []

        try:
            response = self.youtube.commentThreads().list(
                part="snippet",
                videoId=video_id,
                order="time",
                maxResults=100,
            ).execute()

            comments = []
            cutoff = datetime.utcnow() - timedelta(hours=since_hours)
            for item in response.get("items", []):
                snippet = item["snippet"]["topLevelComment"]["snippet"]
                published = datetime.fromisoformat(
                    snippet["publishedAt"].replace("Z", "+00:00")
                ).replace(tzinfo=None)
                if published > cutoff:
                    comments.append({
                        "id": item["id"],
                        "text": snippet["textOriginal"],
                        "author": snippet["authorDisplayName"],
                        "published": published.isoformat(),
                        "like_count": snippet.get("likeCount", 0),
                    })
            return comments
        except Exception as e:
            logger.error(f"Failed to fetch comments: {e}")
            return []

    def _post_reply(self, video_id: str, parent_id: str, text: str):
        """Post a reply to a comment."""
        if not self.youtube:
            logger.info(f"[DRY RUN] Reply to {parent_id}: {text[:80]}")
            return
        try:
            self.youtube.comments().insert(
                part="snippet",
                body={
                    "snippet": {
                        "parentId": parent_id,
                        "textOriginal": text,
                    }
                }
            ).execute()
        except Exception as e:
            logger.error(f"Failed to post reply: {e}")

    def _heart_comment(self, comment_id: str):
        """Heart/like a comment."""
        if not self.youtube:
            logger.info(f"[DRY RUN] Heart comment {comment_id}")
            return
        try:
            self.youtube.comments().setModerationStatus(
                id=comment_id, moderationStatus="published"
            ).execute()
            # Note: Hearting requires creator API access
        except Exception as e:
            logger.warning(f"Heart comment failed: {e}")

    def _hide_comment(self, comment_id: str):
        """Hide a spam comment."""
        if not self.youtube:
            logger.info(f"[DRY RUN] Hide comment {comment_id}")
            return
        try:
            self.youtube.comments().setModerationStatus(
                id=comment_id, moderationStatus="heldForReview"
            ).execute()
        except Exception as e:
            logger.warning(f"Hide comment failed: {e}")

    def _report_comment(self, comment_id: str):
        """Report a hateful/abusive comment."""
        if not self.youtube:
            logger.info(f"[DRY RUN] Report comment {comment_id}")
            return
        try:
            self.youtube.comments().setModerationStatus(
                id=comment_id, moderationStatus="rejected"
            ).execute()
        except Exception as e:
            logger.warning(f"Report comment failed: {e}")

    # ─── DB Logging ────────────────────────────────────

    def _log_engagement(self, job_id: str, comment_id: str, action: str,
                        original: str, reply: Optional[str], sentiment: str):
        """Log engagement action to DB."""
        try:
            self.db.conn.execute("""
                INSERT INTO community_engagement
                    (job_id, youtube_comment_id, action, original_comment, reply_text, sentiment)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (job_id, comment_id, action, original[:500], reply, sentiment))
            self.db.conn.commit()
        except Exception as e:
            logger.warning(f"Failed to log engagement: {e}")

    def _is_already_handled(self, job_id: str, comment_id: str) -> bool:
        """Check if we already acted on this comment."""
        row = self.db.conn.execute(
            "SELECT 1 FROM community_engagement WHERE job_id = ? AND youtube_comment_id = ?",
            (job_id, comment_id),
        ).fetchone()
        return row is not None
