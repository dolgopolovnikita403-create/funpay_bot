"""Модуль автоматического поднятия лотов для отдельного пользователя."""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.config_manager import ConfigManager
    from core.database import Database
    from core.funpay_api import FunPayAPI

logger = logging.getLogger("AutoBump")


class AutoBump:
    def __init__(self, config: ConfigManager, funpay: FunPayAPI, telegram_id: int):
        self.config = config
        self.funpay = funpay
        self.telegram_id = telegram_id
        self._running = False
        self._task: asyncio.Task | None = None
        self._last_bump = None

    @property
    async def enabled(self) -> bool:
        return await self.db.get_module_state(self.telegram_id, "auto_bump")

    async def enable(self) -> None:
        await self.db.set_module_state(self.telegram_id, "auto_bump", True)

    async def disable(self) -> None:
        await self.db.set_module_state(self.telegram_id, "auto_bump", False)

    async def interval_hours(self) -> float:
        return await self.db.get_user_bump_interval(self.telegram_id)

    async def set_interval(self, hours: float) -> None:
        await self.db.set_user_bump_interval(self.telegram_id, hours)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        interval = await self.interval_hours()
        logger.info(f"🚀 AutoBump для пользователя {self.telegram_id} запущен (интервал {interval} ч).")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(f"🛑 AutoBump для пользователя {self.telegram_id} остановлен.")

    async def bump_now(self) -> tuple[bool, str]:
        success, msg = await self.funpay.bump_lots()
        self._last_bump = asyncio.get_event_loop().time()
        return success, msg

    async def _loop(self) -> None:
        while self._running:
            try:
                if await self.enabled:
                    success, msg = await self.bump_now()
                    if success:
                        logger.info(f"✅ Пользователь {self.telegram_id}: {msg}")
                    else:
                        logger.warning(f"⚠️ Пользователь {self.telegram_id}: ошибка поднятия: {msg}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"AutoBump ошибка (пользователь {self.telegram_id}): {e}", exc_info=True)
            interval = await self.interval_hours()
            await asyncio.sleep(interval * 3600)

    @property
    def last_bump(self) -> str:
        if self._last_bump:
            return asyncio.get_event_loop().time()
        return "никогда"
