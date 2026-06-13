#!/usr/bin/env python3
"""
FunPay Cortex — Telegram-бот для автоматизации продаж на FunPay.
"""

import asyncio
import logging
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
LOGS_DIR = BASE_DIR / "logs"
DATA_DIR = BASE_DIR / "data"
PLUGINS_DIR = BASE_DIR / "plugins"

for d in (LOGS_DIR, DATA_DIR, PLUGINS_DIR):
    d.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOGS_DIR / "cortex.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("FunPayCortex")


async def main() -> None:
    from core.config_manager import ConfigManager
    from core.database import Database
    from core.funpay_api import FunPayAPI
    from core.auto_delivery import AutoDelivery
    from core.auto_bump import AutoBump
    from core.auto_responder import AutoResponder
    from core.online_keeper import OnlineKeeper
    from core.plugin_manager import PluginManager
    from bot.telegram_bot import CortexBot

    config = ConfigManager(BASE_DIR / "config.ini")
    db = Database(DATA_DIR / "database.db")
    await db.initialize()

    admin_golden_key = config.get("FunPay", "golden_key")
    funpay = FunPayAPI(admin_golden_key)
    await funpay.fetch_profile()

    auto_delivery = AutoDelivery(config, db, funpay)
    auto_bump = AutoBump(config, funpay)
    auto_responder = AutoResponder(config, funpay, db)   # ← передаём db
    online_keeper = OnlineKeeper(config, funpay)

    plugin_manager = PluginManager(PLUGINS_DIR)
    plugin_manager.discover()

    bot = CortexBot(
        config=config,
        db=db,
        funpay=funpay,
        auto_delivery=auto_delivery,
        auto_bump=auto_bump,
        auto_responder=auto_responder,
        online_keeper=online_keeper,
        plugin_manager=plugin_manager,
    )

    token = config.get("Telegram", "bot_token")
    if not token:
        logger.error("Telegram bot_token не задан!")
        print("\n⚠️  Укажите bot_token в config.ini → [Telegram] → bot_token\n")
        return

    logger.info("🚀 FunPay Cortex запускается…")
    await bot.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем (Ctrl+C).")
