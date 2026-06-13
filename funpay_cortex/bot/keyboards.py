from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Главное меню: для админа все кнопки, для обычного пользователя — публичные."""
    if is_admin:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("▶️ Запуск", callback_data="cmd_start_bot"),
                InlineKeyboardButton("⏹ Стоп", callback_data="cmd_stop_bot"),
            ],
            [
                InlineKeyboardButton("📊 Статистика", callback_data="cmd_stat"),
                InlineKeyboardButton("📋 Статус", callback_data="cmd_status"),
            ],
            [
                InlineKeyboardButton("👤 Профиль", callback_data="cmd_profile"),
                InlineKeyboardButton("🔌 Плагины", callback_data="cmd_plugins"),
            ],
            [
                InlineKeyboardButton("⚙️ Настройки", callback_data="cmd_settings"),
            ],
        ])
    else:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📊 Статистика", callback_data="cmd_stat"),
                InlineKeyboardButton("📋 Статус", callback_data="cmd_status"),
            ],
            [
                InlineKeyboardButton("👤 Профиль", callback_data="cmd_profile"),
                InlineKeyboardButton("🔌 Плагины", callback_data="cmd_plugins"),
            ],
        ])


def settings_kb(config, is_admin: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура настроек: для админа — переключатели, для остальных — только информация."""
    ad = "✅" if config.getbool("Settings", "auto_delivery") else "❌"
    ab = "✅" if config.getbool("Settings", "auto_bump") else "❌"
    ar = "✅" if config.getbool("Settings", "auto_responder") else "❌"
    ok = "✅" if config.getbool("Settings", "online_keeper") else "❌"
    interval = config.get("Settings", "bump_interval", "4")

    if is_admin:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{ad} Автовыдача", callback_data="toggle_auto_delivery")],
            [InlineKeyboardButton(f"{ab} Автоподнятие", callback_data="toggle_auto_bump")],
            [InlineKeyboardButton(f"{ar} Автоответчик", callback_data="toggle_auto_responder")],
            [InlineKeyboardButton(f"{ok} Вечный онлайн", callback_data="toggle_online_keeper")],
            [InlineKeyboardButton(f"⏱ Интервал поднятия: {interval}ч", callback_data="change_interval")],
            [InlineKeyboardButton("🔙 Назад", callback_data="cmd_menu")],
        ])
    else:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(f"📦 Автовыдача: {ad}", callback_data="noop")],
            [InlineKeyboardButton(f"📈 Автоподнятие: {ab}", callback_data="noop")],
            [InlineKeyboardButton(f"💬 Автоответчик: {ar}", callback_data="noop")],
            [InlineKeyboardButton(f"🟢 Вечный онлайн: {ok}", callback_data="noop")],
            [InlineKeyboardButton(f"⏱ Интервал: {interval}ч", callback_data="noop")],
            [InlineKeyboardButton("🔙 Назад", callback_data="cmd_menu")],
        ])


def stat_period_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📅 День", callback_data="stat_day"),
            InlineKeyboardButton("📅 Неделя", callback_data="stat_week"),
        ],
        [
            InlineKeyboardButton("📅 Месяц", callback_data="stat_month"),
            InlineKeyboardButton("📅 Всё время", callback_data="stat_all"),
        ],
        [InlineKeyboardButton("🔙 Назад", callback_data="cmd_menu")],
    ])


def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Меню", callback_data="cmd_menu")],
    ])
