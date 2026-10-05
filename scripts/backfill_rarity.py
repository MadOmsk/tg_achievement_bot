"""One-time backfill: rarity for the Xbox history that never had any.

Rarity arrives only on contract 4 — the per-title call a live poll makes.
Backfill reads the whole library with one contract-2 request, which carries
no percentage at all, so a freshly linked account's entire history lands
without one: 25 692 rows of 25 825 on production. Those achievements can
never be rare, anywhere, because nothing ever told the bot how rare they are.

The rows themselves cannot be repaired — every insert is `INSERT OR IGNORE`
and nothing in the project UPDATEs `seen_achievements`. This fills
the catalog (`title_achievements`) instead, which the reading side prefers over the
row (`db/repo/_sql.py::rarity`).

**One request per title, not per person.** A contract-4 reply lists every
achievement of the game, the caller's own or not, and rarity is a fact about
the achievement — so whichever owner is asked answers for everybody. On
production that is 963 distinct titles against 1 704 person-title pairs.

**`poller/rarity_backfill.py` does the same walk and needs no operator.** It
runs five titles a minute inside the bot and finishes production in about
three hours, unattended. This script exists for the one case that poller
cannot serve: finishing a known backlog in one sitting, right after a
deploy, at the full pace the rate limiter allows — roughly a request a
second, so about sixteen minutes for those 963 titles.

**The bot must be stopped.** Xbox rotates a per-user refresh token and
Microsoft invalidates the previous one, so two processes refreshing the same
person log that person out of the bot. `XboxAuthService`'s guard is an
`asyncio.Lock`: it serializes callers inside one process and does nothing
across two. This script takes the bot's own single-instance lock and refuses
to start if the bot holds it, rather than trusting the operator to remember.

Idempotent and resumable: the gap query excludes anything already cached, so
interrupting it and re-running picks up where it stopped.

Usage:
    systemctl stop xbox-bot
    .venv/bin/python -m scripts.backfill_rarity --dry-run
    .venv/bin/python -m scripts.backfill_rarity --limit 20
    .venv/bin/python -m scripts.backfill_rarity
    systemctl start xbox-bot
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from bot.config import get_settings
from bot.constants import Platform
from bot.db.repo import Database, Repo
from bot.lock import AlreadyRunningError, single_instance
from bot.services.crypto import TokenCipher
from bot.services.xbox.auth import XboxAuthService
from bot.services.xbox.client import XboxApiError, XboxClient

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", stream=sys.stdout
)
log = logging.getLogger("backfill_rarity")

#: How often to report progress, in titles. A sixteen-minute run with no
#: output reads as a hang.
PROGRESS_EVERY = 25


async def run() -> int:
    parser = argparse.ArgumentParser(description="Backfill Xbox achievement rarity.")
    parser.add_argument("--limit", type=int, default=0, help="stop after N titles (0 = no limit)")
    parser.add_argument("--dry-run", action="store_true", help="count the work, fetch nothing")
    parser.add_argument(
        "--platform",
        choices=["all", "xbox_modern", "xbox_360"],
        default="all",
        help="which platform to backfill (default: all)",
    )
    args = parser.parse_args()

    settings = get_settings()
    database = await Database(settings.db_path).connect()
    repo = Repo(database)

    platforms = (
        [Platform.XBOX_MODERN, Platform.XBOX_360]
        if args.platform == "all"
        else [Platform(args.platform)]
    )

    all_titles: list[tuple[str, int, Platform]] = []
    for plat in platforms:
        cached, total = await repo.rarity_coverage(plat)
        titles = await repo.titles_missing_rarity(plat, args.limit or 10**6)
        log.info(
            "%s: %s of %s titles already cached, %s to fetch (one request each)",
            plat.value,
            cached,
            total,
            len(titles),
        )
        all_titles.extend((t_id, tg_id, plat) for t_id, tg_id in titles)

    if args.dry_run or not all_titles:
        await database.close()
        return 0

    cipher = TokenCipher(settings.fernet_key.get_secret_value())
    auth = XboxAuthService(settings, repo, cipher)
    await auth.start()
    client = XboxClient(auth)

    done = skipped = failed = percentages = 0
    for index, (title_id, tg_id, plat) in enumerate(all_titles, start=1):
        try:
            rarity = await client.title_rarity(tg_id, title_id)
        except XboxApiError as exc:
            # A delisted game, an owner whose token is dead, an unlucky
            # afternoon at Microsoft. One title must never end the run.
            log.info("  %s (%s): skipped (%s)", title_id, plat.value, exc)
            failed += 1
            continue
        if not rarity:
            # Asked, and there is none — a game Microsoft reports no percentages for.
            skipped += 1
            continue
        await repo.cache_rarity(plat, title_id, rarity)
        done += 1
        percentages += len(rarity)
        if index % PROGRESS_EVERY == 0:
            log.info("  %s/%s titles, %s percentages cached", index, len(all_titles), percentages)

    log.info(
        "done: %s titles cached (%s percentages), %s had none to give, %s failed",
        done,
        percentages,
        skipped,
        failed,
    )
    await auth.close()
    await database.close()
    return 0


def main() -> int:
    settings = get_settings()
    # The bot's own lock, for the reason in the module docstring: this must
    # not run beside a live bot, and asking the operating system beats
    # trusting the operator.
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
