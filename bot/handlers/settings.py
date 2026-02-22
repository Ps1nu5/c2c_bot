from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.keyboards.inline import (
    cancel_keyboard,
    credentials_confirm_keyboard,
    filters_confirm_keyboard,
    main_menu_keyboard,
    notifications_keyboard,
    settings_menu_keyboard,
)
from db.engine import get_session
from db.repository import SettingsRepository

router = Router()


class CredentialsFSM(StatesGroup):
    login = State()
    password = State()
    confirm = State()


class FiltersFSM(StatesGroup):
    min_amount = State()
    max_amount = State()
    confirm = State()


# ─── helpers ────────────────────────────────────────────────────────────────

async def _show_settings_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Настройки:", reply_markup=settings_menu_keyboard())
    await callback.answer()


async def _get_main_menu_markup():
    async with get_session() as session:
        repo = SettingsRepository(session)
        settings = await repo.get_or_create()
    from main import processor
    return main_menu_keyboard(
        is_running=processor.is_running(),
        has_credentials=bool(settings.login and settings.password),
    )


# ─── Settings menu ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "settings:menu")
async def settings_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await _show_settings_menu(callback, state)


@router.callback_query(F.data == "settings:open")  # legacy entry point
async def settings_open_legacy(callback: CallbackQuery, state: FSMContext) -> None:
    await _show_settings_menu(callback, state)


@router.callback_query(F.data == "settings:back")
async def settings_back(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    markup = await _get_main_menu_markup()
    await callback.message.edit_text("Главное меню:", reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data == "settings:cancel")  # legacy cancel
async def settings_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await _show_settings_menu(callback, state)


# ─── Credentials FSM ────────────────────────────────────────────────────────

@router.callback_query(F.data == "settings:credentials")
async def credentials_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "Введите логин (email) для входа на cards2cards:",
        reply_markup=cancel_keyboard("settings:menu"),
    )
    await state.set_state(CredentialsFSM.login)
    await callback.answer()


@router.message(CredentialsFSM.login)
async def credentials_login(message: Message, state: FSMContext) -> None:
    login = message.text.strip()
    if not login or "@" not in login:
        await message.answer(
            "Введите корректный email:",
            reply_markup=cancel_keyboard("settings:menu"),
        )
        return
    await state.update_data(login=login)
    await message.answer("Введите пароль:", reply_markup=cancel_keyboard("settings:menu"))
    await state.set_state(CredentialsFSM.password)


@router.message(CredentialsFSM.password)
async def credentials_password(message: Message, state: FSMContext) -> None:
    password = message.text.strip()
    if not password:
        await message.answer(
            "Пароль не может быть пустым. Введите пароль:",
            reply_markup=cancel_keyboard("settings:menu"),
        )
        return
    await state.update_data(password=password)
    data = await state.get_data()
    await message.answer(
        f"Проверьте данные для входа:\n\n"
        f"Логин: <code>{data['login']}</code>\n"
        f"Пароль: {'*' * len(password)}",
        parse_mode="HTML",
        reply_markup=credentials_confirm_keyboard(),
    )
    await state.set_state(CredentialsFSM.confirm)


