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

    Returns how many of that title's descriptions ended up cached. Raises
    XboxApiError if this owner's token could not answer — the caller decides
    whether to try another owner or leave the title for next time.
    """
    xbox_platform = Platform.XBOX_360 if platform == Platform.XBOX_360 else Platform.XBOX_MODERN
    russian = await client.title_achievements(tg_id, title_id, xbox_platform, language="ru-RU")
    english = await client.title_achievements(tg_id, title_id, xbox_platform, language="en-US")

    english_by_id = {item.achievement_id: item.description for item in english}
    native = {
        item.achievement_id: (item.description, english_by_id.get(item.achievement_id))
        for item in russian
        if item.description
    }
    if not native:
        return 0
    await bilingual_descriptions(repo, anthropic_auth, platform, title_id, native)
    return len(native)


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
