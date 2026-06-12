"""Менеджер конфигурации — чтение/запись config.ini."""

from __future__ import annotations

import configparser
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("ConfigManager")

_DEFAULT: dict[str, dict[str, str]] = {
    "FunPay": {
        "golden_key": "",
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "proxy": "",
        "base_url": "https://funpay.com",
    },
    "Telegram": {
        "bot_token": "",
        "admin_id": "",
    },
    "Settings": {
        "auto_delivery": "off",
        "auto_bump": "off",
        "auto_responder": "off",
        "online_keeper": "off",
        "bump_interval": "4",
        "request_delay_min": "2",
        "request_delay_max": "5",
    },
    "AutoResponder": {
        "greeting": "Здравствуйте! Спасибо за обращение. Чем могу помочь?",
        "payment": "После оплаты товар будет выдан автоматически в течение минуты.",
        "delivery_time": "Выдача моментальная — автоматически после оплаты.",
        "default": "Спасибо за сообщение! Я отвечу вам в ближайшее время.",
    },
}


class ConfigManager:
    """Thread-safe обёртка вокруг configparser."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._cfg = configparser.ConfigParser(interpolation=None)
        self._load()

    # ── Публичные методы ──────────────────────────────────────────

    def get(self, section: str, key: str, fallback: str = "") -> str:
        return self._cfg.get(section, key, fallback=fallback)

    def getint(self, section: str, key: str, fallback: int = 0) -> int:
        try:
            return self._cfg.getint(section, key, fallback=fallback)
        except (ValueError, TypeError):
            return fallback

    def getfloat(self, section: str, key: str, fallback: float = 0.0) -> float:
        try:
            return self._cfg.getfloat(section, key, fallback=fallback)
        except (ValueError, TypeError):
            return fallback

    def getbool(self, section: str, key: str) -> bool:
        return self.get(section, key).lower() in ("on", "true", "1", "yes")

    def set(self, section: str, key: str, value: Any) -> None:
        if not self._cfg.has_section(section):
            self._cfg.add_section(section)
        self._cfg.set(section, key, str(value))
        self._save()

    def sections(self) -> list[str]:
        return self._cfg.sections()

    def items(self, section: str) -> list[tuple[str, str]]:
        if self._cfg.has_section(section):
            return list(self._cfg.items(section))
        return []

    # ── Приватные методы ──────────────────────────────────────────

    def _load(self) -> None:
        if self.path.exists():
            self._cfg.read(self.path, encoding="utf-8")
        # дополняем недостающие значения по умолчанию
        changed = False
        for section, pairs in _DEFAULT.items():
            if not self._cfg.has_section(section):
                self._cfg.add_section(section)
                changed = True
            for k, v in pairs.items():
                if not self._cfg.has_option(section, k):
                    self._cfg.set(section, k, v)
                    changed = True
        if changed:
            self._save()
        logger.info("Конфиг загружен: %s", self.path)

    def _save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as fh:
            self._cfg.write(fh)
