"""Поддержание статуса «онлайн» на FunPay."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.config_manager import ConfigManager
    from core.funpay_api import FunPayAPI

logger = logging.getLogger("OnlineKeeper")


class OnlineKeeper:
    PING_INTERVAL = 60  # секунд

    def __init__(self, config: ConfigManager, funpay: FunPayAPI) -> None:
        self.config = config
        self.funpay = funpay
        self._running = False
        self._task: asyncio.Task | None = None

    @property
    def enabled(self) -> bool:
        return self.config.getbool("Settings", "online_keeper")

    def enable(self) -> None:
        self.config.set("Settings", "online_keeper", "on")

    def disable(self) -> None:
        self.config.set("Settings", "online_keeper", "off")

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("OnlineKeeper запущен.")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("OnlineKeeper остановлен.")

    async def _loop(self) -> None:
        while self._running:
            try:
                if self.enabled:
                    ok = await self.funpay.keep_alive()
                    if ok:
                        logger.debug("Online ping OK")
                    else:
                        logger.warning("Online ping FAIL")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("OnlineKeeper ошибка: %s", e, exc_info=True)
            await asyncio.sleep(self.PING_INTERVAL)
