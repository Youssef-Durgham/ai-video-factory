"""
Telegram Callback Query Router — handles all inline button presses.
Routes callbacks to appropriate handlers for topics, scripts, images, jobs.
All UI text in Arabic (MSA).
"""

import json
import logging
import os
import re
import threading
from pathlib import Path
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters


def _parse_time(t: str) -> float:
    """Parse 'm:ss' or 'ss' to seconds. E.g. '1:30' → 90, '45' → 45."""
    t = t.strip()
    parts = t.split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    elif len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    return int(t)


def _fmt_time(sec: float) -> str:
    """Format seconds as m:ss."""
    m = int(sec) // 60
    s = int(sec) % 60
    return f"{m}:{s:02d}"


def _parse_time_ranges(text: str) -> list[tuple[float, float]]:
    """Parse '0:30-2:00, 5:15-8:00' → [(30, 120), (315, 480)]."""
    ranges = []
    for part in re.split(r'[,،\n]', text):
        part = part.strip()
        if not part:
            continue
        match = re.match(r'([\d:]+)\s*[-–—]\s*([\d:]+)', part)
        if match:
            try:
                start = _parse_time(match.group(1))
                end = _parse_time(match.group(2))
                if end > start:
                    ranges.append((start, end))
            except (ValueError, IndexError):
                continue
    return ranges

logger = logging.getLogger(__name__)

REVIEW_STATE_PATH = Path("data/review_state.json")

# Rate limiter for progress updates — max 1 per job per 30 seconds
_last_update_times: dict[str, float] = {}
_RATE_LIMIT_SECONDS = 30


def send_telegram_sync(text: str, reply_markup: dict = None, parse_mode: str = "HTML"):
    """Send a message via Telegram Bot API (sync, for use from background threads)."""
    import requests
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not bot_token or not chat_id:
        from src.core.config import load_config
        cfg = load_config()
        tg = cfg.get("settings", {}).get("telegram", {})
        bot_token = bot_token or tg.get("bot_token", "")
        chat_id = chat_id or tg.get("admin_chat_id") or tg.get("chat_id", "")
    if not bot_token or not chat_id:
        logger.warning("No Telegram credentials for sync send")
        return None
    payload = {"chat_id": chat_id, "text": text[:4096], "parse_mode": parse_mode}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json=payload, timeout=15,
        )
        return resp.json() if resp.ok else None
    except Exception as e:
        logger.error(f"send_telegram_sync error: {e}")
        return None


def send_progress_update(job_id: str, phase: str, status: str = "completed"):
    """Send pipeline progress update to Telegram (sync, for background threads)."""
    import time

    # Skip stub/pass-through phases — don't spam user with phases that do nothing
    STUB_PHASES = {"video", "video_qa", "video_regen", "voice", "music", "sfx",
                   "compose", "overlay_qa", "final_qa", "image_qa", "image_regen"}
    if phase in STUB_PHASES:
        return  # Don't notify for stub phases

    now = time.time()
    key = f"{job_id}_{phase}"
    last = _last_update_times.get(key, 0)
    if now - last < _RATE_LIMIT_SECONDS:
        return  # Rate limit ALL updates, not just "started"
    _last_update_times[key] = now

    PHASE_NAMES_AR = {
        "research": "🔬 البحث", "seo": "🔎 SEO", "script": "📝 السكربت",
        "compliance": "✅ الامتثال", "images": "🎨 الصور", "image_qa": "🔍 فحص الصور",
        "video": "🎬 الفيديو", "voice": "🎙️ الصوت", "music": "🎵 الموسيقى",
        "compose": "🎞️ التجميع", "final_qa": "✔️ الفحص النهائي",
        "manual_review": "👁️ المراجعة", "publish": "📤 النشر",
    }
    STATUS_AR = {
        "started": "⏳ بدأت", "completed": "✅ اكتملت",
        "failed": "❌ فشلت", "blocked": "🚫 محظورة",
    }
    phase_ar = PHASE_NAMES_AR.get(phase, phase)
    status_ar = STATUS_AR.get(status, status)
    text = f"📊 <b>تحديث المشروع</b>\n\n🆔 <code>{job_id}</code>\n{phase_ar}: {status_ar}"
    send_telegram_sync(text)


