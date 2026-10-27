"""One-time backfill: the games the catalogue never learned the name of.

Two gaps, both found by auditing production on 2026-09-19, both invisible
until somebody looks at a list and sees a row with no name on it.

**76 Xbox games have achievements and no `titles` row at all** — 658
achievements between them. A game's name is learned when the game is
*polled*, and a game nobody plays any more is never polled again, so these
were never going to fill in by themselves. Steam's own version of this was
#70 and is long closed; this is the Xbox half, and it needs one titlehub
request per game, through an owner's own token.

(A second gap, 125 rows with a NULL `platform`, was closed for good by
migration 090: the platform is now part of a game's key.)

**The bot must be stopped**, for the reason every Xbox script here says:
Microsoft invalidates the previous refresh token when a new one is issued,
and `XboxAuthService`'s guard is an `asyncio.Lock` — it serializes callers
inside one process and does nothing across two. This takes the bot's own
single-instance lock rather than trusting the operator to remember.

Idempotent and resumable: the gap query excludes what is already filled,
so interrupting it and re-running picks up where it stopped.

Usage:
    systemctl stop xbox-bot
    .venv/bin/python -m scripts.backfill_title_names --dry-run
    .venv/bin/python -m scripts.backfill_title_names
    systemctl start xbox-bot
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from bot.config import get_settings
from bot.db.repo import Database, Repo
from bot.lock import AlreadyRunningError, single_instance
from bot.services.crypto import TokenCipher
from bot.services.xbox.auth import XboxAuthService
from bot.services.xbox.client import XboxApiError, XboxClient

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", stream=sys.stdout
)
log = logging.getLogger("backfill_title_names")

#: A run with no output reads as a hang, and this one is a request per game.
PROGRESS_EVERY = 20


async def run() -> int:
    parser = argparse.ArgumentParser(description="Name the games the catalogue is missing.")
    parser.add_argument("--limit", type=int, default=0, help="stop after N games (0 = no limit)")
    parser.add_argument("--dry-run", action="store_true", help="count the work, fetch nothing")
    args = parser.parse_args()

    settings = get_settings()
    database = await Database(settings.db_path).connect()
    repo = Repo(database)

    # One titlehub request per game.
    missing = await repo.titles_missing_from_catalogue(args.limit or 10**6)
    log.info("%s games have achievements and no catalogue row (one request each)", len(missing))
    if args.dry_run or not missing:
        await database.close()
        return 0

    cipher = TokenCipher(settings.fernet_key.get_secret_value())
    auth = XboxAuthService(settings, repo, cipher)
    await auth.start()
    client = XboxClient(auth)

    named = unanswered = failed = 0
    for index, (title_id, _platform, person_id) in enumerate(missing, start=1):
        try:
            entry = await client.resolve_title(person_id, title_id)
        except XboxApiError as exc:
            # A delisted game, a bad afternoon at Microsoft. One title must
            # never end the run.
            log.info("  %s: skipped (%s)", title_id, exc)
            failed += 1
            continue
        if entry is None or not entry.name:
            # Asked, and titlehub has nothing to say. Nothing to store and
            # nothing to retry.
            unanswered += 1
            continue
        await repo.upsert_title(entry.title_id, entry.name, entry.platform, entry.icon_url)
        named += 1
        if index % PROGRESS_EVERY == 0:
            log.info("  %s/%s games, %s named", index, len(missing), named)

    log.info("done: %s games named, %s had no name to give, %s failed", named, unanswered, failed)
    await auth.close()
    await database.close()
    return 0


def main() -> int:
    settings = get_settings()
    try:
        with single_instance(settings.db_path.parent / "bot.lock"):
            return asyncio.run(run())
    except AlreadyRunningError:
        log.error(
            "the bot is running — stop it first (systemctl stop xbox-bot). "
            "Two processes refreshing one person's Xbox token log that person out."
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
