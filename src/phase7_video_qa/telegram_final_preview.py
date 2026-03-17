"""
Phase 7D — Telegram Final Preview: Send composed video with QA scores + approve/reject.
Sends the full video to the admin chat with inline keyboard buttons.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

from src.core.config import load_config, get_setting
from src.core.telegram_bot import TelegramBot

logger = logging.getLogger(__name__)


def _format_duration(seconds: float) -> str:
    """Format seconds as MM:SS or HH:MM:SS."""
    total = int(seconds)
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _score_emoji(score: float) -> str:
    """Return emoji based on score value."""
    if score >= 9.0:
        return "🟢"
    elif score >= 7.0:
        return "🟡"
    elif score >= 5.0:
        return "🟠"
    return "🔴"


async def _send_preview(
    job_id: str,
    video_path: str,
    title: str,
    duration_sec: float,
    technical_score: float,
    content_score: float,
    compliance_passed: bool,
    issues: list[str] = None,
    bot: TelegramBot = None,
    chat_id: Optional[str] = None,
) -> None:
    """
    Send final video to Telegram with QA scores and approve/reject buttons.
    """
    issues = issues or []

    # Build caption
    compliance_str = "✅ PASS" if compliance_passed else "❌ FAIL"
    tech_emoji = _score_emoji(technical_score)
    content_emoji = _score_emoji(content_score)

    caption_lines = [
        f"🎬 <b>FINAL VIDEO — Ready for Review</b>",
        f"📋 Topic: <i>{title}</i>",
        f"⏱️ Duration: {_format_duration(duration_sec)}",
        f"",
        f"🎯 <b>QA Scores:</b>",
        f"   {tech_emoji} Technical: {technical_score:.1f}/10",
        f"   {content_emoji} Content Match: {content_score:.1f}/10",
        f"   Compliance: {compliance_str}",
    ]

    if issues:
        caption_lines.append("")
        caption_lines.append(f"⚠️ <b>Issues ({len(issues)}):</b>")
        for issue in issues[:5]:  # Max 5 in caption
            caption_lines.append(f"  • {issue[:80]}")
        if len(issues) > 5:
            caption_lines.append(f"  ... +{len(issues) - 5} more")

    caption_lines.append("")
    caption_lines.append(f"🆔 <code>{job_id}</code>")

    caption = "\n".join(caption_lines)

    # Inline keyboard buttons
    buttons = [
        [
            {"text": "✅ Publish", "data": f"p7_publish:{job_id}"},
            {"text": "🔄 Regenerate", "data": f"p7_regen:{job_id}"},
            {"text": "❌ Cancel", "data": f"p7_cancel:{job_id}"},
        ]
    ]

    # Initialize bot if not provided
    if bot is None:
        config = load_config()
        tg_config = get_setting("telegram", config) or {}
        bot = TelegramBot(tg_config)

    target = chat_id or bot.chat_id

    # Send video with caption and buttons
    await bot.send_video(
        video_path=video_path,
        caption=caption,
        buttons=buttons,
        chat_id=target,
    )

    logger.info("Final preview sent to Telegram for job %s", job_id)


def send_final_preview(
    job_id: str,
    video_path: str,
    title: str,
    duration_sec: float,
    technical_score: float,
    content_score: float,
    compliance_passed: bool,
    issues: list[str] = None,
    bot: TelegramBot = None,
    chat_id: Optional[str] = None,
) -> None:
    """
    Synchronous wrapper for sending final preview to Telegram.
    Handles event loop creation if needed.
    """
    coro = _send_preview(
        job_id=job_id,
        video_path=video_path,
        title=title,
        duration_sec=duration_sec,
        technical_score=technical_score,
        content_score=content_score,
        compliance_passed=compliance_passed,
        issues=issues,
        bot=bot,
        chat_id=chat_id,
    )

    try:
        loop = asyncio.get_running_loop()
        # Already in async context — schedule as task
        loop.create_task(coro)
    except RuntimeError:
        # No running loop — create one
        asyncio.run(coro)
