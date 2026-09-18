"""One-glance summary of the database, for `manage.ps1 status`.

Read-only and dependency-free on purpose: it must work while the bot is down.
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = ROOT / "data" / "bot.db"


def scalar(conn: sqlite3.Connection, query: str) -> object:
    row = conn.execute(query).fetchone()
    return row[0] if row else None


def main() -> int:
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DB_PATH
    if not db_path.exists():
        print("Database not created yet.")
        return 0

    # read-only: the running bot must not be disturbed by a status check
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        # People with at least one active platform link (#52) — users.xuid
        # no longer exists; the account lives on accounts/account_links.
        try:
            linked = scalar(
                conn,
                "SELECT COUNT(DISTINCT tg_id) FROM account_links WHERE is_active = 1",
            )
        except sqlite3.OperationalError:
            print(
                "Database schema is outdated (missing account_links). "
                "Start the bot once to migrate."
            )
            return 1
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
    print(f"  linked:        {linked} (Xbox tokens live {active}, dead {dead})")
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