@router.callback_query(F.data == "credentials:save", CredentialsFSM.confirm)
async def credentials_save(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    async with get_session() as session:
        repo = SettingsRepository(session)
        await repo.update(login=data["login"], password=data["password"])
    await callback.message.edit_text(
        "Данные для входа сохранены.",
        reply_markup=settings_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "credentials:edit", CredentialsFSM.confirm)
async def credentials_edit(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "Введите логин (email) для входа на cards2cards:",
        reply_markup=cancel_keyboard("settings:menu"),
    )
    await state.set_state(CredentialsFSM.login)
    await callback.answer()


# ─── Filters FSM ────────────────────────────────────────────────────────────

@router.callback_query(F.data == "settings:filters")
async def filters_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    async with get_session() as session:
        repo = SettingsRepository(session)
        settings = await repo.get_or_create()

    min_hint = f" (сейчас: {settings.min_amount:,.0f})" if settings.min_amount else ""
    await callback.message.edit_text(
        f"Введите минимальную сумму ордера (₽){min_hint}.\n"
        "Отправьте <b>-</b> чтобы не ограничивать.",
        parse_mode="HTML",
        reply_markup=cancel_keyboard("settings:menu"),
    )
    await state.set_state(FiltersFSM.min_amount)
    await callback.answer()


@router.message(FiltersFSM.min_amount)
async def filters_min_amount(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if text in ("0", "-", "нет", ""):
        await state.update_data(min_amount=None)
    else:
        try:
            value = float(text.replace(",", ".").replace(" ", ""))
            await state.update_data(min_amount=value if value > 0 else None)
        except ValueError:
            await message.answer(
                "Введите число (например, 1000) или <b>-</b> чтобы пропустить:",
                parse_mode="HTML",
                reply_markup=cancel_keyboard("settings:menu"),
            )
            return

    async with get_session() as session:
        repo = SettingsRepository(session)
        settings = await repo.get_or_create()
    max_hint = f" (сейчас: {settings.max_amount:,.0f})" if settings.max_amount else ""
    await message.answer(
        f"Введите максимальную сумму ордера (₽){max_hint}.\n"
        "Отправьте <b>-</b> чтобы не ограничивать.",
        parse_mode="HTML",
        reply_markup=cancel_keyboard("settings:menu"),
    )
    await state.set_state(FiltersFSM.max_amount)


@router.message(FiltersFSM.max_amount)
async def filters_max_amount(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if text in ("0", "-", "нет", ""):
        await state.update_data(max_amount=None)
    else:
        try:
            value = float(text.replace(",", ".").replace(" ", ""))
            await state.update_data(max_amount=value if value > 0 else None)
        except ValueError:
            await message.answer(
                "Введите число (например, 50000) или <b>-</b> чтобы пропустить:",
                parse_mode="HTML",
                reply_markup=cancel_keyboard("settings:menu"),
            )
            return

    data = await state.get_data()
    min_a = data.get("min_amount")
    max_a = data.get("max_amount")
    min_str = f"{min_a:,.0f} ₽" if min_a else "не задана"
    max_str = f"{max_a:,.0f} ₽" if max_a else "не задана"
    await message.answer(
        f"Проверьте фильтры суммы:\n\n"
        f"Минимум: {min_str}\n"
        f"Максимум: {max_str}",
        reply_markup=filters_confirm_keyboard(),
    )
    await state.set_state(FiltersFSM.confirm)


@router.callback_query(F.data == "filters:save", FiltersFSM.confirm)
async def filters_save(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    async with get_session() as session:
        repo = SettingsRepository(session)
        await repo.update(
            min_amount=data.get("min_amount"),
            max_amount=data.get("max_amount"),
        )
    await callback.message.edit_text(
        "Фильтры суммы сохранены.",
        reply_markup=settings_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "filters:edit", FiltersFSM.confirm)
async def filters_edit(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "Введите минимальную сумму ордера (₽).\n"
        "Отправьте <b>-</b> чтобы не ограничивать.",
        parse_mode="HTML",
        reply_markup=cancel_keyboard("settings:menu"),
    )
    await state.set_state(FiltersFSM.min_amount)
    await callback.answer()


# ─── Notifications ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "settings:notifications")
async def notifications_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    async with get_session() as session:
        repo = SettingsRepository(session)
        settings = await repo.get_or_create()
    await callback.message.edit_text(
        "Настройка оповещений:",
        reply_markup=notifications_keyboard(settings.notify_taken),
    )
    await callback.answer()


@router.callback_query(F.data == "settings:notify_toggle")
async def notify_toggle(callback: CallbackQuery) -> None:
    async with get_session() as session:
        repo = SettingsRepository(session)
        settings = await repo.get_or_create()
        new_val = not settings.notify_taken
        await repo.update(notify_taken=new_val)

    # Update the in-memory cache in the processor immediately
    from main import processor
    processor.set_notify_taken(new_val)

    await callback.message.edit_text(
        "Настройка оповещений:",
        reply_markup=notifications_keyboard(new_val),
    )
    await callback.answer("Включено" if new_val else "Отключено")
