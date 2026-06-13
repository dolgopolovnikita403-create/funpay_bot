"""Менеджер фоновых задач для каждого пользователя (автоответчик, автоподнятие, автовыдача, онлайн-кипер)."""
import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional

from core.database import Database
from core.funpay_api import FunPayAPI
from core.auto_responder import AutoResponder
from core.auto_delivery import AutoDelivery
from core.auto_bump import AutoBump
from core.online_keeper import OnlineKeeper

logger = logging.getLogger("UserModuleManager")


class UserModuleManager:
    def __init__(self, db: Database):
        self.db = db
        self.tasks: Dict[int, asyncio.Task] = {}  # telegram_id -> task
        self.responders: Dict[int, AutoResponder] = {}
        self.deliveries: Dict[int, AutoDelivery] = {}
        self.bumps: Dict[int, AutoBump] = {}
        self.keepers: Dict[int, OnlineKeeper] = {}

    async def start_for_user(self, telegram_id: int, golden_key: str, config) -> None:
        """Запускает все модули для конкретного пользователя (если они включены в БД)."""
        if telegram_id in self.tasks and not self.tasks[telegram_id].done():
            logger.info(f"Модули для пользователя {telegram_id} уже запущены")
            return

        user = await self.db.get_user(telegram_id)
        if not user:
            logger.error(f"Пользователь {telegram_id} не найден")
            return

        # Создаём экземпляр FunPayAPI для пользователя
        funpay = FunPayAPI(golden_key)
        profile = await funpay.fetch_profile()
        if not profile:
            logger.error(f"Не удалось инициализировать FunPay для {telegram_id}")
            return

        # Создаём модули для этого пользователя
        auto_responder = AutoResponder(config, funpay, self.db, telegram_id)
        auto_delivery = AutoDelivery(config, self.db, funpay, telegram_id)
        auto_bump = AutoBump(config, funpay, telegram_id)
        online_keeper = OnlineKeeper(config, funpay, telegram_id)

        # Запускаем только те модули, которые включены в БД
        if await self.db.get_module_state(telegram_id, "auto_responder"):
            await auto_responder.start()
        if await self.db.get_module_state(telegram_id, "auto_delivery"):
            await auto_delivery.start()
        if await self.db.get_module_state(telegram_id, "auto_bump"):
            await auto_bump.start()
        if await self.db.get_module_state(telegram_id, "online_keeper"):
            await online_keeper.start()

        # Сохраняем ссылки на модули
        self.responders[telegram_id] = auto_responder
        self.deliveries[telegram_id] = auto_delivery
        self.bumps[telegram_id] = auto_bump
        self.keepers[telegram_id] = online_keeper

        # Создаём задачу, которая следит за состоянием модулей (например, перезапускает при изменении настроек)
        task = asyncio.create_task(self._monitor_user(telegram_id))
        self.tasks[telegram_id] = task
        logger.info(f"✅ Запущены модули для пользователя {telegram_id}")

    async def stop_for_user(self, telegram_id: int) -> None:
        """Останавливает все модули пользователя."""
        # Останавливаем каждый модуль
        if telegram_id in self.responders:
            await self.responders[telegram_id].stop()
            del self.responders[telegram_id]
        if telegram_id in self.deliveries:
            await self.deliveries[telegram_id].stop()
            del self.deliveries[telegram_id]
        if telegram_id in self.bumps:
            await self.bumps[telegram_id].stop()
            del self.bumps[telegram_id]
        if telegram_id in self.keepers:
            await self.keepers[telegram_id].stop()
            del self.keepers[telegram_id]

        # Отменяем задачу мониторинга
        if telegram_id in self.tasks:
            self.tasks[telegram_id].cancel()
            try:
                await self.tasks[telegram_id]
            except asyncio.CancelledError:
                pass
            del self.tasks[telegram_id]
        logger.info(f"🛑 Остановлены модули для пользователя {telegram_id}")

    async def _monitor_user(self, telegram_id: int):
        """Фоновый мониторинг: при изменении настроек в БД перезапускает модули."""
        last_state = {}
        while True:
            try:
                # Получаем текущее состояние модулей из БД
                new_state = {
                    "auto_responder": await self.db.get_module_state(telegram_id, "auto_responder"),
                    "auto_delivery": await self.db.get_module_state(telegram_id, "auto_delivery"),
                    "auto_bump": await self.db.get_module_state(telegram_id, "auto_bump"),
                    "online_keeper": await self.db.get_module_state(telegram_id, "online_keeper"),
                }
                # Если состояние изменилось, перезапускаем соответствующий модуль
                if telegram_id in self.responders and new_state["auto_responder"] != last_state.get("auto_responder"):
                    if new_state["auto_responder"]:
                        await self.responders[telegram_id].start()
                    else:
                        await self.responders[telegram_id].stop()
                if telegram_id in self.deliveries and new_state["auto_delivery"] != last_state.get("auto_delivery"):
                    if new_state["auto_delivery"]:
                        await self.deliveries[telegram_id].start()
                    else:
                        await self.deliveries[telegram_id].stop()
                if telegram_id in self.bumps and new_state["auto_bump"] != last_state.get("auto_bump"):
                    if new_state["auto_bump"]:
                        await self.bumps[telegram_id].start()
                    else:
                        await self.bumps[telegram_id].stop()
                if telegram_id in self.keepers and new_state["online_keeper"] != last_state.get("online_keeper"):
                    if new_state["online_keeper"]:
                        await self.keepers[telegram_id].start()
                    else:
                        await self.keepers[telegram_id].stop()

                last_state = new_state
                await asyncio.sleep(10)  # проверяем каждые 10 секунд
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка мониторинга пользователя {telegram_id}: {e}")
                await asyncio.sleep(30)

    async def start_all_active_users(self, config) -> None:
        """Запускает модули для всех пользователей с активной подпиской и golden_key."""
        users = await self.db.get_all_active_users()
        for user in users:
            if user.get("golden_key"):
                await self.start_for_user(user["telegram_id"], user["golden_key"], config)

    async def stop_all(self) -> None:
        """Останавливает модули всех пользователей."""
        for tg_id in list(self.tasks.keys()):
            await self.stop_for_user(tg_id)
