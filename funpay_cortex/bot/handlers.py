"""Обработчики команд и callback-запросов Telegram-бота."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from telegram import Update
from telegram.ext import ContextTypes

from bot.keyboards import main_menu_kb, settings_kb, stat_period_kb, back_kb

if TYPE_CHECKING:
    from bot.telegram_bot import CortexBot

logger = logging.getLogger("Handlers")

LOGO = """
╔═══════════════════════════════════╗
║   🧠  FunPay Cortex  v1.0        ║
║   Автоматизация продаж FunPay    ║
╚═══════════════════════════════════╝
"""


def is_admin(bot_ref: CortexBot, user_id: int) -> bool:
    admin_id = bot_ref.config.get("Telegram", "admin_id")
    if not admin_id:
        return True
    return str(user_id) == str(admin_id)


def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        bot_ref: CortexBot = context.bot_data["cortex"]
        uid = update.effective_user.id
        if not is_admin(bot_ref, uid):
            await update.effective_message.reply_text("⛔ Доступ запрещён.")
            return
        return await func(update, context)
    return wrapper


# ═══════════════════════════════════════════════════════════════════
# ОСНОВНЫЕ КОМАНДЫ
# ═══════════════════════════════════════════════════════════════════

@admin_only
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_ref: CortexBot = context.bot_data["cortex"]
    admin_id = bot_ref.config.get("Telegram", "admin_id")
    if not admin_id:
        bot_ref.config.set("Telegram", "admin_id", str(update.effective_user.id))
    await update.message.reply_text(LOGO + "\nГлавное меню:", reply_markup=main_menu_kb())


@admin_only
async def cmd_setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_ref: CortexBot = context.bot_data["cortex"]
    args = context.args or []

    if len(args) < 1:
        gk = bot_ref.config.get("FunPay", "golden_key")
        gk_display = (gk[:8] + "…" + gk[-4:]) if len(gk) > 12 else (gk or "не задан")
        text = (
            "⚙️ *Настройка FunPay Cortex*\n\n"
            f"Golden Key: `{gk_display}`\n\n"
            "Использование:\n"
            "`/setup golden_key ВАША_GOLDEN_KEY`\n"
            "`/setup proxy http://user:pass@host:port`\n"
        )
        await update.message.reply_text(text, parse_mode="Markdown")
        return

    param = args[0].lower()
    if param == "golden_key" and len(args) >= 2:
        bot_ref.config.set("FunPay", "golden_key", args[1])
        await update.message.reply_text("✅ Golden Key сохранён.")
    elif param == "proxy" and len(args) >= 2:
        bot_ref.config.set("FunPay", "proxy", args[1])
        await update.message.reply_text("✅ Прокси сохранён.")
    else:
        await update.message.reply_text("❌ Неизвестный параметр. См. /setup")


@admin_only
async def cmd_start_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_ref: CortexBot = context.bot_data["cortex"]
    gk = bot_ref.config.get("FunPay", "golden_key")
    if not gk:
        await update.message.reply_text("❌ Сначала укажите Golden Key: `/setup golden_key ...`",
                                        parse_mode="Markdown")
        return

    msg = await update.message.reply_text("⏳ Запускаю модули…")

    profile = await bot_ref.funpay.fetch_profile()
    if not profile:
        await msg.edit_text("❌ Не удалось подключиться к FunPay. Проверьте Golden Key.")
        return

    # Получаем баланс
    balance_str = "0 ₽"
    try:
        balance_obj = await bot_ref.funpay.account.get_balance()
        balance_str = f"{balance_obj.available_rub:.2f} ₽"
    except Exception as e:
        logger.error(f"Ошибка получения баланса: {e}")

    await bot_ref.auto_delivery.start()
    await bot_ref.auto_bump.start()
    await bot_ref.auto_responder.start()
    await bot_ref.online_keeper.start()
    bot_ref.is_running = True

    text = (
        f"✅ *Бот запущен!*\n\n"
        f"👤 Профиль: {profile.username}\n"
        f"💰 Баланс: {balance_str}\n"
        f"🆔 ID: {profile.id}\n\n"
        f"📦 Автовыдача: {'✅' if bot_ref.auto_delivery.enabled else '❌'}\n"
        f"📈 Автоподнятие: {'✅' if bot_ref.auto_bump.enabled else '❌'}\n"
        f"💬 Автоответчик: {'✅' if bot_ref.auto_responder.enabled else '❌'}\n"
        f"🟢 Вечный онлайн: {'✅' if bot_ref.online_keeper.enabled else '❌'}\n"
    )
    await msg.edit_text(text, parse_mode="Markdown")


@admin_only
async def cmd_stop_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_ref: CortexBot = context.bot_data["cortex"]
    await bot_ref.auto_delivery.stop()
    await bot_ref.auto_bump.stop()
    await bot_ref.auto_responder.stop()
    await bot_ref.online_keeper.stop()
    bot_ref.is_running = False
    await update.message.reply_text("⏹ Бот остановлен. Все модули выключены.")


@admin_only
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_ref: CortexBot = context.bot_data["cortex"]
    running = "🟢 Работает" if bot_ref.is_running else "🔴 Остановлен"
    products_count = await bot_ref.db.count_products()
    text = (
        f"📋 *Статус FunPay Cortex*\n\n"
        f"Состояние: {running}\n\n"
        f"📦 Автовыдача: {'✅ ON' if bot_ref.auto_delivery.enabled else '❌ OFF'}\n"
        f"📈 Автоподнятие: {'✅ ON' if bot_ref.auto_bump.enabled else '❌ OFF'}"
        f" (каждые {bot_ref.auto_bump.interval_hours}ч)\n"
        f"💬 Автоответчик: {'✅ ON' if bot_ref.auto_responder.enabled else '❌ OFF'}\n"
        f"🟢 Вечный онлайн: {'✅ ON' if bot_ref.online_keeper.enabled else '❌ OFF'}\n\n"
        f"📦 Товаров на выдачу: {products_count}\n"
        f"⏱ Последнее поднятие: {bot_ref.auto_bump.last_bump}\n"
        f"🔌 Плагинов: {len(bot_ref.plugin_manager.plugins)}\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=back_kb())


@admin_only
async def cmd_stat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("📊 Выберите период:", reply_markup=stat_period_kb())


@admin_only
async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_ref: CortexBot = context.bot_data["cortex"]
    profile = await bot_ref.funpay.fetch_profile()
    if not profile:
        await update.message.reply_text("❌ Не удалось загрузить профиль. Проверьте Golden Key.")
        return
    lots = await bot_ref.funpay.fetch_lots()
    
    # Получаем баланс
    balance_str = "0 ₽"
    try:
        balance_obj = await bot_ref.funpay.account.get_balance()
        balance_str = f"{balance_obj.available_rub:.2f} ₽"
    except:
        pass
    
    text = (
        f"👤 *Профиль FunPay*\n\n"
        f"Имя: {profile.username}\n"
        f"ID: {profile.id}\n"
        f"Баланс: {balance_str}\n"
        f"Активных лотов: {len(lots)}\n"
    )
    if lots[:5]:
        text += "\n*Лоты:*\n"
        for lot in lots[:10]:
            text += f"• {lot.title} — {lot.price}\n"
        if len(lots) > 10:
            text += f"_…и ещё {len(lots) - 10}_\n"

    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=back_kb())


@admin_only
async def cmd_autodelivery(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_ref: CortexBot = context.bot_data["cortex"]
    args = context.args or []
    if not args:
        status = "✅ ON" if bot_ref.auto_delivery.enabled else "❌ OFF"
        await update.message.reply_text(
            f"📦 Автовыдача: {status}\n\nИспользование: `/autodelivery on` или `/autodelivery off`",
            parse_mode="Markdown",
        )
        return

    if args[0].lower() in ("on", "вкл", "1"):
        bot_ref.auto_delivery.enable()
        await update.message.reply_text("✅ Автовыдача включена.")
    elif args[0].lower() in ("off", "выкл", "0"):
        bot_ref.auto_delivery.disable()
        await update.message.reply_text("❌ Автовыдача выключена.")


@admin_only
async def cmd_autobump(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_ref: CortexBot = context.bot_data["cortex"]
    args = context.args or []
    if not args:
        status = "✅ ON" if bot_ref.auto_bump.enabled else "❌ OFF"
        await update.message.reply_text(
            f"📈 Автоподнятие: {status} (каждые {bot_ref.auto_bump.interval_hours}ч)\n\n"
            "Использование: `/autobump on` или `/autobump off`",
            parse_mode="Markdown",
        )
        return

    if args[0].lower() in ("on", "вкл", "1"):
        bot_ref.auto_bump.enable()
        await update.message.reply_text("✅ Автоподнятие включено.")
    elif args[0].lower() in ("off", "выкл", "0"):
        bot_ref.auto_bump.disable()
        await update.message.reply_text("❌ Автоподнятие выключено.")


@admin_only
async def cmd_autoresponder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_ref: CortexBot = context.bot_data["cortex"]
    args = context.args or []
    if not args:
        status = "✅ ON" if bot_ref.auto_responder.enabled else "❌ OFF"
        await update.message.reply_text(
            f"💬 Автоответчик: {status}\n\n"
            "Использование: `/autoresponder on` или `/autoresponder off`",
            parse_mode="Markdown",
        )
        return

    if args[0].lower() in ("on", "вкл", "1"):
        bot_ref.auto_responder.enable()
        await update.message.reply_text("✅ Автоответчик включён.")
    elif args[0].lower() in ("off", "выкл", "0"):
        bot_ref.auto_responder.disable()
        await update.message.reply_text("❌ Автоответчик выключен.")


@admin_only
async def cmd_interval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_ref: CortexBot = context.bot_data["cortex"]
    args = context.args or []
    if not args:
        await update.message.reply_text(
            f"⏱ Текущий интервал: {bot_ref.auto_bump.interval_hours}ч\n"
            "Использование: `/interval 4`",
            parse_mode="Markdown",
        )
        return
    try:
        hours = float(args[0])
        if hours < 0.5:
            await update.message.reply_text("❌ Минимальный интервал — 0.5 часа.")
            return
        bot_ref.auto_bump.set_interval(hours)
        await update.message.reply_text(f"✅ Интервал установлен: {hours}ч")
    except ValueError:
        await update.message.reply_text("❌ Укажите число. Пример: `/interval 4`", parse_mode="Markdown")


@admin_only
async def cmd_plugins(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_ref: CortexBot = context.bot_data["cortex"]
    plugins = bot_ref.plugin_manager.list_plugins()
    if not plugins:
        await update.message.reply_text("🔌 Плагины не найдены.\n\nПоложите `.py` файлы в папку `plugins/`.",
                                        parse_mode="Markdown", reply_markup=back_kb())
        return
    text = "🔌 *Плагины:*\n\n"
    for p in plugins:
        text += f"{p}\n"
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=back_kb())


@admin_only
async def cmd_add_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_ref: CortexBot = context.bot_data["cortex"]
    raw = update.message.text
    raw = raw.split(maxsplit=1)
    if len(raw) < 2 or "|" not in raw[1]:
        await update.message.reply_text(
            "📦 *Добавление товара для автовыдачи*\n\n"
            "Формат: `/add_product Название лота | Содержимое товара`\n\n"
            "Пример:\n"
            "`/add_product Аккаунт Steam | login:password`",
            parse_mode="Markdown",
        )
        return

    parts = raw[1].split("|", maxsplit=1)
    lot_name = parts[0].strip()
    content = parts[1].strip()

    pid = await bot_ref.db.add_product(lot_name, content)
    total = await bot_ref.db.count_products(lot_name)
    await update.message.reply_text(
        f"✅ Товар добавлен (#{pid})\n"
        f"📦 Лот: {lot_name}\n"
        f"📦 Всего товаров для этого лота: {total}"
    )


@admin_only
async def cmd_products(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_ref: CortexBot = context.bot_data["cortex"]
    lot_names = await bot_ref.db.get_all_lot_names()
    if not lot_names:
        await update.message.reply_text("📦 Товаров для автовыдачи нет.\n\nДобавьте: `/add_product`",
                                        parse_mode="Markdown")
        return

    text = "📦 *Товары для автовыдачи:*\n\n"
    total = 0
    for name in lot_names:
        cnt = await bot_ref.db.count_products(name)
        total += cnt
        text += f"• {name}: {cnt} шт.\n"
    text += f"\n*Всего:* {total} шт."
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=back_kb())


# ═══════════════════════════════════════════════════════════════════
# ТЕСТОВЫЕ КОМАНДЫ ДЛЯ ДИАГНОСТИКИ
# ═══════════════════════════════════════════════════════════════════

@admin_only
async def cmd_check_chats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_ref: CortexBot = context.bot_data["cortex"]
    await update.message.reply_text("🔍 Проверяю чаты FunPay...")
    
    nodes = await bot_ref.funpay.fetch_chat_nodes()
    
    if not nodes:
        await update.message.reply_text("❌ Чаты не найдены.\n\nВозможные причины:\n• Нет активных диалогов\n• Golden key не даёт доступа к чатам\n• Ошибка парсинга")
        return
    
    text = f"✅ Найдено чатов: {len(nodes)}\n\n"
    for node in nodes[:5]:
        text += f"📱 Собеседник: {node['sender'] or 'Без имени'}\n"
        text += f"💬 Последнее сообщение: {node['last_message'][:50]}\n"
        text += f"📬 Непрочитано: {'✅ ДА' if node['unread'] else '❌ НЕТ'}\n"
        text += f"🆔 Node ID: {node['node_id']}\n\n"
    
    if len(nodes) > 5:
        text += f"…и ещё {len(nodes)-5} чатов."
    
    await update.message.reply_text(text)


@admin_only
async def cmd_test_send(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Тестовая отправка сообщения: /testsend <node_id> <текст>"""
    bot_ref: CortexBot = context.bot_data["cortex"]
    args = context.args
    
    if len(args) < 2:
        await update.message.reply_text(
            "📤 *Тест отправки сообщения*\n\n"
            "Использование: `/testsend <node_id> <текст>`\n\n"
            "Пример: `/testsend 265618373 Привет!`\n\n"
            "Node ID можно получить через `/checkchats`",
            parse_mode="Markdown"
        )
        return
    
    node_id = args[0]
    text = " ".join(args[1:])
    
    await update.message.reply_text(f"⏳ Отправляю сообщение в чат {node_id}...")
    
    result = await bot_ref.funpay.send_message(node_id, text)
    
    if result:
        await update.message.reply_text(f"✅ Сообщение успешно отправлено в чат {node_id}")
    else:
        await update.message.reply_text(f"❌ Не удалось отправить сообщение в чат {node_id}\n\nПроверьте логи.")


