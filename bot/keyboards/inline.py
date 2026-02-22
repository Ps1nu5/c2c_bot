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
    builder.button(text="Настройки", callback_data="settings:menu")
    builder.button(text="Статистика", callback_data="stats:show")
    builder.adjust(1)
    return builder.as_markup()


def settings_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Данные для входа", callback_data="settings:credentials")
    builder.button(text="Фильтры суммы", callback_data="settings:filters")
    builder.button(text="Оповещения", callback_data="settings:notifications")
    builder.button(text="Назад", callback_data="settings:back")
    builder.adjust(1)
    return builder.as_markup()


def notifications_keyboard(notify_taken: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    status = "ВКЛ" if notify_taken else "ВЫКЛ"
    builder.button(
        text=f"Уведомления о взятых ордерах: {status}",
        callback_data="settings:notify_toggle",
    )
    builder.button(text="Назад к настройкам", callback_data="settings:menu")
    builder.adjust(1)
    return builder.as_markup()


def cancel_keyboard(back_to: str = "settings:menu") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Отмена", callback_data=back_to)
    return builder.as_markup()


def credentials_confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Сохранить", callback_data="credentials:save")
    builder.button(text="Изменить", callback_data="credentials:edit")
    builder.button(text="Отмена", callback_data="settings:menu")
    builder.adjust(2, 1)
    return builder.as_markup()


def filters_confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Сохранить", callback_data="filters:save")
    builder.button(text="Изменить", callback_data="filters:edit")
    builder.button(text="Отмена", callback_data="settings:menu")
    builder.adjust(2, 1)
    return builder.as_markup()


# kept for any leftover references
def settings_confirm_keyboard() -> InlineKeyboardMarkup:
    return filters_confirm_keyboard()
