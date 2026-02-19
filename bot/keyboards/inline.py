from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_keyboard(is_running: bool, has_credentials: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    if is_running:
        builder.button(text="Остановить бота", callback_data="bot:stop")
    else:
        if has_credentials:
            builder.button(text="Запустить бота", callback_data="bot:start")
        else:
            builder.button(text="Запустить бота (нет настроек)", callback_data="bot:no_settings")

    builder.button(text="Настройки фильтров", callback_data="settings:open")
    builder.button(text="Статистика", callback_data="stats:show")
    builder.adjust(1)
    return builder.as_markup()


def cancel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Отмена", callback_data="settings:cancel")
    return builder.as_markup()


def settings_confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Сохранить", callback_data="settings:save")
    builder.button(text="Изменить", callback_data="settings:edit")
    builder.button(text="Отмена", callback_data="settings:cancel")
    builder.adjust(2, 1)
    return builder.as_markup()
