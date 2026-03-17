"""
Telegram Handlers — Command handlers + callback routing.
Commands: /status, /queue, /cancel, /retry, /quota, /disk, /health, /new, /settings
Callback routing by prefix: approve_images, regen_scene, select_topic, rollback, etc.
"""

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

if TYPE_CHECKING:
    from src.core.database import FactoryDB
    from src.core.event_bus import EventBus
    from src.core.quota_tracker import QuotaTracker
    from src.core.storage_manager import StorageManager

logger = logging.getLogger(__name__)


class TelegramHandlers:
    """
    Command and callback handlers.
    Injected with DB, EventBus, etc. at startup.
    """

    def __init__(
        self,
        db: "FactoryDB",
        event_bus: "EventBus",
        quota_tracker: "QuotaTracker | None" = None,
        storage_manager: "StorageManager | None" = None,
    ):
        self.db = db
        self.events = event_bus
        self.quota = quota_tracker
        self.storage = storage_manager
        # Set by orchestrator after pipeline is wired
        self.pipeline_resume_callback = None

    # ------------------------------------------------------------------
    # Command Handlers
    # ------------------------------------------------------------------

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show current pipeline status."""
        jobs = self.db.get_active_jobs()
        if not jobs:
            await update.message.reply_text("📊 No active jobs.")
            return

        job = jobs[0]
        lines = [
            "📊 <b>Pipeline Status</b>",
            f"🎬 Job: <code>{job['id']}</code>",
            f"📋 Topic: {job.get('topic', 'N/A')}",
            f"🔄 Phase: <b>{job['status']}</b>",
            f"📅 Created: {job.get('created_at', '')}",
        ]
        if job.get("blocked_reason"):
            lines.append(f"⚠️ Blocked: {job['blocked_reason']}")

        queue_count = len(jobs) - 1
        if queue_count > 0:
            lines.append(f"\n⏳ Queue: {queue_count} more job(s)")

        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    async def cmd_queue(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show job queue."""
        active = self.db.get_active_jobs()
        blocked = self.db.get_blocked_jobs()

        lines = ["📋 <b>Job Queue</b>\n"]
        if active:
            for i, j in enumerate(active):
                icon = "🟢" if i == 0 else "⏳"
                lines.append(f"{icon} #{i+1}: {j.get('topic','?')} ({j['status']})")
        else:
            lines.append("No active jobs.")

        if blocked:
            lines.append(f"\n❌ Blocked: {len(blocked)}")
            for j in blocked[:3]:
                lines.append(f"  • {j.get('topic','?')} — {j.get('blocked_reason','')[:60]}")

        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    async def cmd_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel the active job (with confirmation)."""
        jobs = self.db.get_active_jobs()
        if not jobs:
            await update.message.reply_text("No active job to cancel.")
            return
        job = jobs[0]
        buttons = [[
            InlineKeyboardButton("✅ Yes, cancel", callback_data=f"cancel:{job['id']}"),
            InlineKeyboardButton("❌ No", callback_data="cancel:no"),
        ]]
        await update.message.reply_text(
            f"Cancel job <b>{job['id']}</b>?\nTopic: {job.get('topic','')}",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML",
        )

    async def cmd_retry(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Retry the latest blocked job."""
        blocked = self.db.get_blocked_jobs()
        if not blocked:
            await update.message.reply_text("No blocked jobs.")
            return
        job = blocked[0]
        buttons = [[
            InlineKeyboardButton("🔄 Retry", callback_data=f"retry:{job['id']}"),
            InlineKeyboardButton("❌ Cancel it", callback_data=f"cancel:{job['id']}"),
        ]]
        await update.message.reply_text(
            f"🔄 Retry <b>{job['id']}</b>?\n"
            f"Blocked at: {job.get('blocked_phase','?')}\n"
            f"Reason: {job.get('blocked_reason','')}",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML",
        )

    async def cmd_quota(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """YouTube API quota status."""
        if self.quota is None:
            await update.message.reply_text("Quota tracker not configured.")
            return
        status = self.quota.get_status()
        await update.message.reply_text(
            f"📊 <b>YouTube Quota</b>\n"
            f"Used: {status['used']}/{10000}\n"
            f"Remaining: {status['remaining']}\n"
            f"Max videos left: {status['max_videos_remaining']}\n"
            f"Resets: midnight Pacific Time",
            parse_mode="HTML",
        )

    async def cmd_disk(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Disk usage."""
        if self.storage is None:
            await update.message.reply_text("Storage manager not configured.")
            return
        usage = self.storage.get_disk_usage()
        await update.message.reply_text(
            f"💾 <b>Disk Usage</b>\n"
            f"Total used: {usage.get('total_gb', 0):.1f} GB\n"
            f"Jobs: {len(usage.get('by_job', {}))}\n"
            f"Est. days until full: {usage.get('estimated_days_until_full', '?')}",
            parse_mode="HTML",
        )

    async def cmd_health(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """System health overview."""
        lines = ["🏥 <b>System Health</b>\n"]
        # Basic checks
        try:
            import psutil
            ram = psutil.virtual_memory()
            disk = psutil.disk_usage(".")
            lines.append(f"🧠 RAM: {ram.available / (1024**3):.1f} GB free")
            lines.append(f"💾 Disk: {disk.free / (1024**3):.1f} GB free")
        except ImportError:
            lines.append("(psutil not available)")

        active = self.db.get_active_jobs()
        lines.append(f"🎬 Active jobs: {len(active)}")
        blocked = self.db.get_blocked_jobs()
        lines.append(f"❌ Blocked jobs: {len(blocked)}")
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    async def cmd_new(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start a new video — triggers topic selection flow."""
        await update.message.reply_text(
            "🎬 Starting new video pipeline...\n"
            "Researching topics. You'll get a selection shortly."
        )
        # In production, this would trigger Phase 1 via job queue
        # For now, acknowledge and let the orchestrator handle it.

    async def cmd_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """View/change settings."""
        buttons = [
            [InlineKeyboardButton("📋 Manual Review Mode", callback_data="settings:review_mode")],
            [InlineKeyboardButton("🔊 Default Voice", callback_data="settings:voice")],
            [InlineKeyboardButton("📺 Channel", callback_data="settings:channel")],
        ]
        await update.message.reply_text(
            "⚙️ <b>Settings</b>\nSelect an option:",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML",
        )

    # ------------------------------------------------------------------
    # Callback Router
    # ------------------------------------------------------------------

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Routes inline button callbacks by prefix.
        Callback data format: "action:job_id:extra" or "action:param".
        """
        query = update.callback_query
        await query.answer()  # Acknowledge within 5s

        data = query.data or ""
        parts = data.split(":")
        action = parts[0]

        ROUTES = {
            "approve_images": self._handle_approve_images,
            "regen_failed": self._handle_regen_failed,
            "regen_scene": self._handle_regen_scene,
            "approve_videos": self._handle_approve_videos,
            "approve_final": self._handle_approve_final,
            "reject_final": self._handle_reject_final,
            "publish": self._handle_publish,
            "cancel": self._handle_cancel,
            "retry": self._handle_retry,
            "select_topic": self._handle_select_topic,
            "rollback": self._handle_rollback,
            "edit_prompt": self._handle_edit_prompt,
            "settings": self._handle_settings,
        }

        handler = ROUTES.get(action)
        if handler:
            try:
                await handler(query, parts)
            except Exception as e:
                logger.error(f"Callback handler error ({action}): {e}", exc_info=True)
                await query.edit_message_text(f"❌ Error: {str(e)[:200]}")
        else:
            logger.warning(f"Unknown callback action: {action}")

    # ------------------------------------------------------------------
    # Callback Implementations
    # ------------------------------------------------------------------

    async def _handle_approve_images(self, query, parts):
        job_id = parts[1] if len(parts) > 1 else ""
        self.db.update_job_status(job_id, "video")
        await query.edit_message_text(f"✅ Images approved for {job_id}. Starting video generation...")
        if self.pipeline_resume_callback:
            await self.pipeline_resume_callback(job_id)

    async def _handle_regen_failed(self, query, parts):
        job_id = parts[1] if len(parts) > 1 else ""
        self.db.update_job_status(job_id, "image_regen")
        await query.edit_message_text(f"🔄 Regenerating failed images for {job_id}...")
        if self.pipeline_resume_callback:
            await self.pipeline_resume_callback(job_id)

    async def _handle_regen_scene(self, query, parts):
        job_id = parts[1] if len(parts) > 1 else ""
        scene_idx = parts[2] if len(parts) > 2 else "?"
        await query.edit_message_text(f"🔄 Regenerating scene {scene_idx} for {job_id}...")

    async def _handle_approve_videos(self, query, parts):
        job_id = parts[1] if len(parts) > 1 else ""
        self.db.update_job_status(job_id, "voice")
        await query.edit_message_text(f"✅ Videos approved for {job_id}. Starting voice generation...")
        if self.pipeline_resume_callback:
            await self.pipeline_resume_callback(job_id)

    async def _handle_approve_final(self, query, parts):
        job_id = parts[1] if len(parts) > 1 else ""
        self.db.update_job_status(job_id, "publish")
        await query.edit_message_text(f"✅ Final approved for {job_id}. Publishing...")
        if self.pipeline_resume_callback:
            await self.pipeline_resume_callback(job_id)

    async def _handle_reject_final(self, query, parts):
        job_id = parts[1] if len(parts) > 1 else ""
        self.db.block_job(job_id, "manual_review", "Rejected by human reviewer")
        await query.edit_message_text(f"❌ Video rejected: {job_id}")

    async def _handle_publish(self, query, parts):
        job_id = parts[1] if len(parts) > 1 else ""
        self.db.update_job_status(job_id, "publish")
        await query.edit_message_text(f"🚀 Publishing {job_id}...")
        if self.pipeline_resume_callback:
            await self.pipeline_resume_callback(job_id)

    async def _handle_cancel(self, query, parts):
        param = parts[1] if len(parts) > 1 else ""
        if param == "no":
            await query.edit_message_text("Cancelled — job continues.")
            return
        self.db.update_job_status(param, "cancelled")
        await query.edit_message_text(f"❌ Job {param} cancelled.")

    async def _handle_retry(self, query, parts):
        job_id = parts[1] if len(parts) > 1 else ""
        job = self.db.get_job(job_id)
        if not job:
            await query.edit_message_text(f"Job {job_id} not found.")
            return
        resume_phase = job.get("blocked_phase", "pending")
        self.db.update_job_status(job_id, resume_phase)
        await query.edit_message_text(f"🔄 Retrying {job_id} from {resume_phase}...")
        if self.pipeline_resume_callback:
            await self.pipeline_resume_callback(job_id)

    async def _handle_select_topic(self, query, parts):
        job_id = parts[1] if len(parts) > 1 else ""
        topic_idx = int(parts[2]) if len(parts) > 2 else 0
        # Store selected topic
        rows = self.db.conn.execute(
            "SELECT topic FROM research WHERE job_id = ? ORDER BY rank_score DESC",
            (job_id,),
        ).fetchall()
        if topic_idx < len(rows):
            topic = rows[topic_idx]["topic"]
            self.db.conn.execute(
                "UPDATE jobs SET topic = ? WHERE id = ?", (topic, job_id)
            )
            self.db.conn.commit()
            self.db.update_job_status(job_id, "seo")
            await query.edit_message_text(f"✅ Topic selected: {topic}\nStarting SEO...")
            if self.pipeline_resume_callback:
                await self.pipeline_resume_callback(job_id)
        else:
            await query.edit_message_text("Invalid topic selection.")

    async def _handle_rollback(self, query, parts):
        job_id = parts[1] if len(parts) > 1 else ""
        scene_idx = parts[2] if len(parts) > 2 else "0"
        version = parts[3] if len(parts) > 3 else "1"
        await query.edit_message_text(
            f"🔄 Rolling back scene {scene_idx} to v{version} for {job_id}..."
        )

    async def _handle_edit_prompt(self, query, parts):
        job_id = parts[1] if len(parts) > 1 else ""
        scene_idx = int(parts[2]) if len(parts) > 2 else 0
        scenes = self.db.get_scenes(job_id)
        current_prompt = ""
        for s in scenes:
            if s["scene_index"] == scene_idx:
                current_prompt = s.get("visual_prompt", "")
                break
        await query.edit_message_text(
            f"✏️ Scene {scene_idx} — Send new visual prompt:\n\n"
            f"Current:\n<code>{current_prompt[:500]}</code>",
            parse_mode="HTML",
        )

    async def _handle_settings(self, query, parts):
        setting = parts[1] if len(parts) > 1 else ""
        await query.edit_message_text(f"⚙️ Setting: {setting}\n(Not yet implemented)")
