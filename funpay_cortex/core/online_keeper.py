from __future__ import annotations
import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.config_manager import ConfigManager
    from core.database import Database
    from core.funpay_api import FunPayAPI

logger = logging.getLogger("OnlineKeeper")

class OnlineKeeper:
    PING_INTERVAL = 60

    def __init__(self, config: ConfigManager, db: Database, funpay: FunPayAPI, telegram_id: int):
        self.config = config
        self.db = db
        self.funpay = funpay
        self.telegram_id = telegram_id
        self._running = False
        self._task: asyncio.Task | None = None

    @property
    async def enabled(self) -> bool:
        return await self.db.get_module_state(self.telegram_id, "online_keeper")

    async def enable(self) -> None:
        await self.db.set_module_state(self.telegram_id, "online_keeper", True)

    async def disable(self) -> None:
        await self.db.set_module_state(self.telegram_id, "online_keeper", False)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(f"🚀 OnlineKeeper для {self.telegram_id} запущен.")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(f"🛑 OnlineKeeper для {self.telegram_id} остановлен.")

    async def _loop(self) -> None:
        while self._running:
            try:
                if await self.enabled:
                    ok = await self.funpay.keep_alive()
                    if ok:
                        logger.debug(f"Online ping OK для {self.telegram_id}")
                    else:
                        logger.warning(f"Online ping FAIL для {self.telegram_id}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"OnlineKeeper ошибка ({self.telegram_id}): {e}", exc_info=True)
            await asyncio.sleep(self.PING_INTERVAL)
