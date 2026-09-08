"""One-time reconciliation: cache a Steam game's name into `titles` for
every already-linked account (SPEC 9, follow-up 2026-09-05).

Why this is needed: `insert_new_achievements_steam()` only started caching a
game's name into `titles` on 2026-09-05 (db/repo.py) — Xbox's own fetcher had
done this from the start (`ensure_title_name`), Steam never had an
equivalent. Every Steam achievement stored before that fix has a title_id
with no matching `titles` row, so `/recent` and `/stats`' games table show
"без названия" for them, even after the JOIN-key bug itself (chat_recent()
was keyed on xuid, not tg_id) was fixed the same day. This script closes the
gap for what is already in the database — same reasoning and same pattern as
scripts/reconcile_achievements.py's own gap-closing for Xbox.

Uses GetOwnedGames (the official Web API, same call steam_fetcher.py's own
backfill() already makes), not the Store API — the Store API needs a
cc=US/cc=RU dance to avoid dropping games blocked in the Russian store
(TODO.md's own note on this, from the /hltb description research) and this
already-used endpoint has no such problem.

Safe to run any time, including while the bot is live: `upsert_title` is an
idempotent UPSERT keyed on title_id, and nothing here touches
seen_achievements at all.

Usage:
    .venv/Scripts/python.exe -X utf8 -m scripts.backfill_steam_titles
"""

from __future__ import annotations

import asyncio
import logging

from bot.config import get_settings
from bot.db.repo import Database, Repo
from bot.services.crypto import TokenCipher
from bot.services.steam.auth import SteamAuth, SteamNotConfiguredError
from bot.services.steam.client import SteamApiError, get_owned_games

logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)-7s %(message)s")
# httpx logs "HTTP Request: GET <full url> ..." at INFO for every call, and
# GetOwnedGames' own URL carries the Steam API key as a plain query param —
# found live running this script for real: the key printed straight to the
# terminal. main.py already does this same suppression for the exact same
# reason (M-Steam-1); this script needs it independently, its own
# basicConfig is a separate logging setup that doesn't inherit main.py's.
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("backfill_steam_titles")


async def main() -> None:
    settings = get_settings()
    database = await Database(settings.db_path).connect()
    repo = Repo(database)

    # Follow the same key SteamFetcher/service_health actually use (#17) —
    # the key can now live only in app_settings, set/changed/cleared from
    # the admin panel with no .env edit, so reading settings.steam_api_key
    # directly here (the old shape) could silently use a stale or absent
    # key once an admin manages it only through the panel.
    cipher = TokenCipher(settings.fernet_key.get_secret_value())
    steam_env_key = settings.steam_api_key.get_secret_value() if settings.steam_api_key else None
    steam_auth = SteamAuth(repo, cipher, env_key=steam_env_key)
    try:
        api_key = await steam_auth.require_key()
    except SteamNotConfiguredError:
        log.info("Steam is not configured, nothing to do")
        await database.close()
        return

    links = await repo.platform_links_all("steam")
    log.info("checking titles for %s linked Steam accounts", len(links))

    cached = 0
    for link in links:
        name = link.display_name or f"tg_id={link.tg_id}"
        try:
            games = await get_owned_games(api_key, link.external_id)
        except SteamApiError as exc:
            log.warning("%s: skipped, %s", name, exc)
            continue
        for game in games:
            await repo.upsert_title(game.appid, game.name, "steam")
        log.info("%s: checked %s owned games", name, len(games))
        cached += len(games)

    log.info("done: upserted up to %s title rows (existing ones just refreshed)", cached)
    await database.close()


if __name__ == "__main__":
    asyncio.run(main())
