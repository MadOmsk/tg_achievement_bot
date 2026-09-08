"""One-time reconciliation: cache each PSN account's trophy level for every
already-linked account (#23).

Why this is needed: `psn_trophy_level` is only cached by
`poller/psn_fetcher.py::_refresh_level` in two places — right after
`backfill()`, and after a poll tick that finds *new* trophies. An account
linked before that caching existed already had its backfill run under the
old code (no level cached at all), and won't get one until it earns an
actual new trophy — until then `/stats` simply omits the "· уровень N" line
for it (the line only renders when `psn_trophy_level is not None`). This
script closes that one-time gap for what is already linked, mirroring
scripts/backfill_steam_titles.py's own role for Steam's own reconciliation
gap.

Safe to run any time, including while the bot is live: it only ever calls
account_trophy_level() (read-only) and set_psn_trophy_level() (an UPDATE
keyed on tg_id, independent of anything the poller is doing concurrently).

Usage:
    .venv/Scripts/python.exe -X utf8 -m scripts.backfill_psn_levels
"""

from __future__ import annotations

import asyncio
import logging

from bot.config import get_settings
from bot.db.repo import Database, Repo
from bot.services.crypto import TokenCipher
from bot.services.psn.auth import PsnAuth, PsnNotConfiguredError
from bot.services.psn.client import PsnApiError, account_trophy_level

logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)-7s %(message)s")
log = logging.getLogger("backfill_psn_levels")


async def main() -> None:
    settings = get_settings()
    database = await Database(settings.db_path).connect()
    repo = Repo(database)
    cipher = TokenCipher(settings.fernet_key.get_secret_value())
    auth = PsnAuth(repo, cipher)

    try:
        client = await auth.get_client()
    except PsnNotConfiguredError:
        log.info("PSN is not configured, nothing to do")
        await database.close()
        return

    links = await repo.platform_links_all("psn")
    log.info("checking trophy level for %s linked PSN accounts", len(links))

    updated = 0
    for link in links:
        name = link.display_name or f"tg_id={link.tg_id}"
        if link.psn_trophy_level is not None:
            log.info("%s: already has a level (%s), skipping", name, link.psn_trophy_level)
            continue
        try:
            level = await account_trophy_level(client, link.external_id)
        except PsnApiError as exc:
            log.warning("%s: skipped, %s", name, exc)
            continue
        await repo.set_psn_trophy_level(link.tg_id, level)
        log.info("%s: level %s", name, level)
        updated += 1

    log.info("done: cached a level for %s account(s) that had none", updated)
    await database.close()


if __name__ == "__main__":
    asyncio.run(main())
