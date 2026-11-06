"""SQLite persistence for per-symbol alert state and an email outbox."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True, slots=True)
class PendingAlert:
    id: int
    symbol: str
    rsi: float
    period: int
    interval: str
    threshold: float
    candle_close: str
    candle_close_time: str
    event_time: str
    attempts: int


class AlertStore:
    """Persist alert arming state and pending/sent email notifications."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS symbol_state (
                    symbol TEXT PRIMARY KEY,
                    armed INTEGER NOT NULL CHECK (armed IN (0, 1)),
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS alert_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    rsi REAL NOT NULL,
                    period INTEGER NOT NULL,
                    interval TEXT NOT NULL,
                    threshold REAL NOT NULL,
                    candle_close TEXT NOT NULL,
                    candle_close_time TEXT NOT NULL,
                    event_time TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('pending', 'sent')),
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    sent_at TEXT
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_alert_history_status ON alert_history(status, id)"
            )

    def initialize_symbol(self, symbol: str, armed: bool) -> None:
        """Create initial state without overwriting state restored from a prior run."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO symbol_state(symbol, armed, updated_at)
                VALUES (?, ?, ?)
                """,
                (symbol, int(armed), utc_now()),
            )

    def observe_rsi(
        self,
        *,
        symbol: str,
        rsi: float,
        period: int,
        interval: str,
        threshold: float,
        candle_close: str,
        candle_close_time: str,
        candle_closed: bool = False,
    ) -> int | None:
        """Persist a live threshold crossing; only a closed candle can re-arm."""

        now = utc_now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT armed FROM symbol_state WHERE symbol = ?", (symbol,)
            ).fetchone()
            if row is None:
                armed = rsi >= threshold
                connection.execute(
                    "INSERT INTO symbol_state(symbol, armed, updated_at) VALUES (?, ?, ?)",
                    (symbol, int(armed), now),
                )
                if not armed:
                    return None
            else:
                armed = bool(row["armed"])

            if rsi >= threshold:
                if candle_closed:
                    connection.execute(
                        "UPDATE symbol_state SET armed = 1, updated_at = ? WHERE symbol = ?",
                        (now, symbol),
                    )
                return None

            if not armed:
                return None

            cursor = connection.execute(
                """
                INSERT INTO alert_history (
                    symbol, rsi, period, interval, threshold, candle_close,
                    candle_close_time, event_time, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                """,
                (
                    symbol, rsi, period, interval, threshold, candle_close,
                    candle_close_time, now,
                ),
            )
            connection.execute(
                "UPDATE symbol_state SET armed = 0, updated_at = ? WHERE symbol = ?",
                (now, symbol),
            )
            return int(cursor.lastrowid)

    def get_pending_alerts(self, limit: int = 100) -> list[PendingAlert]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM alert_history
                WHERE status = 'pending'
                ORDER BY id
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            PendingAlert(
                id=row["id"],
                symbol=row["symbol"],
                rsi=row["rsi"],
                period=row["period"],
                interval=row["interval"],
                threshold=row["threshold"],
                candle_close=row["candle_close"],
                candle_close_time=row["candle_close_time"],
                event_time=row["event_time"],
                attempts=row["attempts"],
            )
            for row in rows
        ]

    def mark_alert_sent(self, alert_id: int) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE alert_history
                SET status = 'sent', sent_at = ?, last_error = NULL
                WHERE id = ? AND status = 'pending'
                """,
                (utc_now(), alert_id),
            )

    def record_delivery_failure(self, alert_id: int, error: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE alert_history
                SET attempts = attempts + 1, last_error = ?
                WHERE id = ? AND status = 'pending'
                """,
                (error[:1000], alert_id),
            )

    def get_symbol_state(self, symbol: str) -> bool | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT armed FROM symbol_state WHERE symbol = ?", (symbol,)
            ).fetchone()
        return None if row is None else bool(row["armed"])

    def close(self) -> None:
        """Connections are short-lived; provided for API symmetry."""
        return None