def _load_review_state() -> dict:
    """Load pending review state from JSON file."""
    if REVIEW_STATE_PATH.exists():
        try:
            return json.loads(REVIEW_STATE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_review_state(state: dict):
    """Save review state to JSON file."""
    REVIEW_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    REVIEW_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_db():
    from src.core.config import load_config
    from src.core.database import FactoryDB
    config = load_config()
    db_path = config.get("settings", {}).get("database", {}).get("path", "data/factory.db")
    return FactoryDB(db_path), config


_running_jobs = set()  # Track which jobs are currently running

def _run_pipeline_async(job_id: str):
    """Run pipeline in a background thread (non-blocking). Prevents duplicate runs."""
    if job_id in _running_jobs:
        logger.warning(f"Pipeline already running for {job_id} — skipping duplicate start")
        return
    
    def _run():
        _running_jobs.add(job_id)
        try:
            from src.core.pipeline_runner import PipelineRunner
            runner = PipelineRunner()
            result = runner.run_job(job_id)
            if result == "error":
                send_telegram_sync(f"❌ <b>خطأ في المشروع</b>\n\n🆔 <code>{job_id}</code>\n\nتحقق من السجلات.")
            elif result == "completed":
                send_telegram_sync(f"🏁 <b>اكتمل المشروع</b>\n\n🆔 <code>{job_id}</code>")
        except Exception as e:
            logger.error(f"Pipeline error for {job_id}: {e}", exc_info=True)
            send_telegram_sync(f"❌ <b>خطأ في المشروع</b>\n\n🆔 <code>{job_id}</code>\n\n{str(e)[:200]}")
        finally:
            _running_jobs.discard(job_id)
    t = threading.Thread(target=_run, daemon=True)
    t.start()


# ═══════════════════════════════════════════════════════════════
# Main Callback Router
# ═══════════════════════════════════════════════════════════════

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Central callback query handler — routes all button presses."""
    query = update.callback_query
    await query.answer()
    data = query.data

    try:
        # Menu callbacks
        if data == "menu_main":
            await _menu_main(query)
        elif data == "menu_new":
            await _menu_new(query, context)
        elif data == "menu_jobs":
            await _menu_jobs(query)
        elif data == "menu_stats":
            await _menu_stats(query)
        elif data == "menu_settings":
            await _menu_settings(query)
        elif data == "new_auto_research":
            await _new_auto_research(query, context)

        # Topic selection: ts_{job_id}_{idx}
        elif data.startswith("ts_"):
            # Format: ts_{job_id}_{topic_idx} — last segment is index
            last_underscore = data.rfind("_")
            topic_idx = int(data[last_underscore + 1:])
            job_id = data[3:last_underscore]
            await _topic_select(query, job_id, topic_idx)

        # Script review
        elif data.startswith("sa_"):
            job_id = data[3:]
            await _script_approve(query, job_id)
        elif data.startswith("se_"):
            job_id = data[3:]
            await _script_edit_mode(query, job_id, context)
        elif data.startswith("sr_"):
            job_id = data[3:]
            await _script_rewrite(query, job_id)
        elif data.startswith("sl_"):
            # Format: sl_{job_id}_{minutes}
            last_underscore = data.rfind("_")
            minutes = int(data[last_underscore + 1:])
            job_id = data[3:last_underscore]
            await _script_change_length(query, job_id, minutes)

        # Image review
        elif data.startswith("iaa_"):
            job_id = data[4:]
            await _img_approve_all(query, job_id)
        elif data.startswith("ia_"):
            # Format: ia_{job_id}_{scene_idx}
            last_underscore = data.rfind("_")
            scene_idx = int(data[last_underscore + 1:])
            job_id = data[3:last_underscore]
            await _img_approve(query, job_id, scene_idx)
        elif data.startswith("ie_"):
            last_underscore = data.rfind("_")
            scene_idx = int(data[last_underscore + 1:])
            job_id = data[3:last_underscore]
            await _img_edit_mode(query, job_id, scene_idx, context)
        elif data.startswith("ir_"):
            last_underscore = data.rfind("_")
            scene_idx = int(data[last_underscore + 1:])
            job_id = data[3:last_underscore]
            await _img_regen(query, job_id, scene_idx)
        elif data.startswith("ix_"):
            last_underscore = data.rfind("_")
            scene_idx = int(data[last_underscore + 1:])
            job_id = data[3:last_underscore]
            await _img_reject(query, job_id, scene_idx)

        # Review (manual review phase): ra_, rr_, rx_
        elif data.startswith("ra_"):
            job_id = data[3:]
            await _review_approve(query, job_id)
        elif data.startswith("rr_"):
            job_id = data[3:]
            await _review_regen_all(query, job_id)
        elif data.startswith("rx_"):
            job_id = data[3:]
            await _review_reject(query, job_id)

        # Job management: jr_, jd_, jgm_, jg_, jx_, jxc_
        elif data.startswith("jr_"):
            job_id = data[3:]
            await _job_resume(query, job_id)
        elif data.startswith("jd_"):
            job_id = data[3:]
            await _job_details(query, job_id)
        elif data.startswith("jgm_"):
            job_id = data[4:]
            await _job_goto_menu(query, job_id)
        elif data.startswith("jg_"):
            # Format: jg_{job_id}_{phase} — job_id is like "job_20260320_005207"
            # Phase names may contain underscores (image_qa, video_qa, etc.)
            # Job ID format: job_YYYYMMDD_HHMMSS (always 3 parts with "job" prefix)
            rest = data[3:]  # after "jg_"
            # Job ID = first 3 underscore-separated parts (job_DATE_TIME)
            parts = rest.split("_")
            if len(parts) >= 4 and parts[0] == "job":
                job_id = "_".join(parts[0:3])  # job_20260320_005207
                phase = "_".join(parts[3:])     # image_qa, manual_review, etc.
            else:
                # Fallback
                last_underscore = rest.rfind("_")
                phase = rest[last_underscore + 1:]
                job_id = rest[:last_underscore]
            await _job_goto(query, job_id, phase)
        elif data.startswith("jsc_"):
            job_id = data[4:]
            await _job_show_script(query, job_id)
        elif data.startswith("jim_"):
            job_id = data[4:]
            await _job_show_images(query, job_id)
        elif data.startswith("jph_"):
            job_id = data[4:]
            await _job_phase_details(query, job_id)
        elif data.startswith("jsf_"):
            job_id = data[4:]
            await _job_send_script_file(query, job_id)
        elif data.startswith("jpa_"):
            job_id = data[4:]
            await _job_pause(query, job_id)
        elif data.startswith("jrs_"):
            job_id = data[4:]
            await _job_full_restart(query, job_id)
        elif data.startswith("jxc_"):
            job_id = data[4:]
            await _job_delete_confirm(query, job_id)
        elif data.startswith("jx_"):
            job_id = data[3:]
            await _job_delete(query, job_id)

        # Voice review: va_ (approve), vr_ (regen), vx_ (reject), var_ (approve all)
        elif data.startswith("var_"):
            job_id = data[4:]
            await _voice_approve_all(query, job_id)
        elif data.startswith("va_"):
            last_underscore = data.rfind("_")
            scene_idx = int(data[last_underscore + 1:])
            job_id = data[3:last_underscore]
            await query.answer(f"✅ تمت الموافقة على صوت المشهد {scene_idx + 1}")
        elif data.startswith("vr_"):
            last_underscore = data.rfind("_")
            scene_idx = int(data[last_underscore + 1:])
            job_id = data[3:last_underscore]
            await _voice_regen_scene(query, job_id, scene_idx)
        elif data.startswith("vx_"):
            last_underscore = data.rfind("_")
            scene_idx = int(data[last_underscore + 1:])
            job_id = data[3:last_underscore]
            await query.answer(f"❌ تم رفض صوت المشهد {scene_idx + 1}")

        # Voice selection (from VoicePhase pipeline pause)
        elif data.startswith("vs_"):
            # Format: vs_{job_id}_{voice_id}
            parts = data.split("_", 2)
            if len(parts) >= 3:
                # voice_id may contain underscores, job_id is after vs_
                # Format: vs_{job_id}_{voice_id} — job_id has no underscores (UUID)
                rest = data[3:]  # after "vs_"
                last_underscore = rest.rfind("_")
                if last_underscore > 0:
                    # Try to detect: job_id is first UUID-like part
                    # Actually voice_id can have underscores like __edge_tts__
                    # Job IDs are UUIDs (36 chars with dashes)
                    # Find the split point: job_id is 36 chars
                    if len(rest) > 37 and rest[36] == "_":
                        job_id = rest[:36]
                        voice_id = rest[37:]
                    else:
                        # Fallback: find first underscore after reasonable job_id length
                        job_id = rest[:last_underscore]
                        voice_id = rest[last_underscore + 1:]
                else:
                    job_id = rest
                    voice_id = ""
                await _voice_select(query, job_id, voice_id)

        # No-op (category headers in voice selection)
        elif data.startswith("noop_"):
            pass  # Do nothing

        # Voice category toggle/confirm (during clone flow)
        elif data == "vcat_confirm":
            # Confirm selection → move to ID step
            selected = context.user_data.get("voice_clone_categories", [])
            if not selected:
                selected = ["documentary"]  # Default
            context.user_data["voice_clone_category"] = ",".join(selected)
            context.user_data["voice_clone_state"] = "awaiting_id"
            from src.phase5_production.voice_cloner import VOICE_CATEGORIES
            labels = [VOICE_CATEGORIES.get(c, c) for c in selected]
            await query.edit_message_text(
                f"✅ الأنواع: {' | '.join(labels)}\n\n"
                "🔤 اختر معرّف للصوت (بالإنجليزي، بدون مسافات):\n"
                '<i>مثال: narrator_ahmed</i>',
                parse_mode="HTML",
            )
        elif data.startswith("vcat_"):
            # Toggle category selection
            cat = data[5:]
            selected = context.user_data.get("voice_clone_categories", [])
            if cat in selected:
                selected.remove(cat)
            else:
                selected.append(cat)
            context.user_data["voice_clone_categories"] = selected

            # Rebuild buttons with toggle state
            from src.phase5_production.voice_cloner import VOICE_CATEGORIES
            buttons = []
            for cat_id, cat_label in VOICE_CATEGORIES.items():
                icon = "✅" if cat_id in selected else "⬜"
                buttons.append([InlineKeyboardButton(f"{icon} {cat_label}", callback_data=f"vcat_{cat_id}")])
            count = len(selected)
            buttons.append([InlineKeyboardButton(
                f"✅ تأكيد ({count} مختار)" if count else "✅ تأكيد الاختيار",
                callback_data="vcat_confirm"
            )])
            await query.edit_message_text(
                f"🎭 <b>اختر أنواع المحتوى لهذا الصوت:</b>\n"
                f"<i>اضغط على الأنواع المناسبة ثم اضغط تأكيد</i>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(buttons),
            )

        # Voice management callbacks
        elif data == "settings_voices":
            await _settings_voices(query)
        elif data.startswith("vc_add"):
            await _voice_add_start(query, context)
        elif data.startswith("vt_"):
            # Voice test: vt_{voice_id}
            voice_id = data[3:]
            await _voice_test_start(query, voice_id, context)
        elif data.startswith("vp_"):
            # Voice play sample: vp_{voice_id}
            voice_id = data[3:]
            await _voice_play_sample(query, voice_id)
        elif data.startswith("vd_"):
            # Voice delete: vd_{voice_id}
            voice_id = data[3:]
            await _voice_delete(query, voice_id)
        elif data.startswith("vdf_"):
            # Voice set default: vdf_{voice_id}
            voice_id = data[4:]
            await _voice_set_default(query, voice_id)

        # Channel settings
        elif data.startswith("ch_edit_"):
            ch_idx = int(data[8:])
            await _channel_edit_name(query, ch_idx, context)
        elif data == "settings_channels":
            await _settings_channels(query)

        # Settings
        elif data == "settings_video_length":
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("3 دقائق", callback_data="set_length_3"),
                    InlineKeyboardButton("5 دقائق", callback_data="set_length_5"),
                    InlineKeyboardButton("8 دقائق", callback_data="set_length_8"),
                ],
                [
                    InlineKeyboardButton("10 دقائق", callback_data="set_length_10"),
                    InlineKeyboardButton("15 دقيقة", callback_data="set_length_15"),
                    InlineKeyboardButton("20 دقيقة", callback_data="set_length_20"),
                ],
                [InlineKeyboardButton("◀️ رجوع", callback_data="menu_settings")],
            ])
            await query.edit_message_text("📏 <b>اختر طول الفيديو الافتراضي:</b>", reply_markup=keyboard, parse_mode="HTML")
        elif data.startswith("set_length_"):
            minutes = int(data.split("_")[2])
            await query.edit_message_text(f"✅ تم تعيين طول الفيديو الافتراضي: <b>{minutes} دقائق</b>\n\n(سيُطبق على المشاريع الجديدة)", parse_mode="HTML")
        elif data == "settings_auto_threshold":
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("6/10", callback_data="set_threshold_6"),
                    InlineKeyboardButton("7/10", callback_data="set_threshold_7"),
                    InlineKeyboardButton("8/10", callback_data="set_threshold_8"),
                ],
                [
                    InlineKeyboardButton("9/10", callback_data="set_threshold_9"),
                    InlineKeyboardButton("يدوي دائماً", callback_data="set_threshold_10"),
                ],
                [InlineKeyboardButton("◀️ رجوع", callback_data="menu_settings")],
            ])
            await query.edit_message_text("✅ <b>حد النشر التلقائي:</b>\n\nإذا تجاوز الفيديو هذا التقييم يُنشر تلقائياً:", reply_markup=keyboard, parse_mode="HTML")
        elif data.startswith("set_threshold_"):
            val = int(data.split("_")[2])
            label = "يدوي دائماً" if val >= 10 else f"{val}/10"
            await query.edit_message_text(f"✅ تم تعيين حد النشر التلقائي: <b>{label}</b>", parse_mode="HTML")
        elif data == "settings_narrative":
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📰 إخباري رسمي", callback_data="set_narrative_formal_news")],
                [InlineKeyboardButton("🎭 درامي مشوق", callback_data="set_narrative_dramatic")],
                [InlineKeyboardButton("📚 تاريخي وثائقي", callback_data="set_narrative_historical")],
                [InlineKeyboardButton("💻 تقني حديث", callback_data="set_narrative_modern_tech")],
                [InlineKeyboardButton("📖 سردي قصصي", callback_data="set_narrative_storytelling")],
                [InlineKeyboardButton("◀️ رجوع", callback_data="menu_settings")],
            ])
            await query.edit_message_text("🗣️ <b>اختر أسلوب السرد:</b>", reply_markup=keyboard, parse_mode="HTML")
        elif data.startswith("set_narrative_"):
            style = data[len("set_narrative_"):]
            STYLES = {"formal_news": "إخباري رسمي", "dramatic": "درامي مشوق", "historical": "تاريخي وثائقي", "modern_tech": "تقني حديث", "storytelling": "سردي قصصي"}
            await query.edit_message_text(f"✅ أسلوب السرد: <b>{STYLES.get(style, style)}</b>", parse_mode="HTML")
        elif data == "settings_language":
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🇸🇦 عربي فصحى (MSA)", callback_data="set_lang_ar_msa")],
                [InlineKeyboardButton("🇮🇶 عراقي", callback_data="set_lang_ar_iq")],
                [InlineKeyboardButton("🇪🇬 مصري", callback_data="set_lang_ar_eg")],
                [InlineKeyboardButton("🇬🇧 English", callback_data="set_lang_en")],
                [InlineKeyboardButton("◀️ رجوع", callback_data="menu_settings")],
            ])
            await query.edit_message_text("🌐 <b>اختر لغة المحتوى:</b>", reply_markup=keyboard, parse_mode="HTML")
        elif data.startswith("set_lang_"):
            lang = data[len("set_lang_"):]
            LANGS = {"ar_msa": "عربي فصحى", "ar_iq": "عراقي", "ar_eg": "مصري", "en": "English"}
            await query.edit_message_text(f"✅ لغة المحتوى: <b>{LANGS.get(lang, lang)}</b>", parse_mode="HTML")

        else:
            await query.edit_message_text(f"⚠️ أمر غير معروف: {data}")

    except Exception as e:
        logger.error(f"Callback error for '{data}': {e}", exc_info=True)
        try:
            await query.edit_message_text(f"❌ خطأ: {e}")
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
# Menu Handlers
# ═══════════════════════════════════════════════════════════════

async def _menu_main(query):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🆕 مشروع جديد", callback_data="menu_new")],
        [InlineKeyboardButton("📋 مشاريعي", callback_data="menu_jobs")],
        [InlineKeyboardButton("⚙️ الإعدادات", callback_data="menu_settings")],
    ])
    await query.edit_message_text(
        "🏭 <b>مصنع الفيديو الذكي</b>\n\nاختر من القائمة:",
        reply_markup=keyboard, parse_mode="HTML",
    )


async def _menu_new(query, context):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 بحث تلقائي عن مواضيع", callback_data="new_auto_research")],
        [InlineKeyboardButton("◀️ رجوع", callback_data="menu_main")],
    ])
    await query.edit_message_text(
        "📝 <b>مشروع جديد</b>\n\n"
        "أرسل الموضوع كرسالة نصية:\n"
        "<code>/new اسم الموضوع</code>\n\n"
        "أو اختر بحث تلقائي:",
        reply_markup=keyboard, parse_mode="HTML",
    )


async def _menu_jobs(query):
    db, config = _get_db()
    rows = db.conn.execute(
        "SELECT id, topic, status, created_at FROM jobs ORDER BY created_at DESC LIMIT 10"
    ).fetchall()

    if not rows:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🆕 مشروع جديد", callback_data="menu_new")],
            [InlineKeyboardButton("◀️ رجوع", callback_data="menu_main")],
        ])
        await query.edit_message_text("📭 لا توجد مشاريع.", reply_markup=keyboard, parse_mode="HTML")
        return

    STATUS_EMOJI = {
        "pending": "⏳", "research": "🔬", "seo": "🔎", "script": "📝",
        "compliance": "✅", "images": "🎨", "manual_review": "👁️",
        "publish": "📤", "published": "✅", "blocked": "🚫", "cancelled": "❌",
        "complete": "🏁",
    }

    text = "📋 <b>مشاريعي</b>\n\n"
    buttons = []
    for row in rows:
        # row = (id, topic, status, created_at)
        job_id, topic, status, created_at = row[0], row[1], row[2], row[3]
        emoji = STATUS_EMOJI.get(status, "❓")
        topic_short = (topic or "—")[:40]
        text += f"{emoji} {topic_short} — <code>{job_id[:8]}</code>\n"
        buttons.append([
            InlineKeyboardButton(
                f"{emoji} {topic_short[:20]}",
                callback_data=f"jd_{job_id}"
            ),
        ])

    buttons.append([InlineKeyboardButton("◀️ رجوع", callback_data="menu_main")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")


async def _menu_settings(query):
    db, config = _get_db()
    settings = config.get("settings", {})
    channels = config.get("channels", [])
    if isinstance(channels, dict):
        channels = channels.get("channels", [])

    # Current settings summary
    ollama_model = settings.get("ollama", {}).get("model", "?")
    comfyui_url = settings.get("comfyui", {}).get("url", "?")
    tg_chat = settings.get("telegram", {}).get("chat_id", "?")
    max_revisions = settings.get("pipeline", {}).get("max_script_revisions", "?")
    auto_threshold = settings.get("manual_review", {}).get("auto_publish_threshold", "?")
    channel_names = ", ".join(c.get("name", c.get("id", "?")) for c in channels) if channels else "—"

    text = (
        "⚙️ <b>الإعدادات الحالية</b>\n\n"
        f"🤖 <b>نموذج LLM:</b> {ollama_model}\n"
        f"🎨 <b>ComfyUI:</b> {comfyui_url}\n"
        f"📱 <b>Telegram Chat:</b> <code>{tg_chat}</code>\n"
        f"📺 <b>القنوات:</b> {channel_names}\n"
        f"📝 <b>أقصى مراجعات السكربت:</b> {max_revisions}\n"
        f"✅ <b>حد النشر التلقائي:</b> {auto_threshold}/10\n\n"
        "للتعديل اختر:"
    )
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📏 طول الفيديو الافتراضي", callback_data="settings_video_length"),
            InlineKeyboardButton("✅ حد النشر التلقائي", callback_data="settings_auto_threshold"),
        ],
        [
            InlineKeyboardButton("🗣️ أسلوب السرد", callback_data="settings_narrative"),
            InlineKeyboardButton("🌐 اللغة", callback_data="settings_language"),
        ],
        [InlineKeyboardButton("📺 إدارة القنوات", callback_data="settings_channels")],
        [InlineKeyboardButton("🎙️ إدارة الأصوات", callback_data="settings_voices")],
        [InlineKeyboardButton("◀️ رجوع", callback_data="menu_main")],
    ])
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")


async def _menu_stats(query):
    """Show stats inline."""
    db, _ = _get_db()
    total = dict(db.conn.execute("SELECT COUNT(*) as c FROM jobs").fetchone())["c"]
    published = dict(db.conn.execute("SELECT COUNT(*) as c FROM jobs WHERE status IN ('published','complete')").fetchone())["c"]
    active = dict(db.conn.execute("SELECT COUNT(*) as c FROM jobs WHERE status NOT IN ('published','cancelled','complete','blocked')").fetchone())["c"]
    blocked = dict(db.conn.execute("SELECT COUNT(*) as c FROM jobs WHERE status = 'blocked'").fetchone())["c"]
    rate = (published / total * 100) if total > 0 else 0

    text = (
        "📊 <b>الإحصائيات</b>\n\n"
        f"📁 إجمالي: {total}\n"
        f"✅ مكتملة: {published}\n"
        f"▶️ نشطة: {active}\n"
        f"🚫 محظورة: {blocked}\n"
        f"📈 نسبة النجاح: {rate:.0f}%"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ رجوع", callback_data="menu_main")],
    ])
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")


async def _new_auto_research(query, context):
    """Start auto-research to find topics."""
    try:
        db, config = _get_db()
        channels = config.get("channels", [])
        if isinstance(channels, dict):
            channels = channels.get("channels", [])
        channel_id = channels[0]["id"] if channels else "default"
        job_id = db.create_job(channel_id, "بحث تلقائي", topic_source="auto")
        db.update_job_status(job_id, "research")

        # Add to queue
        try:
            db.conn.execute(
                "INSERT OR REPLACE INTO job_queue (job_id, priority, position) VALUES (?, 0, 0)",
                (job_id,)
            )
            db.conn.commit()
        except Exception:
            pass

        await query.edit_message_text(
            "🔍 <b>جاري البحث عن مواضيع...</b>\n\n"
            f"🆔 <code>{job_id}</code>\n\n"
            "سيتم إرسال المواضيع المقترحة عند الانتهاء.",
            parse_mode="HTML",
        )
        _run_pipeline_async(job_id)
    except Exception as e:
        await query.edit_message_text(f"❌ خطأ: {e}")


# ═══════════════════════════════════════════════════════════════
# Topic Selection
# ═══════════════════════════════════════════════════════════════

async def send_topic_cards(bot, chat_id: str, job_id: str, topics: list):
    """Send topic cards to Telegram for user selection."""
    await bot.send_message(
        chat_id=chat_id,
        text=f"🔬 <b>تم العثور على {len(topics)} مواضيع</b>\n\nاختر الموضوع المناسب:",
        parse_mode="HTML",
    )

    for i, topic in enumerate(topics[:10]):
        title = topic.get("topic", topic.get("title", f"موضوع {i+1}"))
        score = topic.get("score", 0)
        pros = topic.get("pros", [])
        cons = topic.get("cons", [])
        est_length = topic.get("estimated_length", "8-10 دقائق")

        text = f"📌 <b>{title}</b>\n\n"
        text += f"⭐ التقييم: {score}/10\n"
        text += f"⏱️ المدة المتوقعة: {est_length}\n\n"
        if pros:
            text += "✅ <b>المميزات:</b>\n"
            for p in pros[:4]:
                text += f"  • {p}\n"
        if cons:
            text += "\n⚠️ <b>التحديات:</b>\n"
            for c in cons[:3]:
                text += f"  • {c}\n"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ اختيار هذا الموضوع", callback_data=f"ts_{job_id}_{i}")],
        ])
        await bot.send_message(chat_id=chat_id, text=text[:4096], reply_markup=keyboard, parse_mode="HTML")


async def _topic_select(query, job_id: str, topic_idx: int):
    """User selected a topic from the research results."""
    state = _load_review_state()
    topics = state.get(f"topics_{job_id}", [])

    if topic_idx < len(topics):
        selected = topics[topic_idx]
        topic_title = selected.get("topic", selected.get("title", "موضوع مختار"))
        ideal_length = selected.get("ideal_length_min", 10)
    else:
        topic_title = f"الموضوع #{topic_idx + 1}"
        ideal_length = 10

    db, config = _get_db()
    db.conn.execute("UPDATE jobs SET topic = ?, target_length_min = ? WHERE id = ?",
                    (topic_title, ideal_length, job_id))
    db.conn.commit()

    await query.edit_message_text(
        f"✅ <b>تم اختيار الموضوع</b>\n\n"
        f"📌 {topic_title}\n\n"
        "جاري المتابعة إلى المرحلة التالية...",
        parse_mode="HTML",
    )

    # Clear state, add to queue, and resume pipeline
    state.pop(f"topics_{job_id}", None)
    _save_review_state(state)

    # Ensure job is in the queue
    try:
        db.conn.execute(
            "INSERT OR REPLACE INTO job_queue (job_id, priority, position) VALUES (?, 0, 0)",
            (job_id,)
        )
        db.conn.commit()
    except Exception:
        pass

    _run_pipeline_async(job_id)


# ═══════════════════════════════════════════════════════════════
# Script Review
# ═══════════════════════════════════════════════════════════════

async def send_script_review(bot, chat_id: str, job_id: str, script_text: str,
                              word_count: int, duration_sec: int, scene_count: int):
    """Send script for review with approval buttons."""
    # Split long scripts into multiple messages
    MAX_LEN = 4000
    chunks = [script_text[i:i+MAX_LEN] for i in range(0, len(script_text), MAX_LEN)]

    await bot.send_message(
        chat_id=chat_id,
        text=(
            f"📝 <b>مراجعة السكربت</b>\n\n"
            f"📊 عدد الكلمات: {word_count}\n"
            f"⏱️ المدة المتوقعة: {duration_sec // 60} دقيقة {duration_sec % 60} ثانية\n"
            f"🎬 عدد المشاهد: {scene_count}\n"
            f"🆔 <code>{job_id}</code>"
        ),
        parse_mode="HTML",
    )

    for i, chunk in enumerate(chunks):
        prefix = f"📄 <b>الجزء {i+1}/{len(chunks)}</b>\n\n" if len(chunks) > 1 else ""
        await bot.send_message(chat_id=chat_id, text=prefix + chunk, parse_mode="HTML")

    # Action buttons (short prefixes: sa=script approve, se=script edit, sr=rewrite, sl=length)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ موافقة", callback_data=f"sa_{job_id}")],
        [
            InlineKeyboardButton("✏️ تعديل", callback_data=f"se_{job_id}"),
            InlineKeyboardButton("🔄 إعادة كتابة", callback_data=f"sr_{job_id}"),
        ],
        [
            InlineKeyboardButton("3 د", callback_data=f"sl_{job_id}_3"),
            InlineKeyboardButton("5 د", callback_data=f"sl_{job_id}_5"),
            InlineKeyboardButton("8 د", callback_data=f"sl_{job_id}_8"),
            InlineKeyboardButton("10 د", callback_data=f"sl_{job_id}_10"),
            InlineKeyboardButton("15 د", callback_data=f"sl_{job_id}_15"),
        ],
    ])
    await bot.send_message(
        chat_id=chat_id,
        text="👆 <b>اختر إجراء:</b>",
        reply_markup=keyboard, parse_mode="HTML",
    )


async def _script_approve(query, job_id: str):
    db, _ = _get_db()
    db.conn.execute(
        "UPDATE scripts SET status = 'approved' WHERE job_id = ?",
        (job_id,)
    )
    # Transition manual_review → compliance so pipeline resumes from next phase
    try:
        from src.core.job_state_machine import JobStateMachine, JobStatus
        sm = JobStateMachine(db)
        sm.force_reset(job_id, JobStatus.COMPLIANCE)
    except Exception:
        db.update_job_status(job_id, "compliance")
        db.conn.commit()

    await query.edit_message_text(
        "✅ <b>تمت الموافقة على السكربت</b>\n\nجاري المتابعة...",
        parse_mode="HTML",
    )

    state = _load_review_state()
    state.pop(f"script_waiting_{job_id}", None)
    _save_review_state(state)
    _run_pipeline_async(job_id)


async def _script_edit_mode(query, job_id: str, context):
    """Enter edit mode — next text message will be edit instructions."""
    context.user_data["awaiting_script_edit"] = job_id
    await query.edit_message_text(
        "✏️ <b>وضع التعديل</b>\n\n"
        "أرسل تعليمات التعديل كرسالة نصية.\n"
        'مثال: "أضف قسم عن الحرب العالمية الثانية" أو "اجعله أقصر"',
        parse_mode="HTML",
    )


async def _script_rewrite(query, job_id: str):
    state = _load_review_state()
    state[f"script_edit_{job_id}"] = {"action": "rewrite"}
    _save_review_state(state)

    db, _ = _get_db()
    db.conn.execute("UPDATE jobs SET script_revisions = script_revisions + 1 WHERE id = ?", (job_id,))
    db.update_job_status(job_id, "script")
    db.conn.commit()

    await query.edit_message_text(
        "🔄 <b>جاري إعادة كتابة السكربت...</b>",
        parse_mode="HTML",
    )
    _run_pipeline_async(job_id)


async def _script_change_length(query, job_id: str, minutes: int):
    db, _ = _get_db()
    db.conn.execute("UPDATE jobs SET target_length_min = ?, script_revisions = script_revisions + 1 WHERE id = ?",
                    (minutes, job_id))
    db.update_job_status(job_id, "script")
    db.conn.commit()

    await query.edit_message_text(
        f"📏 <b>تغيير المدة إلى {minutes} دقائق</b>\n\nجاري إعادة كتابة السكربت...",
        parse_mode="HTML",
    )
    _run_pipeline_async(job_id)


# ═══════════════════════════════════════════════════════════════
# Image Review
# ═══════════════════════════════════════════════════════════════

async def send_image_review(bot, chat_id: str, job_id: str, scenes: list, output_dir: str):
    """Send scene images for review with per-image buttons."""
    import os

    state = _load_review_state()
    state[f"images_{job_id}"] = {
        "total": len(scenes),
        "approved": [],
        "rejected": [],
        "edits": {},
    }
    _save_review_state(state)

    await bot.send_message(
        chat_id=chat_id,
        text=f"🎨 <b>مراجعة الصور — {len(scenes)} مشهد</b>\n\n🆔 <code>{job_id}</code>",
        parse_mode="HTML",
    )

    for scene in scenes:
        idx = scene["scene_index"]
        img_path = os.path.join(output_dir, f"scene_{idx:03d}.png")
        if not os.path.exists(img_path):
            continue

        narration = (scene.get("narration_text") or "")[:300]
        visual = (scene.get("visual_prompt") or "")[:150]
        camera = scene.get("camera_movement", "static")

        caption = (
            f"<b>مشهد {idx + 1}/{len(scenes)}</b> | 🎥 {camera}\n\n"
            f"📝 {narration}\n\n"
            f"🎨 <i>{visual}</i>"
        )[:1024]

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅", callback_data=f"ia_{job_id}_{idx}"),
                InlineKeyboardButton("✏️", callback_data=f"ie_{job_id}_{idx}"),
                InlineKeyboardButton("🔄", callback_data=f"ir_{job_id}_{idx}"),
                InlineKeyboardButton("❌", callback_data=f"ix_{job_id}_{idx}"),
            ],
        ])

        with open(img_path, "rb") as f:
            await bot.send_photo(
                chat_id=chat_id, photo=f, caption=caption,
                reply_markup=keyboard, parse_mode="HTML",
            )

    # Final summary buttons
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ موافقة على الكل", callback_data=f"iaa_{job_id}")],
        [InlineKeyboardButton("◀️ رجوع", callback_data="menu_main")],
    ])
    await bot.send_message(
        chat_id=chat_id,
        text="👆 <b>راجع كل صورة، ثم اضغط موافقة على الكل للمتابعة</b>",
        reply_markup=keyboard, parse_mode="HTML",
    )


async def _img_approve(query, job_id: str, scene_idx: int):
    state = _load_review_state()
    key = f"images_{job_id}"
    if key not in state:
        state[key] = {"approved": [], "rejected": [], "edits": {}}
    if scene_idx not in state[key]["approved"]:
        state[key]["approved"].append(scene_idx)
    state[key]["rejected"] = [r for r in state[key].get("rejected", []) if r != scene_idx]
    _save_review_state(state)

    approved = len(state[key]["approved"])
    total = state[key].get("total", "?")
    await query.answer(f"✅ تمت الموافقة على المشهد {scene_idx + 1} ({approved}/{total})")


async def _img_reject(query, job_id: str, scene_idx: int):
    state = _load_review_state()
    key = f"images_{job_id}"
    if key not in state:
        state[key] = {"approved": [], "rejected": [], "edits": {}}
    if scene_idx not in state[key]["rejected"]:
        state[key]["rejected"].append(scene_idx)
    state[key]["approved"] = [a for a in state[key].get("approved", []) if a != scene_idx]
    _save_review_state(state)

    await query.answer(f"❌ تم رفض المشهد {scene_idx + 1}")


async def _img_edit_mode(query, job_id: str, scene_idx: int, context):
    context.user_data["awaiting_img_edit"] = {"job_id": job_id, "scene_idx": scene_idx}
    await query.answer("✏️ أرسل تعليمات التعديل كرسالة نصية")


async def _img_regen(query, job_id: str, scene_idx: int):
    state = _load_review_state()
    key = f"images_{job_id}"
    if key not in state:
        state[key] = {"approved": [], "rejected": [], "edits": {}}
    state[key]["edits"][str(scene_idx)] = {"action": "regenerate"}
    _save_review_state(state)

    await query.answer(f"🔄 سيتم إعادة توليد المشهد {scene_idx + 1}")


async def _img_approve_all(query, job_id: str):
    """Approve all images and resume pipeline from voice phase."""
    state = _load_review_state()
    state.pop(f"images_{job_id}", None)
    state[f"images_approved_{job_id}"] = True
    _save_review_state(state)

    await query.edit_message_text(
        "✅ <b>تمت الموافقة على جميع الصور</b>\n\n⏳ جاري المتابعة إلى التعليق الصوتي...",
        parse_mode="HTML",
    )

    db, _ = _get_db()
    # Resume pipeline: set to voice and let callback start it
    try:
        from src.core.job_state_machine import JobStateMachine, JobStatus
        sm = JobStateMachine(db)
        sm.force_reset(job_id, JobStatus.VOICE)
    except Exception:
        db.conn.execute("UPDATE jobs SET status='voice', blocked_reason=NULL, blocked_phase=NULL, blocked_at=NULL WHERE id=?", (job_id,))
        db.conn.commit()

    _run_pipeline_async(job_id)


async def _voice_approve_all(query, job_id: str):
    """Approve all voice clips and resume pipeline."""
    state = _load_review_state()
    state[f"voice_approved_{job_id}"] = True
    _save_review_state(state)

    await query.edit_message_text(
        "✅ <b>تمت الموافقة على التعليق الصوتي</b>\n\n⏳ جاري المتابعة...",
        parse_mode="HTML",
    )

    db, _ = _get_db()
    try:
        from src.core.job_state_machine import JobStateMachine, JobStatus
        sm = JobStateMachine(db)
        sm.force_reset(job_id, JobStatus.VOICE)
    except Exception:
        db.conn.execute("UPDATE jobs SET status='voice', blocked_reason=NULL, blocked_phase=NULL, blocked_at=NULL WHERE id=?", (job_id,))
        db.conn.commit()

    _run_pipeline_async(job_id)


# ═══════════════════════════════════════════════════════════════
# Review Phase (approve/reject from ManualReviewPhase)
# ═══════════════════════════════════════════════════════════════

async def _review_approve(query, job_id: str):
    """Approve all and continue pipeline to the next phase."""
    db, _ = _get_db()
    db.conn.execute(
        "UPDATE jobs SET manual_review_status = 'approved', manual_review_at = ? WHERE id = ?",
        (datetime.utcnow().isoformat(), job_id),
    )
    db.conn.commit()

    from src.core.job_state_machine import JobStateMachine, JobStatus
    sm = JobStateMachine(db)

    await query.edit_message_text(
        "✅ <b>تمت الموافقة على الصور</b>\n\n"
        "📌 المراحل التالية (الفيديو، الصوت، الموسيقى) لم يتم تفعيلها بعد.\n"
        "المشروع مكتمل حتى مرحلة الصور. عند تفعيل المراحل التالية يمكنك المتابعة من /jobs.",
        parse_mode="HTML",
    )

    # Mark as complete for now (images done, stubs not ready)
    try:
        sm.force_reset(job_id, JobStatus.PUBLISHED)
    except Exception as e:
        logger.error(f"Transition error: {e}")

    _run_pipeline_async(job_id)


async def _review_regen_all(query, job_id: str):
    db, _ = _get_db()
    db.conn.execute("UPDATE jobs SET image_regenerations = image_regenerations + 1 WHERE id = ?", (job_id,))
    db.update_job_status(job_id, "images")
    db.conn.commit()

    await query.edit_message_text(
        "🔄 <b>جاري إعادة توليد جميع الصور...</b>",
        parse_mode="HTML",
    )
    _run_pipeline_async(job_id)


async def _review_reject(query, job_id: str):
    db, _ = _get_db()
    db.conn.execute(
        "UPDATE jobs SET manual_review_status = 'rejected', status = 'cancelled' WHERE id = ?",
        (job_id,),
    )
    db.conn.commit()

    await query.edit_message_text(
        "❌ <b>تم إلغاء المشروع</b>",
        parse_mode="HTML",
    )


# ═══════════════════════════════════════════════════════════════
# Job Management
# ═══════════════════════════════════════════════════════════════

async def _job_resume(query, job_id: str):
    db, _ = _get_db()
    job = db.get_job(job_id)
    status = job.get("status", "") if job else ""

    # If blocked, unblock and resume from the blocked phase
    if status == "blocked":
        blocked_phase = job.get("blocked_phase", "research")
        db.conn.execute(
            "UPDATE jobs SET status=?, blocked_reason=NULL, blocked_phase=NULL, blocked_at=NULL WHERE id=?",
            (blocked_phase, job_id)
        )
        db.conn.commit()
        await query.edit_message_text(
            f"\u25b6\ufe0f <b>جاري استئناف المشروع...</b>\n"
            f"\U0001f504 إعادة المحاولة من مرحلة: {blocked_phase}\n"
            f"\U0001f194 <code>{job_id}</code>",
            parse_mode="HTML",
        )
    else:
        await query.edit_message_text(
            f"\u25b6\ufe0f <b>جاري استئناف المشروع...</b>\n\U0001f194 <code>{job_id}</code>",
            parse_mode="HTML",
        )

    _run_pipeline_async(job_id)


async def _job_details(query, job_id: str):
    db, _ = _get_db()
    job = db.get_job(job_id)
    if not job:
        await query.edit_message_text("❌ المشروع غير موجود")
        return

    # Count scenes
    scene_count = db.conn.execute(
        "SELECT COUNT(*) as c FROM scenes WHERE job_id = ?", (job_id,)
    ).fetchone()
    scenes = dict(scene_count)["c"] if scene_count else 0

    # Get script info
    script = db.conn.execute(
        "SELECT word_count, estimated_duration_sec, version FROM scripts WHERE job_id = ? ORDER BY version DESC LIMIT 1",
        (job_id,)
    ).fetchone()

    text = (
        f"📊 <b>تفاصيل المشروع</b>\n\n"
        f"📝 <b>الموضوع:</b> {job.get('topic', '—')}\n"
        f"🔄 <b>الحالة:</b> {job.get('status', '—')}\n"
        f"📅 <b>الإنشاء:</b> {str(job.get('created_at', ''))[:19]}\n"
        f"🎬 <b>المشاهد:</b> {scenes}\n"
        f"🆔 <code>{job_id}</code>\n"
    )
    if script:
        s = dict(script)
        text += (
            f"\n📄 <b>السكربت (v{s.get('version', 1)}):</b>\n"
            f"  • كلمات: {s.get('word_count', 0)}\n"
            f"  • المدة: {(s.get('estimated_duration_sec', 0) or 0) // 60} دقيقة\n"
        )

    if job.get("blocked_reason"):
        text += f"\n🚫 <b>سبب الحظر:</b> {job['blocked_reason']}"

    buttons = [
        [
            InlineKeyboardButton("▶️ استئناف", callback_data=f"jr_{job_id}"),
            InlineKeyboardButton("⏪ العودة إلى...", callback_data=f"jgm_{job_id}"),
        ],
        [
            InlineKeyboardButton("📝 عرض السكربت", callback_data=f"jsc_{job_id}"),
            InlineKeyboardButton("🖼️ عرض الصور", callback_data=f"jim_{job_id}"),
        ],
        [
            InlineKeyboardButton("📊 تفاصيل المراحل", callback_data=f"jph_{job_id}"),
            InlineKeyboardButton("📋 نسخ السكربت", callback_data=f"jsf_{job_id}"),
        ],
        [
            InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data=f"jpa_{job_id}"),
            InlineKeyboardButton("🔄 إعادة تشغيل", callback_data=f"jrs_{job_id}"),
        ],
        [InlineKeyboardButton("◀️ رجوع", callback_data="menu_jobs")],
    ]
    keyboard = InlineKeyboardMarkup(buttons)
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")


async def _job_goto_menu(query, job_id: str):
    """Show phase list to go back to."""
    phases = [
        ("research", "🔬 البحث"),
        ("seo", "🔎 SEO"),
        ("script", "📝 السكربت"),
        ("compliance", "✅ الامتثال"),
        ("images", "🎨 الصور"),
        ("image_qa", "🔍 فحص الصور"),
        ("video", "🎬 الفيديو"),
        ("voice", "🎙️ الصوت"),
        ("music", "🎵 الموسيقى"),
        ("compose", "🎞️ التجميع"),
        ("final_qa", "✔️ الفحص النهائي"),
        ("manual_review", "👁️ المراجعة"),
    ]

    # Get current phase to show which phases are available
    db, _ = _get_db()
    job = db.get_job(job_id)
    current = job["status"] if job else "pending"

    buttons = []
    for phase_key, label in phases:
        marker = " ◄" if phase_key == current else ""
        buttons.append([InlineKeyboardButton(
            f"{label}{marker}",
            callback_data=f"jg_{job_id}_{phase_key}"
        )])
    buttons.append([InlineKeyboardButton("◀️ رجوع", callback_data=f"jd_{job_id}")])

    await query.edit_message_text(
        f"⏪ <b>العودة إلى مرحلة:</b>\n\n"
        f"المرحلة الحالية: <code>{current}</code>\n"
        f"اختر المرحلة التي تريد إعادة تشغيلها.\n"
        f"<i>⚠️ سيتم مسح نتائج المراحل بعد المرحلة المختارة وإعادة تنفيذها من جديد.</i>",
        reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML",
    )


async def _job_goto(query, job_id: str, phase: str):
    """Force-reset a job to a specific phase and restart pipeline."""
    db, config = _get_db()
    try:
        from src.core.job_state_machine import JobStateMachine, JobStatus

        sm = JobStateMachine(db)
        target = JobStatus(phase)

        # Force reset (bypasses transition rules)
        previous = sm.force_reset(job_id, target)

        # Clean up data from phases AFTER the target phase
        _cleanup_after_phase(db, job_id, phase)

        PHASE_NAMES_AR = {
            "research": "البحث", "seo": "SEO", "script": "السكربت",
            "compliance": "الامتثال", "images": "الصور", "image_qa": "فحص الصور",
            "video": "الفيديو", "voice": "الصوت", "music": "الموسيقى",
            "compose": "التجميع", "final_qa": "الفحص النهائي",
            "manual_review": "المراجعة",
        }
        phase_ar = PHASE_NAMES_AR.get(phase, phase)

        # Ensure job is in the queue
        try:
            db.conn.execute(
                "INSERT OR REPLACE INTO job_queue (job_id, priority, position) VALUES (?, 0, 0)",
                (job_id,)
            )
            db.conn.commit()
        except Exception as qe:
            logger.warning(f"Failed to re-queue job: {qe}")

        # For voice phase: don't auto-start — wait for user to select voice
        # The voice phase will send selection menu and block
        needs_input = (phase == "voice" and not db.get_job(job_id).get("selected_voice_id"))
        
        if needs_input:
            # Just send selection menu, don't start pipeline
            from src.phase5_production.voice_cloner import VoiceCloner
            cloner = VoiceCloner()
            voices = cloner.list_voices()
            if voices:
                await query.edit_message_text(
                    f"⏪ <b>تم الرجوع إلى: {phase_ar}</b>\n\n"
                    f"🎙️ اختر المعلق الصوتي أولاً:",
                    parse_mode="HTML",
                )
                # Send voice selection inline
                import os
                bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
                chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
                if not bot_token or not chat_id:
                    tg = config.get("settings", {}).get("telegram", {})
                    bot_token = bot_token or tg.get("bot_token", "")
                    chat_id = chat_id or tg.get("admin_chat_id") or tg.get("chat_id", "")
                
                import requests as req
                api = f"https://api.telegram.org/bot{bot_token}"
                buttons = []
                default_id = cloner.get_default_voice_id()
                for v in voices:
                    label = f"👤 {v.name}"
                    if v.voice_id == default_id:
                        label += " ⭐"
                    buttons.append([{"text": label, "callback_data": f"vs_{job_id}_{v.voice_id}"}])
                buttons.append([{"text": "🤖 Edge TTS الافتراضي", "callback_data": f"vs_{job_id}___edge_tts__"}])
                
                req.post(f"{api}/sendMessage", json={
                    "chat_id": chat_id, "parse_mode": "HTML",
                    "text": f"🎙️ <b>اختر الشخصية الصوتية:</b>\n🆔 <code>{job_id}</code>",
                    "reply_markup": {"inline_keyboard": buttons},
                }, timeout=10)
            else:
                await query.edit_message_text(
                    f"⏪ <b>تم الرجوع إلى: {phase_ar}</b>\n🔄 جاري إعادة التشغيل...\n🆔 <code>{job_id}</code>",
                    parse_mode="HTML",
                )
                _run_pipeline_async(job_id)
        else:
            await query.edit_message_text(
                f"⏪ <b>تم الرجوع إلى: {phase_ar}</b>\n\n"
                f"🔄 جاري إعادة التشغيل من مرحلة {phase_ar}...\n"
                f"🆔 <code>{job_id}</code>",
                parse_mode="HTML",
            )
            _run_pipeline_async(job_id)
    except Exception as e:
        logger.error(f"Job goto failed: {e}", exc_info=True)
        await query.edit_message_text(f"❌ خطأ: {e}")


def _cleanup_after_phase(db, job_id: str, phase: str):
    """Clean up DB data from phases after the target phase.
    This ensures a clean restart from the target phase forward."""

    # Phase order
    PHASE_ORDER = [
        "research", "seo", "script", "compliance",
        "images", "image_qa", "image_regen",
        "video", "video_qa", "video_regen",
        "voice", "music", "sfx", "compose", "overlay_qa",
        "final_qa", "manual_review", "publish",
    ]

    try:
        phase_idx = PHASE_ORDER.index(phase)
    except ValueError:
        return

    phases_to_clean = PHASE_ORDER[phase_idx:]  # Include current phase (will be re-run)

    # Map phases to DB tables to clean
    PHASE_TABLES = {
        "research": [],  # Keep research — it's the foundation
        "seo": ["seo_data"],
        "script": ["scripts", "scenes"],
        "compliance": ["compliance_checks"],
        "images": [],  # Images are files, not DB rows (scene assets updated in-place)
        "image_qa": [],
        "video": [],
        "voice": [],
        "music": [],
        "compose": [],
        "final_qa": [],
        "manual_review": [],
        "publish": [],
    }

    for p in phases_to_clean:
        tables = PHASE_TABLES.get(p, [])
        for table in tables:
            try:
                db.conn.execute(f"DELETE FROM {table} WHERE job_id = ?", (job_id,))
                logger.info(f"Cleaned {table} for {job_id} (phase reset: {phase})")
            except Exception as e:
                logger.warning(f"Failed to clean {table}: {e}")

    # Clear phase completion timestamps for phases being re-run
    PHASE_TIMESTAMP_MAP = {
        "research": "phase1_completed_at",
        "seo": "phase2_completed_at",
        "script": "phase3_completed_at",
        "compliance": "phase4_completed_at",
        "images": "phase5_completed_at",
        "image_qa": "phase6_completed_at",
        "video": "phase7_completed_at",
        "manual_review": "phase7_5_completed_at",
        "publish": "phase8_completed_at",
    }

    nulls = []
    for p in phases_to_clean:
        ts_col = PHASE_TIMESTAMP_MAP.get(p)
        if ts_col:
            nulls.append(f"{ts_col} = NULL")

    if nulls:
        sql = f"UPDATE jobs SET {', '.join(nulls)} WHERE id = ?"
        db.conn.execute(sql, (job_id,))

    # Clean up output files for phases being re-run
    import shutil
    base = Path(f"output/{job_id}")
    PHASE_FILES = {
        "voice": [base / "voice"],
        "music": [base / "audio" / "music"],
        "sfx": [base / "audio" / "sfx"],
        "images": [base / "images"],
        "video": [base / "videos"],
        "compose": [base / "final.mp4", base / "temp_video_concat.mp4", base / "temp_mixed_audio.mp3"],
    }
    for p in phases_to_clean:
        for path in PHASE_FILES.get(p, []):
            try:
                if path.is_dir():
                    shutil.rmtree(str(path), ignore_errors=True)
                    logger.info(f"Deleted dir: {path}")
                elif path.exists():
                    path.unlink()
                    logger.info(f"Deleted file: {path}")
            except Exception as e:
                logger.warning(f"Failed to delete {path}: {e}")

    # Clear selection/approval state when going back
    if phase in ("voice", "research", "script", "images"):
        state = _load_review_state()
        state.pop(f"voice_selected_{job_id}", None)
        state.pop(f"voice_approved_{job_id}", None)
        state.pop(f"images_approved_{job_id}", None)
        _save_review_state(state)
        # Also clear voice_id from DB so user gets asked again
        try:
            db.conn.execute("UPDATE jobs SET selected_voice_id=NULL WHERE id=?", (job_id,))
            db.conn.commit()
        except Exception:
            pass

    db.conn.commit()
    logger.info(f"Cleanup complete for {job_id}: reset from {phase} forward (files + DB)")


async def _job_show_script(query, job_id: str):
    """Show full script text."""
    db, _ = _get_db()
    script_row = db.conn.execute(
        "SELECT full_text, word_count, version FROM scripts WHERE job_id = ? ORDER BY version DESC LIMIT 1",
        (job_id,)
    ).fetchone()
    if not script_row:
        await query.edit_message_text("📝 لا يوجد سكربت لهذا المشروع بعد.", parse_mode="HTML")
        return
    script = dict(script_row)
    text = script.get("full_text", "")[:3800]
    header = f"📝 <b>السكربت (v{script.get('version', 1)})</b> — {script.get('word_count', 0)} كلمة\n\n"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ رجوع", callback_data=f"jd_{job_id}")],
    ])
    await query.edit_message_text(header + text, reply_markup=keyboard, parse_mode="HTML")


async def _job_show_images(query, job_id: str):
    """Show image count and info (can't send images via edit_message)."""
    db, _ = _get_db()
    scenes = db.conn.execute(
        "SELECT scene_index, visual_prompt FROM scenes WHERE job_id = ? ORDER BY scene_index",
        (job_id,)
    ).fetchall()
    if not scenes:
        await query.edit_message_text("🖼️ لا توجد صور لهذا المشروع بعد.", parse_mode="HTML")
        return
    text = f"🖼️ <b>الصور — {len(scenes)} مشهد</b>\n\n"
    for s in scenes[:15]:
        sd = dict(s)
        prompt_short = (sd.get("visual_prompt") or "—")[:60]
        text += f"  🎬 مشهد {sd['scene_index'] + 1}: {prompt_short}\n"
    if len(scenes) > 15:
        text += f"\n  ... و{len(scenes) - 15} مشاهد أخرى"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ رجوع", callback_data=f"jd_{job_id}")],
    ])
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")


