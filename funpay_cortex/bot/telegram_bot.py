"""Главный модуль Telegram-бота — собирает всё воедино."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
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
    cmd_check_chats,
    cmd_test_send,
    callback_handler,
)

if TYPE_CHECKING:
    from core.config_manager import ConfigManager
    from core.database import Database
    from core.funpay_api import FunPayAPI
    from core.auto_delivery import AutoDelivery
    from core.auto_bump import AutoBump
    from core.auto_responder import AutoResponder
    from core.online_keeper import OnlineKeeper
    from core.plugin_manager import PluginManager

logger = logging.getLogger("CortexBot")


class CortexBot:
    """Объединяет Telegram-бот и FunPay-модули."""

    def __init__(
        self,
        config: ConfigManager,
        db: Database,
        funpay: FunPayAPI,
        auto_delivery: AutoDelivery,
        auto_bump: AutoBump,
        auto_responder: AutoResponder,
        online_keeper: OnlineKeeper,
        plugin_manager: PluginManager,
    ) -> None:
        self.config = config
        self.db = db
        self.funpay = funpay
        self.auto_delivery = auto_delivery
        self.auto_bump = auto_bump
        self.auto_responder = auto_responder
        self.online_keeper = online_keeper
        self.plugin_manager = plugin_manager
        self.is_running = False
        self._app: Application | None = None

        self.auto_delivery.on_delivery(self._on_delivery)
        self.auto_bump.on_bump(self._on_bump)

    async def _on_delivery(self, order_id, buyer, lot_name, product) -> None:
        admin_id = self.config.get("Telegram", "admin_id")
        if not admin_id or not self._app:
            return
        if product:
            text = (
                f"✅ *Товар выдан!*\n\n"
                f"🆔 Заказ: `{order_id}`\n"
                f"👤 Покупатель: {buyer}\n"
                f"📦 Лот: {lot_name}\n"
                f"📄 Товар: ||{product[:100]}||"
            )
        else:
            text = (
                f"⚠️ *Товар НЕ выдан — закончились!*\n\n"
                f"🆔 Заказ: `{order_id}`\n"
                f"👤 Покупатель: {buyer}\n"
                f"📦 Лот: {lot_name}\n\n"
                f"Добавьте товары: `/add_product {lot_name} | содержимое`"
            )
        try:
            await self._app.bot.send_message(
                chat_id=int(admin_id), text=text, parse_mode="Markdown"
            )
        except Exception as e:
            logger.error("Ошибка отправки уведомления: %s", e)

    async def _on_bump(self, success: bool, message: str) -> None:
        admin_id = self.config.get("Telegram", "admin_id")
        if not admin_id or not self._app:
            return
        emoji = "✅" if success else "❌"
        try:
            await self._app.bot.send_message(
                chat_id=int(admin_id),
                text=f"{emoji} Автоподнятие: {message}",
                parse_mode=None
            )
        except Exception as e:
            logger.error("Ошибка отправки уведомления о бампе: %s", e)

    async def run(self) -> None:
        token = self.config.get("Telegram", "bot_token")
        self._app = Application.builder().token(token).build()

        self._app.bot_data["cortex"] = self

        # ── Регистрация команд ──
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
        self._app.add_handler(CommandHandler("checkchats", cmd_check_chats))
        self._app.add_handler(CommandHandler("testsend", cmd_test_send))  # Новая команда

        # ── Callback-кнопки ──
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

    async def _shutdown(self) -> None:
        logger.info("Завершение работы…")
        await self.auto_delivery.stop()
        await self.auto_bump.stop()
        await self.auto_responder.stop()
        await self.online_keeper.stop()
        await self.funpay.close()
        await self.db.close()
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
        logger.info("FunPay Cortex остановлен.")