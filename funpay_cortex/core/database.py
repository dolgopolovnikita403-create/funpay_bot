"""SQLite-хранилище: заказы, товары для автовыдачи, статистика."""

from __future__ import annotations

import aiosqlite
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger("Database")


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL;")
        await self._create_tables()
        logger.info("БД инициализирована: %s", self.path)

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    # ── Таблицы ───────────────────────────────────────────────────

    async def _create_tables(self) -> None:
        await self._db.executescript(
            """
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
            """
        )
        await self._db.commit()

    # ── Заказы ────────────────────────────────────────────────────

    async def add_order(
        self, order_id: str, buyer: str, lot_name: str = "",
        amount: float = 0, currency: str = "RUB", status: str = "new"
    ) -> bool:
        try:
            await self._db.execute(
                "INSERT OR IGNORE INTO orders (order_id, buyer, lot_name, amount, currency, status) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (order_id, buyer, lot_name, amount, currency, status),
            )
            await self._db.commit()
            return True
        except Exception as e:
            logger.error("add_order error: %s", e)
            return False

    async def mark_delivered(self, order_id: str) -> None:
        await self._db.execute(
            "UPDATE orders SET delivered = 1, delivered_at = datetime('now'), status = 'delivered' "
            "WHERE order_id = ?",
            (order_id,),
        )
        await self._db.commit()

    async def is_order_known(self, order_id: str) -> bool:
        cur = await self._db.execute("SELECT 1 FROM orders WHERE order_id = ?", (order_id,))
        return await cur.fetchone() is not None

    # ── Товары для автовыдачи ─────────────────────────────────────

    async def add_product(self, lot_name: str, content: str) -> int:
        cur = await self._db.execute(
            "INSERT INTO products (lot_name, content) VALUES (?, ?)",
            (lot_name, content),
        )
        await self._db.commit()
        return cur.lastrowid  # type: ignore[return-value]

    async def get_product(self, lot_name: str) -> str | None:
        """Достаёт один неиспользованный товар (FIFO) и помечает used=1."""
        cur = await self._db.execute(
            "SELECT id, content FROM products WHERE lot_name = ? AND used = 0 "
            "ORDER BY id ASC LIMIT 1",
            (lot_name,),
        )
        row = await cur.fetchone()
        if row is None:
            return None
        await self._db.execute("UPDATE products SET used = 1 WHERE id = ?", (row["id"],))
        await self._db.commit()
        return row["content"]

    async def count_products(self, lot_name: str | None = None) -> int:
        if lot_name:
            cur = await self._db.execute(
                "SELECT COUNT(*) FROM products WHERE lot_name = ? AND used = 0",
                (lot_name,),
            )
        else:
            cur = await self._db.execute("SELECT COUNT(*) FROM products WHERE used = 0")
        row = await cur.fetchone()
        return row[0] if row else 0

    async def get_all_lot_names(self) -> list[str]:
        cur = await self._db.execute(
            "SELECT DISTINCT lot_name FROM products WHERE used = 0 ORDER BY lot_name"
        )
        rows = await cur.fetchall()
        return [r["lot_name"] for r in rows]

    # ── Статистика ────────────────────────────────────────────────

    async def get_stats(self, period: str = "all") -> dict[str, Any]:
        now = datetime.utcnow()
        if period == "day":
            since = (now - timedelta(days=1)).isoformat()
        elif period == "week":
            since = (now - timedelta(weeks=1)).isoformat()
        elif period == "month":
            since = (now - timedelta(days=30)).isoformat()
        else:
            since = "2000-01-01T00:00:00"

        cur = await self._db.execute(
            "SELECT COUNT(*) as cnt, COALESCE(SUM(amount), 0) as total "
            "FROM orders WHERE created_at >= ?",
            (since,),
        )
        row = await cur.fetchone()
        delivered_cur = await self._db.execute(
            "SELECT COUNT(*) as cnt FROM orders WHERE delivered = 1 AND created_at >= ?",
            (since,),
        )
        d_row = await delivered_cur.fetchone()
        return {
            "period": period,
            "orders": row["cnt"] if row else 0,
            "revenue": row["total"] if row else 0,
            "delivered": d_row["cnt"] if d_row else 0,
        }

    # ── Лог сообщений ────────────────────────────────────────────

    async def log_message(self, node_id: str, sender: str, text: str, replied: bool = False) -> None:
        await self._db.execute(
            "INSERT INTO messages_log (node_id, sender, text, replied) VALUES (?, ?, ?, ?)",
            (node_id, sender, text, int(replied)),
        )
        await self._db.commit()
