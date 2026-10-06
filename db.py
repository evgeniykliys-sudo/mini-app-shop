"""Заказы: new → paid → refunded (демо-возврат звёзд)."""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

DB_PATH = os.getenv("DB_PATH") or "orders.db"
TZ = ZoneInfo(os.getenv("TZ_NAME") or "Asia/Novosibirsk")


@contextmanager
def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def init_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                items_json TEXT NOT NULL,
                total_rub INTEGER NOT NULL,
                pickup TEXT,
                comment TEXT,
                status TEXT NOT NULL DEFAULT 'new',
                stars INTEGER,
                tg_charge_id TEXT,
                created_at TEXT NOT NULL,
                paid_at TEXT,
                refunded_at TEXT
            )
        """)


def create(user_id, username, lines, total, pickup, comment, stars) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO orders (user_id, username, items_json, total_rub, pickup, comment, stars, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, username, json.dumps(lines, ensure_ascii=False), total, pickup, comment, stars, now_iso()),
        )
        return cur.lastrowid


def get(order_id: int):
    with _connect() as conn:
        return conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()


def mark_paid(order_id: int, charge_id: str) -> bool:
    """False — уже оплачен (повторное уведомление об оплате)."""
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE orders SET status = 'paid', tg_charge_id = ?, paid_at = ? WHERE id = ? AND status = 'new'",
            (charge_id, now_iso(), order_id),
        )
        return cur.rowcount == 1


def mark_refunded(order_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE orders SET status = 'refunded', refunded_at = ? WHERE id = ? AND status = 'paid'",
            (now_iso(), order_id),
        )
        return cur.rowcount == 1


def lines(order) -> list[dict]:
    return json.loads(order["items_json"])
