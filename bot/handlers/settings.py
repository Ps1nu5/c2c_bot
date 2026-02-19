from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.keyboards.inline import cancel_keyboard, main_menu_keyboard, settings_confirm_keyboard
from db.engine import get_session
from db.repository import SettingsRepository

router = Router()


class SettingsFSM(StatesGroup):
    login = State()
    password = State()
    min_amount = State()
    max_amount = State()
    confirm = State()


@router.callback_query(F.data == "settings:open")
async def settings_open(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text(
        "Введите логин (email) для входа на cards2cards:",
        reply_markup=cancel_keyboard(),
    )
    await state.set_state(SettingsFSM.login)
    await callback.answer()


@router.message(SettingsFSM.login)
async def settings_login(message: Message, state: FSMContext) -> None:
    login = message.text.strip()
    if not login or "@" not in login:
        await message.answer("Введите корректный email:", reply_markup=cancel_keyboard())
        return

    await state.update_data(login=login)
    await message.answer("Введите пароль:", reply_markup=cancel_keyboard())
    await state.set_state(SettingsFSM.password)


@router.message(SettingsFSM.password)
async def settings_password(message: Message, state: FSMContext) -> None:
    password = message.text.strip()
    if not password:
        await message.answer("Пароль не может быть пустым. Введите пароль:", reply_markup=cancel_keyboard())
        return

    await state.update_data(password=password)
    await message.answer(
        "Введите минимальную сумму ордера (в рублях).\n"
        "Отправьте <b>0</b> или <b>-</b> чтобы не ограничивать.",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    await state.set_state(SettingsFSM.min_amount)


@router.message(SettingsFSM.min_amount)
async def settings_min_amount(message: Message, state: FSMContext) -> None:
    text = message.text.strip()

    if text in ("0", "-", "нет", ""):
        await state.update_data(min_amount=None)
    else:
        try:
            value = float(text.replace(",", ".").replace(" ", ""))
            if value <= 0:
                await state.update_data(min_amount=None)
            else:
                await state.update_data(min_amount=value)
        except ValueError:
            await message.answer(
                "Введите число (например, 1000) или <b>-</b> чтобы пропустить:",
                parse_mode="HTML",
                reply_markup=cancel_keyboard(),
            )
            return

    await message.answer(
        "Введите максимальную сумму ордера (в рублях).\n"
        "Отправьте <b>0</b> или <b>-</b> чтобы не ограничивать.",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    await state.set_state(SettingsFSM.max_amount)


@router.message(SettingsFSM.max_amount)
async def settings_max_amount(message: Message, state: FSMContext) -> None:
    text = message.text.strip()

    if text in ("0", "-", "нет", ""):
        await state.update_data(max_amount=None)
    else:
        try:
            value = float(text.replace(",", ".").replace(" ", ""))
            if value <= 0:
                await state.update_data(max_amount=None)
            else:
                await state.update_data(max_amount=value)
        except ValueError:
            await message.answer(
                "Введите число (например, 50000) или <b>-</b> чтобы пропустить:",
                parse_mode="HTML",
                reply_markup=cancel_keyboard(),
            )
            return

    data = await state.get_data()
    min_a = data.get("min_amount")
    max_a = data.get("max_amount")

    min_str = f"{min_a:,.0f} RUB" if min_a else "не задана"
    max_str = f"{max_a:,.0f} RUB" if max_a else "не задана"

    await message.answer(
        f"Проверьте настройки:\n\n"
        f"Логин: <code>{data['login']}</code>\n"
        f"Пароль: {'*' * len(data['password'])}\n"
        f"Мин. сумма: {min_str}\n"
        f"Макс. сумма: {max_str}",
        parse_mode="HTML",
        reply_markup=settings_confirm_keyboard(),
    )
    await state.set_state(SettingsFSM.confirm)


@router.callback_query(F.data == "settings:save", SettingsFSM.confirm)
async def settings_save(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()

    async with get_session() as session:
        repo = SettingsRepository(session)
        await repo.update(
            login=data["login"],
            password=data["password"],
            min_amount=data.get("min_amount"),
            max_amount=data.get("max_amount"),
        )

    from main import processor

    is_running = processor.is_running()

    await callback.message.edit_text(
        "Настройки сохранены.",
        reply_markup=main_menu_keyboard(is_running, True),
    )
    await callback.answer()


@router.callback_query(F.data == "settings:edit", SettingsFSM.confirm)
async def settings_edit(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "Введите логин (email) для входа на cards2cards:",
        reply_markup=cancel_keyboard(),
    )
    await state.set_state(SettingsFSM.login)
    await callback.answer()


@router.callback_query(F.data == "settings:cancel")
async def settings_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()

    async with get_session() as session:
        repo = SettingsRepository(session)
        settings = await repo.get_or_create()

    from main import processor

    is_running = processor.is_running()
    has_credentials = bool(settings.login and settings.password)

    await callback.message.edit_text(
        "Настройки не изменены.",
        reply_markup=main_menu_keyboard(is_running, has_credentials),
    )
    await callback.answer()
