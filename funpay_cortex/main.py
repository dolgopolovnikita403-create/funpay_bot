#!/usr/bin/env python3
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
    from core.user_module_manager import UserModuleManager
    from bot.telegram_bot import CortexBot

    config = ConfigManager(BASE_DIR / "config.ini")
    db = Database(DATA_DIR / "database.db")
    await db.initialize()

    # Админский экземпляр для общих команд (не обязателен)
    admin_golden_key = config.get("FunPay", "golden_key")
    funpay_admin = FunPayAPI(admin_golden_key)
    await funpay_admin.fetch_profile()

    # Менеджер пользовательских модулей
    user_module_manager = UserModuleManager(db)

    # Запуск модулей для всех активных пользователей при старте бота
    await user_module_manager.start_all_active_users(config)

    bot = CortexBot(
        config=config,
        db=db,
        funpay_admin=funpay_admin,
        user_module_manager=user_module_manager,
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
