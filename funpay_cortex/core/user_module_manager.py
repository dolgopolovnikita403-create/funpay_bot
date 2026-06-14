"""Менеджер фоновых задач для каждого пользователя."""
from __future__ import annotations

import asyncio
import logging
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
        self.tasks: Dict[int, asyncio.Task] = {}
        self.responders: Dict[int, AutoResponder] = {}
        self.deliveries: Dict[int, AutoDelivery] = {}
        self.bumps: Dict[int, AutoBump] = {}
        self.keepers: Dict[int, OnlineKeeper] = {}

    async def start_for_user(self, telegram_id: int, golden_key: str, config) -> None:
        if telegram_id in self.tasks and not self.tasks[telegram_id].done():
            logger.info(f"Модули для {telegram_id} уже запущены")
            return

        user = await self.db.get_user(telegram_id)
        if not user:
            logger.error(f"Пользователь {telegram_id} не найден")
            return

        funpay = FunPayAPI(golden_key)
        profile = await funpay.fetch_profile()
        if not profile:
            logger.error(f"Не удалось инициализировать FunPay для {telegram_id}")
            return

        # Создаём модули
        auto_responder = AutoResponder(config, self.db, funpay, telegram_id)
        auto_delivery = AutoDelivery(config, self.db, funpay, telegram_id)
        auto_bump = AutoBump(config, self.db, funpay, telegram_id)
        online_keeper = OnlineKeeper(config, self.db, funpay, telegram_id)

        # Запускаем только включённые
        if await self.db.get_module_state(telegram_id, "auto_responder"):
            await auto_responder.start()
        if await self.db.get_module_state(telegram_id, "auto_delivery"):
            await auto_delivery.start()
        if await self.db.get_module_state(telegram_id, "auto_bump"):
            await auto_bump.start()
        if await self.db.get_module_state(telegram_id, "online_keeper"):
            await online_keeper.start()

        self.responders[telegram_id] = auto_responder
        self.deliveries[telegram_id] = auto_delivery
        self.bumps[telegram_id] = auto_bump
        self.keepers[telegram_id] = online_keeper

        task = asyncio.create_task(self._monitor_user(telegram_id))
        self.tasks[telegram_id] = task
        logger.info(f"✅ Запущены модули для {telegram_id}")

    async def stop_for_user(self, telegram_id: int) -> None:
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

        if telegram_id in self.tasks:
            self.tasks[telegram_id].cancel()
            try:
                await self.tasks[telegram_id]
            except asyncio.CancelledError:
                pass
            del self.tasks[telegram_id]
        logger.info(f"🛑 Остановлены модули для {telegram_id}")

    async def restart_module(self, telegram_id: int, module_name: str) -> None:
        """Перезапускает конкретный модуль для пользователя."""
        if module_name == "auto_responder" and telegram_id in self.responders:
            await self.responders[telegram_id].stop()
            await self.responders[telegram_id].start()
        elif module_name == "auto_delivery" and telegram_id in self.deliveries:
            await self.deliveries[telegram_id].stop()
            await self.deliveries[telegram_id].start()
        elif module_name == "auto_bump" and telegram_id in self.bumps:
            await self.bumps[telegram_id].stop()
            await self.bumps[telegram_id].start()
        elif module_name == "online_keeper" and telegram_id in self.keepers:
            await self.keepers[telegram_id].stop()
            await self.keepers[telegram_id].start()

    async def _monitor_user(self, telegram_id: int):
        last_state = {}
        while True:
            try:
                new_state = {
                    "auto_responder": await self.db.get_module_state(telegram_id, "auto_responder"),
                    "auto_delivery": await self.db.get_module_state(telegram_id, "auto_delivery"),
                    "auto_bump": await self.db.get_module_state(telegram_id, "auto_bump"),
                    "online_keeper": await self.db.get_module_state(telegram_id, "online_keeper"),
                }
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
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка мониторинга {telegram_id}: {e}")
                await asyncio.sleep(30)

    async def start_all_active_users(self, config) -> None:
        users = await self.db.get_all_active_users()
        for user in users:
            if user.get("golden_key"):
                await self.start_for_user(user["telegram_id"], user["golden_key"], config)

    async def stop_all(self) -> None:
        for tg_id in list(self.tasks.keys()):
            await self.stop_for_user(tg_id)
