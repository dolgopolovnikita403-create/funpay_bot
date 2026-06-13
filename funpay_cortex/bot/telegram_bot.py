"""Главный модуль Telegram-бота."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
    MessageHandler,
    filters,
)

from bot.handlers import (
    cmd_start,
    cmd_setup,
    cmd_start_bot,
    cmd_stop_bot,
    cmd_status,
    cmd_stat,
    cmd_profile,
    cmd_autodelivery,
    cmd_autobump,
    cmd_autoresponder,
    cmd_interval,
    cmd_plugins,
    cmd_add_product,
    cmd_products,
    cmd_checkchats,
    cmd_subscribe,
    cmd_help,
    callback_handler,
)
from core.subscription_manager import SubscriptionManager

if TYPE_CHECKING:
    from core.config_manager import ConfigManager
    from core.database import Database
    from core.funpay_api import FunPayAPI
    from core.user_module_manager import UserModuleManager

logger = logging.getLogger("CortexBot")


class CortexBot:
    def __init__(
        self,
        config: ConfigManager,
        db: Database,
        funpay_admin: FunPayAPI,
        user_module_manager: UserModuleManager,
    ) -> None:
        self.config = config
        self.db = db
        self.funpay_admin = funpay_admin  # используется только для команд админа (статистика, глобальное)
        self.user_module_manager = user_module_manager
        self.subscription_manager = SubscriptionManager(db)
        self._app: Application | None = None

    async def run(self):
        token = self.config.get("Telegram", "bot_token")
        if not token:
            logger.error("Telegram bot_token не задан!")
            return

        self._app = Application.builder().token(token).build()
        self._app.bot_data["cortex"] = self

        # Регистрация команд
        self._app.add_handler(CommandHandler(["start", "menu"], cmd_start))
        self._app.add_handler(CommandHandler("setup", cmd_setup))
        self._app.add_handler(CommandHandler("start_bot", cmd_start_bot))
        self._app.add_handler(CommandHandler("stop_bot", cmd_stop_bot))
        self._app.add_handler(CommandHandler("status", cmd_status))
        self._app.add_handler(CommandHandler("stat", cmd_stat))
        self._app.add_handler(CommandHandler("profile", cmd_profile))
        self._app.add_handler(CommandHandler("autodelivery", cmd_autodelivery))
        self._app.add_handler(CommandHandler("autobump", cmd_autobump))
        self._app.add_handler(CommandHandler("autoresponder", cmd_autoresponder))
        self._app.add_handler(CommandHandler("interval", cmd_interval))
        self._app.add_handler(CommandHandler("plugins", cmd_plugins))
        self._app.add_handler(CommandHandler("add_product", cmd_add_product))
        self._app.add_handler(CommandHandler("products", cmd_products))
        self._app.add_handler(CommandHandler("checkchats", cmd_checkchats))
        self._app.add_handler(CommandHandler("subscribe", cmd_subscribe))
        self._app.add_handler(CommandHandler("help", cmd_help))

        # Платежи
        self._app.add_handler(PreCheckoutQueryHandler(self.pre_checkout_query))
        self._app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, self.successful_payment))

        self._app.add_handler(CallbackQueryHandler(callback_handler))

        logger.info("Telegram-бот запущен. Polling…")
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)

        try:
            import asyncio
            stop_event = asyncio.Event()
            await stop_event.wait()
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await self._shutdown()

    async def pre_checkout_query(self, update, context):
        await update.pre_checkout_query.answer(ok=True)

    async def successful_payment(self, update, context):
        user_id = update.effective_user.id
        await self.subscription_manager.activate_premium(user_id, 30)
        await update.message.reply_text("✅ Premium активирован на 30 дней! Спасибо за покупку!")

    async def _shutdown(self):
        logger.info("Завершение работы…")
        await self.user_module_manager.stop_all()
        await self.db.close()
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
        logger.info("FunPay Cortex остановлен.")
