"""Обработчики команд и callback-запросов Telegram-бота. Версия без разделения на админа/пользователя."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from telegram import Update, LabeledPrice
from telegram.ext import ContextTypes

from bot.keyboards import main_menu_kb, settings_kb, stat_period_kb, back_kb
from core.funpay_api import FunPayAPI

if TYPE_CHECKING:
    from bot.telegram_bot import CortexBot

logger = logging.getLogger("Handlers")

LOGO = """
╔═══════════════════════════════════╗
║   🧠  FunPay Cortex  v2.0        ║
║   Автоматизация продаж FunPay    ║
╚═══════════════════════════════════╝
"""

# ---------- Вспомогательные функции ----------
def requires_golden_key(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        bot_ref: CortexBot = context.bot_data["cortex"]
        user_id = update.effective_user.id
        user = await bot_ref.db.get_user(user_id)
        if not user or not user.get("golden_key"):
            await update.message.reply_text(
                "❌ *Бот не настроен!*\n\n"
                "Сначала введите ваш golden_key:\n"
                "`/setup ВАШ_ЗОЛОТОЙ_КЛЮЧ`\n\n"
                "Инструкция: /help",
                parse_mode="Markdown"
            )
            return
        return await func(update, context)
    return wrapper


# ---------- ПУБЛИЧНЫЕ КОМАНДЫ ----------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_ref: CortexBot = context.bot_data["cortex"]
    user_id = update.effective_user.id
    username = update.effective_user.username or ""

    await bot_ref.db.create_user(user_id, username)
    user = await bot_ref.db.get_user(user_id)

    if not user.get("golden_key"):
        text = (
            "🤖 *Добро пожаловать в FunPay Cortex!*\n\n"
            "Этот бот автоматически отвечает на сообщения в вашем аккаунте *FunPay*.\n\n"
            "🚀 *Что нужно сделать:*\n"
            "1️⃣ *Получить golden_key*:\n"
            "   • Зайдите на FunPay.com (браузер)\n"
            "   • Нажмите F12 → Application → Cookies\n"
            "   • Скопируйте значение `golden_key`\n\n"
            "2️⃣ *Ввести ключ*:\n"
            "   • Отправьте команду: `/setup ВАШ_КЛЮЧ`\n\n"
            "3️⃣ *Пользоваться*:\n"
            "   • Первые 7 дней — *бесплатно*\n"
            "   • Затем — Premium: 75 Stars / 30 дней\n\n"
            "📋 *Команды:* `/help`"
        )
        await update.message.reply_text(text, parse_mode="Markdown")
    else:
        status = await bot_ref.subscription_manager.get_subscription_status(user_id)
        days = status.get("days_left", 0)
        tariff = status.get("tariff", "free").upper()
        text = (
            f"{LOGO}\n"
            f"🔹 *Ваш статус:* `{tariff}`\n"
            f"📅 Осталось дней: {days}\n"
            f"🔑 Golden key: уже установлен\n"
            f"👤 Профиль FunPay: {user.get('funpay_username') or 'не загружен'}\n\n"
            f"📌 Используйте `/status` для деталей."
        )
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_menu_kb())


async def cmd_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_ref: CortexBot = context.bot_data["cortex"]
    user_id = update.effective_user.id
    args = context.args

    if not args:
        await update.message.reply_text("❌ Укажите golden_key: `/setup КЛЮЧ`", parse_mode="Markdown")
        return

    golden_key = args[0].strip()
    if len(golden_key) < 10:
        await update.message.reply_text("❌ Неверный формат ключа.")
        return

    await update.message.reply_text("⏳ Проверяю golden_key...")
    try:
        test_api = FunPayAPI(golden_key)
        profile = await test_api.fetch_profile()
        if not profile or not profile.id:
            await update.message.reply_text("❌ Golden_key недействителен. Проверьте и попробуйте снова.")
            return
        funpay_username = profile.username
        funpay_id = profile.id
    except Exception as e:
        logger.error(f"Ошибка проверки ключа: {e}")
        await update.message.reply_text("❌ Не удалось проверить ключ. Попробуйте позже.")
        return

    await bot_ref.db.save_golden_key(user_id, golden_key, funpay_username, funpay_id)
    sub_status = await bot_ref.subscription_manager.get_subscription_status(user_id)
    if not sub_status["has_subscription"]:
        await bot_ref.subscription_manager.activate_free_trial(user_id)

    await update.message.reply_text(
        f"✅ *Golden key принят!*\n\n"
        f"🎉 Бесплатный период активирован на 7 дней.\n"
        f"👤 Профиль: {funpay_username} (id: {funpay_id})\n"
        f"💎 Чтобы продлить подписку: `/subscribe`",
        parse_mode="Markdown"
    )


@requires_golden_key
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_ref: CortexBot = context.bot_data["cortex"]
    user_id = update.effective_user.id

    user = await bot_ref.db.get_user(user_id)
    if not user or not user.get("golden_key"):
        await update.message.reply_text("❌ Бот не настроен. Используйте /setup")
        return

    sub_status = await bot_ref.subscription_manager.get_subscription_status(user_id)
    tariff = sub_status.get("tariff", "free")
    days_left = sub_status.get("days_left", 0)
    is_active = sub_status.get("has_subscription", False)

    status_icon = "🟢" if is_active else "🔴"
    tariff_display = tariff.upper() if is_active else "EXPIRED"

    products_count = await bot_ref.db.count_products()

    text = (
        f"📋 *Статус FunPay Cortex*\n\n"
        f"💎 *Подписка:* {status_icon} {tariff_display}\n"
        f"📅 Осталось дней: {days_left}\n"
        f"👤 Профиль: {user.get('funpay_username') or 'не загружен'}\n"
        f"📦 Товаров на выдачу: {products_count}\n"
        f"🔌 Плагинов: {len(bot_ref.plugin_manager.plugins)}\n\n"
        f"📌 /subscribe — оплатить Premium"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=back_kb())


@requires_golden_key
async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_ref: CortexBot = context.bot_data["cortex"]
    user_id = update.effective_user.id
    user = await bot_ref.db.get_user(user_id)
    if not user or not user.get("golden_key"):
        await update.message.reply_text("❌ Бот не настроен.")
        return

    api = FunPayAPI(user["golden_key"])
    profile = await api.fetch_profile()
    if not profile:
        await update.message.reply_text("❌ Ошибка загрузки профиля. Проверьте golden_key.")
        return
    lots = await api.fetch_lots()
    # Получаем баланс через get_balance()
    try:
        balance_obj = await api.account.get_balance()
        balance_str = f"{balance_obj.available_rub:.2f} ₽" if balance_obj else "не удалось получить"
    except Exception as e:
        logger.error(f"Ошибка получения баланса: {e}")
        balance_str = "не удалось получить"
    text = f"👤 *Профиль FunPay*\nИмя: {profile.username}\nID: {profile.id}\nБаланс: {balance_str}\nАктивных лотов: {len(lots)}"
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=back_kb())


@requires_golden_key
async def cmd_checkchats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_ref: CortexBot = context.bot_data["cortex"]
    user_id = update.effective_user.id
    user = await bot_ref.db.get_user(user_id)
    if not user or not user.get("golden_key"):
        await update.message.reply_text("❌ Бот не настроен.")
        return
    api = FunPayAPI(user["golden_key"])
    await api.fetch_profile()
    nodes = await api.fetch_chat_nodes()
    if not nodes:
        await update.message.reply_text("❌ Чаты не найдены.")
        return
    text = f"✅ Найдено чатов: {len(nodes)}\n\n"
    for node in nodes[:5]:
        text += f"👤 {node['sender']}\n💬 {node['last_message'][:50]}\n📬 {'❗' if node['unread'] else '✅'}\n🆔 {node['node_id']}\n\n"
    await update.message.reply_text(text)


@requires_golden_key
async def cmd_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_ref: CortexBot = context.bot_data["cortex"]
    user_id = update.effective_user.id

    user = await bot_ref.db.get_user(user_id)
    if not user or not user.get("golden_key"):
        await update.message.reply_text("❌ Сначала настройте бота: /setup")
        return

    await context.bot.send_invoice(
        chat_id=user_id,
        title="FunPay Cortex Premium",
        description="Подписка на 30 дней. Все функции бота.",
        payload="premium_30days",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="Premium 30 дней", amount=75)],
        start_parameter="premium_subscription"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
🤖 *FunPay Cortex — автоответчик для FunPay*

📌 *Первая настройка:*
1. Получить golden_key на FunPay (F12 → Application → Cookies)
2. Отправить: `/setup КЛЮЧ`

💰 *Тарифы:*
• Бесплатно: 7 дней (все функции)
• Premium: 75 Stars / 30 дней

📋 *Команды:*
/start — приветствие
/status — статус подписки
/profile — профиль FunPay
/subscribe — оплатить Premium
/setup КЛЮЧ — ввести golden_key
/checkchats — список чатов (для теста)

🛠 *Админ-команды:*
/start_bot, /stop_bot, /autodelivery, /autobump, /autoresponder, /interval, /add_product, /products, /plugins

❓ *Помощь:* @ваш_username (указать свой)
"""
    await update.message.reply_text(help_text, parse_mode="Markdown")


