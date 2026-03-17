"""
Phase 1: Present ranked topics to user via Telegram inline keyboard.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class TopicPresenter:
    """Present topics to user via Telegram for selection."""

    def __init__(self, config: dict):
        self.config = config
        self.bot_token = config["settings"]["telegram"]["bot_token"]
        self.chat_id = config["settings"]["telegram"]["admin_chat_id"]

    def format_topics_message(self, ranked_topics: list[dict]) -> str:
        """Format ranked topics into a readable Telegram message."""
        lines = ["🔍 <b>البحث مكتمل! اختر موضوعاً:</b>\n"]

        for i, topic in enumerate(ranked_topics[:10], 1):
            score = topic.get("score", 0)
            angle = topic.get("suggested_angle", "")
            region = topic.get("suggested_region", "global")

            # Score emoji
            if score >= 8:
                score_emoji = "🔥"
            elif score >= 6:
                score_emoji = "⭐"
            else:
                score_emoji = "📌"

            # Region flag
            region_flags = {
                "iraq": "🇮🇶", "gulf": "🇸🇦", "egypt": "🇪🇬",
                "levant": "🇱🇧", "maghreb": "🇲🇦", "global": "🌍",
            }
            flag = region_flags.get(region, "🌍")

            lines.append(
                f"{i}️⃣ {score_emoji} <b>{topic['topic']}</b>\n"
                f"   📊 Score: {score:.1f}/10 | {flag} {region}\n"
                f"   💡 {angle}\n"
            )

        lines.append("\nاختر رقم الموضوع أو اكتب موضوعك الخاص:")
        return "\n".join(lines)

    def build_inline_keyboard(self, ranked_topics: list[dict], job_id: str) -> list[list[dict]]:
        """Build Telegram inline keyboard buttons for topic selection."""
        buttons = []
        row = []

        for i, topic in enumerate(ranked_topics[:10]):
            short_title = topic["topic"][:30]
            row.append({
                "text": f"{i+1}️⃣ {short_title}",
                "data": f"select_topic:{job_id}:{i}",
            })
            if len(row) == 2:  # 2 buttons per row
                buttons.append(row)
                row = []

        if row:
            buttons.append(row)

        # Add refresh button
        buttons.append([{
            "text": "🔄 مواضيع جديدة",
            "data": f"refresh_topics:{job_id}",
        }])

        return buttons

    async def present_to_user_async(
        self,
        ranked_topics: list[dict],
        job_id: str,
        bot=None,
    ) -> None:
        """
        Send topics to Telegram with inline keyboard.
        Used when telegram bot instance is available.
        """
        if bot is None:
            logger.warning("No Telegram bot instance — logging topics only")
            for i, t in enumerate(ranked_topics[:10], 1):
                logger.info(f"  {i}. [{t.get('score', 0):.1f}] {t['topic']}")
            return

        message = self.format_topics_message(ranked_topics)
        keyboard = self.build_inline_keyboard(ranked_topics, job_id)

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(b["text"], callback_data=b["data"]) for b in row]
            for row in keyboard
        ])

        await bot.send_message(
            chat_id=self.chat_id,
            text=message,
            reply_markup=markup,
            parse_mode="HTML",
        )

    def present_to_user_sync(
        self, ranked_topics: list[dict], job_id: str
    ) -> dict:
        """
        Synchronous version — sends via requests (no async bot needed).
        Returns the formatted data for the orchestrator to send.
        """
        import requests

        message = self.format_topics_message(ranked_topics)
        keyboard = self.build_inline_keyboard(ranked_topics, job_id)

        # Build Telegram API inline keyboard
        inline_keyboard = []
        for row in keyboard:
            inline_keyboard.append([
                {"text": b["text"], "callback_data": b["data"]}
                for b in row
            ])

        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML",
            "reply_markup": {"inline_keyboard": inline_keyboard},
        }

        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            logger.info(f"Topics sent to Telegram for job {job_id}")
            return resp.json()
        except Exception as e:
            logger.error(f"Failed to send topics to Telegram: {e}")
            # Log topics for manual review
            for i, t in enumerate(ranked_topics[:10], 1):
                logger.info(f"  {i}. [{t.get('score', 0):.1f}] {t['topic']}")
            return {}
