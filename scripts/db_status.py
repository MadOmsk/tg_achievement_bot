"""One-glance summary of the database, for `manage.ps1 status`.

Read-only and dependency-free on purpose: it must work while the bot is down.
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def scalar(conn: sqlite3.Connection, query: str) -> object:
    row = conn.execute(query).fetchone()
    return row[0] if row else None


def _resolve_db_path(raw: str | None) -> Path:
    # manage.ps1 passes the instance DB (bot.db or test.db); bare runs keep
    # the historical default so a one-line `python scripts/db_status.py` still
    # means the main database.
    path = Path(raw) if raw else ROOT / "data" / "bot.db"
    if not path.is_absolute():
        path = ROOT / path
    return path


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    db_path = _resolve_db_path(args[0] if args else None)
    if not db_path.exists():
        print("Database not created yet.")
        return 0

    # read-only: the running bot must not be disturbed by a status check
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        users = scalar(conn, "SELECT COUNT(*) FROM users WHERE xuid IS NOT NULL")
        active = scalar(conn, "SELECT COUNT(*) FROM tokens WHERE status = 'active'")
        dead = scalar(conn, "SELECT COUNT(*) FROM tokens WHERE status <> 'active'")
        chats = scalar(conn, "SELECT COUNT(*) FROM chats WHERE is_active = 1")
        subs = scalar(conn, "SELECT COUNT(*) FROM subscriptions")
        seen = scalar(conn, "SELECT COUNT(*) FROM seen_achievements")
        published = scalar(conn, "SELECT COUNT(*) FROM publications")
        last_poll = scalar(conn, "SELECT MAX(updated_at) FROM presence_state")
        today = scalar(
            conn,
            "SELECT COUNT(*) FROM seen_achievements "
            "WHERE unlocked_at >= date('now') AND is_backfill = 0",
        )
    finally:
        conn.close()

    print("Database:")
    print(f"  linked:        {users} (tokens live {active}, dead {dead})")
    print(f"  chats:         {chats}, subscriptions {subs}")
    print(f"  achievements:  {seen}, published {published}, new today {today}")
    print(f"  last tick:     {last_poll or 'never'}{_age(last_poll)}")
    return 0


def _age(timestamp: object) -> str:
    if not isinstance(timestamp, str):
        return ""
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError:
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    minutes = int((datetime.now(UTC) - parsed).total_seconds() // 60)
    return f"  ({minutes} min ago)" if minutes else "  (just now)"


if __name__ == "__main__":
    sys.exit(main())
