"""One-time backfill: bilingual descriptions for everything unlocked before
the description cache existed (#48).

All three platform clients have been filling `achievement_description_cache`
since 2026-09-09, but only for achievements unlocked *since* — every row
already in `seen_achievements` at that point carries a single-language
snapshot and nothing else. A chat set to English therefore still sees
Russian descriptions on those, because `descriptions_view.localize_descriptions`
has nothing to swap in and falls back to the stored column.

This script closes that gap, per title, using each platform's own live path
rather than a second implementation of it:

- the unit of work is a **title**, not an achievement: every platform
  returns a whole game's achievements in one request, and a description does
  not vary by who unlocked it. On Xbox that alone is the difference between
  1918 (owner, title) pairs and 1164 distinct titles.
- both locales are fetched from the platform, then handed to
  `services/translate/descriptions.py::bilingual_descriptions` — the same
  orchestration the pollers use, so `source` is recorded truthfully
  ('native' when the platform really has two translations, 'llm' only when
  it silently returned the same text twice) and the LLM is never asked for
  something a platform already answered.

Idempotent and resumable: the gap query itself excludes anything already
cached, and `bilingual_descriptions` skips cached achievements again on its
own. Interrupt it and re-run; it picks up where it stopped.

Safe to run while the bot is live — it only ever inserts into the
description cache, never touches `seen_achievements`, and never publishes.

Usage:
    .venv/bin/python -m scripts.backfill_descriptions --dry-run
    .venv/bin/python -m scripts.backfill_descriptions --platform steam
    .venv/bin/python -m scripts.backfill_descriptions --limit 20
    .venv/bin/python -m scripts.backfill_descriptions
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field

from bot.config import get_settings
from bot.constants import Platform
from bot.db.repo import Database, Repo
from bot.services.crypto import TokenCipher
from bot.services.psn.auth import PsnAuth
from bot.services.psn.client import (
    PsnApiError,
    trophies_for_title,
    trophy_titles_for_account,
)
from bot.services.steam.auth import SteamAuth
from bot.services.steam.client import SteamApiError, get_player_achievements
from bot.services.translate.auth import AnthropicAuth
from bot.services.translate.descriptions import bilingual_descriptions
from bot.services.xbox.auth import XboxAuthService
from bot.services.xbox.client import XboxApiError, XboxClient

logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)-7s %(message)s")
# Same suppression, same reason as every other script here (M-Steam-1):
# httpx logs full request URLs at INFO and Steam's carry the key in a param.
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("backfill_descriptions")

# Pacing, per platform, between titles. Each title costs two requests.
#
# Xbox: Microsoft allows 300 requests per 5 minutes *per user token* — one
# request a second. Two requests per title on one person's token means two
# seconds is the honest steady rate, and the work is spread across owners
# anyway, so this is conservative rather than tight.
# Steam: the documented cap is 100k/day, which this could not approach.
# PSN: no published limit at all — it is a reverse-engineered API behind one
# shared credential, so this is politeness, not arithmetic.
DELAYS = {Platform.MODERN: 2.0, Platform.X360: 2.0, Platform.STEAM: 0.5, Platform.PSN: 2.0}


@dataclass(slots=True)
class TitleWork:
    """One game's worth of missing descriptions, and who can be used to ask
    for them (Xbox needs a token-bearing owner; Steam needs a SteamID64;
    PSN needs an account_id)."""

    platform: str
    title_id: str
    achievement_ids: set[str] = field(default_factory=set)
    owners: list[tuple[int, str]] = field(default_factory=list)  # (tg_id, external id)


@dataclass(slots=True)
class Totals:
    titles: int = 0
    cached: int = 0
    native: int = 0
    llm: int = 0
    skipped: int = 0
    failed: int = 0


async def gather_work(repo: Repo, platforms: set[str]) -> list[TitleWork]:
    """Everything stored, with a description, that the cache has no entry
    for — grouped by title, with every owner who could be asked."""
    grouped: dict[tuple[str, str], TitleWork] = {}
    for (
        platform,
        title_id,
        achievement_id,
        tg_id,
        external_id,
    ) in await repo.uncached_descriptions():
        if platform not in platforms:
            continue
        key = (platform, title_id)
        work = grouped.get(key)
        if work is None:
            work = grouped[key] = TitleWork(platform=platform, title_id=title_id)
        work.achievement_ids.add(achievement_id)
        owner = (tg_id, external_id)
        if owner not in work.owners:
            work.owners.append(owner)
    return sorted(grouped.values(), key=lambda w: (w.platform, w.title_id))


async def _record(
    repo: Repo,
    anthropic_auth: AnthropicAuth,
    work: TitleWork,
    native: dict[str, tuple[str | None, str | None]],
    totals: Totals,
) -> None:
    """Hand the two locales to the shared orchestration and count what it
    decided. Counting is done by re-reading the cache rather than trusting
    the return value: `bilingual_descriptions` returns text, not whether it
    had to pay for it."""
    wanted = {key: value for key, value in native.items() if key in work.achievement_ids}
    if not wanted:
        totals.skipped += 1
        log.info("  %s/%s: platform returned nothing we need", work.platform, work.title_id)
        return
    await bilingual_descriptions(repo, anthropic_auth, work.platform, work.title_id, wanted)
    for achievement_id in wanted:
        cached = await repo.get_cached_description(work.platform, work.title_id, achievement_id)
        if cached is None:
            continue
        totals.cached += 1
        if cached.source == "llm":
            totals.llm += 1
        else:
            totals.native += 1


async def run_xbox(
    repo: Repo,
    anthropic_auth: AnthropicAuth,
    client: XboxClient,
    work: TitleWork,
    totals: Totals,
) -> None:
    """Any owner will do — the description is the game's, not the person's.
    A dead or unlucky token just means trying the next owner rather than
    giving up on the title."""
    platform = Platform.X360 if work.platform == Platform.X360 else Platform.MODERN
    for tg_id, _external in work.owners:
        try:
            russian = await client.title_achievements(
                tg_id, work.title_id, platform, language="ru-RU"
            )
            english = await client.title_achievements(
                tg_id, work.title_id, platform, language="en-US"
            )
        except XboxApiError as exc:
            log.warning("  %s: owner %s failed (%s), trying the next", work.title_id, tg_id, exc)
            continue
        english_by_id = {item.achievement_id: item.description for item in english}
        native = {
            item.achievement_id: (item.description, english_by_id.get(item.achievement_id))
            for item in russian
            if item.description
        }
        await _record(repo, anthropic_auth, work, native, totals)
        return
    totals.failed += 1
    log.warning("  %s/%s: every owner failed", work.platform, work.title_id)


async def run_steam(
    repo: Repo, anthropic_auth: AnthropicAuth, api_key: str, work: TitleWork, totals: Totals
) -> None:
    for _tg_id, steam_id in work.owners:
        try:
            russian = await get_player_achievements(
                api_key, steam_id, work.title_id, language="russian"
            )
            english = await get_player_achievements(
                api_key, steam_id, work.title_id, language="english"
            )
        except SteamApiError as exc:
            log.warning("  %s: owner %s failed (%s)", work.title_id, steam_id, exc)
            continue
        english_by_id = {item.apiname: item.description for item in english}
        native = {
            item.apiname: (item.description, english_by_id.get(item.apiname))
            for item in russian
            if item.description
        }
        await _record(repo, anthropic_auth, work, native, totals)
        return
    totals.failed += 1
    log.warning("  %s/%s: every owner failed", work.platform, work.title_id)


async def run_psn(
    repo: Repo,
    anthropic_auth: AnthropicAuth,
    psn_auth: PsnAuth,
    work: TitleWork,
    titles_by_account: dict[str, dict],
    totals: Totals,
) -> None:
    """PSN needs the `TrophyTitle` object itself, not just an id — the
    account's title list is fetched once per account by the caller and
    passed in here."""
    primary = await psn_auth.get_client()
    translation = await psn_auth.get_translation_client()
    for _tg_id, account_id in work.owners:
        title = (titles_by_account.get(account_id) or {}).get(work.title_id)
        if title is None:
            continue
        try:
            english = await trophies_for_title(primary, account_id, title)
            russian = await trophies_for_title(translation, account_id, title)
        except PsnApiError as exc:
            log.warning("  %s: account %s failed (%s)", work.title_id, account_id, exc)
            continue
        russian_by_id = {str(t.trophy_id): t.trophy_detail for t in russian}
        native = {
            str(item.trophy_id): (russian_by_id.get(str(item.trophy_id)), item.trophy_detail)
            for item in english
            if item.trophy_detail
        }
        await _record(repo, anthropic_auth, work, native, totals)
        return
    totals.failed += 1
    log.warning("  %s/%s: no account could supply this title", work.platform, work.title_id)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--platform",
        choices=["all", "xbox", "modern", "x360", "steam", "psn"],
        default="all",
    )
    parser.add_argument("--limit", type=int, default=0, help="stop after N titles (0 = no limit)")
    parser.add_argument("--dry-run", action="store_true", help="count the work, fetch nothing")
    args = parser.parse_args()

    wanted = {
        "all": {Platform.MODERN, Platform.X360, Platform.STEAM, Platform.PSN},
        "xbox": {Platform.MODERN, Platform.X360},
        "modern": {Platform.MODERN},
        "x360": {Platform.X360},
        "steam": {Platform.STEAM},
        "psn": {Platform.PSN},
    }[args.platform]

    settings = get_settings()
    database = await Database(settings.db_path).connect()
    repo = Repo(database)
    cipher = TokenCipher(settings.fernet_key.get_secret_value())

    work_items = await gather_work(repo, wanted)
    if args.limit:
        work_items = work_items[: args.limit]

    by_platform: dict[str, int] = defaultdict(int)
    for item in work_items:
        by_platform[item.platform] += len(item.achievement_ids)
    log.info(
        "%s titles, %s achievements: %s",
        len(work_items),
        sum(by_platform.values()),
        ", ".join(f"{name} {count}" for name, count in sorted(by_platform.items())),
    )
    log.info(
        "estimated platform requests: %s (two per title)",
        len(work_items) * 2,
    )
    if args.dry_run:
        await database.close()
        return

    anthropic_auth = AnthropicAuth(
        repo,
        cipher,
        env_key=(
            settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None
        ),
    )
    xbox_auth = XboxAuthService(settings, repo, cipher)
    await xbox_auth.start()
    xbox_client = XboxClient(xbox_auth)
    steam_auth = SteamAuth(
        repo,
        cipher,
        env_key=(settings.steam_api_key.get_secret_value() if settings.steam_api_key else None),
    )
    psn_auth = PsnAuth(repo, cipher)

    # PSN's per-title fetch needs the TrophyTitle object, so each account's
    # list is pulled once up front rather than per title.
    titles_by_account: dict[str, dict] = {}
    if any(item.platform == Platform.PSN for item in work_items):
        client = await psn_auth.get_client()
        accounts = {
            account
            for item in work_items
            for _tg, account in item.owners
            if item.platform == Platform.PSN
        }
        for account_id in accounts:
            try:
                titles = await trophy_titles_for_account(client, account_id, limit=None)
            except PsnApiError as exc:
                log.warning("PSN: could not list titles for %s (%s)", account_id, exc)
                continue
            titles_by_account[account_id] = {t.np_communication_id: t for t in titles}
            log.info("PSN: %s has %s trophy titles", account_id, len(titles_by_account[account_id]))

    totals = Totals()
    steam_key: str | None = None
    for index, item in enumerate(work_items, start=1):
        totals.titles += 1
        log.info(
            "[%s/%s] %s %s (%s achievements)",
            index,
            len(work_items),
            item.platform,
            item.title_id,
            len(item.achievement_ids),
        )
        try:
            if item.platform in (Platform.MODERN, Platform.X360):
                await run_xbox(repo, anthropic_auth, xbox_client, item, totals)
            elif item.platform == Platform.STEAM:
                if steam_key is None:
                    steam_key = await steam_auth.get_key()
                if not steam_key:
                    log.error("no Steam key configured — skipping every Steam title")
                    break
                await run_steam(repo, anthropic_auth, steam_key, item, totals)
            elif item.platform == Platform.PSN:
                await run_psn(repo, anthropic_auth, psn_auth, item, titles_by_account, totals)
        except Exception:
            # One bad title must never end the run — same rule every poller
            # in this project follows.
            totals.failed += 1
            log.exception("  %s/%s failed", item.platform, item.title_id)

        await asyncio.sleep(DELAYS.get(item.platform, 1.0))

    log.info(
        "done: %s titles, %s descriptions cached (%s native, %s from the LLM), "
        "%s titles skipped, %s failed",
        totals.titles,
        totals.cached,
        totals.native,
        totals.llm,
        totals.skipped,
        totals.failed,
    )
    await database.close()


if __name__ == "__main__":
    asyncio.run(main())
