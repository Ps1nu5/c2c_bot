import asyncio
import logging
from typing import Optional, Set

from aiogram import Bot

from config import HEADLESS
from core.selenium_worker import SeleniumWorker
from db.engine import get_session
from db.repository import OrderLogRepository, SettingsRepository

logger = logging.getLogger(__name__)


class OrderProcessor:
    def __init__(self, bot: Bot) -> None:
        self._bot = bot
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._chat_ids: Set[int] = set()
        self._worker = SeleniumWorker(
            on_order_taken=self._on_taken,
            on_order_failed=self._on_failed,
            headless=HEADLESS,
        )

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def register_chat(self, chat_id: int) -> None:
        self._chat_ids.add(chat_id)

    def is_running(self) -> bool:
        return self._worker.is_running()

    async def start(self) -> bool:
        async with get_session() as session:
            repo = SettingsRepository(session)
            settings = await repo.get_or_create()

        if not settings.login or not settings.password:
            return False

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

    def _on_taken(self, slug: str, amount: Optional[float]) -> None:
        if self._loop:
            asyncio.run_coroutine_threadsafe(
                self._handle_taken(slug, amount), self._loop
            )

    def _on_failed(self, slug: str, amount: Optional[float]) -> None:
        if self._loop:
            asyncio.run_coroutine_threadsafe(
                self._handle_failed(slug, amount), self._loop
            )

    async def _handle_taken(self, slug: str, amount: Optional[float]) -> None:
        async with get_session() as session:
            repo = OrderLogRepository(session)
            await repo.add(slug, amount, "taken")

        amount_str = f"{amount:,.0f}" if amount else "—"
        text = f"Ордер взят\n\nID: <code>{slug}</code>\nСумма: {amount_str} RUB"
        await self._broadcast(text)

    async def _handle_failed(self, slug: str, amount: Optional[float]) -> None:
        from aiogram.utils.keyboard import InlineKeyboardBuilder

        async with get_session() as session:
            repo = OrderLogRepository(session)
            await repo.add(slug, amount, "failed")

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
        for chat_id in list(self._chat_ids):
            try:
                await self._bot.send_message(chat_id, text, parse_mode="HTML", **kwargs)
            except Exception as exc:
                logger.warning("Failed to send message to %s: %s", chat_id, exc)
