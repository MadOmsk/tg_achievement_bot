"""Fetching one Xbox title's descriptions in both locales (#48).

Shared deliberately: the one-time script (scripts/backfill_descriptions.py)
and the self-healing poller (poller/description_backfill.py) do the same
thing at different paces, and a second copy of "ask for ru, ask for en, hand
both to bilingual_descriptions" is exactly the kind of duplication that
drifts apart the first time one of them is fixed.

Xbox only, because Xbox is the only platform whose *backfill* misses this.
Steam and PSN both route their first-time history through the same function
their pollers use (`fetch_unlocked` / `sync_account`), so a freshly linked
account there is bilingual from the start. Xbox's backfill deliberately uses
the one broad contract-2 call for the whole library — one request instead of
one per title, which is the entire point of it — and that endpoint takes no
language at all. So every new Xbox account arrives with a fully uncached
history, and something has to come along afterwards and fill it in.
"""

from __future__ import annotations

import logging

from bot.constants import Platform
from bot.db.repo import Repo
from bot.services.translate.auth import AnthropicAuth
from bot.services.translate.descriptions import bilingual_descriptions
from bot.services.xbox.client import XboxApiError, XboxClient

log = logging.getLogger(__name__)


async def fill_xbox_title(
    repo: Repo,
    anthropic_auth: AnthropicAuth,
    client: XboxClient,
    *,
    tg_id: int,
    title_id: str,
    platform: str,
) -> int:
    """Cache both locales for one title, asking on `tg_id`'s behalf.

    Returns how many descriptions this call **newly** cached — measured
    against the cache, not counted from what the platform returned. Those two
    numbers are not the same, and believing they were is what made the poller
    spin (found live on the test bot, 2026-09-13): Xbox 360 answers both
    locale requests with the same English text, which means "no native
    translation", so those achievements go to the LLM instead — and with no
    Anthropic key configured `bilingual_descriptions` deliberately leaves them
    *uncached*, so a later attempt can still do better than a bad cache entry.
    Reporting them as cached anyway told the poller the title was done while
    the selection query still found it, and the same ten titles were re-fetched
    every single minute, two Xbox requests each, forever.

    Raises XboxApiError if this owner's token could not answer — the caller
    decides whether to try another owner or leave the title for next time.
    """
    xbox_platform = Platform.XBOX_360 if platform == Platform.XBOX_360 else Platform.XBOX_MODERN
    russian = await client.title_achievements(tg_id, title_id, xbox_platform, language="ru-RU")
    english = await client.title_achievements(tg_id, title_id, xbox_platform, language="en-US")

    # Names and the game's own title ride along (#61) — this job walks every
    # title a few per tick, which makes it the one thing that reaches a game
    # nobody plays any more. Without this the localized name would only ever
    # arrive for games somebody is still unlocking things in.
    english_names = {item.achievement_id: item.name for item in english}
    await repo.cache_names(
        platform,
        title_id,
        {
            item.achievement_id: (item.name, english_names.get(item.achievement_id))
            for item in russian
        },
    )
    await repo.set_title_names(
        title_id,
        next((item.title_name for item in russian if item.title_name), None),
        next((item.title_name for item in english if item.title_name), None),
    )

    english_by_id = {item.achievement_id: item.description for item in english}
    native = {
        item.achievement_id: (item.description, english_by_id.get(item.achievement_id))
        for item in russian
        if item.description
    }
    if not native:
        return 0
    keys = [(platform, title_id, achievement_id) for achievement_id in native]
    before = len(await repo.cached_descriptions(keys))
    await bilingual_descriptions(repo, anthropic_auth, platform, title_id, native)
    return len(await repo.cached_descriptions(keys)) - before


async def fill_xbox_title_any_owner(
    repo: Repo,
    anthropic_auth: AnthropicAuth,
    client: XboxClient,
    *,
    owners: list[int],
    title_id: str,
    platform: str,
) -> int | None:
    """`fill_xbox_title` with a fallback across owners — a description is the
    game's, not the person's, so any owner will do and a dead token is a
    reason to ask someone else rather than to give up on the title.

    Returns None when every owner failed, so the caller can tell "nothing to
    cache" (0) apart from "could not ask" (None).
    """
    for tg_id in owners:
        try:
            return await fill_xbox_title(
                repo, anthropic_auth, client, tg_id=tg_id, title_id=title_id, platform=platform
            )
        except XboxApiError as exc:
            log.info("title %s: owner %s could not answer (%s)", title_id, tg_id, exc)
    return None
