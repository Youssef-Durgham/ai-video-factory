"""
Telegram Bot Command Handlers — Interactive control for the video pipeline.
Commands: /start, /new, /jobs, /status, /help, /queue, /logs, /stats
All UI text in Arabic (MSA).
"""

import logging
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler

logger = logging.getLogger(__name__)

# Phase order for progress bar
PHASE_ORDER = [
    "research", "seo", "script", "compliance", "images",
    "video", "voice", "music", "compose",
]

PHASE_NAMES_AR = {
    "pending": "في الانتظار", "research": "البحث", "seo": "تحسين محركات البحث",
    "script": "كتابة السكربت", "compliance": "فحص الامتثال",
    "images": "توليد الصور", "image_qa": "فحص الصور", "image_regen": "إعادة توليد الصور",
    "video": "إنتاج الفيديو", "video_qa": "فحص الفيديو", "video_regen": "إعادة إنتاج الفيديو",
    "voice": "التعليق الصوتي", "music": "الموسيقى", "sfx": "المؤثرات الصوتية",
    "compose": "التجميع النهائي", "overlay_qa": "فحص النصوص",
    "final_qa": "الفحص النهائي", "manual_review": "المراجعة اليدوية",
    "publish": "النشر", "published": "تم النشر", "blocked": "محظور",
    "cancelled": "ملغي", "complete": "مكتمل",
}

STATUS_EMOJI = {
    "pending": "⏳", "research": "🔬", "seo": "🔎", "script": "📝",
    "compliance": "✅", "images": "🎨", "image_qa": "🔍", "image_regen": "🔄",
    "video": "🎬", "video_qa": "🔍", "video_regen": "🔄",
    "voice": "🎙️", "music": "🎵", "sfx": "🔊", "compose": "🎞️",
    "overlay_qa": "🔍", "final_qa": "✔️", "manual_review": "👁️",
    "publish": "📤", "published": "✅", "blocked": "🚫", "cancelled": "❌",
    "complete": "🏁",
}


def _get_db():
    from src.core.config import load_config
    from src.core.database import FactoryDB
    config = load_config()
    db_path = config.get("settings", {}).get("database", {}).get("path", "data/factory.db")
    return FactoryDB(db_path), config


def _progress_bar(status: str) -> str:
    """Generate a progress bar based on current phase."""
    try:
        idx = PHASE_ORDER.index(status)
    except ValueError:
        # Handle sub-phases
        mapping = {"image_qa": "images", "image_regen": "images", "video_qa": "video",
                   "video_regen": "video", "sfx": "music", "overlay_qa": "compose",
                   "final_qa": "compose", "manual_review": "compose", "publish": "compose",
                   "published": "compose", "complete": "compose"}
        mapped = mapping.get(status, "")
        try:
            idx = PHASE_ORDER.index(mapped)
        except ValueError:
            return ""
    total = len(PHASE_ORDER)
    filled = idx + 1
    bar = "█" * filled + "░" * (total - filled)
    return f"{bar} {filled}/{total}"