# ---------- КОМАНДЫ УПРАВЛЕНИЯ (доступны всем, но требуют golden_key) ----------
@requires_golden_key
async def cmd_start_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_ref: CortexBot = context.bot_data["cortex"]
    gk = bot_ref.config.get("FunPay", "golden_key")
    if not gk:
        await update.message.reply_text("❌ Сначала укажите Golden Key: `/setup golden_key ...`", parse_mode="Markdown")
        return
    msg = await update.message.reply_text("⏳ Запускаю модули…")
    profile = await bot_ref.funpay.fetch_profile()
    if not profile:
        await msg.edit_text("❌ Не удалось подключиться к FunPay. Проверьте Golden Key.")
        return
    await bot_ref.auto_delivery.start()
    await bot_ref.auto_bump.start()
    await bot_ref.auto_responder.start()
    await bot_ref.online_keeper.start()
    bot_ref.is_running = True
    balance_str = "0 ₽"
    try:
        balance_obj = await bot_ref.funpay.account.get_balance()
        balance_str = f"{balance_obj.available_rub:.2f} ₽"
    except:
        pass
    text = f"✅ *Бот запущен!*\n👤 {profile.username}\n💰 {balance_str}\n📦 Автовыдача: {'✅' if bot_ref.auto_delivery.enabled else '❌'}\n📈 Автоподнятие: {'✅' if bot_ref.auto_bump.enabled else '❌'}\n💬 Автоответчик: {'✅' if bot_ref.auto_responder.enabled else '❌'}\n🟢 Вечный онлайн: {'✅' if bot_ref.online_keeper.enabled else '❌'}"
    await msg.edit_text(text, parse_mode="Markdown")


