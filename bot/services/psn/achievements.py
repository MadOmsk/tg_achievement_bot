"""PSN trophies: fetch + progress cache, composing over services/psn/client.py
(SPEC 9, M-PSN-2). Mirrors services/steam/achievements.py's role — a
cache-backed service layer sitting above a stateless client — but the cache
here answers a different question: Steam's caches are about the *game*
(schema/rarity never change per person), PSN's is about *this account's
progress* in the game, because trophy sync has no presence signal to key
off (M-PSN-2's own "ключевое отличие" paragraph) — the only cheap way to
know whether a recently-touched game is worth a full trophy-detail call
this tick is to compare its progress% against what was there last time.

Errors from the client (PsnApiError and friends) are not caught here on
purpose — same "log it and skip this tick" handling belongs to the poller
that calls this (poller/psn_fetcher.py), not to this layer.
"""

from __future__ import annotations

from psnawp_api import PSNAWP

from bot.db.repo import Repo
from bot.services.models import ParsedAchievement
from bot.services.psn.client import (
    EarnedTrophy,
    PsnPrivateProfileError,
    trophies_for_title,
    trophy_titles_for_account,
)
from bot.util import parse_iso

# How many of an account's most-recently-touched games to look at each poll
# — same bound the admin test screen uses (services/psn/client.py's own
# _RECENT_TITLES_TO_SCAN), for the same reason: trophy_titles() has no
# "only what changed" filter of its own, so this is the practical ceiling
# on how far back "recent" reaches before a real event (opening the trophy
# menu) would have surfaced it anyway.
TITLES_TO_SCAN = 10


async def fetch_unlocked(
    repo: Repo, client: PSNAWP, account_id: str, *, limit: int | None = TITLES_TO_SCAN
) -> list[ParsedAchievement]:
    """Every newly-earned trophy across `limit` of this account's most
    recently-touched games. Writing to seen_achievements and resolving
    tg_id are the poller's job (SPEC 9, M-PSN-2) — this only ever reads the
    PSN API and this module's own progress cache.

    `limit=None` (poller/psn_fetcher.py's own backfill) scans the whole
    account instead of just the recent window regular polling uses —
    a fresh account has no psn_title_progress row for anything yet, so
    every title's `previous is None` and nothing here is skipped either
    way; only the *how far back trophy_titles() even looks* changes.
    """
    titles = await trophy_titles_for_account(client, account_id, limit=limit)

    result: list[ParsedAchievement] = []
    for title in titles:
        progress = title.progress or 0
        previous = await repo.get_psn_title_progress(account_id, title.np_communication_id)
        # Always store the latest progress, whether or not it grew — a game
        # sitting flat between polls must not get re-checked at full cost
        # every single tick just because it once had activity (SPEC 9,
        # M-PSN-2).
        await repo.set_psn_title_progress(account_id, title.np_communication_id, progress)
        if previous is not None and progress <= previous:
            continue

        try:
            earned = await trophies_for_title(client, account_id, title)
        except PsnPrivateProfileError:
            continue  # this one game's detail is hidden — skip it, not the whole account

        result.extend(_to_parsed(title.np_communication_id, item) for item in earned)
    return result


def _to_parsed(np_communication_id: str, item: EarnedTrophy) -> ParsedAchievement:
    return ParsedAchievement(
        achievement_id=str(item.trophy_id),
        title_id=np_communication_id,
        title_name=item.title_name,
        name=item.trophy_name,
        description=item.trophy_detail,
        icon_url=item.trophy_icon_url,
        unlocked_at=parse_iso(item.earned_date_time) if item.earned_date_time else None,
        gamerscore=0,  # PSN has no gamerscore — a trophy has no per-item score at all
        rarity_percent=item.trophy_earn_rate,
        platform="psn",
        is_secret=item.trophy_hidden,
        trophy_type=item.trophy_type.value if item.trophy_type else None,
    )
