"""Менеджер подписок."""
import logging
from datetime import datetime
from typing import Optional
from core.database import Database

logger = logging.getLogger("SubscriptionManager")


class SubscriptionManager:
    def __init__(self, db: Database):
        self.db = db

    async def get_subscription_status(self, telegram_id: int) -> dict:
        user = await self.db.get_user(telegram_id)
        if not user:
            return {"has_subscription": False, "tariff": None, "days_left": 0}

        end_str = user.get("subscription_end")
        if not end_str:
            return {"has_subscription": False, "tariff": user.get("tariff"), "days_left": 0}

        try:
            end_date = datetime.fromisoformat(end_str)
            now = datetime.now()
            if end_date > now:
                days_left = (end_date - now).days
                return {"has_subscription": True, "tariff": user.get("tariff"), "days_left": days_left, "end_date": end_date}
            else:
                return {"has_subscription": False, "tariff": "expired", "days_left": 0}
        except:
            return {"has_subscription": False, "tariff": user.get("tariff"), "days_left": 0}

    async def activate_free_trial(self, telegram_id: int) -> None:
        await self.db.update_subscription(telegram_id, "free", 7)

    async def activate_premium(self, telegram_id: int, days: int = 30) -> None:
        await self.db.update_subscription(telegram_id, "premium", days)
