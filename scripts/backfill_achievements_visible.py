"""One-time reconciliation: fill in `achievements_visible` for every
Steam/PSN account linked before that column actually meant anything in
production (#5, achievements_visible, migration 028).

Why this is needed: the column is only ever *set* at connect time or by a
backfill/admin resync (`SteamFetcher`/`PsnFetcher`) — nothing re-checks it on
a plain poller tick. Migration 028's own comment assumed "the next backfill
or resync" would naturally fill it in for accounts that already existed when
it shipped, but backfill only ever runs once per account (gated by its own
"done" flag) and nothing schedules an automatic resync — so every account
linked before the feature actually reached production stays stuck at `NULL`
("видимость неизвестна" in /panel and the admin card) forever, unless an
admin happens to click "🔄 Обновить" by hand (found live 2026-09-09: 5 of 6
platform_links rows in production were still NULL).

This script is exactly that manual resync, automated for every affected
account in one pass — it calls the same `SteamFetcher.refresh_user()` /
`PsnFetcher.refresh_user()` the admin panel's own button already uses, not a
separate reimplementation of the visibility check. That also means it can
publish a genuinely-new achievement if one was earned since the account's
last poll (refresh_user's own poll_title/poll_account branch) — the same
side effect the admin button already has, not something to route around.

Safe to run any time, including while the bot is live: only touches accounts
whose `achievements_visible` is still NULL, and refresh_user() is already
the admin panel's own on-demand action.

Usage:
    .venv/Scripts/python.exe -X utf8 -m scripts.backfill_achievements_visible
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties

from bot.config import get_settings
from bot.db.repo import Database, PlatformLink, Repo
from bot.poller.psn_fetcher import PsnFetcher
from bot.poller.publisher import Publisher
from bot.poller.steam_fetcher import SteamFetcher
from bot.services.crypto import TokenCipher
from bot.services.psn.auth import PsnAuth
from bot.services.steam.auth import SteamAuth

logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)-7s %(message)s")
# Same suppression as scripts/backfill_steam_titles.py, same reason (M-Steam-1):
# httpx logs full request URLs at INFO, and Steam's own calls carry the API
# key in a plain query param.
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("backfill_achievements_visible")


async def _process(
    links: list[PlatformLink], label: str, refresh: Callable[[int, str, str], Awaitable[str]]
) -> None:
    pending = [link for link in links if link.achievements_visible is None]
    log.info(
        "%s: %s of %s linked accounts need a visibility check", label, len(pending), len(links)
    )
    for link in pending:
        name = link.display_name or link.external_id
        try:
            summary = await refresh(link.tg_id, link.external_id, name)
        except Exception:
            log.exception("%s: refresh failed for tg_id=%s (%s)", label, link.tg_id, name)
            continue
        log.info("%s: tg_id=%s (%s) -> %s", label, link.tg_id, name, summary)


async def main() -> None:
    settings = get_settings()
    database = await Database(settings.db_path).connect()
    repo = Repo(database)
    cipher = TokenCipher(settings.fernet_key.get_secret_value())

    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(link_preview_is_disabled=True),
    )
    publisher = Publisher(bot, repo)
    # So a genuinely-new trophy found below actually gets sent, not just queued.
    await publisher.start()

    psn_auth = PsnAuth(repo, cipher)
    steam_env_key = settings.steam_api_key.get_secret_value() if settings.steam_api_key else None
    steam_auth = SteamAuth(repo, cipher, env_key=steam_env_key)
    psn_fetcher = PsnFetcher(settings, repo, psn_auth, publisher)
    steam_fetcher = SteamFetcher(repo, steam_auth, publisher, settings.backfill_concurrency)

    await _process(await repo.platform_links_all("steam"), "steam", steam_fetcher.refresh_user)
    await _process(await repo.platform_links_all("psn"), "psn", psn_fetcher.refresh_user)

    await publisher._queue.join()  # let anything just enqueued above actually go out
    await publisher.stop()
    await bot.session.close()
    await database.close()
    log.info("done")


if __name__ == "__main__":
    asyncio.run(main())
