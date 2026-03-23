"""
Telegram Bot — Core layer.
Bot init, message routing, media sending (albums up to 10, videos, documents).
Rate limiting (25 msg/sec).
"""

import os
import asyncio
import logging
from pathlib import Path
from typing import Optional

from telegram import (
    Bot,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaVideo,
)
from telegram.ext import Application

logger = logging.getLogger(__name__)


class RateLimiter:
    """Token-bucket rate limiter for Telegram API calls."""

    def __init__(self, rate: float = 25.0):
        self._rate = rate
        self._tokens = rate
        self._last = asyncio.get_event_loop().time() if asyncio.get_event_loop().is_running() else 0
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            now = asyncio.get_event_loop().time()
            elapsed = now - self._last
            self._tokens = min(self._rate, self._tokens + elapsed * self._rate)
            self._last = now
            if self._tokens < 1:
                wait = (1 - self._tokens) / self._rate
                await asyncio.sleep(wait)
                self._tokens = 0
            else:
                self._tokens -= 1


def _build_markup(buttons: Optional[list] = None) -> Optional[InlineKeyboardMarkup]:
    """Build InlineKeyboardMarkup from nested list of button dicts."""
    if not buttons:
        return None
    rows = []
    for row in buttons:
        if isinstance(row, dict):
            row = [row]
        rows.append([
            InlineKeyboardButton(b["text"], callback_data=b["data"])
            for b in row
        ])
    return InlineKeyboardMarkup(rows)


class TelegramBot:
    """
    Core Telegram bot — handles connection, media, rate limiting.
    Higher-level handlers and conversations are registered externally.
    """

    def __init__(self, config: dict):
        self.token = config.get("bot_token", "")
        self.chat_id = config.get("admin_chat_id") or config.get("chat_id", "")
        self._rate_limiter = RateLimiter(rate=25)
        self._app: Optional[Application] = None
        self._bot: Optional[Bot] = None
        if self.token:
            self._bot = Bot(token=self.token)
        logger.info("TelegramBot initialized (chat_id=%s)", self.chat_id)

    # ------------------------------------------------------------------
    # Application lifecycle (used when running the full polling loop)
    # ------------------------------------------------------------------

    def build_app(self) -> Application:
        """Build and return the Application (for handler registration)."""
        if self._app is None:
            self._app = Application.builder().token(self.token).build()
            self._register_handlers(self._app)
        return self._app

    def _register_handlers(self, app: Application):
        """Register command and callback handlers."""
        try:
            from src.core.telegram_commands import register_commands
            from src.core.telegram_callbacks import register_callbacks
            register_commands(app)
            register_callbacks(app)
            logger.info("Telegram interactive handlers registered")
        except Exception as e:
            logger.warning(f"Failed to register interactive handlers: {e}")

    @property
    def app(self) -> Application:
        return self.build_app()

    @property
    def bot(self) -> Bot:
        if self._app and self._app.bot:
            return self._app.bot
        return self._bot  # type: ignore[return-value]

    async def start_polling(self):
        """Start the bot in polling mode (blocks forever)."""
        app = self.build_app()
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram bot polling started")
        # Keep alive — block until cancelled
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass

    async def stop(self):
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()

    # ------------------------------------------------------------------
    # Sending helpers
    # ------------------------------------------------------------------

    async def send(
        self,
        text: str,
        buttons: Optional[list] = None,
        chat_id: Optional[str] = None,
        parse_mode: str = "HTML",
    ) -> None:
        """Send a text message with optional inline buttons."""
        await self._rate_limiter.acquire()
        target = chat_id or self.chat_id
        markup = _build_markup(buttons)
        await self.bot.send_message(
            chat_id=target,
            text=text,
            reply_markup=markup,
            parse_mode=parse_mode,
        )

    async def send_image_album(
        self,
        images: list[dict],
        chat_id: Optional[str] = None,
    ) -> None:
        """
        Send images as Telegram media group (max 10 per album).
        images: [{"path": str, "caption": str (optional)}]
        Splits into multiple albums if >10.
        """
        target = chat_id or self.chat_id
        for chunk in _chunks(images, 10):
            await self._rate_limiter.acquire()
            media = []
            open_files = []
            for i, img in enumerate(chunk):
                f = open(img["path"], "rb")
                open_files.append(f)
                caption = img.get("caption", "")[:1024]
                media.append(InputMediaPhoto(
                    media=f,
                    caption=caption if caption else None,
                    parse_mode="HTML" if caption else None,
                ))
            try:
                await self.bot.send_media_group(chat_id=target, media=media)
            finally:
                for f in open_files:
                    f.close()
            await asyncio.sleep(1)  # gentle pause between albums

    async def send_video(
        self,
        video_path: str,
        caption: str = "",
        buttons: Optional[list] = None,
        chat_id: Optional[str] = None,
    ) -> None:
        """Send a video file. Falls back to document for files >50 MB."""
        await self._rate_limiter.acquire()
        target = chat_id or self.chat_id
        markup = _build_markup(buttons)
        file_size = os.path.getsize(video_path)

        with open(video_path, "rb") as f:
            if file_size > 50 * 1024 * 1024:
                await self.bot.send_document(
                    chat_id=target,
                    document=f,
                    caption=caption[:1024] or None,
                    reply_markup=markup,
                    parse_mode="HTML",
                )
            else:
                await self.bot.send_video(
                    chat_id=target,
                    video=f,
                    caption=caption[:1024] or None,
                    reply_markup=markup,
                    supports_streaming=True,
                    parse_mode="HTML",
                )

    async def send_document(
        self,
        file_path: str,
        caption: str = "",
        chat_id: Optional[str] = None,
    ) -> None:
        """Send an arbitrary file as a Telegram document."""
        await self._rate_limiter.acquire()
        target = chat_id or self.chat_id
        with open(file_path, "rb") as f:
            await self.bot.send_document(
                chat_id=target,
                document=f,
                caption=caption[:1024] or None,
                parse_mode="HTML",
            )

    async def alert(self, text: str, chat_id: Optional[str] = None) -> None:
        """Send an alert message with 🚨 prefix."""
        await self.send(f"🚨 {text}", chat_id=chat_id)

    async def edit_message(
        self,
        chat_id: str,
        message_id: int,
        text: str,
        buttons: Optional[list] = None,
    ) -> None:
        await self._rate_limiter.acquire()
        markup = _build_markup(buttons)
        await self.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=markup,
            parse_mode="HTML",
        )


# ------------------------------------------------------------------
# Utility
# ------------------------------------------------------------------

def _chunks(lst: list, n: int):
    for i in range(0, len(lst), n):
        yield lst[i : i + n]
