"""Менеджер подписок — проверка статуса, активация тарифов."""
import logging
from datetime import datetime
from typing import Optional
from core.database import Database

logger = logging.getLogger("SubscriptionManager")


class SubscriptionManager:
    def __init__(self, db: Database):
        self.db = db

    async def get_subscription_status(self, telegram_id: int) -> dict:
        """
        Возвращает статус подписки пользователя.
        {
            "has_subscription": bool,
            "tariff": str | None,
            "days_left": int,
            "end_date": datetime | None
        }
        """
        user = await self.db.get_user(telegram_id)
        if not user:
            return {"has_subscription": False, "tariff": None, "days_left": 0, "end_date": None}

        end_str = user.get("subscription_end")
        if not end_str:
            return {"has_subscription": False, "tariff": user.get("tariff"), "days_left": 0, "end_date": None}

        try:
            end_date = datetime.fromisoformat(end_str)
            now = datetime.now()
            if end_date > now:
                days_left = (end_date - now).days
                return {
                    "has_subscription": True,
                    "tariff": user.get("tariff", "free"),
                    "days_left": days_left,
                    "end_date": end_date
                }
            else:
                return {
                    "has_subscription": False,
                    "tariff": "expired",
                    "days_left": 0,
                    "end_date": end_date
                }
        except Exception as e:
            logger.error(f"Ошибка парсинга даты подписки для {telegram_id}: {e}")
            return {"has_subscription": False, "tariff": user.get("tariff"), "days_left": 0, "end_date": None}

    async def activate_free_trial(self, telegram_id: int) -> None:
        """Активирует бесплатный пробный период на 7 дней."""
        await self.db.update_subscription(telegram_id, "free", 7)
        logger.info(f"Бесплатный период активирован для {telegram_id}")

    async def activate_premium(self, telegram_id: int, days: int = 30) -> None:
        """Активирует премиум-подписку на указанное количество дней."""
        await self.db.update_subscription(telegram_id, "premium", days)
        logger.info(f"Премиум подписка активирована для {telegram_id} на {days} дней")

    async def extend_subscription(self, telegram_id: int, extra_days: int) -> None:
        """Продлевает текущую подписку (добавляет дни к существующей)."""
        user = await self.db.get_user(telegram_id)
        if not user:
            await self.activate_free_trial(telegram_id)
            return

        current_end = user.get("subscription_end")
        if current_end:
            try:
                end_date = datetime.fromisoformat(current_end)
                if end_date > datetime.now():
                    # Добавляем дни к текущей дате окончания
                    new_end = end_date + timedelta(days=extra_days)
                    await self.db.execute(
                        "UPDATE bot_users SET subscription_end = ? WHERE telegram_id = ?",
                        (new_end.isoformat(), telegram_id)
                    )
                    logger.info(f"Подписка продлена для {telegram_id} на {extra_days} дней")
                    return
            except:
                pass
        # Если нет активной подписки — просто активируем новую
        await self.db.update_subscription(telegram_id, user.get("tariff", "free"), extra_days)
