import asyncio
import logging
import sqlite3
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Optional, Set

from aiogram import Bot

from config import BOT_TOKEN, DATABASE_URL, HEADLESS
from core.selenium_worker import SeleniumWorker
from db.engine import get_session
from db.repository import OrderLogRepository, SettingsRepository

logger = logging.getLogger(__name__)

# Derive the raw sqlite file path from the async URL, e.g.:
#   "sqlite+aiosqlite:///./data/bot.db"  →  "./data/bot.db"
_DB_PATH = DATABASE_URL.replace("sqlite+aiosqlite:///", "")


def _db_add_sync(slug: str, amount: Optional[float], status: str) -> None:
    """Write an order_log entry synchronously (safe to call from any thread)."""
    try:
        con = sqlite3.connect(_DB_PATH)
        con.execute(
            "INSERT INTO order_log (order_slug, amount, status, taken_at) VALUES (?, ?, ?, ?)",
            (
                slug,
                float(amount) if amount is not None else None,
                status,
                datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f"),
            ),
        )
        con.commit()
        con.close()
        logger.info("DB write OK: slug=%s status=%s", slug, status)
    except Exception as exc:
        logger.error("DB write failed: slug=%s status=%s err=%s", slug, status, exc)


def _tg_send_sync(chat_ids: Set[int], text: str) -> None:
    """Send a Telegram message synchronously via urllib (no asyncio required)."""
    if not chat_ids:
        logger.warning("_tg_send_sync: no chat_ids registered, cannot send")
        return
    for chat_id in list(chat_ids):
        try:
            payload = urllib.parse.urlencode(
                {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
            ).encode()
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                data=payload,
            )
            urllib.request.urlopen(req, timeout=10)
            logger.info("Sync TG sent to chat_id=%s", chat_id)
        except Exception as exc:
            logger.warning("Sync TG send failed chat_id=%s: %s", chat_id, exc)


class OrderProcessor:
    def __init__(self, bot: Bot) -> None:
        self._bot = bot
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._chat_ids: Set[int] = set()
        self._notify_taken: bool = True
        self._worker = SeleniumWorker(
            on_order_taken=self._on_taken,
            on_order_failed=self._on_failed,
            headless=HEADLESS,
        )

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def set_notify_taken(self, value: bool) -> None:
        self._notify_taken = value
        logger.info("notify_taken set to %s", value)

    def register_chat(self, chat_id: int) -> None:
        if chat_id in self._chat_ids:
            return
        self._chat_ids.add(chat_id)
        logger.info("Chat registered: %s (total: %d)", chat_id, len(self._chat_ids))
        # Persist so it's available after restart
        try:
            con = sqlite3.connect(_DB_PATH)
            con.execute("UPDATE settings SET chat_id = ? WHERE id = 1", (chat_id,))
            con.commit()
            con.close()
        except Exception as exc:
            logger.warning("Failed to persist chat_id=%s: %s", chat_id, exc)

    def is_running(self) -> bool:
        return self._worker.is_running()

    async def start(self) -> bool:
        async with get_session() as session:
            repo = SettingsRepository(session)
            settings = await repo.get_or_create()

        if not settings.login or not settings.password:
            return False

        # Cache notify_taken
        self._notify_taken = bool(settings.notify_taken) if settings.notify_taken is not None else True

        # Restore persisted chat_id (so notifications work even after restart)
        if settings.chat_id and settings.chat_id not in self._chat_ids:
            self._chat_ids.add(settings.chat_id)
            logger.info("Restored chat_id=%s from DB", settings.chat_id)

        await self._set_active(True)
        self._worker.start(
            login=settings.login,
            password=settings.password,
            min_amount=settings.min_amount,
            max_amount=settings.max_amount,
        )
        return True

    async def stop(self) -> None:
        await self._set_active(False)
        self._worker.stop()

    async def _set_active(self, value: bool) -> None:
        async with get_session() as session:
            repo = SettingsRepository(session)
            await repo.update(is_active=value)

    # ── Callbacks called from the Selenium thread ────────────────────────────

    def _on_taken(self, slug: str, amount: Optional[float]) -> None:
        logger.info(
            "_on_taken: slug=%s amount=%s notify=%s chat_ids=%s loop_set=%s",
            slug, amount, self._notify_taken, self._chat_ids, self._loop is not None,
        )
        # 1. Write to DB synchronously — guaranteed, no asyncio dependency
        _db_add_sync(slug, amount, "taken")

        # 2. Send TG notification synchronously
        if self._notify_taken:
            amount_str = f"{amount:,.0f}" if amount else "—"
            text = f"Ордер взят\n\nID: <code>{slug}</code>\nСумма: {amount_str} RUB"
            _tg_send_sync(self._chat_ids, text)

    def _on_failed(self, slug: str, amount: Optional[float]) -> None:
        logger.info("_on_failed: slug=%s amount=%s", slug, amount)
        # 1. Write to DB synchronously
        _db_add_sync(slug, amount, "failed")

        # 2. Send notification with retry/skip keyboard via asyncio
        if self._loop:
            future = asyncio.run_coroutine_threadsafe(
                self._send_failed_notification(slug, amount), self._loop
            )
            future.add_done_callback(self._log_future_exc)
        else:
            # Fallback: plain sync message without keyboard
            amount_str = f"{amount:,.0f}" if amount else "—"
            text = (
                f"Не удалось взять ордер\n\n"
                f"ID: <code>{slug}</code>\nСумма: {amount_str} RUB"
            )
            _tg_send_sync(self._chat_ids, text)

    @staticmethod
    def _log_future_exc(future) -> None:
        try:
            exc = future.exception()
            if exc:
                logger.error("Async notification error: %s", exc, exc_info=exc)
        except Exception as e:
            logger.error("Could not read future exception: %s", e)

    # ── Async helpers (run in event loop) ───────────────────────────────────

    async def _send_failed_notification(self, slug: str, amount: Optional[float]) -> None:
        from aiogram.utils.keyboard import InlineKeyboardBuilder

        builder = InlineKeyboardBuilder()
        builder.button(text="Повторить", callback_data=f"retry:{slug}")
        builder.button(text="Пропустить", callback_data=f"skip:{slug}")

        amount_str = f"{amount:,.0f}" if amount else "—"
        text = (
            f"Не удалось взять ордер\n\n"
            f"ID: <code>{slug}</code>\nСумма: {amount_str} RUB\n\n"
            f"Повторить попытку?"
        )
        await self._broadcast(text, reply_markup=builder.as_markup())

    async def _broadcast(self, text: str, **kwargs) -> None:
        if not self._chat_ids:
            logger.warning("_broadcast: no registered chats")
        for chat_id in list(self._chat_ids):
            try:
                await self._bot.send_message(chat_id, text, parse_mode="HTML", **kwargs)
            except Exception as exc:
                logger.warning("_broadcast failed chat_id=%s: %s", chat_id, exc)
