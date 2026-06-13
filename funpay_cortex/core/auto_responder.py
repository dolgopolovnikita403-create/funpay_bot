"""Автоответчик — отвечает на частые вопросы в чатах по шаблонам."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.config_manager import ConfigManager
    from core.funpay_api import FunPayAPI

logger = logging.getLogger("AutoResponder")

# ============================================================
# РАСШИРЕННЫЙ СЛОВАРЬ КЛЮЧЕВЫХ СЛОВ
# ============================================================

_KEYWORD_MAP: dict[str, dict[str, list[str]]] = {
    "greeting": {
        "keywords": [
            "привет", "здравствуйте", "добрый день", "добрый вечер", "доброе утро",
            "hello", "hi", "хай", "здрасте", "здравствуй", "доброго времени суток",
            "добра", "приветствую", "салют", "здорово", "доброго дня", "доброго вечера",
            "хелло", "хей", "приветик", "ку", "здарова", "хаюшки", "хэллоу"
        ],
        "template": "greeting"
    },
    "payment": {
        "keywords": [
            "оплатил", "заплатил", "оплата", "деньги", "перевод", "кинул", "отправил",
            "чек", "квитанция", "счёт оплачен", "заказ оплачен", "перевёл", "деньги ушли",
            "оплачено", "платеж прошел", "средства переведены", "оплатил заказ",
            "денежки", "бабки", "перевел деньги", "отправил деньги", "кинул деньги"
        ],
        "template": "payment"
    },
    "delivery_time": {
        "keywords": [
            "когда выдача", "когда получу", "сколько ждать", "время выдачи", "как быстро",
            "моментально", "автовыдача", "скоро выдашь", "когда будет", "через сколько",
            "доставка", "получу товар", "скорость выдачи", "выдача товара"
        ],
        "template": "delivery_time"
    },
    "delivery_issue": {
        "keywords": [
            "не пришёл", "не пришел товар", "не получил", "где товар", "не отправили",
            "не выдали", "товар не пришел", "нет товара", "не получил товар"
        ],
        "template": "delivery_issue"
    },
    "guarantee": {
        "keywords": [
            "гарантия", "возврат", "вернуть деньги", "refund", "гарантируешь", "какая гарантия",
            "срок гарантии", "гарантийный срок", "вернуть средства", "отмена заказа"
        ],
        "template": "guarantee"
    },
    "price": {
        "keywords": [
            "сколько стоит", "цена", "стоимость", "почём", "сколько денег", "ценник"
        ],
        "template": "price"
    },
    "discount": {
        "keywords": [
            "скидка", "торг", "дешевле", "уступишь", "нижняя цена", "подешевле",
            "бонус", "акция", "распродажа", "дешево", "уступите", "скидочку"
        ],
        "template": "discount"
    },
    "wholesale": {
        "keywords": [
            "оптом", "много", "несколько", "партия", "оптовая цена", "сколько есть",
            "количество", "много штук", "пачкой", "навалом", "большой заказ"
        ],
        "template": "wholesale"
    },
    "availability": {
        "keywords": [
            "есть в наличии", "товар есть", "в наличии", "доступно", "есть ли",
            "актуально", "ещё есть", "не забрали", "свободно", "не продано"
        ],
        "template": "availability"
    },
    "technical": {
        "keywords": [
            "не работает", "ошибка", "глюк", "не открывается", "не запускается",
            "проблема", "баг", "не отправляется", "не загружается", "битая ссылка"
        ],
        "template": "technical"
    },
    "thanks": {
        "keywords": [
            "спасибо", "благодарю", "спс", "пасиб", "thanks", "thank you", "благодарность"
        ],
        "template": "thanks"
    },
    "goodbye": {
        "keywords": [
            "пока", "до свидания", "удачи", "всего хорошего", "до связи",
            "bye", "goodbye", "прощай", "всего доброго", "счастливо"
        ],
        "template": "goodbye"
    },
    "help": {
        "keywords": [
            "помоги", "нужна помощь", "помощь", "поддержка", "help", "не понимаю"
        ],
        "template": "help"
    },
    "working_hours": {
        "keywords": [
            "работаешь", "до скольки", "во сколько", "режим работы", "когда онлайн"
        ],
        "template": "working_hours"
    },
    "agreement": {
        "keywords": [
            "да", "yes", "ок", "хорошо", "договорились", "согласен", "давай", "окей"
        ],
        "template": "agreement"
    },
}


class AutoResponder:
    def __init__(self, config: ConfigManager, funpay: FunPayAPI) -> None:
        self.config = config
        self.funpay = funpay
        self._running = False
        self._task: asyncio.Task | None = None
        self._answered_messages: set[str] = set()

    @property
    def enabled(self) -> bool:
        return self.config.getbool("Settings", "auto_responder")

    def enable(self) -> None:
        self.config.set("Settings", "auto_responder", "on")

    def disable(self) -> None:
        self.config.set("Settings", "auto_responder", "off")

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("🚀 AutoResponder запущен.")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 AutoResponder остановлен.")

    def _match_template(self, text: str) -> str | None:
        if not text:
            return None
        text_lower = text.lower().strip()
        for category, data in _KEYWORD_MAP.items():
            for keyword in data["keywords"]:
                if keyword in text_lower:
                    reply = self.config.get("AutoResponder", data["template"], "")
                    if reply:
                        return reply
        return None

    async def _loop(self) -> None:
        while self._running:
            try:
                if self.enabled:
                    await self._check_messages()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"AutoResponder ошибка: {e}", exc_info=True)
            await asyncio.sleep(3)  # проверка каждые 3 секунды

    async def _check_messages(self) -> None:
        try:
            if not self.funpay.account:
                await self.funpay.fetch_profile()
            if not self.funpay.account:
                return

            chats = self.funpay.account.request_chats()
            for chat in chats:
                if not chat.unread:
                    continue

                history = await self.funpay.get_chat_history(chat.id)
                if not history:
                    continue

                for msg in reversed(history):
                    if msg.get("author_id") == self.funpay.account.id:
                        continue

                    msg_text = msg.get("text", "")
                    if not msg_text:
                        continue

                    msg_key = f"{chat.id}:{msg.get('id')}"
                    if msg_key in self._answered_messages:
                        continue

                    reply = self._match_template(msg_text)
                    if not reply:
                        reply = self.config.get("AutoResponder", "no_match", "")
                    if reply:
                        success = await self.funpay.send_message(str(chat.id), reply)
                        if success:
                            self._answered_messages.add(msg_key)
                            logger.info(f"✅ Ответ в чат {chat.id}: {reply[:50]}...")
                            await asyncio.sleep(0.3)
                        break

            if len(self._answered_messages) > 500:
                self._answered_messages = set(list(self._answered_messages)[-250:])
        except Exception as e:
            logger.error(f"Ошибка проверки сообщений: {e}", exc_info=True)
