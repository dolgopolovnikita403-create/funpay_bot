"""
Обёртка над библиотекой FunPayAPI
"""
import logging
import json
import requests
from bs4 import BeautifulSoup
from FunPayAPI import Account

logger = logging.getLogger("FunPayAPI")


class FunPayAPI:
    def __init__(self, config) -> None:
        self.config = config
        self.account = None
        self._user_id = None

    @property
    def golden_key(self) -> str:
        return self.config.get("FunPay", "golden_key")

    async def fetch_profile(self):
        try:
            self.account = Account(self.golden_key)
            self.account.get()
            self._user_id = self.account.id
            logger.info(f"✅ Профиль загружен: {self.account.username} (id={self.account.id})")
            return self.account
        except Exception as e:
            logger.error(f"❌ Ошибка авторизации: {e}")
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
                logger.info("✅ Лоты успешно подняты")
                return True, "Лоты подняты"
            return False, "Ошибка поднятия"
        except Exception as e:
            logger.error(f"Ошибка поднятия: {e}")
            return False, str(e)

    async def fetch_orders(self):
        if not self.account:
            await self.fetch_profile()
        try:
            _, orders = self.account.get_sells()
            return orders
        except Exception as e:
            logger.error(f"Ошибка получения заказов: {e}")
            return []

    async def send_message(self, node_id: str, text: str):
        """Отправляет сообщение в чат используя библиотечный метод"""
        try:
            if not self.account:
                await self.fetch_profile()
            
            if not self.account:
                logger.error("Аккаунт не инициализирован")
                return False
            
            chat_id = int(node_id) if str(node_id).isdigit() else node_id
            
            # Используем встроенный метод библиотеки
            self.account.send_message(chat_id, text)
            logger.info(f"✅ Сообщение отправлено в {node_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки в {node_id}: {e}")
            return False

    async def send_order_message(self, order_id: str, text: str):
        return await self.send_message(f"order-{order_id}", text)

    async def fetch_chat_nodes(self):
        if not self.account:
            await self.fetch_profile()
        try:
            chats = self.account.request_chats()
            result = []
            for chat in chats:
                result.append({
                    "node_id": str(chat.id),
                    "sender": chat.name,
                    "last_message": chat.last_message_text,
                    "unread": chat.unread,
                })
            return result
        except Exception as e:
            logger.error(f"Ошибка получения чатов: {e}")
            return []

    async def get_chat_history(self, chat_id: int, limit: int = 10):
        """Получает последние текстовые сообщения из чата через runner"""
        if not self.account:
            await self.fetch_profile()
        
        if not self.account.csrf_token:
            logger.error("Нет CSRF токена")
            return []
        
        try:
            objects = [{
                "type": "chat_node",
                "id": chat_id,
                "tag": "00000000",
                "data": {
                    "node": chat_id,
                    "last_message": -1,
                    "content": ""
                }
            }]
            
            payload = {
                "objects": json.dumps(objects),
                "request": False,
                "csrf_token": self.account.csrf_token
            }
            
            headers = {
                "accept": "*/*",
                "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
                "x-requested-with": "XMLHttpRequest",
                "cookie": f"golden_key={self.golden_key}",
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            response = requests.post("https://funpay.com/runner/", data=payload, headers=headers, timeout=10)
            
            if response.status_code != 200:
                logger.error(f"Ошибка runner: {response.status_code}")
                return []
            
            data = response.json()
            messages = []
            
            for obj in data.get("objects", []):
                if obj.get("type") == "chat_node" and obj.get("data", {}).get("messages"):
                    for msg in obj["data"]["messages"]:
                        html_content = msg.get("html", "")
                        if not html_content:
                            continue
                        
                        soup = BeautifulSoup(html_content, "html.parser")
                        
                        text = None
                        for selector in [".message-text", ".chat-message-text", ".msg-text"]:
                            elem = soup.select_one(selector)
                            if elem:
                                text = elem.get_text(strip=True)
                                break
                        
                        if not text:
                            divs = soup.find_all("div")
                            for div in divs:
                                if div.get_text(strip=True) and len(div.get_text(strip=True)) > 3:
                                    text = div.get_text(strip=True)
                                    break
                        
                        if not text or len(text) < 2:
                            continue
                        
                        system_keywords = ["подтвердил", "оплатил", "администратор", "возврат", "открыт повторно"]
                        if any(kw in text for kw in system_keywords):
                            continue
                        
                        messages.append({
                            "id": msg.get("id"),
                            "author_id": msg.get("author"),
                            "text": text,
                        })
            
            if messages:
                logger.info(f"✅ Получено {len(messages)} сообщений из чата {chat_id}")
                if messages:
                    logger.info(f"📝 Пример сообщения: {messages[-1]['text'][:50]}")
                return messages[-limit:]
            else:
                logger.warning(f"⚠️ В чате {chat_id} нет текстовых сообщений")
                return []
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения истории чата {chat_id}: {e}")
            return []

    async def keep_alive(self):
        if not self.account:
            await self.fetch_profile()
        try:
            self.account.get()
            return True
        except Exception as e:
            logger.error(f"Ошибка keep_alive: {e}")
            return False

    async def close(self):
        pass

    @property
    def user_id(self):
        return self._user_id

    @property
    def username(self):
        return self.account.username if self.account else None

    @property
    def balance(self):
        if not self.account:
            return "0"
        try:
            balance = self.account.get_balance()
            return str(balance.available_rub)
        except:
            return "0"