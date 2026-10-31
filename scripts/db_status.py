"""One-glance summary of the database, for `manage.ps1 status`.

Read-only on purpose: it must work while the bot is down.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime

import psycopg

from bot.db import tools


def scalar(conn: tools.Connection, query: str) -> object:
    row = conn.execute(query).fetchone()
    return row[0] if row else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    tools.add_arguments(parser)
    args = parser.parse_args()

    # read-only: the running bot must not be disturbed by a status check
    try:
        conn = tools.connect(schema=args.schema, readonly=True)
    except psycopg.OperationalError as exc:
        print(
            "Database not created yet." if "does not exist" in str(exc) else "Database not running."
        )
        return 0
    try:
        # People with at least one active platform link (#52) — users.xuid
        # no longer exists; the account lives on accounts/account_links.
        try:
            linked = scalar(
                conn,
                "SELECT COUNT(DISTINCT person_id) FROM account_links WHERE is_active = 1",
            )
        except psycopg.errors.UndefinedTable:
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
            "WHERE unlocked_at >= to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD') "
            "AND is_backfill = 0",
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
