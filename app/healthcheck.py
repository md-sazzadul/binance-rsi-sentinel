"""Docker health check for the persistent SQLite store."""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path


def main() -> int:
    database_path = Path(os.getenv("DATABASE_PATH", "data/alerts.sqlite3"))
    if not database_path.is_file():
        print(f"Database does not exist yet: {database_path}", file=sys.stderr)
        return 1

    try:
        with sqlite3.connect(f"file:{database_path}?mode=ro", uri=True, timeout=5) as db:
            result = db.execute("PRAGMA quick_check").fetchone()
            if not result or result[0] != "ok":
                print(f"SQLite quick_check failed: {result}", file=sys.stderr)
                return 1
            db.execute("SELECT 1 FROM symbol_state LIMIT 1").fetchone()
            db.execute("SELECT 1 FROM alert_history LIMIT 1").fetchone()
    except sqlite3.Error as exc:
        print(f"SQLite health check failed: {exc}", file=sys.stderr)
        return 1

    print("SQLite database is healthy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