async def _job_phase_details(query, job_id: str):
    """Show which phases completed with timestamps."""
    db, _ = _get_db()
    job = db.get_job(job_id)
    if not job:
        await query.edit_message_text("❌ المشروع غير موجود")
        return

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

    text = f"📊 <b>تفاصيل المراحل</b>\n🆔 <code>{job_id}</code>\n\n"
    for field, label in ts_fields:
        val = job.get(field)
        if val:
            text += f"✅ {label}: {str(val)[:19]}\n"
        else:
            text += f"⬜ {label}: —\n"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ رجوع", callback_data=f"jd_{job_id}")],
    ])
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")


async def _job_send_script_file(query, job_id: str):
    """Send script as a text document."""
    db, _ = _get_db()
    script_row = db.conn.execute(
        "SELECT full_text, version FROM scripts WHERE job_id = ? ORDER BY version DESC LIMIT 1",
        (job_id,)
    ).fetchone()
    if not script_row:
        await query.answer("لا يوجد سكربت بعد")
        return

    import io
    script = dict(script_row)
    text = script.get("full_text", "")
    buf = io.BytesIO(text.encode("utf-8"))
    buf.name = f"script_v{script.get('version', 1)}_{job_id[:8]}.txt"

    import requests
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not bot_token or not chat_id:
        from src.core.config import load_config
        cfg = load_config()
        tg = cfg.get("settings", {}).get("telegram", {})
        bot_token = bot_token or tg.get("bot_token", "")
        chat_id = chat_id or tg.get("admin_chat_id") or tg.get("chat_id", "")

    try:
        requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendDocument",
            data={"chat_id": chat_id, "caption": f"📋 سكربت المشروع\n🆔 {job_id[:8]}"},
            files={"document": (buf.name, buf, "text/plain")},
            timeout=15,
        )
        await query.answer("📋 تم إرسال الملف")
    except Exception as e:
        await query.answer(f"خطأ: {e}")


