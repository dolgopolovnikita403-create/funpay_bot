"""Асинхронный клиент для FunPay (работает с конкретным golden_key)."""
import logging
import json
import requests
from bs4 import BeautifulSoup
from FunPayAPI import Account

logger = logging.getLogger("FunPayAPI")


class FunPayAPI:
    def __init__(self, golden_key: str):
        self.golden_key = golden_key
        self.account = None
        self._user_id = None

    async def fetch_profile(self):
        try:
            self.account = Account(self.golden_key)
            self.account.get()
            self._user_id = self.account.id
            logger.info(f"✅ Профиль загружен: {self.account.username}")
            return self.account
        except Exception as e:
            logger.error(f"Ошибка авторизации: {e}")
            return None

    async def fetch_lots(self):
        if not self.account:
            await self.fetch_profile()
        try:
            user = self.account.get_user(self._user_id)
            return user.get_lots()
        except Exception as e:
            logger.error(f"Ошибка получения лотов: {e}")
            return []

    async def bump_lots(self):
        if not self.account:
            await self.fetch_profile()
        try:
            url = f"https://funpay.com/users/{self._user_id}/?bump=1"
            response = requests.get(url, cookies={"golden_key": self.golden_key})
            if response.status_code == 200:
                logger.info("Лоты подняты")
                return True, "Лоты подняты"
            return False, "Ошибка"
        except Exception as e:
            return False, str(e)

    async def fetch_orders(self):
        if not self.account:
            await self.fetch_profile()
        try:
            _, orders = self.account.get_sells()
            return orders
        except Exception as e:
            return []

    async def send_message(self, node_id: str, text: str):
        if not self.account:
            await self.fetch_profile()
        try:
            chat_id = int(node_id) if str(node_id).isdigit() else node_id
            self.account.send_message(chat_id, text)
            logger.info(f"Сообщение отправлено в {node_id}")
            return True
        except Exception as e:
            logger.error(f"Ошибка отправки: {e}")
            return False

    async def send_order_message(self, order_id: str, text: str):
        return await self.send_message(f"order-{order_id}", text)

    async def fetch_chat_nodes(self):
        if not self.account:
            await self.fetch_profile()
        try:
            chats = self.account.request_chats()
            return [{"node_id": str(c.id), "sender": c.name, "last_message": c.last_message_text, "unread": c.unread} for c in chats]
        except Exception as e:
            return []

    async def keep_alive(self):
        if not self.account:
            await self.fetch_profile()
        try:
            self.account.get()
            return True
        except:
            return False

    async def close(self):
        pass

    @property
    def user_id(self):
        return self._user_id

    @property
    def username(self):
        return self.account.username if self.account else None
