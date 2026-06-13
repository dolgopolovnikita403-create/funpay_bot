"""Модуль автоматической выдачи товаров для отдельного пользователя."""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.config_manager import ConfigManager
    from core.database import Database
    from core.funpay_api import FunPayAPI

logger = logging.getLogger("AutoDelivery")


class AutoDelivery:
    def __init__(self, config: ConfigManager, db: Database, funpay: FunPayAPI, telegram_id: int):
        self.config = config
        self.db = db
        self.funpay = funpay
        self.telegram_id = telegram_id
        self._running = False
        self._task: asyncio.Task | None = None
        self._processed_orders: set[str] = set()  # локально для пользователя

    @property
    async def enabled(self) -> bool:
        return await self.db.get_module_state(self.telegram_id, "auto_delivery")

    async def enable(self) -> None:
        await self.db.set_module_state(self.telegram_id, "auto_delivery", True)

    async def disable(self) -> None:
        await self.db.set_module_state(self.telegram_id, "auto_delivery", False)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(f"🚀 AutoDelivery для пользователя {self.telegram_id} запущен.")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(f"🛑 AutoDelivery для пользователя {self.telegram_id} остановлен.")

    async def _loop(self) -> None:
        while self._running:
            try:
                if await self.enabled:
                    await self._check_orders()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"AutoDelivery ошибка (пользователь {self.telegram_id}): {e}", exc_info=True)
            await asyncio.sleep(15)

    async def _check_orders(self) -> None:
        try:
            if not self.funpay.account:
                await self.funpay.fetch_profile()
            if not self.funpay.account:
                return

            _, orders = self.funpay.account.get_sells()
            for order in orders:
                order_id = order.id
                if order_id in self._processed_orders:
                    continue
                if await self.db.is_order_known(order_id):
                    self._processed_orders.add(order_id)
                    continue
                # Сохраняем заказ в БД (глобально, но можно добавить telegram_id)
                await self.db.add_order(
                    order_id=order_id,
                    buyer=order.buyer_username,
                    lot_name=order.description,
                    amount=order.price,
                    status=order.status.name if hasattr(order.status, 'name') else str(order.status),
                )
                # Если заказ оплачен
                if order.status.name == "PAID" or "paid" in str(order.status).lower():
                    self._processed_orders.add(order_id)
                    await self._deliver(order)

        except Exception as e:
            logger.error(f"Ошибка проверки заказов (пользователь {self.telegram_id}): {e}", exc_info=True)

    async def _get_chat_id_by_username(self, username: str) -> str | None:
        try:
            chat = self.funpay.account.get_chat_by_name(username, make_request=True)
            if chat:
                return str(chat.id)
        except Exception as e:
            logger.error(f"Ошибка поиска чата для {username}: {e}")
        return None

    async def _deliver(self, order) -> None:
        try:
            product = await self.db.get_product(order.description, self.telegram_id)  # нужно модифицировать get_product
            if product is None:
                logger.warning(f"⚠️ Нет товаров для лота '{order.description}' (пользователь {self.telegram_id}, заказ {order.id})")
                return
            chat_id = await self._get_chat_id_by_username(order.buyer_username)
            if not chat_id:
                chat_id = f"order-{order.id}"
            message = f"✅ *Ваш товар по заказу #{order.id}*\n\n{product}\n\nСпасибо за покупку!"
            sent = await self.funpay.send_message(chat_id, message)
            if sent:
                await self.db.mark_delivered(order.id)
                logger.info(f"✅ Товар выдан пользователем {self.telegram_id}: заказ {order.id}")
        except Exception as e:
            logger.error(f"Ошибка выдачи товара (пользователь {self.telegram_id}): {e}", exc_info=True)