async def _job_pause(query, job_id: str):
    """Pause a job by setting it to manual_review."""
    db, _ = _get_db()
    try:
        from src.core.job_state_machine import JobStateMachine, JobStatus
        sm = JobStateMachine(db)
        sm.force_reset(job_id, JobStatus.MANUAL_REVIEW)
    except Exception:
        db.update_job_status(job_id, "manual_review")
        db.conn.commit()

    await query.edit_message_text(
        f"⏸️ <b>تم إيقاف المشروع مؤقتاً</b>\n🆔 <code>{job_id}</code>\n\nاستخدم ▶️ استئناف للمتابعة.",
        parse_mode="HTML",
    )


async def _job_full_restart(query, job_id: str):
    """Full restart from research."""
    db, _ = _get_db()
    try:
        from src.core.job_state_machine import JobStateMachine, JobStatus
        sm = JobStateMachine(db)
        sm.force_reset(job_id, JobStatus.RESEARCH)
        _cleanup_after_phase(db, job_id, "research")
    except Exception as e:
        logger.error(f"Full restart error: {e}", exc_info=True)
        db.update_job_status(job_id, "research")
        db.conn.commit()

    await query.edit_message_text(
        f"🔄 <b>تم إعادة تشغيل المشروع من البداية</b>\n🆔 <code>{job_id}</code>",
        parse_mode="HTML",
    )
    _run_pipeline_async(job_id)


