"""Модуль автоматического поднятия лотов."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Callable, Coroutine, Any

if TYPE_CHECKING:
    from core.config_manager import ConfigManager
    from core.funpay_api import FunPayAPI

logger = logging.getLogger("AutoBump")


class AutoBump:
    def __init__(self, config: ConfigManager, funpay: FunPayAPI) -> None:
        self.config = config
        self.funpay = funpay
        self._running = False
        self._task: asyncio.Task | None = None
        self._last_bump: datetime | None = None
        self._bump_callbacks: list[Callable[..., Coroutine[Any, Any, None]]] = []

    @property
    def enabled(self) -> bool:
        return self.config.getbool("Settings", "auto_bump")

    @property
    def interval_hours(self) -> float:
        return self.config.getfloat("Settings", "bump_interval", 4.0)

    def enable(self) -> None:
        self.config.set("Settings", "auto_bump", "on")

    def disable(self) -> None:
        self.config.set("Settings", "auto_bump", "off")

    def set_interval(self, hours: float) -> None:
        self.config.set("Settings", "bump_interval", str(hours))

    def on_bump(self, callback) -> None:
        self._bump_callbacks.append(callback)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("AutoBump запущен (интервал: %.1f ч).", self.interval_hours)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("AutoBump остановлен.")

    async def bump_now(self) -> tuple[bool, str]:
        success, msg = await self.funpay.bump_lots()
        self._last_bump = datetime.utcnow()
        for cb in self._bump_callbacks:
            await cb(success, msg)
        return success, msg

    async def _loop(self) -> None:
        while self._running:
            try:
                if self.enabled:
                    success, msg = await self.bump_now()
                    if success:
                        logger.info("Лоты подняты: %s", msg)
                    else:
                        logger.warning("Ошибка поднятия: %s", msg)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("AutoBump ошибка: %s", e, exc_info=True)

            await asyncio.sleep(self.interval_hours * 3600)

    @property
    def last_bump(self) -> str:
        if self._last_bump:
            return self._last_bump.strftime("%Y-%m-%d %H:%M:%S UTC")
        return "никогда"
