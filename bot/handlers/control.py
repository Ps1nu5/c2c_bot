from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.keyboards.inline import main_menu_keyboard
from db.engine import get_session
from db.repository import OrderLogRepository, SettingsRepository

router = Router()


@router.callback_query(F.data == "bot:start")
async def bot_start(callback: CallbackQuery) -> None:
    from main import processor

    if processor.is_running():
        await callback.answer("Бот уже запущен.", show_alert=True)
        return

    await callback.message.edit_text("Запускаю бота, подождите...")
    success = await processor.start()

    if not success:
        await callback.message.edit_text(
            "Не удалось запустить: не заданы логин и пароль.\nПерейдите в настройки.",
            reply_markup=main_menu_keyboard(False, False),
        )
    else:
        await callback.message.edit_text(
            "Бот запущен. Начинаю мониторинг новых ордеров.",
            reply_markup=main_menu_keyboard(True, True),
        )
    await callback.answer()


@router.callback_query(F.data == "bot:stop")
async def bot_stop(callback: CallbackQuery) -> None:
    from main import processor

    if not processor.is_running():
        await callback.answer("Бот уже остановлен.", show_alert=True)
        return

    await callback.message.edit_text("Останавливаю бота...")
    await processor.stop()

    async with get_session() as session:
        repo = SettingsRepository(session)
        settings = await repo.get_or_create()

    await callback.message.edit_text(
        "Бот остановлен.",
        reply_markup=main_menu_keyboard(False, bool(settings.login and settings.password)),
    )
    await callback.answer()


@router.callback_query(F.data == "bot:no_settings")
async def bot_no_settings(callback: CallbackQuery) -> None:
    await callback.answer(
        "Сначала заполните настройки фильтров (логин и пароль).",
        show_alert=True,
    )


@router.callback_query(F.data == "stats:show")
async def stats_show(callback: CallbackQuery) -> None:
    async with get_session() as session:
        log_repo = OrderLogRepository(session)
        taken = await log_repo.count_taken()
        failed = await log_repo.count_failed()
        last = await log_repo.last_entries(5)

    lines = [
        f"Статистика\n",
        f"Взято ордеров: {taken}",
        f"Ошибок: {failed}",
    ]

    if last:
        lines.append("\nПоследние 5 записей:")
        for entry in last:
            amount_str = f"{entry.amount:,.0f} RUB" if entry.amount else "—"
            dt_str = entry.taken_at.strftime("%d.%m %H:%M")
            icon = "+" if entry.status == "taken" else "x"
            lines.append(f"[{icon}] {dt_str}  {amount_str}  <code>{entry.order_slug[:18]}...</code>")

    await callback.message.answer("\n".join(lines), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("retry:"))
async def retry_order(callback: CallbackQuery) -> None:
    from main import processor

    slug = callback.data.split(":", 1)[1]

    if not processor.is_running():
        await callback.answer("Бот не запущен, повтор невозможен.", show_alert=True)
        return

    processor._worker._retry_slug = slug
    await callback.message.edit_text(
        f"Повтор попытки для ордера <code>{slug}</code> запланирован.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("skip:"))
async def skip_order(callback: CallbackQuery) -> None:
    slug = callback.data.split(":", 1)[1]
    await callback.message.edit_text(
        f"Ордер <code>{slug}</code> пропущен.",
        parse_mode="HTML",
    )
    await callback.answer()
