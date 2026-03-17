"""
Telegram Conversations — Multi-step conversation flows.
- Topic selection flow (5 topics → user taps → confirm)
- Manual review flow (approve/changes/reject with sub-options)
Uses python-telegram-bot v20+ ConversationHandler.
"""

import logging
from typing import TYPE_CHECKING

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ConversationHandler,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

if TYPE_CHECKING:
    from src.core.database import FactoryDB

logger = logging.getLogger(__name__)

# ─── Conversation States ───────────────────────────────────────
TOPIC_SELECT, TOPIC_CONFIRM = range(2)
REVIEW_DECISION, REVIEW_CHANGES, REVIEW_SCENE_SELECT = range(10, 13)


class TopicSelectionFlow:
    """
    Topic selection conversation.
    Triggered when Phase 1 completes and topics are ready.

    Flow:
    1. Bot sends top 5 topics with scores
    2. User taps one → confirm
    3. User can also type a custom topic
    """

    def __init__(self, db: "FactoryDB"):
        self.db = db

    async def entry(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Entry: show topic list. Triggered by callback 'topics_ready:{job_id}'."""
        query = update.callback_query
        if query:
            await query.answer()

        data = (query.data if query else "") or ""
        job_id = data.split(":", 1)[1] if ":" in data else ""
        context.user_data["topic_job_id"] = job_id

        # Fetch researched topics
        rows = self.db.conn.execute(
            "SELECT topic, rank_score, suggested_angle, category "
            "FROM research WHERE job_id = ? ORDER BY rank_score DESC LIMIT 5",
            (job_id,),
        ).fetchall()

        if not rows:
            text = "🔍 No topics found. Type a custom topic:"
            if query:
                await query.edit_message_text(text)
            else:
                await update.message.reply_text(text)
            return TOPIC_SELECT

        lines = ["🔍 <b>Select a topic:</b>\n"]
        buttons = []
        for i, r in enumerate(rows):
            score = r["rank_score"] or 0
            lines.append(
                f"{i+1}️⃣ {r['topic']}\n"
                f"   Score: {score:.1f} | {r.get('category', '')}"
            )
            buttons.append([InlineKeyboardButton(
                f"{i+1}️⃣ {r['topic'][:40]}",
                callback_data=f"sel_topic:{job_id}:{i}",
            )])

        buttons.append([
            InlineKeyboardButton("🔄 New Topics", callback_data=f"refresh_topics:{job_id}"),
        ])
        text = "\n".join(lines) + "\n\nOr type a custom topic:"
        markup = InlineKeyboardMarkup(buttons)

        if query:
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
        else:
            await update.message.reply_text(text, reply_markup=markup, parse_mode="HTML")
        return TOPIC_SELECT

    async def topic_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """User tapped a topic button."""
        query = update.callback_query
        await query.answer()
        parts = query.data.split(":")
        job_id = parts[1] if len(parts) > 1 else context.user_data.get("topic_job_id", "")
        idx = int(parts[2]) if len(parts) > 2 else 0

        rows = self.db.conn.execute(
            "SELECT topic FROM research WHERE job_id = ? ORDER BY rank_score DESC LIMIT 5",
            (job_id,),
        ).fetchall()

        if idx < len(rows):
            topic = rows[idx]["topic"]
            context.user_data["selected_topic"] = topic
            buttons = [[
                InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_topic:{job_id}"),
                InlineKeyboardButton("🔙 Back", callback_data="back_to_topics"),
            ]]
            await query.edit_message_text(
                f"Selected: <b>{topic}</b>\n\nConfirm?",
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode="HTML",
            )
            return TOPIC_CONFIRM
        await query.edit_message_text("Invalid selection.")
        return ConversationHandler.END

    async def topic_refresh(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Refresh topics — re-run research."""
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("🔄 Refreshing topics... (re-running research)")
        return ConversationHandler.END

    async def custom_topic(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """User typed a custom topic."""
        topic = update.message.text.strip()
        job_id = context.user_data.get("topic_job_id", "")
        context.user_data["selected_topic"] = topic
        buttons = [[
            InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_topic:{job_id}"),
            InlineKeyboardButton("🔙 Back", callback_data="back_to_topics"),
        ]]
        await update.message.reply_text(
            f"Custom topic: <b>{topic}</b>\n\nConfirm?",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML",
        )
        return TOPIC_CONFIRM

    async def topic_confirmed(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Topic confirmed — update DB and resume pipeline."""
        query = update.callback_query
        await query.answer()
        parts = query.data.split(":")
        job_id = parts[1] if len(parts) > 1 else context.user_data.get("topic_job_id", "")
        topic = context.user_data.get("selected_topic", "")

        self.db.conn.execute("UPDATE jobs SET topic = ? WHERE id = ?", (topic, job_id))
        self.db.conn.commit()
        self.db.update_job_status(job_id, "seo")

        await query.edit_message_text(f"✅ Topic confirmed: {topic}\nStarting SEO phase...")
        return ConversationHandler.END

    async def topic_back(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Go back to topic list."""
        return await self.entry(update, context)

    def build_handler(self) -> ConversationHandler:
        return ConversationHandler(
            entry_points=[
                CallbackQueryHandler(self.entry, pattern=r"^topics_ready:"),
            ],
            states={
                TOPIC_SELECT: [
                    CallbackQueryHandler(self.topic_selected, pattern=r"^sel_topic:"),
                    CallbackQueryHandler(self.topic_refresh, pattern=r"^refresh_topics:"),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.custom_topic),
                ],
                TOPIC_CONFIRM: [
                    CallbackQueryHandler(self.topic_confirmed, pattern=r"^confirm_topic:"),
                    CallbackQueryHandler(self.topic_back, pattern=r"^back_to_topics"),
                ],
            },
            fallbacks=[CommandHandler("cancel", _cancel)],
            per_message=False,
        )


class ManualReviewFlow:
    """
    Manual review conversation.
    Triggered when Phase 7.5 requests human review.

    Flow:
    1. Bot sends final video + QA scores
    2. User: Approve / Request Changes / Reject
    3. If changes: specify what (scene, script, audio, full regen)
    """

    def __init__(self, db: "FactoryDB"):
        self.db = db

    async def entry(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Entry: show review options."""
        query = update.callback_query
        if query:
            await query.answer()

        data = (query.data if query else "") or ""
        job_id = data.split(":", 1)[1] if ":" in data else ""
        context.user_data["review_job_id"] = job_id

        job = self.db.get_job(job_id)
        topic = job.get("topic", "N/A") if job else "N/A"

        buttons = [
            [InlineKeyboardButton("✅ Approve & Publish", callback_data=f"rev_approve:{job_id}")],
            [InlineKeyboardButton("✏️ Request Changes", callback_data=f"rev_changes:{job_id}")],
            [InlineKeyboardButton("❌ Reject", callback_data=f"rev_reject:{job_id}")],
        ]
        text = (
            f"🎬 <b>REVIEW REQUIRED</b>\n\n"
            f"Job: <code>{job_id}</code>\n"
            f"Topic: {topic}\n\n"
            f"Choose an action:"
        )
        if query:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")
        return REVIEW_DECISION

    async def approve(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        job_id = query.data.split(":")[1] if ":" in query.data else ""
        self.db.update_job_status(job_id, "publish")
        await query.edit_message_text(f"✅ Approved! Publishing {job_id}...")
        return ConversationHandler.END

    async def request_changes(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        job_id = query.data.split(":")[1] if ":" in query.data else ""
        context.user_data["review_job_id"] = job_id

        buttons = [
            [InlineKeyboardButton("🖼️ Specific Scene", callback_data=f"chg_scene:{job_id}")],
            [InlineKeyboardButton("📝 Script", callback_data=f"chg_script:{job_id}")],
            [InlineKeyboardButton("🎵 Audio", callback_data=f"chg_audio:{job_id}")],
            [InlineKeyboardButton("🎬 Full Regen", callback_data=f"chg_full:{job_id}")],
            [InlineKeyboardButton("🔙 Back", callback_data=f"rev_back:{job_id}")],
        ]
        await query.edit_message_text(
            "What needs changing?",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return REVIEW_CHANGES

    async def reject(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        job_id = query.data.split(":")[1] if ":" in query.data else ""
        self.db.block_job(job_id, "manual_review", "Rejected by reviewer")
        await query.edit_message_text(f"❌ Video rejected: {job_id}")
        return ConversationHandler.END

    async def change_scene(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        job_id = query.data.split(":")[1] if ":" in query.data else ""
        scenes = self.db.get_scenes(job_id)
        buttons = []
        for s in scenes[:15]:
            idx = s["scene_index"]
            buttons.append([InlineKeyboardButton(
                f"Scene {idx}: {s.get('narration_text','')[:30]}...",
                callback_data=f"scene_pick:{job_id}:{idx}",
            )])
        await query.edit_message_text(
            "Select scene to change:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return REVIEW_SCENE_SELECT

    async def change_script(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        job_id = query.data.split(":")[1] if ":" in query.data else ""
        self.db.update_job_status(job_id, "script")
        await query.edit_message_text(f"📝 Re-running script phase for {job_id}...")
        return ConversationHandler.END

    async def change_audio(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        job_id = query.data.split(":")[1] if ":" in query.data else ""
        self.db.update_job_status(job_id, "voice")
        await query.edit_message_text(f"🎵 Re-running audio for {job_id}...")
        return ConversationHandler.END

    async def change_full(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        job_id = query.data.split(":")[1] if ":" in query.data else ""
        self.db.update_job_status(job_id, "images")
        await query.edit_message_text(f"🎬 Full regeneration for {job_id}...")
        return ConversationHandler.END

    async def scene_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        parts = query.data.split(":")
        job_id = parts[1] if len(parts) > 1 else ""
        scene_idx = parts[2] if len(parts) > 2 else "0"
        context.user_data["change_scene"] = {"job_id": job_id, "scene_index": scene_idx}
        await query.edit_message_text(
            f"Scene {scene_idx} selected.\nType your change instructions:"
        )
        return REVIEW_SCENE_SELECT

    async def scene_custom_instruction(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        text = update.message.text
        info = context.user_data.get("change_scene", {})
        job_id = info.get("job_id", "")
        scene_idx = info.get("scene_index", "0")
        await update.message.reply_text(
            f"📝 Got it. Will re-generate scene {scene_idx} with your instructions:\n"
            f"<i>{text[:200]}</i>",
            parse_mode="HTML",
        )
        # In production: store instruction, trigger regen
        return ConversationHandler.END

    async def back_to_review(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        return await self.entry(update, context)

    def build_handler(self) -> ConversationHandler:
        return ConversationHandler(
            entry_points=[
                CallbackQueryHandler(self.entry, pattern=r"^review_ready:"),
            ],
            states={
                REVIEW_DECISION: [
                    CallbackQueryHandler(self.approve, pattern=r"^rev_approve:"),
                    CallbackQueryHandler(self.request_changes, pattern=r"^rev_changes:"),
                    CallbackQueryHandler(self.reject, pattern=r"^rev_reject:"),
                ],
                REVIEW_CHANGES: [
                    CallbackQueryHandler(self.change_scene, pattern=r"^chg_scene:"),
                    CallbackQueryHandler(self.change_script, pattern=r"^chg_script:"),
                    CallbackQueryHandler(self.change_audio, pattern=r"^chg_audio:"),
                    CallbackQueryHandler(self.change_full, pattern=r"^chg_full:"),
                    CallbackQueryHandler(self.back_to_review, pattern=r"^rev_back:"),
                ],
                REVIEW_SCENE_SELECT: [
                    CallbackQueryHandler(self.scene_selected, pattern=r"^scene_pick:"),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.scene_custom_instruction),
                ],
            },
            fallbacks=[CommandHandler("cancel", _cancel)],
            per_message=False,
        )


# ─── Shared ────────────────────────────────────────────────────

async def _cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Conversation cancelled.")
    return ConversationHandler.END
