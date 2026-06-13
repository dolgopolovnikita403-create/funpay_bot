"""SQLite-хранилище с поддержкой пользователей и подписок."""
from __future__ import annotations

import sqlite3
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger("Database")

executor = ThreadPoolExecutor(max_workers=1)


def run_sync(func, *args, **kwargs):
    return asyncio.get_event_loop().run_in_executor(executor, lambda: func(*args, **kwargs))


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS orders (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id      TEXT    UNIQUE NOT NULL,
                    buyer         TEXT    NOT NULL,
                    lot_name      TEXT    NOT NULL DEFAULT '',
                    amount        REAL    NOT NULL DEFAULT 0,
                    currency      TEXT    NOT NULL DEFAULT 'RUB',
                    status        TEXT    NOT NULL DEFAULT 'new',
                    delivered     INTEGER NOT NULL DEFAULT 0,
                    delivered_at  TEXT,
                    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS products (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    lot_name    TEXT    NOT NULL,
                    content     TEXT    NOT NULL,
                    used        INTEGER NOT NULL DEFAULT 0,
                    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS messages_log (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    node_id     TEXT,
                    sender      TEXT,
                    text        TEXT,
                    replied     INTEGER NOT NULL DEFAULT 0,
                    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS bot_users (
                    telegram_id       INTEGER PRIMARY KEY,
                    username         TEXT,
                    golden_key       TEXT,
                    funpay_username  TEXT,
                    funpay_id        INTEGER,
                    tariff           TEXT DEFAULT 'free',
                    subscription_end  TEXT,
                    created_at       TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS payments (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL,
                    amount      REAL NOT NULL,
                    stars       INTEGER,
                    status      TEXT NOT NULL,
                    payment_id  TEXT,
                    created_at  TEXT DEFAULT (datetime('now'))
                );
            """)
        logger.info("БД инициализирована: %s", self.path)

    async def initialize(self) -> None:
        await run_sync(self._init_db)

    async def execute(self, query: str, params: tuple = ()) -> None:
        def _execute():
            with sqlite3.connect(self.path) as conn:
                conn.execute(query, params)
                conn.commit()
        await run_sync(_execute)

    async def fetch_one(self, query: str, params: tuple = ()) -> dict | None:
        def _fetch_one():
            with sqlite3.connect(self.path) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(query, params)
                row = cur.fetchone()
                return dict(row) if row else None
        return await run_sync(_fetch_one)

    async def fetch_all(self, query: str, params: tuple = ()) -> list[dict]:
        def _fetch_all():
            with sqlite3.connect(self.path) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(query, params)
                return [dict(row) for row in cur.fetchall()]
        return await run_sync(_fetch_all)

    # ------------------ ПОЛЬЗОВАТЕЛИ ------------------
    async def get_user(self, telegram_id: int) -> dict | None:
        return await self.fetch_one("SELECT * FROM bot_users WHERE telegram_id = ?", (telegram_id,))

    async def create_user(self, telegram_id: int, username: str = "") -> None:
        await self.execute(
            "INSERT OR IGNORE INTO bot_users (telegram_id, username, tariff, subscription_end) VALUES (?, ?, 'free', datetime('now', '+7 days'))",
            (telegram_id, username)
        )

    async def save_golden_key(self, telegram_id: int, golden_key: str, funpay_username: str = "", funpay_id: int = 0) -> None:
        await self.execute(
            "UPDATE bot_users SET golden_key = ?, funpay_username = ?, funpay_id = ? WHERE telegram_id = ?",
            (golden_key, funpay_username, funpay_id, telegram_id)
        )

    async def update_subscription(self, telegram_id: int, tariff: str, days: int) -> None:
        await self.execute(
            "UPDATE bot_users SET tariff = ?, subscription_end = datetime('now', ?) WHERE telegram_id = ?",
            (tariff, f"+{days} days", telegram_id)
        )

    async def is_subscription_active(self, telegram_id: int) -> bool:
        user = await self.get_user(telegram_id)
        if not user:
            return False
        end_str = user.get("subscription_end")
        if not end_str:
            return False
        try:
            end_date = datetime.fromisoformat(end_str)
            return end_date > datetime.now()
        except:
            return False

    async def get_active_users(self) -> list[dict]:
        return await self.fetch_all("SELECT * FROM bot_users WHERE subscription_end > datetime('now')")

    # ------------------ ЗАКАЗЫ ------------------
    async def add_order(self, order_id: str, buyer: str, lot_name: str = "", amount: float = 0, currency: str = "RUB", status: str = "new") -> bool:
        try:
            await self.execute(
                "INSERT OR IGNORE INTO orders (order_id, buyer, lot_name, amount, currency, status) VALUES (?, ?, ?, ?, ?, ?)",
                (order_id, buyer, lot_name, amount, currency, status),
            )
            return True
        except Exception as e:
            logger.error("add_order error: %s", e)
            return False

    async def mark_delivered(self, order_id: str) -> None:
        await self.execute(
            "UPDATE orders SET delivered = 1, delivered_at = datetime('now'), status = 'delivered' WHERE order_id = ?",
            (order_id,),
        )

    async def is_order_known(self, order_id: str) -> bool:
        row = await self.fetch_one("SELECT 1 FROM orders WHERE order_id = ?", (order_id,))
        return row is not None

    # ------------------ ТОВАРЫ ------------------
    async def add_product(self, lot_name: str, content: str) -> int:
        await self.execute("INSERT INTO products (lot_name, content) VALUES (?, ?)", (lot_name, content))
        row = await self.fetch_one("SELECT last_insert_rowid() as id")
        return row["id"] if row else 0

    async def get_product(self, lot_name: str) -> str | None:
        row = await self.fetch_one(
            "SELECT id, content FROM products WHERE lot_name = ? AND used = 0 ORDER BY id ASC LIMIT 1",
            (lot_name,),
        )
        if not row:
            return None
        await self.execute("UPDATE products SET used = 1 WHERE id = ?", (row["id"],))
        return row["content"]

    async def count_products(self, lot_name: str | None = None) -> int:
        if lot_name:
            row = await self.fetch_one("SELECT COUNT(*) as cnt FROM products WHERE lot_name = ? AND used = 0", (lot_name,))
        else:
            row = await self.fetch_one("SELECT COUNT(*) as cnt FROM products WHERE used = 0")
        return row["cnt"] if row else 0

    async def get_all_lot_names(self) -> list[str]:
        rows = await self.fetch_all("SELECT DISTINCT lot_name FROM products WHERE used = 0 ORDER BY lot_name")
        return [row["lot_name"] for row in rows]

    # ------------------ СТАТИСТИКА ------------------
    async def get_stats(self, period: str = "all") -> dict[str, Any]:
        now = datetime.utcnow()
        since = "2000-01-01T00:00:00"
        if period == "day":
            since = (now - timedelta(days=1)).isoformat()
        elif period == "week":
            since = (now - timedelta(weeks=1)).isoformat()
        elif period == "month":
            since = (now - timedelta(days=30)).isoformat()
        row = await self.fetch_one("SELECT COUNT(*) as cnt, COALESCE(SUM(amount), 0) as total FROM orders WHERE created_at >= ?", (since,))
        d_row = await self.fetch_one("SELECT COUNT(*) as cnt FROM orders WHERE delivered = 1 AND created_at >= ?", (since,))
        return {
            "period": period,
            "orders": row["cnt"] if row else 0,
            "revenue": row["total"] if row else 0,
            "delivered": d_row["cnt"] if d_row else 0,
        }

    # ------------------ ЛОГ СООБЩЕНИЙ ------------------
    async def log_message(self, node_id: str, sender: str, text: str, replied: bool = False) -> None:
        await self.execute(
            "INSERT INTO messages_log (node_id, sender, text, replied) VALUES (?, ?, ?, ?)",
            (node_id, sender, text, int(replied)),
        )

    async def close(self) -> None:
        pass
