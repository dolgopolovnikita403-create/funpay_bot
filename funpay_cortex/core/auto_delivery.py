"""Модуль автоматической выдачи товаров после оплаты.
   Использует библиотеку FunPayAPI для работы с заказами и чатами.
"""

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
    def __init__(self, config: ConfigManager, db: Database, funpay: FunPayAPI) -> None:
        self.config = config
        self.db = db
        self.funpay = funpay
        self._running = False
        self._task: asyncio.Task | None = None
        self._delivery_callbacks: list = []
        self._processed_orders: set[str] = set()  # Заказы в обработке

    @property
    def enabled(self) -> bool:
        return self.config.getbool("Settings", "auto_delivery")

    def enable(self) -> None:
        self.config.set("Settings", "auto_delivery", "on")

    def disable(self) -> None:
        self.config.set("Settings", "auto_delivery", "off")

    def on_delivery(self, callback):
        """Регистрирует callback(order_id, buyer, lot_name, product)."""
        self._delivery_callbacks.append(callback)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("🚀 AutoDelivery запущен.")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 AutoDelivery остановлен.")

    async def _loop(self) -> None:
        """Основной цикл проверки заказов."""
        while self._running:
            try:
                if self.enabled:
                    await self._check_orders()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"AutoDelivery ошибка: {e}", exc_info=True)
            await asyncio.sleep(15)  # Проверяем каждые 15 секунд

    async def _check_orders(self) -> None:
        """Проверяет новые оплаченные заказы."""
        try:
            # Инициализируем аккаунт если нужно
            if not self.funpay.account:
                await self.funpay.fetch_profile()
            
            if not self.funpay.account:
                logger.warning("Аккаунт не инициализирован")
                return
            
            # Получаем список заказов через библиотеку FunPayAPI
            _, orders = self.funpay.account.get_sells()
            
            for order in orders:
                order_id = order.id
                
                # Пропускаем уже обработанные заказы
                if order_id in self._processed_orders:
                    continue
                
                # Пропускаем уже обработанные (из БД)
                if await self.db.is_order_known(order_id):
                    self._processed_orders.add(order_id)
                    continue
                
                # Добавляем в БД
                await self.db.add_order(
                    order_id=order_id,
                    buyer=order.buyer_username,
                    lot_name=order.description,
                    amount=order.price,
                    status=order.status.name if hasattr(order.status, 'name') else str(order.status),
                )
                
                # Если заказ оплачен и ожидает выполнения
                if order.status.name == "PAID" or "paid" in str(order.status).lower():
                    self._processed_orders.add(order_id)
                    await self._deliver(order)
                    
        except Exception as e:
            logger.error(f"Ошибка при проверке заказов: {e}", exc_info=True)
    
    async def _get_chat_id_by_username(self, username: str) -> str | None:
        """Получает ID чата по никнейму покупателя."""
        try:
            chat = self.funpay.account.get_chat_by_name(username, make_request=True)
            if chat:
                return str(chat.id)
        except Exception as e:
            logger.error(f"Ошибка поиска чата для {username}: {e}")
        return None

    async def _deliver(self, order) -> None:
        """Пытается выдать товар из БД."""
        try:
            # Ищем товар в БД по названию лота
            product = await self.db.get_product(order.description)
            
            if product is None:
                logger.warning(
                    f"⚠️ Нет товаров для лота '{order.description}' (заказ {order.id}). Покупатель: {order.buyer_username}"
                )
                # Уведомляем через callback (бот пришлёт в ТГ)
                for cb in self._delivery_callbacks:
                    await cb(order.id, order.buyer_username, order.description, None)
                return
            
            # Получаем ID чата с покупателем
            chat_id = await self._get_chat_id_by_username(order.buyer_username)
            
            if not chat_id:
                logger.error(f"❌ Не найден чат с покупателем {order.buyer_username}")
                # Пробуем отправить в чат заказа
                chat_id = f"order-{order.id}"
            
            # Формируем сообщение с товаром
            message = f"✅ *Ваш товар по заказу #{order.id}*\n\n{product}\n\nСпасибо за покупку! Если есть вопросы — пишите."
            
            # Отправляем товар
            sent = await self.funpay.send_message(chat_id, message)
            
            if sent:
                await self.db.mark_delivered(order.id)
                logger.info(f"✅ Товар выдан: заказ {order.id}, покупатель {order.buyer_username}")
                for cb in self._delivery_callbacks:
                    await cb(order.id, order.buyer_username, order.description, product)
            else:
                logger.error(f"❌ Не удалось отправить товар по заказу {order.id}")
                
        except Exception as e:
            logger.error(f"Ошибка при выдаче товара для заказа {order.id}: {e}", exc_info=True)