@requires_golden_key
async def cmd_stop_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_ref: CortexBot = context.bot_data["cortex"]
    await bot_ref.auto_delivery.stop()
    await bot_ref.auto_bump.stop()
    await bot_ref.auto_responder.stop()
    await bot_ref.online_keeper.stop()
    bot_ref.is_running = False
    await update.message.reply_text("⏹ Бот остановлен. Все модули выключены.")


@requires_golden_key
async def cmd_stat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📊 Выберите период:", reply_markup=stat_period_kb())


@requires_golden_key
async def cmd_plugins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_ref: CortexBot = context.bot_data["cortex"]
    plugins = bot_ref.plugin_manager.list_plugins()
    if not plugins:
        await update.message.reply_text("🔌 Плагины не найдены.", reply_markup=back_kb())
        return
    text = "🔌 *Плагины:*\n\n" + "\n".join(str(p) for p in plugins)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=back_kb())


@requires_golden_key
async def cmd_autodelivery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_ref: CortexBot = context.bot_data["cortex"]
    args = context.args
    if not args:
        status = "✅ ON" if bot_ref.auto_delivery.enabled else "❌ OFF"
        await update.message.reply_text(f"📦 Автовыдача: {status}\nИспользование: /autodelivery on/off")
        return
    if args[0].lower() == "on":
        bot_ref.auto_delivery.enable()
        await update.message.reply_text("✅ Автовыдача включена.")
    else:
        bot_ref.auto_delivery.disable()
        await update.message.reply_text("❌ Автовыдача выключена.")


