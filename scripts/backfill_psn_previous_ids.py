"""One-time backfill: ask Sony for the previous online ID of every linked
PSN account, for renames that happened before the bot started watching (#51).

The poller notices a rename on its own from now on — the stored nickname it
replaces *is* the previous one — but it can only see changes from here
forward. An account renamed years ago looks like any other. Sony does record
it, on the legacy profile endpoint, which is addressed **by nickname**:

    GET /userProfile/v1/users/<onlineId>/profile2
        ?fields=accountId,onlineId,currentOnlineId

`currentOnlineId` appears in that response **only** for an account that has
actually been renamed; when it does, `onlineId` beside it is the original.
Verified read-only against production (2026-09-12): all four linked accounts
answer, none carries `currentOnlineId`, so none has ever been renamed and
this run stores nothing. It still exists for the accounts linked later.

One request per account, run once. Safe to re-run: an account whose previous
id is already stored is skipped, and an account with nothing to store is left
alone rather than written with a copy of its current name.

Usage (the bot may keep running — PSN has no per-request token rotation, and
this only reads):
    .venv/Scripts/python.exe -X utf8 -m scripts.backfill_psn_previous_ids
"""

from __future__ import annotations

import asyncio
import logging

from bot.config import get_settings
from bot.constants import Platform
from bot.db.repo import Database, Repo
from bot.services.crypto import TokenCipher
from bot.services.psn.auth import PsnAuth
from bot.services.psn.client import legacy_profile

logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)-7s %(message)s")
log = logging.getLogger("psn-previous-ids")

REQUEST_DELAY_SECONDS = 1.0


async def main() -> None:
    settings = get_settings()
    database = await Database(settings.db_path).connect()
    repo = Repo(database)
    cipher = TokenCipher(settings.fernet_key.get_secret_value())
    psn_auth = PsnAuth(repo, cipher)
    client = await psn_auth.get_client()

    links = await repo.platform_links_all(Platform.PSN)
    log.info("%s linked PSN accounts to check", len(links))

    renamed = skipped = unchanged = 0
    for link in links:
        if link.secondary_name:
            skipped += 1
            continue
        if not link.display_name:
            log.warning("%s: no online ID stored, nothing to ask by", link.external_id)
            unchanged += 1
            continue

        profile = await legacy_profile(client, link.display_name)
        await asyncio.sleep(REQUEST_DELAY_SECONDS)
        previous = profile.get("onlineId") if profile else None
        current = profile.get("currentOnlineId") if profile else None
        if not current or not previous or previous == current:
            log.info("%s: never renamed", link.display_name)
            unchanged += 1
            continue

        await repo.set_platform_secondary_name(link.tg_id, Platform.PSN, previous)
        # The stored nickname can be the pre-rename one too, if the account
        # was renamed after it was linked but before the poller learned to
        # notice — take Sony's word for which is current.
        await repo.update_platform_names(link.tg_id, Platform.PSN, current)
        renamed += 1
        log.info("%s: previously known as %s", current, previous)

    log.info("done: %s renamed, %s already known, %s never renamed", renamed, skipped, unchanged)
    await database.close()


if __name__ == "__main__":
    asyncio.run(main())
