"""A browser session on the dev database for the person named on the command
line, so the Mini App can be screenshotted locally. The token goes to
data/ (gitignored), never to the output."""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from bot.db.repo import Repo  # noqa: E402
from bot.db.repo._database import Database  # noqa: E402

OUT = ROOT / "data" / "screenshot-session.txt"


async def main(handle: str) -> None:
    db = Database(ROOT / "data" / "test.db")
    await db.connect()
    repo = Repo(db)
    cursor = await db.conn.execute("SELECT id FROM users WHERE handle_norm = ?", (handle.lower(),))
    row = await cursor.fetchone()
    if row is None:
        raise SystemExit(f"no person {handle}")
    token = await repo.create_session(int(row[0]), "local screenshot")
    OUT.write_text(token, encoding="utf-8")
    await db.close()
    print("session for person", row[0])


asyncio.run(main(sys.argv[1]))