# ═══════════════════════════════════════════════════════════════════
# CALLBACK-ЗАПРОСЫ
# ═══════════════════════════════════════════════════════════════════

@admin_only
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    bot_ref: CortexBot = context.bot_data["cortex"]

    if data == "cmd_menu":
        await query.edit_message_text(LOGO + "\nГлавное меню:", reply_markup=main_menu_kb())

    elif data == "cmd_start_bot":
        gk = bot_ref.config.get("FunPay", "golden_key")
        if not gk:
            await query.edit_message_text("❌ Golden Key не задан. Используйте /setup",
                                          reply_markup=back_kb())
            return
        await query.edit_message_text("⏳ Запускаю…")
        profile = await bot_ref.funpay.fetch_profile()
        if not profile:
            await query.edit_message_text("❌ Ошибка подключения к FunPay.", reply_markup=back_kb())
            return
        
        # Получаем баланс
        balance_str = "0 ₽"
        try:
            balance_obj = await bot_ref.funpay.account.get_balance()
            balance_str = f"{balance_obj.available_rub:.2f} ₽"
        except:
            pass
        
        await bot_ref.auto_delivery.start()
        await bot_ref.auto_bump.start()
        await bot_ref.auto_responder.start()
        await bot_ref.online_keeper.start()
        bot_ref.is_running = True
        await query.edit_message_text(
            f"✅ Запущено!\n👤 {profile.username}\n💰 {balance_str}",
            reply_markup=back_kb(),
        )

    elif data == "cmd_stop_bot":
        await bot_ref.auto_delivery.stop()
        await bot_ref.auto_bump.stop()
        await bot_ref.auto_responder.stop()
        await bot_ref.online_keeper.stop()
        bot_ref.is_running = False
        await query.edit_message_text("⏹ Остановлено.", reply_markup=back_kb())

    elif data == "cmd_status":
        running = "🟢" if bot_ref.is_running else "🔴"
        pc = await bot_ref.db.count_products()
        await query.edit_message_text(
            f"📋 Статус: {running}\n\n"
            f"📦 Автовыдача: {'✅' if bot_ref.auto_delivery.enabled else '❌'}\n"
            f"📈 Автоподнятие: {'✅' if bot_ref.auto_bump.enabled else '❌'}\n"
            f"💬 Автоответчик: {'✅' if bot_ref.auto_responder.enabled else '❌'}\n"
            f"🟢 Онлайн: {'✅' if bot_ref.online_keeper.enabled else '❌'}\n"
            f"📦 Товаров: {pc}\n"
            f"⏱ Посл. поднятие: {bot_ref.auto_bump.last_bump}",
            reply_markup=back_kb(),
        )

    elif data == "cmd_stat":
        await query.edit_message_text("📊 Выберите период:", reply_markup=stat_period_kb())

    elif data.startswith("stat_"):
        period = data.replace("stat_", "")
        stats = await bot_ref.db.get_stats(period)
        period_labels = {"day": "день", "week": "неделю", "month": "месяц", "all": "всё время"}
        await query.edit_message_text(
            f"📊 *Статистика за {period_labels.get(period, period)}*\n\n"
            f"📦 Заказов: {stats['orders']}\n"
            f"✅ Выдано: {stats['delivered']}\n"
            f"💰 Оборот: {stats['revenue']:.2f} ₽\n",
            parse_mode="Markdown",
            reply_markup=back_kb(),
        )

    elif data == "cmd_profile":
        profile = await bot_ref.funpay.fetch_profile()
        if profile:
            # Получаем баланс
            balance_str = "0 ₽"
            try:
                balance_obj = await bot_ref.funpay.account.get_balance()
                balance_str = f"{balance_obj.available_rub:.2f} ₽"
            except:
                pass
            await query.edit_message_text(
                f"👤 {profile.username}\n🆔 {profile.id}\n💰 {balance_str}",
                reply_markup=back_kb(),
            )
        else:
            await query.edit_message_text("❌ Ошибка загрузки профиля.", reply_markup=back_kb())

    elif data == "cmd_plugins":
        plugins = bot_ref.plugin_manager.list_plugins()
        text = "🔌 Плагины:\n\n" + ("\n".join(str(p) for p in plugins) if plugins else "Нет плагинов.")
        await query.edit_message_text(text, reply_markup=back_kb())

    elif data == "cmd_settings":
        await query.edit_message_text("⚙️ Настройки:", reply_markup=settings_kb(bot_ref.config))

    elif data == "toggle_auto_delivery":
        if bot_ref.auto_delivery.enabled:
            bot_ref.auto_delivery.disable()
        else:
            bot_ref.auto_delivery.enable()
        await query.edit_message_text("⚙️ Настройки:", reply_markup=settings_kb(bot_ref.config))

    elif data == "toggle_auto_bump":
        if bot_ref.auto_bump.enabled:
            bot_ref.auto_bump.disable()
        else:
            bot_ref.auto_bump.enable()
        await query.edit_message_text("⚙️ Настройки:", reply_markup=settings_kb(bot_ref.config))

    elif data == "toggle_auto_responder":
        if bot_ref.auto_responder.enabled:
            bot_ref.auto_responder.disable()
        else:
            bot_ref.auto_responder.enable()
        await query.edit_message_text("⚙️ Настройки:", reply_markup=settings_kb(bot_ref.config))

    elif data == "toggle_online_keeper":
        if bot_ref.online_keeper.enabled:
            bot_ref.online_keeper.disable()
        else:
            bot_ref.online_keeper.enable()
        await query.edit_message_text("⚙️ Настройки:", reply_markup=settings_kb(bot_ref.config))

    elif data == "change_interval":
        await query.edit_message_text(
            f"⏱ Текущий интервал: {bot_ref.auto_bump.interval_hours}ч\n\n"
            "Отправьте команду: `/interval <часы>`",
            parse_mode="Markdown",
            reply_markup=back_kb(),
        )