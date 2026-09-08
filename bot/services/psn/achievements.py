"""PSN trophies: fetch, persist, and progress cache — composing over
services/psn/client.py (SPEC 9, M-PSN-2).

Unlike services/steam/achievements.py, this module now *writes* as it goes
(#26): every game's trophies are inserted into `seen_achievements` and its
`psn_title_progress` row advanced **in that order, one game at a time**,
rather than collecting the whole scan into one list handed back to the
poller only at the very end. The old shape had a silent-corruption bug —
`psn_title_progress` was stamped for a game *before* its trophy detail was
even fetched, so any exception partway through the scan left already-visited
games marked "seen, nothing new" while their trophies were never persisted
anywhere, hiding them from every future poll and backfill. Now "progress
advanced" and "trophies stored" happen together, per game, so an
interruption can only ever cost one redundant re-fetch next run
(`INSERT OR IGNORE`), never a dropped trophy.

Resolving `tg_id` and publishing stay the poller's job (poller/
psn_fetcher.py) — sync_account returns the freshly-inserted rows for it to
publish.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from psnawp_api import PSNAWP

from bot.constants import Platform
from bot.db.repo import AchievementRow, Repo
from bot.services.models import ParsedAchievement
from bot.services.psn.client import (
    EarnedTrophy,
    PsnApiError,
    PsnPrivateProfileError,
    PsnTitleUnavailableError,
    trophies_for_title,
    trophy_titles_for_account,
)
from bot.services.rows import to_achievement_row
from bot.util import parse_iso

log = logging.getLogger(__name__)

# How many of an account's most-recently-touched games to look at each poll
# — same bound the admin test screen uses (services/psn/client.py's own
# _RECENT_TITLES_TO_SCAN), for the same reason: trophy_titles() has no
# "only what changed" filter of its own, so this is the practical ceiling
# on how far back "recent" reaches before a real event (opening the trophy
# menu) would have surfaced it anyway.
TITLES_TO_SCAN = 10


@dataclass(slots=True)
class PsnSyncOutcome:
    """What one sync_account() pass did — the poller publishes `new_rows`,
    folds `private_title_ids` into the backfill notice (#28), and logs
    `unmapped_errors` at the account level."""

    new_rows: list[AchievementRow] = field(default_factory=list)
    scanned: int = 0
    # Games whose trophy detail is hidden by that game's own privacy setting
    # (PsnPrivateProfileError) — the account as a whole passed the connect-
    # time visibility check, but a specific title is still closed (#28).
    private_title_ids: list[str] = field(default_factory=list)
    # Games skipped this pass because their detail fetch raised something
    # unexpected (not a mapped PsnApiError). Their progress is left untouched
    # so they are retried next pass, once their data can actually be saved.
    unmapped_errors: int = 0


async def sync_account(
    repo: Repo,
    client: PSNAWP,
    tg_id: int,
    account_id: str,
    *,
    is_backfill: bool,
    limit: int | None = TITLES_TO_SCAN,
) -> PsnSyncOutcome:
    """Scan `limit` of this account's most recently-touched games, persist
    every newly-earned trophy, and advance each game's progress cache — one
    game at a time, trophies before progress (see the module docstring for
    why the order matters).

    `limit=None` (poller/psn_fetcher.py's backfill) scans the whole account
    instead of just the recent window regular polling uses.
    """
    titles = await trophy_titles_for_account(client, account_id, limit=limit)
    outcome = PsnSyncOutcome(scanned=len(titles))

    for title in titles:
        progress = title.progress or 0
        previous = await repo.get_psn_title_progress(account_id, title.np_communication_id)
        if previous is not None and progress <= previous:
            # Flat since the last look — not worth a full trophy-detail call.
            # The stored progress already equals this, so nothing to write.
            continue

        try:
            earned = await trophies_for_title(client, account_id, title)
        except PsnPrivateProfileError:
            # This one game's detail is hidden. Record it (#28) and still
            # advance progress so the failing call isn't repeated every
            # tick — parity with the pre-#26 behaviour, which stamped
            # progress before the fetch even ran.
            outcome.private_title_ids.append(title.np_communication_id)
            await repo.set_psn_title_progress(account_id, title.np_communication_id, progress)
            continue
        except PsnTitleUnavailableError:
            # Sony 404s this one game's own data — not our bug, not a
            # privacy setting. Skip it, advance progress (same as above).
            await repo.set_psn_title_progress(account_id, title.np_communication_id, progress)
            continue
        except PsnApiError:
            # A dead service token, a hard rate-limit, a generic API
            # failure — an account-level problem, not this one game's. Let
            # it propagate so poll_account / backfill handle it the way they
            # always have (skip the account this pass / fail the backfill,
            # leaving backfill_done off). Progress for the games already
            # done this pass is safely committed.
            raise
        except Exception:
            # Truly unexpected — an unmapped psnawp error, a network blip
            # surfacing raw, a library bug — on ONE game. Isolate it (#26;
            # the #24 "one bad title kills the whole backfill" class,
            # generalised) instead of aborting the scan. Progress is left
            # untouched so the game is retried next pass.
            log.warning(
                "psn sync: unexpected error on title %s (account %s) — skipped, will retry",
                title.np_communication_id,
                account_id,
                exc_info=True,
            )
            outcome.unmapped_errors += 1
            continue

        rows = [to_achievement_row(_to_parsed(title.np_communication_id, item)) for item in earned]
        inserted = await repo.insert_new_achievements_psn(
            tg_id, account_id, rows, is_backfill=is_backfill
        )
        # Only now — after this game's trophies are committed — is its
        # progress advanced. An interruption before this line leaves the
        # game looking "new" next pass: the re-insert is a no-op
        # (INSERT OR IGNORE), so the cost is one redundant fetch, never a
        # silently dropped trophy (#26).
        await repo.set_psn_title_progress(account_id, title.np_communication_id, progress)
        outcome.new_rows.extend(inserted)

    return outcome


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
        platform=Platform.PSN,
        is_secret=item.trophy_hidden,
        trophy_type=item.trophy_type.value if item.trophy_type else None,
    )