@requires_golden_key
async def cmd_autobump(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_ref: CortexBot = context.bot_data["cortex"]
    args = context.args
    if not args:
        status = "✅ ON" if bot_ref.auto_bump.enabled else "❌ OFF"
        await update.message.reply_text(f"📈 Автоподнятие: {status}\nИспользование: /autobump on/off")
        return
    if args[0].lower() == "on":
        bot_ref.auto_bump.enable()
        await update.message.reply_text("✅ Автоподнятие включено.")
    else:
        bot_ref.auto_bump.disable()
        await update.message.reply_text("❌ Автоподнятие выключено.")


@requires_golden_key
async def cmd_autoresponder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_ref: CortexBot = context.bot_data["cortex"]
    args = context.args
    if not args:
        status = "✅ ON" if bot_ref.auto_responder.enabled else "❌ OFF"
        await update.message.reply_text(f"💬 Автоответчик: {status}\nИспользование: /autoresponder on/off")
        return
    if args[0].lower() == "on":
        bot_ref.auto_responder.enable()
        await update.message.reply_text("✅ Автоответчик включён.")
    else:
        bot_ref.auto_responder.disable()
        await update.message.reply_text("❌ Автоответчик выключен.")


@requires_golden_key
async def cmd_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_ref: CortexBot = context.bot_data["cortex"]
    args = context.args
    if not args:
        await update.message.reply_text(f"⏱ Текущий интервал: {bot_ref.auto_bump.interval_hours} ч")
        return
    try:
        hours = float(args[0])
        bot_ref.auto_bump.set_interval(hours)
        await update.message.reply_text(f"✅ Интервал установлен: {hours} ч")
    except:
        await update.message.reply_text("❌ Укажите число.")


@requires_golden_key
async def cmd_add_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_ref: CortexBot = context.bot_data["cortex"]
    raw = update.message.text
    raw = raw.split(maxsplit=1)
    if len(raw) < 2 or "|" not in raw[1]:
        await update.message.reply_text("Формат: `/add_product Название лота | Товар`", parse_mode="Markdown")
        return
    parts = raw[1].split("|", maxsplit=1)
    lot_name = parts[0].strip()
    content = parts[1].strip()
    pid = await bot_ref.db.add_product(lot_name, content)
    total = await bot_ref.db.count_products(lot_name)
    await update.message.reply_text(f"✅ Товар добавлен (#{pid})\n📦 Лот: {lot_name}\n📦 Всего: {total}")


@requires_golden_key
async def cmd_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_ref: CortexBot = context.bot_data["cortex"]
    lot_names = await bot_ref.db.get_all_lot_names()
    if not lot_names:
        await update.message.reply_text("📦 Товаров нет. Добавьте: /add_product")
        return
    text = "📦 *Товары для автовыдачи:*\n\n"
    total = 0
    for name in lot_names:
        cnt = await bot_ref.db.count_products(name)
        total += cnt
        text += f"• {name}: {cnt} шт.\n"
    text += f"\n*Всего:* {total} шт."
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=back_kb())


# ---------- CALLBACK-ЗАПРОСЫ (доступны всем) ----------
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    bot_ref: CortexBot = context.bot_data["cortex"]
    user_id = update.effective_user.id

    if data == "cmd_menu":
        await query.edit_message_text(LOGO + "\nГлавное меню:", reply_markup=main_menu_kb())

    elif data == "cmd_start_bot":
        gk = bot_ref.config.get("FunPay", "golden_key")
        if not gk:
            await query.edit_message_text("❌ Golden Key не задан.", reply_markup=back_kb())
            return
        await query.edit_message_text("⏳ Запускаю…")
        profile = await bot_ref.funpay.fetch_profile()
        if not profile:
            await query.edit_message_text("❌ Ошибка подключения к FunPay.", reply_markup=back_kb())
            return
        await bot_ref.auto_delivery.start()
        await bot_ref.auto_bump.start()
        await bot_ref.auto_responder.start()
        await bot_ref.online_keeper.start()
        bot_ref.is_running = True
        await query.edit_message_text(f"✅ Запущено!\n👤 {profile.username}", reply_markup=back_kb())

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
            f"📦 Товаров: {pc}",
            reply_markup=back_kb()
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
            f"💰 Оборот: {stats['revenue']:.2f} ₽",
            parse_mode="Markdown",
            reply_markup=back_kb()
        )

    elif data == "cmd_profile":
        profile = await bot_ref.funpay.fetch_profile()
        if profile:
            # Получаем баланс
            try:
                balance_obj = await bot_ref.funpay.account.get_balance()
                balance_str = f"{balance_obj.available_rub:.2f} ₽" if balance_obj else "не удалось получить"
            except:
                balance_str = "не удалось получить"
            await query.edit_message_text(
                f"👤 {profile.username}\n🆔 {profile.id}\n💰 {balance_str}",
                reply_markup=back_kb()
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
            f"⏱ Текущий интервал: {bot_ref.auto_bump.interval_hours} ч\n\nОтправьте команду: `/interval <часы>`",
            parse_mode="Markdown",
            reply_markup=back_kb()
        )
    else:
        await query.edit_message_text("❌ Неизвестная команда.", reply_markup=back_kb())
