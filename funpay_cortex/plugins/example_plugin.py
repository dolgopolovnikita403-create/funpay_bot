"""
Пример плагина для FunPay Cortex.
Каждый плагин — отдельный .py файл в папке plugins/.
"""

PLUGIN_NAME = "ExamplePlugin"
PLUGIN_VERSION = "1.0.0"
PLUGIN_DESCRIPTION = "Пример плагина — логирует события"
PLUGIN_AUTHOR = "Cortex"


def on_load():
    """Вызывается при загрузке плагина."""
    print(f"[{PLUGIN_NAME}] Плагин загружен!")


def on_order_new(order_id: str, buyer: str, lot_name: str):
    """Вызывается при новом заказе."""
    print(f"[{PLUGIN_NAME}] Новый заказ #{order_id} от {buyer}: {lot_name}")


def on_bump(success: bool, message: str):
    """Вызывается после поднятия лотов."""
    print(f"[{PLUGIN_NAME}] Bump: success={success}, {message}")
