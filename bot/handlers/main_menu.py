from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot.keyboards.inline import main_menu_keyboard
from db.engine import get_session
from db.repository import SettingsRepository

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    async with get_session() as session:
        repo = SettingsRepository(session)
        settings = await repo.get_or_create()

    from main import processor

    is_running = processor.is_running()
    has_credentials = bool(settings.login and settings.password)

    status_line = "Статус: работает" if is_running else "Статус: остановлен"

    filter_parts = []
    if settings.min_amount is not None:
        filter_parts.append(f"от {settings.min_amount:,.0f}")
    if settings.max_amount is not None:
        filter_parts.append(f"до {settings.max_amount:,.0f}")
    filter_line = (
        f"Фильтр суммы: {' '.join(filter_parts)} ₽"
        if filter_parts
        else "Фильтр суммы: не задан"
    )

    notify_line = (
        "Уведомления о взятых ордерах: ВКЛ"
        if settings.notify_taken
        else "Уведомления о взятых ордерах: ВЫКЛ"
    )

    text = (
        f"Cards2cards бот\n\n"
        f"{status_line}\n"
        f"{filter_line}\n"
        f"{notify_line}"
    )

    await message.answer(text, reply_markup=main_menu_keyboard(is_running, has_credentials))
