"""
Phase 7.5 — Telegram Review Handler.

Sends video preview + QA summary to admin chat with inline buttons:
  ✅ Approve  |  ❌ Reject  |  🔄 Regenerate
Handles callback responses and updates job status accordingly.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

if TYPE_CHECKING:
    from src.core.database import FactoryDB
    from src.core.event_bus import EventBus

logger = logging.getLogger(__name__)


class ReviewHandler:
    """
    Telegram-based manual review workflow.
    Sends preview messages with approve/reject/regen buttons
    and routes callback responses.
    """

    def __init__(self, db: "FactoryDB", event_bus: "EventBus", config: dict):
        self.db = db
        self.events = event_bus
        self.config = config
        self.admin_chat_id = config["settings"]["telegram"]["admin_chat_id"]
        # Set by orchestrator after wiring
        self.pipeline_resume_callback = None

    async def send_review_request(self, job_id: str, bot) -> None:
        """
        Send a review preview to the admin Telegram chat.

        Includes: video file, thumbnail, QA summary, and action buttons.

        Args:
            job_id: The job awaiting review.
            bot: telegram.Bot instance for sending messages.
        """
        job = self.db.get_job(job_id)
        if not job:
            logger.error(f"Cannot send review: job {job_id} not found")
            return

        # Gather QA summary
        rubric_stats = self.db.get_rubric_stats(job_id)
        flags = self.db.get_job_flags(job_id)
        review_notes = json.loads(job.get("manual_review_notes") or "{}")

        # Build summary text
        lines = [
            "🔍 <b>Manual Review Required</b>\n",
            f"🎬 Job: <code>{job_id}</code>",
            f"📋 Topic: {job.get('topic', 'N/A')}",
            f"📺 Channel: {job.get('channel_id', 'N/A')}",
        ]

        # QA scores
        if rubric_stats:
            lines.append("\n📊 <b>QA Scores:</b>")
            for stat in rubric_stats:
                icon = "✅" if stat["avg_score"] and stat["avg_score"] >= 7.0 else "⚠️"
                lines.append(
                    f"  {icon} {stat['asset_type']}/{stat['check_phase']}: "
                    f"{stat['avg_score']:.1f} "
                    f"({stat['pass_count']}/{stat['total']} pass)"
                )

        # Overall score
        overall = review_notes.get("overall_score", 0)
        lines.append(f"\n🎯 Overall Score: <b>{overall:.1f}</b>")

        # Flags
        if flags:
            lines.append(f"\n🚩 <b>Flags ({len(flags)}):</b>")
            for f in flags[:5]:
                severity_icon = "🔴" if f["severity"] == "error" else "🟡"
                lines.append(f"  {severity_icon} {f['flag']}")
            if len(flags) > 5:
                lines.append(f"  ... and {len(flags) - 5} more")

        # Review reasons
        reasons = review_notes.get("reasons", [])
        if reasons:
            lines.append("\n📝 <b>Review Reasons:</b>")
            for r in reasons:
                lines.append(f"  • {r}")

        # Sensitive category warning
        sensitive = review_notes.get("sensitive_category")
        if sensitive:
            lines.append(f"\n⚠️ <b>Sensitive Category: {sensitive}</b>")

        # Action buttons
        buttons = [
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"review_approve:{job_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"review_reject:{job_id}"),
            ],
            [
                InlineKeyboardButton("🔄 Regenerate", callback_data=f"review_regen:{job_id}"),
                InlineKeyboardButton("📝 Edit & Approve", callback_data=f"review_edit:{job_id}"),
            ],
        ]
        markup = InlineKeyboardMarkup(buttons)

        # Send thumbnail (if available)
        thumb_row = self.db.conn.execute(
            "SELECT file_path FROM thumbnails WHERE job_id = ? ORDER BY readability_score DESC LIMIT 1",
            (job_id,),
        ).fetchone()

        try:
            if thumb_row:
                thumb_path = Path(dict(thumb_row)["file_path"])
                if thumb_path.exists():
                    with open(thumb_path, "rb") as photo:
                        await bot.send_photo(
                            chat_id=self.admin_chat_id,
                            photo=photo,
                            caption="\n".join(lines),
                            parse_mode="HTML",
                            reply_markup=markup,
                        )
                    return

            # Fallback: text only
            await bot.send_message(
                chat_id=self.admin_chat_id,
                text="\n".join(lines),
                parse_mode="HTML",
                reply_markup=markup,
            )
        except Exception as e:
            logger.error(f"Failed to send review message for {job_id}: {e}")

    # ------------------------------------------------------------------
    # Callback Handlers (registered via TelegramHandlers.ROUTES)
    # ------------------------------------------------------------------

    async def handle_approve(self, query, parts: list[str]):
        """Approve video for publishing."""
        job_id = parts[1] if len(parts) > 1 else ""
        self.db.conn.execute(
            "UPDATE jobs SET manual_review_status = 'approved', "
            "manual_review_at = ?, status = 'publish' WHERE id = ?",
            (datetime.now().isoformat(), job_id),
        )
        self.db.conn.commit()

        await query.edit_message_text(
            f"✅ <b>Approved</b>: {job_id}\nPublishing now...",
            parse_mode="HTML",
        )
        logger.info(f"Job {job_id} approved for publishing")

        if self.pipeline_resume_callback:
            await self.pipeline_resume_callback(job_id)

    async def handle_reject(self, query, parts: list[str]):
        """Reject video — blocks the job."""
        job_id = parts[1] if len(parts) > 1 else ""
        self.db.conn.execute(
            "UPDATE jobs SET manual_review_status = 'rejected', "
            "manual_review_at = ? WHERE id = ?",
            (datetime.now().isoformat(), job_id),
        )
        self.db.block_job(job_id, "manual_review", "Rejected by human reviewer")

        await query.edit_message_text(
            f"❌ <b>Rejected</b>: {job_id}\nJob blocked.",
            parse_mode="HTML",
        )
        logger.info(f"Job {job_id} rejected by reviewer")

    async def handle_regenerate(self, query, parts: list[str]):
        """Send video back for regeneration from a specific phase."""
        job_id = parts[1] if len(parts) > 1 else ""

        # Offer phase selection for regeneration
        buttons = [
            [
                InlineKeyboardButton("🖼️ Regen Images", callback_data=f"review_regen_phase:{job_id}:image"),
                InlineKeyboardButton("🎬 Regen Video", callback_data=f"review_regen_phase:{job_id}:video"),
            ],
            [
                InlineKeyboardButton("📝 Regen Script", callback_data=f"review_regen_phase:{job_id}:script"),
                InlineKeyboardButton("🔊 Regen Voice", callback_data=f"review_regen_phase:{job_id}:voice"),
            ],
            [
                InlineKeyboardButton("⬅️ Back", callback_data=f"review_back:{job_id}"),
            ],
        ]
        await query.edit_message_text(
            f"🔄 <b>Regenerate {job_id}</b>\nSelect what to regenerate:",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML",
        )

    async def handle_regen_phase(self, query, parts: list[str]):
        """Execute regeneration for a specific phase."""
        job_id = parts[1] if len(parts) > 1 else ""
        phase = parts[2] if len(parts) > 2 else "image"

        phase_map = {
            "script": "script",
            "image": "image_regen",
            "video": "video",
            "voice": "voice",
        }
        target_status = phase_map.get(phase, "image_regen")

        self.db.conn.execute(
            "UPDATE jobs SET manual_review_status = 'regen_requested', "
            "manual_review_at = ?, manual_review_notes = ? WHERE id = ?",
            (
                datetime.now().isoformat(),
                json.dumps({"regen_phase": phase}),
                job_id,
            ),
        )
        self.db.update_job_status(job_id, target_status)

        await query.edit_message_text(
            f"🔄 <b>Regenerating</b>: {job_id}\n"
            f"Phase: {phase}\nRestarting from {target_status}...",
            parse_mode="HTML",
        )
        logger.info(f"Job {job_id} sent for regeneration at phase={phase}")

        if self.pipeline_resume_callback:
            await self.pipeline_resume_callback(job_id)

    async def handle_edit(self, query, parts: list[str]):
        """Edit & approve — placeholder for future inline editing."""
        job_id = parts[1] if len(parts) > 1 else ""
        # For now, just approve with a note
        self.db.conn.execute(
            "UPDATE jobs SET manual_review_status = 'approved_with_edits', "
            "manual_review_at = ?, status = 'publish' WHERE id = ?",
            (datetime.now().isoformat(), job_id),
        )
        self.db.conn.commit()

        await query.edit_message_text(
            f"📝 <b>Approved with edits</b>: {job_id}\n"
            f"(Inline editing coming soon — publishing as-is)",
            parse_mode="HTML",
        )
        logger.info(f"Job {job_id} approved with edits")

        if self.pipeline_resume_callback:
            await self.pipeline_resume_callback(job_id)

    async def handle_back(self, query, parts: list[str]):
        """Go back to the main review buttons."""
        job_id = parts[1] if len(parts) > 1 else ""
        # Re-send review request is complex, just show main buttons again
        buttons = [
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"review_approve:{job_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"review_reject:{job_id}"),
            ],
            [
                InlineKeyboardButton("🔄 Regenerate", callback_data=f"review_regen:{job_id}"),
                InlineKeyboardButton("📝 Edit & Approve", callback_data=f"review_edit:{job_id}"),
            ],
        ]
        await query.edit_message_text(
            f"🔍 <b>Review</b>: {job_id}\nSelect action:",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML",
        )

    def get_callback_routes(self) -> dict:
        """
        Return callback routing map to register with TelegramHandlers.
        Keys are callback data prefixes, values are handler coroutines.
        """
        return {
            "review_approve": self.handle_approve,
            "review_reject": self.handle_reject,
            "review_regen": self.handle_regenerate,
            "review_regen_phase": self.handle_regen_phase,
            "review_edit": self.handle_edit,
            "review_back": self.handle_back,
        }