async def _job_delete(query, job_id: str):
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ نعم، احذف", callback_data=f"jxc_{job_id}"),
            InlineKeyboardButton("❌ لا", callback_data=f"jd_{job_id}"),
        ],
    ])
    await query.edit_message_text(
        "🗑️ <b>هل أنت متأكد من حذف هذا المشروع؟</b>\n\nلا يمكن التراجع عن هذا الإجراء.",
        reply_markup=keyboard, parse_mode="HTML",
    )


async def _job_delete_confirm(query, job_id: str):
    db, _ = _get_db()
    db.conn.execute("UPDATE jobs SET status = 'cancelled' WHERE id = ?", (job_id,))
    db.conn.commit()
    await query.edit_message_text(
        "🗑️ <b>تم حذف المشروع</b>",
        parse_mode="HTML",
    )


# ═══════════════════════════════════════════════════════════════
# Script Review (Bug 5 — sync, called from pipeline thread)
# ═══════════════════════════════════════════════════════════════

def _send_script_for_review(job_id: str, db):
    """Send script to Telegram for review (sync, from pipeline background thread)."""
    import requests

    # Get script from DB
    script_row = db.conn.execute(
        "SELECT full_text, word_count, estimated_duration_sec, version FROM scripts "
        "WHERE job_id = ? ORDER BY version DESC LIMIT 1",
        (job_id,),
    ).fetchone()
    if not script_row:
        return

    script = dict(script_row)
    script_text = script.get("full_text", "")
    word_count = script.get("word_count", len(script_text.split()))
    duration_sec = script.get("estimated_duration_sec", int(word_count / 2.5))
    version = script.get("version", 1)

    # Count scenes
    scene_row = db.conn.execute(
        "SELECT COUNT(*) as c FROM scenes WHERE job_id = ?", (job_id,)
    ).fetchone()
    scene_count = dict(scene_row)["c"] if scene_row else 0

    # Send header
    header = (
        f"📝 <b>مراجعة السكربت (v{version})</b>\n\n"
        f"📊 عدد الكلمات: {word_count}\n"
        f"⏱️ المدة المتوقعة: {duration_sec // 60} دقيقة {duration_sec % 60} ثانية\n"
        f"🎬 عدد المشاهد: {scene_count}\n"
        f"🆔 <code>{job_id}</code>"
    )
    send_telegram_sync(header)

    # Send script text in chunks
    MAX_LEN = 4000
    chunks = [script_text[i:i+MAX_LEN] for i in range(0, len(script_text), MAX_LEN)]
    for i, chunk in enumerate(chunks):
        prefix = f"📄 <b>الجزء {i+1}/{len(chunks)}</b>\n\n" if len(chunks) > 1 else ""
        send_telegram_sync(prefix + chunk)

    # Send action buttons
    keyboard = {
        "inline_keyboard": [
            [{"text": "✅ موافقة", "callback_data": f"sa_{job_id}"}],
            [
                {"text": "✏️ تعديل", "callback_data": f"se_{job_id}"},
                {"text": "🔄 إعادة كتابة", "callback_data": f"sr_{job_id}"},
            ],
            [
                {"text": "3 د", "callback_data": f"sl_{job_id}_3"},
                {"text": "5 د", "callback_data": f"sl_{job_id}_5"},
                {"text": "8 د", "callback_data": f"sl_{job_id}_8"},
                {"text": "10 د", "callback_data": f"sl_{job_id}_10"},
                {"text": "15 د", "callback_data": f"sl_{job_id}_15"},
            ],
        ]
    }
    send_telegram_sync("👆 <b>اختر إجراء:</b>", reply_markup=keyboard)

    # Mark as waiting for review
    state = _load_review_state()
    state[f"script_waiting_{job_id}"] = True
    _save_review_state(state)


