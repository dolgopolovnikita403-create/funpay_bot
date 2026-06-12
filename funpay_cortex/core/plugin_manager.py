"""Менеджер плагинов — загрузка и управление модулями из папки plugins/."""

from __future__ import annotations

import importlib
import importlib.util
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("PluginManager")


@dataclass
class PluginInfo:
    name: str = ""
    version: str = "0.0.1"
    description: str = ""
    author: str = ""
    enabled: bool = True
    module: Any = None

    def __str__(self) -> str:
        status = "✅" if self.enabled else "❌"
        return f"{status} {self.name} v{self.version} — {self.description}"


class PluginManager:
    def __init__(self, plugins_dir: str | Path) -> None:
        self.plugins_dir = Path(plugins_dir)
        self.plugins: dict[str, PluginInfo] = {}

    def discover(self) -> int:
        """Ищет и загружает плагины из директории."""
        if not self.plugins_dir.exists():
            self.plugins_dir.mkdir(parents=True, exist_ok=True)
            return 0

        count = 0
        for pyfile in sorted(self.plugins_dir.glob("*.py")):
            if pyfile.name.startswith("_"):
                continue
            try:
                self._load_plugin(pyfile)
                count += 1
            except Exception as e:
                logger.error("Ошибка загрузки плагина %s: %s", pyfile.name, e)

        logger.info("Загружено плагинов: %d", count)
        return count

    def _load_plugin(self, path: Path) -> None:
        module_name = f"plugins.{path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            return
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]

        info = PluginInfo(
            name=getattr(mod, "PLUGIN_NAME", path.stem),
            version=getattr(mod, "PLUGIN_VERSION", "0.0.1"),
            description=getattr(mod, "PLUGIN_DESCRIPTION", ""),
            author=getattr(mod, "PLUGIN_AUTHOR", ""),
            enabled=True,
            module=mod,
        )
        self.plugins[info.name] = info
        logger.info("Плагин загружен: %s", info)

        # Вызываем on_load, если есть
        if hasattr(mod, "on_load"):
            mod.on_load()

    def list_plugins(self) -> list[PluginInfo]:
        return list(self.plugins.values())

    def enable(self, name: str) -> bool:
        if name in self.plugins:
            self.plugins[name].enabled = True
            return True
        return False

    def disable(self, name: str) -> bool:
        if name in self.plugins:
            self.plugins[name].enabled = False
            return True
        return False

    async def emit(self, event: str, *args, **kwargs) -> None:
        """Вызывает обработчик события у всех включённых плагинов."""
        for info in self.plugins.values():
            if not info.enabled:
                continue
            handler = getattr(info.module, f"on_{event}", None)
            if handler and callable(handler):
                try:
                    result = handler(*args, **kwargs)
                    if hasattr(result, "__await__"):
                        await result
                except Exception as e:
                    logger.error("Плагин %s ошибка в on_%s: %s", info.name, event, e)