def _time_elapsed(created_at: str) -> str:
    """Calculate elapsed time since creation."""
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        delta = now - created
        hours = int(delta.total_seconds() // 3600)
        minutes = int((delta.total_seconds() % 3600) // 60)
        if hours > 24:
            return f"{hours // 24} يوم {hours % 24} ساعة"
        elif hours > 0:
            return f"{hours} ساعة {minutes} دقيقة"
        else:
            return f"{minutes} دقيقة"
    except Exception:
        return "—"


# ═══════════════════════════════════════════════════════════════
# /start — Main menu
# ═══════════════════════════════════════════════════════════════

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main menu with inline buttons."""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🆕 مشروع جديد", callback_data="menu_new")],
        [InlineKeyboardButton("📋 مشاريعي", callback_data="menu_jobs")],
        [InlineKeyboardButton("📊 الإحصائيات", callback_data="menu_stats")],
        [InlineKeyboardButton("⚙️ الإعدادات", callback_data="menu_settings")],
    ])
    await update.message.reply_text(
        "🏭 <b>مصنع الفيديو الذكي</b>\n\n"
        "مرحباً! اختر من القائمة أدناه:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


# ═══════════════════════════════════════════════════════════════
# /help — Full command list
# ═══════════════════════════════════════════════════════════════

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all available commands with descriptions."""
    text = (
        "📖 <b>قائمة الأوامر</b>\n\n"
        "🏠 <b>الأوامر الأساسية:</b>\n"
        "  /start — القائمة الرئيسية\n"
        "  /help — عرض هذه القائمة\n\n"
        "📝 <b>إدارة المشاريع:</b>\n"
        "  /new [موضوع] — إنشاء مشروع جديد\n"
        "  /jobs — عرض جميع المشاريع\n"
        "  /status — حالة المشروع النشط\n\n"
        "📊 <b>المراقبة:</b>\n"
        "  /queue — حالة الطابور\n"
        "  /logs [job_id] — سجلات المشروع\n"
        "  /stats — الإحصائيات العامة\n\n"
        "💡 <b>نصائح:</b>\n"
        "  • استخدم الأزرار التفاعلية للتحكم بالمشاريع\n"
        "  • يمكنك إرجاع أي مشروع لأي مرحلة سابقة\n"
        "  • السكربت يتطلب موافقتك قبل المتابعة\n"
    )
    await update.message.reply_text(text, parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════
# /new — Start new video project
# ═══════════════════════════════════════════════════════════════

async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start a new video project."""
    topic = " ".join(context.args) if context.args else None

    if topic:
        await update.message.reply_text(
            f"📝 <b>بدء مشروع جديد</b>\n\n"
            f"الموضوع: <i>{topic}</i>\n\n"
            "جاري إنشاء المشروع...",
            parse_mode="HTML",
        )
        try:
            from src.core.config import load_config
            from src.core.database import FactoryDB

            config = load_config()
            db_path = config.get("settings", {}).get("database", {}).get("path", "data/factory.db")
            db = FactoryDB(db_path)
            channels = config.get("channels", [])
            if isinstance(channels, dict):
                channels = channels.get("channels", [])
            channel_id = channels[0]["id"] if channels else "default"

            job_id = db.create_job(channel_id, topic, topic_source="manual")
            db.update_job_status(job_id, "research")

            await update.message.reply_text(
                f"✅ <b>تم إنشاء المشروع</b>\n\n"
                f"🆔 <code>{job_id}</code>\n"
                f"📝 {topic}\n\n"
                "سيبدأ التشغيل عند توفر الدور في الطابور.",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"Failed to create job: {e}", exc_info=True)
            await update.message.reply_text(f"❌ خطأ في إنشاء المشروع: {e}")
    else:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔍 بحث تلقائي عن مواضيع", callback_data="new_auto_research")],
            [InlineKeyboardButton("◀️ رجوع", callback_data="menu_main")],
        ])
        await update.message.reply_text(
            "📝 <b>مشروع جديد</b>\n\n"
            "أرسل الموضوع مباشرة:\n"
            "<code>/new اسم الموضوع</code>\n\n"
            "أو اختر بحث تلقائي:",
            reply_markup=keyboard,
            parse_mode="HTML",
        )


# ═══════════════════════════════════════════════════════════════
# /jobs — List all jobs (enhanced)
# ═══════════════════════════════════════════════════════════════

async def jobs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all jobs with enhanced info: progress bar, time, word count."""
    try:
        db, config = _get_db()

        rows = db.conn.execute(
            "SELECT id, topic, status, created_at FROM jobs ORDER BY created_at DESC LIMIT 20"
        ).fetchall()

        if not rows:
            await update.message.reply_text("📭 لا توجد مشاريع حالياً.\n\nاستخدم /new لإنشاء مشروع جديد.")
            return

        for row in rows:
            job = dict(row)
            job_id = job["id"]
            emoji = STATUS_EMOJI.get(job["status"], "❓")
            topic_short = (job["topic"] or "بدون موضوع")[:60]
            phase_ar = PHASE_NAMES_AR.get(job["status"], job["status"])
            elapsed = _time_elapsed(job["created_at"]) if job["created_at"] else "—"
            progress = _progress_bar(job["status"])

            text = (
                f"{emoji} <b>{topic_short}</b>\n"
                f"📊 {phase_ar}"
            )
            if progress:
                text += f"\n{progress}"
            text += f"\n⏱️ {elapsed}"

            # Get script word count if available
            script_row = db.conn.execute(
                "SELECT word_count FROM scripts WHERE job_id = ? ORDER BY version DESC LIMIT 1",
                (job_id,)
            ).fetchone()
            if script_row and dict(script_row).get("word_count"):
                text += f" | 📝 {dict(script_row)['word_count']} كلمة"

            # Get image count
            img_count = db.conn.execute(
                "SELECT COUNT(*) as c FROM scenes WHERE job_id = ?", (job_id,)
            ).fetchone()
            if img_count and dict(img_count)["c"] > 0:
                text += f" | 🖼️ {dict(img_count)['c']} صورة"

            text += f"\n🆔 <code>{job_id}</code>"

            buttons = []
            if job["status"] not in ("published", "cancelled", "complete"):
                buttons.append([
                    InlineKeyboardButton("▶️ استئناف", callback_data=f"jr_{job_id}"),
                    InlineKeyboardButton("📊 تفاصيل", callback_data=f"jd_{job_id}"),
                ])
                buttons.append([
                    InlineKeyboardButton("⏪ العودة إلى...", callback_data=f"jgm_{job_id}"),
                    InlineKeyboardButton("🗑️ حذف", callback_data=f"jx_{job_id}"),
                ])
            else:
                buttons.append([
                    InlineKeyboardButton("📊 تفاصيل", callback_data=f"jd_{job_id}"),
                ])

            keyboard = InlineKeyboardMarkup(buttons) if buttons else None
            await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Failed to list jobs: {e}", exc_info=True)
        await update.message.reply_text(f"❌ خطأ: {e}")


# ═══════════════════════════════════════════════════════════════
# /status — Current job status
# ═══════════════════════════════════════════════════════════════

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show status of the most recent active job."""
    try:
        db, config = _get_db()

        row = db.conn.execute(
            "SELECT * FROM jobs WHERE status NOT IN ('published','cancelled','complete') "
            "ORDER BY created_at DESC LIMIT 1"
        ).fetchone()

        if not row:
            await update.message.reply_text("📭 لا توجد مشاريع نشطة حالياً.")
            return

        job = dict(row)
        topic = job.get("topic", "بدون موضوع")
        status = job.get("status", "unknown")
        created = job.get("created_at", "?")[:19]
        blocked_reason = job.get("blocked_reason", "")

        phase_ar = PHASE_NAMES_AR.get(status, status)
        progress = _progress_bar(status)
        elapsed = _time_elapsed(job.get("created_at", ""))

        text = (
            f"📊 <b>حالة المشروع</b>\n\n"
            f"📝 <b>الموضوع:</b> {topic}\n"
            f"🔄 <b>المرحلة:</b> {phase_ar} ({status})\n"
        )
        if progress:
            text += f"{progress}\n"
        text += (
            f"⏱️ <b>الوقت المنقضي:</b> {elapsed}\n"
            f"📅 <b>تاريخ الإنشاء:</b> {created}\n"
            f"🆔 <code>{job['id']}</code>"
        )
        if blocked_reason:
            text += f"\n\n🚫 <b>سبب الحظر:</b> {blocked_reason}"

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("▶️ استئناف", callback_data=f"jr_{job['id']}"),
                InlineKeyboardButton("📊 تفاصيل", callback_data=f"jd_{job['id']}"),
            ],
        ])
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Status command error: {e}", exc_info=True)
        await update.message.reply_text(f"❌ خطأ: {e}")


# ═══════════════════════════════════════════════════════════════
# /queue — Queue status
# ═══════════════════════════════════════════════════════════════

async def queue_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show queue status with positions and priorities."""
    try:
        db, _ = _get_db()

        # Active (non-terminal, non-paused) jobs
        rows = db.conn.execute(
            "SELECT id, topic, status, created_at FROM jobs "
            "WHERE status NOT IN ('published','cancelled','complete','blocked','manual_review') "
            "ORDER BY created_at ASC"
        ).fetchall()

        paused = db.conn.execute(
            "SELECT id, topic, status FROM jobs "
            "WHERE status IN ('blocked','manual_review') "
            "ORDER BY created_at ASC"
        ).fetchall()

        if not rows and not paused:
            await update.message.reply_text("📭 الطابور فارغ.\n\nاستخدم /new لإنشاء مشروع جديد.")
            return

        text = "📋 <b>حالة الطابور</b>\n\n"

        if rows:
            text += "▶️ <b>قيد التنفيذ:</b>\n"
            for i, row in enumerate(rows):
                job = dict(row)
                emoji = STATUS_EMOJI.get(job["status"], "❓")
                topic_short = (job["topic"] or "—")[:40]
                text += f"  {i+1}. {emoji} {topic_short} — {job['status']}\n"

        if paused:
            text += "\n⏸️ <b>متوقفة:</b>\n"
            for row in paused:
                job = dict(row)
                emoji = STATUS_EMOJI.get(job["status"], "❓")
                topic_short = (job["topic"] or "—")[:40]
                text += f"  {emoji} {topic_short} — {PHASE_NAMES_AR.get(job['status'], job['status'])}\n"

        text += f"\n📊 في الطابور: {len(rows)} | متوقفة: {len(paused)}"
        await update.message.reply_text(text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Queue command error: {e}", exc_info=True)
        await update.message.reply_text(f"❌ خطأ: {e}")


# ═══════════════════════════════════════════════════════════════
# /logs [job_id] — Recent log entries
# ═══════════════════════════════════════════════════════════════

async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show recent log entries for a job or the most recent job."""
    try:
        db, _ = _get_db()
        job_id = context.args[0] if context.args else None

        if not job_id:
            row = db.conn.execute(
                "SELECT id FROM jobs ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            if not row:
                await update.message.reply_text("📭 لا توجد مشاريع.")
                return
            job_id = dict(row)["id"]

        # Try to get events/logs from DB
        job = db.get_job(job_id)
        if not job:
            await update.message.reply_text(f"❌ المشروع غير موجود: <code>{job_id}</code>", parse_mode="HTML")
            return

        text = f"📋 <b>سجلات المشروع</b>\n🆔 <code>{job_id}</code>\n\n"

        # Show phase timestamps
        ts_fields = [
            ("phase1_completed_at", "🔬 البحث"),
            ("phase2_completed_at", "🔎 SEO"),
            ("phase3_completed_at", "📝 السكربت"),
            ("phase4_completed_at", "✅ الامتثال"),
            ("phase5_completed_at", "🎨 الصور"),
            ("phase6_completed_at", "🔍 فحص الصور"),
            ("phase7_completed_at", "🎬 الإنتاج"),
            ("phase7_5_completed_at", "👁️ المراجعة"),
            ("phase8_completed_at", "📤 النشر"),
        ]

        for field, label in ts_fields:
            val = job.get(field)
            if val:
                text += f"✅ {label}: {str(val)[:19]}\n"
            else:
                text += f"⬜ {label}: —\n"

        if job.get("blocked_reason"):
            text += f"\n🚫 <b>آخر خطأ:</b> {job['blocked_reason'][:200]}"

        await update.message.reply_text(text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Logs command error: {e}", exc_info=True)
        await update.message.reply_text(f"❌ خطأ: {e}")


# ═══════════════════════════════════════════════════════════════
# /stats — Statistics
# ═══════════════════════════════════════════════════════════════

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show overall statistics."""
    try:
        db, _ = _get_db()

        total = db.conn.execute("SELECT COUNT(*) as c FROM jobs").fetchone()
        total_count = dict(total)["c"] if total else 0

        published = db.conn.execute(
            "SELECT COUNT(*) as c FROM jobs WHERE status IN ('published','complete')"
        ).fetchone()
        published_count = dict(published)["c"] if published else 0

        blocked = db.conn.execute(
            "SELECT COUNT(*) as c FROM jobs WHERE status = 'blocked'"
        ).fetchone()
        blocked_count = dict(blocked)["c"] if blocked else 0

        active = db.conn.execute(
            "SELECT COUNT(*) as c FROM jobs WHERE status NOT IN ('published','cancelled','complete','blocked')"
        ).fetchone()
        active_count = dict(active)["c"] if active else 0

        cancelled = db.conn.execute(
            "SELECT COUNT(*) as c FROM jobs WHERE status = 'cancelled'"
        ).fetchone()
        cancelled_count = dict(cancelled)["c"] if cancelled else 0

        success_rate = (published_count / total_count * 100) if total_count > 0 else 0

        text = (
            "📊 <b>الإحصائيات العامة</b>\n\n"
            f"📁 <b>إجمالي المشاريع:</b> {total_count}\n"
            f"✅ <b>مكتملة/منشورة:</b> {published_count}\n"
            f"▶️ <b>نشطة:</b> {active_count}\n"
            f"🚫 <b>محظورة:</b> {blocked_count}\n"
            f"❌ <b>ملغاة:</b> {cancelled_count}\n\n"
            f"📈 <b>نسبة النجاح:</b> {success_rate:.0f}%\n"
        )

        await update.message.reply_text(text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Stats command error: {e}", exc_info=True)
        await update.message.reply_text(f"❌ خطأ: {e}")


# ═══════════════════════════════════════════════════════════════
# /voices — List voice profiles
# ═══════════════════════════════════════════════════════════════

async def voices_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all available voice profiles."""
    try:
        from src.phase5_production.voice_cloner import VoiceCloner
        cloner = VoiceCloner()
        voices = cloner.list_voices()
        default_id = cloner.get_default_voice_id()

        if not voices:
            await update.message.reply_text(
                "🎙️ <b>الأصوات المتاحة</b>\n\n"
                "📭 لا توجد أصوات مُسجلة.\n\n"
                "اذهب إلى ⚙️ الإعدادات → 🎙️ إدارة الأصوات لإضافة صوت جديد.",
                parse_mode="HTML",
            )
            return

        text = f"🎙️ <b>الأصوات المتاحة — {len(voices)} صوت</b>\n\n"
        for v in voices:
            star = " ⭐ افتراضي" if v.voice_id == default_id else ""
            text += (
                f"👤 <b>{v.name}</b> (<code>{v.voice_id}</code>){star}\n"
                f"   ⏱️ مدة العينة: {v.duration_sec:.1f}ث\n"
                f"   📅 {v.created_at[:10]}\n\n"
            )

        text += "💡 استخدم ⚙️ الإعدادات → 🎙️ إدارة الأصوات للتعديل والاختبار."
        await update.message.reply_text(text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Voices command error: {e}", exc_info=True)
        await update.message.reply_text(f"❌ خطأ: {e}")


# ═══════════════════════════════════════════════════════════════
# Handler Registration
# ═══════════════════════════════════════════════════════════════

def register_commands(app):
    """Register all command handlers with the bot Application."""
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("new", new_command))
    app.add_handler(CommandHandler("jobs", jobs_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("queue", queue_command))
    app.add_handler(CommandHandler("logs", logs_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("voices", voices_command))
    logger.info("Telegram command handlers registered")