# ═══════════════════════════════════════════════════════════════
# Channel Management (Bug 4)
# ═══════════════════════════════════════════════════════════════

async def _settings_channels(query):
    """Show list of channels with edit buttons."""
    _, config = _get_db()
    channels = config.get("channels", [])
    if isinstance(channels, dict):
        channels = channels.get("channels", [])

    if not channels:
        await query.edit_message_text("📺 لا توجد قنوات مُعرّفة.", parse_mode="HTML")
        return

    text = "📺 <b>إدارة القنوات</b>\n\n"
    buttons = []
    for i, ch in enumerate(channels):
        name = ch.get("name", ch.get("id", f"قناة {i+1}"))
        ch_id = ch.get("id", "?")
        category = ch.get("category", "—")
        text += f"📌 <b>{name}</b> ({ch_id})\n   📂 {category}\n\n"
        buttons.append([InlineKeyboardButton(f"✏️ تعديل اسم: {name}", callback_data=f"ch_edit_{i}")])

    buttons.append([InlineKeyboardButton("◀️ رجوع", callback_data="menu_settings")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")


async def _channel_edit_name(query, ch_idx: int, context):
    """Enter edit mode for channel name."""
    context.user_data["awaiting_channel_name"] = ch_idx
    _, config = _get_db()
    channels = config.get("channels", [])
    if isinstance(channels, dict):
        channels = channels.get("channels", [])
    current_name = channels[ch_idx].get("name", "?") if ch_idx < len(channels) else "?"
    await query.edit_message_text(
        f"✏️ <b>تعديل اسم القناة</b>\n\n"
        f"الاسم الحالي: <b>{current_name}</b>\n\n"
        "أرسل الاسم الجديد كرسالة نصية:",
        parse_mode="HTML",
    )


# ═══════════════════════════════════════════════════════════════
# Voice Review (scene-by-scene approval)
# ═══════════════════════════════════════════════════════════════
# _voice_approve_all is defined above (near _img_approve_all)


async def _voice_regen_scene(query, job_id: str, scene_idx: int):
    """Regenerate voice for a single scene."""
    await query.answer(f"🔄 جاري إعادة توليد صوت المشهد {scene_idx + 1}...")

    import threading
    def _regen():
        try:
            db, _ = _get_db()
            scenes = db.get_scenes(job_id)
            scene = next((s for s in scenes if s["scene_index"] == scene_idx), None)
            if not scene:
                send_telegram_sync(f"❌ المشهد {scene_idx + 1} غير موجود")
                return

            from src.phase5_production.voice_gen import VoiceGenerator
            gen = VoiceGenerator()
            gen.ensure_server()

            # Use the voice the user selected (from DB), not default
            job = db.get_job(job_id)
            voice_id = job.get("selected_voice_id") if job else None
            if voice_id == "__edge_tts__":
                voice_id = None

            output_dir = f"output/{job_id}/voice"
            result = gen.generate(
                text=scene.get("narration_text", ""),
                output_dir=output_dir,
                filename=f"scene_{scene_idx:03d}",
                voice_id=voice_id,
            )
            if result.success:
                db.update_scene_asset(job_id, scene_idx, voice_path=result.audio_path)
                # Send new audio
                bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
                chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
                if not bot_token or not chat_id:
                    from src.core.config import load_config
                    cfg = load_config()
                    tg = cfg.get("settings", {}).get("telegram", {})
                    bot_token = bot_token or tg.get("bot_token", "")
                    chat_id = chat_id or tg.get("admin_chat_id") or tg.get("chat_id", "")
                import requests as req
                narration = (scene.get("narration_text") or "")[:500]
                caption = f"🔄 <b>مشهد {scene_idx + 1} (إعادة)</b> | {result.engine} ({result.duration_sec}ث)\n\n📝 {narration}"
                keyboard = json.dumps({"inline_keyboard": [[
                    {"text": "✅ موافق", "callback_data": f"va_{job_id}_{scene_idx}"},
                    {"text": "🔄 إعادة", "callback_data": f"vr_{job_id}_{scene_idx}"},
                ]]})
                with open(result.audio_path, "rb") as f:
                    req.post(f"https://api.telegram.org/bot{bot_token}/sendVoice", data={
                        "chat_id": chat_id, "caption": caption[:1024],
                        "parse_mode": "HTML", "reply_markup": keyboard,
                    }, files={"voice": ("voice.mp3", f, "audio/mpeg")}, timeout=30)
            else:
                send_telegram_sync(f"❌ فشل إعادة توليد صوت المشهد {scene_idx + 1}: {result.error}")
        except Exception as e:
            send_telegram_sync(f"❌ خطأ: {str(e)[:300]}")

    threading.Thread(target=_regen, daemon=True).start()


# ═══════════════════════════════════════════════════════════════
# Voice Cloning & Management
# ═══════════════════════════════════════════════════════════════

async def _voice_select(query, job_id: str, voice_id: str):
    """User selected a voice for pipeline generation."""
    state = _load_review_state()
    state[f"voice_selected_{job_id}"] = voice_id
    _save_review_state(state)

    if voice_id == "__edge_tts__":
        label = "🤖 صوت Edge TTS الافتراضي"
    else:
        from src.phase5_production.voice_cloner import VoiceCloner
        cloner = VoiceCloner()
        profile = cloner.get_voice(voice_id)
        label = f"👤 {profile.name}" if profile else voice_id

    db, _ = _get_db()
    # Transition back to voice phase so pipeline resumes
    try:
        from src.core.job_state_machine import JobStateMachine, JobStatus
        sm = JobStateMachine(db)
        sm.force_reset(job_id, JobStatus.VOICE)
    except Exception:
        db.update_job_status(job_id, "voice")
        db.conn.commit()

    await query.edit_message_text(
        f"🎙️ <b>تم اختيار الصوت:</b> {label}\n\n"
        f"⏳ جاري توليد التعليق الصوتي...\n"
        f"🆔 <code>{job_id}</code>",
        parse_mode="HTML",
    )
    _run_pipeline_async(job_id)


async def _settings_voices(query):
    """Show voice management menu."""
    from src.phase5_production.voice_cloner import VoiceCloner
    cloner = VoiceCloner()
    voices = cloner.list_voices()
    default_id = cloner.get_default_voice_id()

    if not voices:
        text = "🎙️ <b>إدارة الأصوات</b>\n\n📭 لا توجد أصوات مُسجلة."
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة صوت جديد", callback_data="vc_add")],
            [InlineKeyboardButton("◀️ رجوع", callback_data="menu_settings")],
        ])
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
        return

    text = f"🎙️ <b>إدارة الأصوات — {len(voices)} صوت</b>\n\n"
    buttons = []
    for v in voices:
        is_default = v.voice_id == default_id
        star = " ⭐" if is_default else ""
        text += f"👤 <b>{v.name}</b> ({v.voice_id}){star}\n   ⏱️ {v.duration_sec:.1f}ث\n\n"
        row = [
            InlineKeyboardButton("▶️ عينة", callback_data=f"vp_{v.voice_id}"),
            InlineKeyboardButton("🎤 اختبار بنص", callback_data=f"vt_{v.voice_id}"),
        ]
        if not is_default:
            row.append(InlineKeyboardButton("⭐ افتراضي", callback_data=f"vdf_{v.voice_id}"))
        row.append(InlineKeyboardButton("🗑️ حذف", callback_data=f"vd_{v.voice_id}"))
        buttons.append(row)

    buttons.append([InlineKeyboardButton("➕ إضافة صوت جديد", callback_data="vc_add")])
    buttons.append([InlineKeyboardButton("◀️ رجوع", callback_data="menu_settings")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")


async def _voice_add_start(query, context):
    """Start voice cloning conversation."""
    context.user_data["voice_clone_state"] = "awaiting_url"
    await query.edit_message_text(
        "🎙️ <b>إضافة صوت جديد</b>\n\n"
        "📎 أرسل رابط فيديو يوتيوب يحتوي على صوت الشخصية المطلوبة:",
        parse_mode="HTML",
    )


async def _voice_test_start(query, voice_id: str, context):
    """Start voice test — wait for text input."""
    from src.phase5_production.voice_cloner import VoiceCloner
    cloner = VoiceCloner()
    profile = cloner.get_voice(voice_id)
    name = profile.name if profile else voice_id

    context.user_data["voice_test_id"] = voice_id
    await query.edit_message_text(
        f"🎤 <b>اختبار صوت: {name}</b>\n\n"
        "أرسل النص الذي تريد اختباره:",
        parse_mode="HTML",
    )


async def _voice_play_sample(query, voice_id: str):
    """Send the reference audio sample as a voice message."""
    from src.phase5_production.voice_cloner import VoiceCloner
    cloner = VoiceCloner()
    profile = cloner.get_voice(voice_id)
    if not profile or not Path(profile.reference_audio).exists():
        await query.answer("❌ ملف الصوت غير موجود")
        return

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not bot_token or not chat_id:
        from src.core.config import load_config
        cfg = load_config()
        tg = cfg.get("settings", {}).get("telegram", {})
        bot_token = bot_token or tg.get("bot_token", "")
        chat_id = chat_id or tg.get("admin_chat_id") or tg.get("chat_id", "")

    import requests as req
    # Convert WAV to OGG for Telegram voice message
    import subprocess
    from src.phase5_production.voice_gen import FFMPEG as _FFMPEG
    ogg_path = str(Path(profile.reference_audio).with_suffix(".ogg"))
    subprocess.run(
        [_FFMPEG, "-y", "-i", profile.reference_audio,
         "-c:a", "libopus", "-b:a", "64k", ogg_path],
        capture_output=True, timeout=30,
    )

    try:
        with open(ogg_path, "rb") as f:
            req.post(
                f"https://api.telegram.org/bot{bot_token}/sendVoice",
                data={"chat_id": chat_id, "caption": f"🎙️ عينة صوت: {profile.name}"},
                files={"voice": (f"{voice_id}.ogg", f, "audio/ogg")},
                timeout=30,
            )
        await query.answer("▶️ تم إرسال العينة")
    except Exception as e:
        await query.answer(f"❌ خطأ: {str(e)[:50]}")


async def _voice_delete(query, voice_id: str):
    """Delete a voice profile."""
    from src.phase5_production.voice_cloner import VoiceCloner
    cloner = VoiceCloner()
    profile = cloner.get_voice(voice_id)
    name = profile.name if profile else voice_id
    cloner.delete_voice(voice_id)
    await query.answer(f"🗑️ تم حذف صوت: {name}")
    # Refresh voice list
    await _settings_voices(query)


async def _voice_set_default(query, voice_id: str):
    """Set a voice as default."""
    from src.phase5_production.voice_cloner import VoiceCloner
    cloner = VoiceCloner()
    profile = cloner.get_voice(voice_id)
    name = profile.name if profile else voice_id
    cloner.set_default_voice(voice_id)
    await query.answer(f"⭐ تم تعيين {name} كصوت افتراضي")
    await _settings_voices(query)


# ═══════════════════════════════════════════════════════════════
# Text Message Handler (for edit modes)
# ═══════════════════════════════════════════════════════════════

async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages for edit modes (script edit, image edit)."""
    user_data = context.user_data

    # Voice clone conversation flow
    if user_data.get("voice_clone_state") == "awaiting_url":
        url = update.message.text.strip()
        if "youtube.com" not in url and "youtu.be" not in url:
            await update.message.reply_text("❌ يرجى إرسال رابط يوتيوب صحيح.")
            return
        user_data["voice_clone_url"] = url
        user_data["voice_clone_state"] = "awaiting_name"
        await update.message.reply_text(
            "✅ تم استلام الرابط.\n\n"
            "📝 ما اسم هذه الشخصية الصوتية؟\n"
            '<i>مثال: "أحمد — معلق وثائقي"</i>',
            parse_mode="HTML",
        )
        return

    if user_data.get("voice_clone_state") == "awaiting_timestamps":
        # User sends narrator time ranges: "0:30-2:00, 5:15-8:00"
        raw = update.message.text.strip()
        ranges = _parse_time_ranges(raw)
        
        if not ranges:
            await update.message.reply_text(
                "❌ صيغة غير صحيحة.\n\n"
                "أرسل بهذا الشكل:\n"
                "<code>0:30-2:00</code>\n"
                "أو عدة مقاطع:\n"
                "<code>0:30-2:00, 5:15-8:00</code>",
                parse_mode="HTML",
            )
            return

        user_data["voice_clone_ranges"] = ranges
        total_sec = sum(e - s for s, e in ranges)
        ranges_str = ", ".join(f"{_fmt_time(s)}-{_fmt_time(e)}" for s, e in ranges)
        
        user_data["voice_clone_state"] = "selecting_categories"
        user_data["voice_clone_categories"] = []

        from src.phase5_production.voice_cloner import VOICE_CATEGORIES
        buttons = []
        for cat_id, cat_label in VOICE_CATEGORIES.items():
            buttons.append([InlineKeyboardButton(f"⬜ {cat_label}", callback_data=f"vcat_{cat_id}")])
        buttons.append([InlineKeyboardButton("✅ تأكيد الاختيار", callback_data="vcat_confirm")])

        await update.message.reply_text(
            f"✅ تم — <b>{len(ranges)} مقطع</b> ({total_sec:.0f} ثانية)\n"
            f"⏱️ {ranges_str}\n\n"
            "🎭 <b>اختر أنواع المحتوى:</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    if user_data.get("voice_clone_state") == "awaiting_name":
        user_data["voice_clone_name"] = update.message.text.strip()
        user_data["voice_clone_state"] = "awaiting_timestamps"

        await update.message.reply_text(
            "✅ تم.\n\n"
            "⏱️ <b>حدد مقاطع المعلق الرئيسي:</b>\n\n"
            "أرسل بداية ونهاية كل مقطع فيه صوت المعلق:\n\n"
            "مقطع واحد:\n"
            "<code>0:30-2:00</code>\n\n"
            "عدة مقاطع (تجاوز الضيوف):\n"
            "<code>0:30-2:00, 5:15-8:00, 10:00-12:30</code>\n\n"
            "<i>💡 الصيغة: دقائق:ثواني-دقائق:ثواني\n"
            "مثال: 1:30 = دقيقة و30 ثانية</i>",
            parse_mode="HTML",
        )
        return

        from src.phase5_production.voice_cloner import VOICE_CATEGORIES
        buttons = []
        for cat_id, cat_label in VOICE_CATEGORIES.items():
            buttons.append([InlineKeyboardButton(f"⬜ {cat_label}", callback_data=f"vcat_{cat_id}")])
        buttons.append([InlineKeyboardButton("✅ تأكيد الاختيار", callback_data="vcat_confirm")])

        await update.message.reply_text(
            "✅ تم.\n\n🎭 <b>اختر أنواع المحتوى لهذا الصوت:</b>\n"
            "<i>اضغط على الأنواع المناسبة ثم اضغط تأكيد</i>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    if user_data.get("voice_clone_state") == "awaiting_id":
        import re
        voice_id = re.sub(r'[^a-zA-Z0-9_]', '', update.message.text.strip())
        if not voice_id:
            await update.message.reply_text("❌ المعرف غير صالح. استخدم حروف إنجليزية وأرقام فقط.")
            return

        url = user_data.pop("voice_clone_url", "")
        name = user_data.pop("voice_clone_name", "")
        category = user_data.pop("voice_clone_category", "documentary")
        time_ranges = user_data.pop("voice_clone_ranges", [(0, 480)])
        user_data.pop("voice_clone_state", None)
        user_data.pop("voice_clone_start_sec", None)

        await update.message.reply_text(
            "⏳ <b>جاري استخراج الصوت وإنشاء الملف الصوتي...</b>\n\n"
            "قد يستغرق هذا بضع دقائق (تحميل + فصل الصوت + معالجة).",
            parse_mode="HTML",
        )

        # Run in background thread
        import threading
        def _clone_voice():
            try:
                from src.phase5_production.voice_cloner import VoiceCloner
                cloner = VoiceCloner()
                from src.phase5_production.voice_cloner import VOICE_CATEGORIES
                profile = cloner.clone_from_youtube(url, voice_id, name, category=category, narrator_ranges=time_ranges)
                cat_label = VOICE_CATEGORIES.get(category, category)

                # Check mood references
                meta_path = cloner.VOICES_DIR / f"{voice_id}.json"
                moods_found = []
                if meta_path.exists():
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    moods_found = list(meta.get("mood_references", {}).keys())

                mood_text = ""
                if moods_found:
                    mood_labels = {"calm": "🧘 هادئ", "dramatic": "🔥 درامي", "question": "❓ تساؤل"}
                    mood_text = "\n🎭 أنماط مستخرجة: " + " | ".join(mood_labels.get(m, m) for m in moods_found)

                send_telegram_sync(
                    f"✅ <b>تم إنشاء الصوت بنجاح!</b>\n\n"
                    f"👤 <b>{profile.name}</b> ({profile.voice_id})\n"
                    f"🎭 النوع: {cat_label}\n"
                    f"⏱️ مدة العينة: {profile.duration_sec:.1f} ثانية"
                    f"{mood_text}\n\n"
                    f"اذهب إلى ⚙️ الإعدادات → 🎙️ إدارة الأصوات لاختبار الصوت.",
                )
            except Exception as e:
                send_telegram_sync(f"❌ <b>فشل استخراج الصوت:</b>\n\n{str(e)[:500]}")

        threading.Thread(target=_clone_voice, daemon=True).start()
        return

    # Voice test — user sends text to generate with a specific voice
    if "voice_test_id" in user_data:
        voice_id = user_data.pop("voice_test_id")
        test_text = update.message.text.strip()
        if not test_text:
            await update.message.reply_text("❌ أرسل نصاً للاختبار.")
            return

        await update.message.reply_text("⏳ جاري توليد الصوت...")

        import threading
        def _test_voice():
            try:
                from src.phase5_production.voice_gen import VoiceGenerator, FFMPEG as _FFMPEG
                import tempfile
                gen = VoiceGenerator()
                gen.config.max_retries = 10
                gen.ensure_server()
                with tempfile.TemporaryDirectory() as tmpdir:
                    result = gen.generate(text=test_text, output_dir=tmpdir, filename="test", voice_id=voice_id)
                    if result.success and result.audio_path:
                        # Convert to OGG and send as voice
                        import subprocess
                        ogg_path = str(Path(result.audio_path).with_suffix(".ogg"))
                        subprocess.run(
                            [_FFMPEG, "-y", "-i", result.audio_path, "-c:a", "libopus", "-b:a", "64k", ogg_path],
                            capture_output=True, timeout=30,
                        )
                        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
                        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
                        if not bot_token or not chat_id:
                            from src.core.config import load_config
                            cfg = load_config()
                            tg = cfg.get("settings", {}).get("telegram", {})
                            bot_token = bot_token or tg.get("bot_token", "")
                            chat_id = chat_id or tg.get("admin_chat_id") or tg.get("chat_id", "")
                        import requests as req
                        with open(ogg_path, "rb") as f:
                            req.post(
                                f"https://api.telegram.org/bot{bot_token}/sendVoice",
                                data={"chat_id": chat_id, "caption": f"🎤 اختبار صوت ({result.engine}, {result.duration_sec}s)"},
                                files={"voice": ("test.ogg", f, "audio/ogg")},
                                timeout=60,
                            )
                    else:
                        send_telegram_sync(f"❌ فشل توليد الصوت: {result.error}")
            except Exception as e:
                send_telegram_sync(f"❌ خطأ في الاختبار: {str(e)[:300]}")

        threading.Thread(target=_test_voice, daemon=True).start()
        return

    # Script edit mode
    if "awaiting_script_edit" in user_data:
        job_id = user_data.pop("awaiting_script_edit")
        edit_text = update.message.text

        state = _load_review_state()
        state[f"script_edit_{job_id}"] = {"action": "edit", "instructions": edit_text}
        _save_review_state(state)

        db, _ = _get_db()
        db.conn.execute("UPDATE jobs SET script_revisions = script_revisions + 1 WHERE id = ?", (job_id,))
        db.update_job_status(job_id, "script")
        db.conn.commit()

        await update.message.reply_text(
            f"✏️ <b>تم استلام التعديلات</b>\n\n"
            f"📝 {edit_text[:200]}\n\n"
            "جاري إعادة كتابة السكربت...",
            parse_mode="HTML",
        )
        _run_pipeline_async(job_id)
        return

    # Channel name edit mode
    if "awaiting_channel_name" in user_data:
        ch_idx = user_data.pop("awaiting_channel_name")
        new_name = update.message.text.strip()
        try:
            import yaml
            channels_path = Path("config/channels.yaml")
            with open(channels_path, encoding="utf-8") as f:
                channels_data = yaml.safe_load(f) or {}
            channel_list = channels_data.get("channels", [])
            if ch_idx < len(channel_list):
                old_name = channel_list[ch_idx].get("name", "?")
                channel_list[ch_idx]["name"] = new_name
                channels_data["channels"] = channel_list
                with open(channels_path, "w", encoding="utf-8") as f:
                    yaml.dump(channels_data, f, allow_unicode=True, default_flow_style=False)
                await update.message.reply_text(
                    f"✅ تم تغيير اسم القناة من <b>{old_name}</b> إلى <b>{new_name}</b>",
                    parse_mode="HTML",
                )
            else:
                await update.message.reply_text("❌ القناة غير موجودة")
        except Exception as e:
            await update.message.reply_text(f"❌ خطأ: {e}")
        return

    # Image edit mode
    if "awaiting_img_edit" in user_data:
        info = user_data.pop("awaiting_img_edit")
        job_id = info["job_id"]
        scene_idx = info["scene_idx"]
        edit_text = update.message.text

        state = _load_review_state()
        key = f"images_{job_id}"
        if key not in state:
            state[key] = {"approved": [], "rejected": [], "edits": {}}
        state[key]["edits"][str(scene_idx)] = {"action": "edit", "instructions": edit_text}
        _save_review_state(state)

        await update.message.reply_text(
            f"✏️ تم حفظ تعديلات المشهد {scene_idx + 1}",
            parse_mode="HTML",
        )
        return


# ═══════════════════════════════════════════════════════════════
# Handler Registration
# ═══════════════════════════════════════════════════════════════

def register_callbacks(app):
    """Register callback query handler and text message handler."""
    app.add_handler(CallbackQueryHandler(callback_router))
    # Text handler for edit modes — low priority group so it doesn't override commands
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler), group=1)
    logger.info("Telegram callback handlers registered")
