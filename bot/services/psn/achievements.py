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
from psnawp_api.models.trophies import TrophyTitle

from bot.constants import Platform
from bot.db.repo import AchievementRow, Repo
from bot.services.models import ParsedAchievement
from bot.services.psn.client import (
    EarnedTrophy,
    PsnApiError,
    PsnPrivateProfileError,
    PsnTitleUnavailableError,
    trophies_for_title,
    trophy_groups_for_title,
    trophy_titles_for_account,
)
from bot.services.rows import to_achievement_row
from bot.services.translate.auth import AnthropicAuth
from bot.services.translate.descriptions import bilingual_descriptions
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
    # Rows from a game this bot had never looked at group-by-group before
    # (#46). Until this shipped only the base game's trophies were ever
    # fetched, so the first such pass surfaces every DLC trophy the person
    # earned — years of them, all at once. Kept apart from `new_rows` so the
    # poller can publish them under the same 24-hour cap a relink uses
    # (#52's own rule) instead of announcing a history nobody asked for.
    catch_up_rows: list[AchievementRow] = field(default_factory=list)
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
    anthropic_auth: AnthropicAuth,
    translation_client: PSNAWP | None,
    limit: int | None = TITLES_TO_SCAN,
) -> PsnSyncOutcome:
    """Scan `limit` of this account's most recently-touched games, persist
    every newly-earned trophy, and advance each game's progress cache — one
    game at a time, trophies before progress (see the module docstring for
    why the order matters).

    `limit=None` (poller/psn_fetcher.py's backfill) scans the whole account
    instead of just the recent window regular polling uses.

    `translation_client` (2026-09-09, #48) is the second, Russian-locale
    PSNAWP instance (PsnAuth.get_translation_client()) — `None` just means
    skip the bilingual fetch for this pass (poller/psn_fetcher.py's own
    best-effort wrapper), same "keep whatever single-locale text the
    primary client already returned" degrade every other platform's
    bilingual fetch uses. Unlike Xbox's own x360-backfill carve-out, this
    runs during backfill too — same shape as Steam's own version of this,
    since sync_account (unlike Xbox's separate poll_title/backfill split)
    is already the one function both paths share, and the cache makes a
    repeat backfill scan of the same game free the second time anyway.
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

        if translation_client is not None:
            await _bilingual_descriptions(
                repo, anthropic_auth, translation_client, account_id, title, earned
            )
        # The name and size of each group this game's trophy list is split
        # into (#46) — one request, once per game, then cached forever: a
        # game's own shape only changes when its publisher ships new
        # trophies.
        if not await repo.has_title_groups(title.np_communication_id):
            groups = await trophy_groups_for_title(client, account_id, title)
            if groups:
                await repo.save_title_groups(
                    title.np_communication_id,
                    [(group.group_id, group.name, group.total) for group in groups],
                )
        # Does this pass widen a game the bot only ever knew the base group
        # of? (see repo.psn_title_needs_widening) Asked before the insert,
        # because the insert is what stops it being true. Backfill publishes
        # nothing at all, so it never needs the split.
        widened = not is_backfill and await repo.psn_title_needs_widening(
            account_id, title.np_communication_id
        )
        # The denominator of the "47/50" beside a notification's game line
        # (#46). PSN never reports a count for a person, but the title list
        # this poll already walked carries how many trophies the game has —
        # the one number Xbox's title_history and Steam's cached schema
        # supply for themselves.
        # getattr, not attribute access: `title` is psnawp's own object and
        # this field is not part of any contract we control — the same
        # defensiveness services/psn/client.py already applies to its types.
        defined = getattr(title, "defined_trophies", None)
        total = (
            (defined.bronze + defined.silver + defined.gold + defined.platinum)
            if defined is not None
            else 0
        )
        if total:
            await repo.upsert_title(
                title.np_communication_id,
                title.title_name,
                Platform.PSN,
                achievements_total=total,
            )
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
        if widened:
            outcome.catch_up_rows.extend(inserted)
        else:
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
        trophy_group_id=item.trophy_group_id,
    )


async def _bilingual_descriptions(
    repo: Repo,
    anthropic_auth: AnthropicAuth,
    translation_client: PSNAWP,
    account_id: str,
    title: TrophyTitle,
    earned: list[EarnedTrophy],
) -> None:
    """Mutates each item's `.trophy_detail` in place — same shape Xbox's own
    `Fetcher._bilingual_descriptions` uses. A second, Russian-locale request
    for this one game's trophy detail text (2026-09-09, #48) — see
    services/psn/auth.py's get_translation_client for why PSN needs a whole
    second client for this, unlike Xbox/Steam's own single-client,
    different-parameter version of the same idea.

    Best-effort throughout: any failure fetching with `translation_client`
    (Sony rate-limiting the second client, a title it can't see, a
    half-dead second session) just leaves this pass's trophies with
    whatever English text the *primary* client already fetched — never
    raised as PsnApiError/PsnTokenDeadError, since a failure here says
    nothing about the primary client's own health and must not be mistaken
    for the service NPSSO itself being dead.
    """
    candidates = {item.trophy_id: item.trophy_detail for item in earned if item.trophy_detail}
    if not candidates:
        return

    to_fetch: dict[int, str] = {}
    cached: dict[int, str] = {}
    for trophy_id, english_text in candidates.items():
        row = await repo.get_cached_description(
            Platform.PSN, title.np_communication_id, str(trophy_id)
        )
        if row is not None:
            if row.description_ru is not None:
                cached[trophy_id] = row.description_ru
        else:
            to_fetch[trophy_id] = english_text
    if not to_fetch:
        _apply(earned, cached)
        return

    # A trophy missing from the response is a fact about the trophy; a
    # failed request is a fact about the client (#50). The two deserve
    # opposite answers, and conflating them is what lost descriptions:
    #
    # - a transient failure (rate limit, half-dead session) says nothing
    #   about whether Russian text exists, so skip and let a later pass get
    #   it natively rather than paying the LLM for something that will
    #   arrive free;
    # - a permanent one — Sony 404ing the title for this client — is never
    #   going to improve. Verified against production on NPWR23378_00,
    #   which 404s from *both* the US and RU clients, so it is not a
    #   regional gap either. Those trophies fall through to the LLM.
    permanently_unavailable = False
    try:
        russian_earned = await trophies_for_title(translation_client, account_id, title)
    except PsnTitleUnavailableError:
        log.info(
            "psn title %s unavailable to the translation client — translating from English",
            title.np_communication_id,
        )
        russian_earned = []
        permanently_unavailable = True
    except Exception:
        log.info(
            "psn bilingual fetch for title %s skipped", title.np_communication_id, exc_info=True
        )
        _apply(earned, cached)
        return

    russian_by_id = {item.trophy_id: item.trophy_detail for item in russian_earned}
    # A trophy present in English and absent from Russian is precisely "Sony
    # has no Russian text for this one" — the case the LLM exists for (#50).
    # It used to be filtered out here and never reached the translator at
    # all: not cached, not translated, uncached again on every future pass.
    # Handing the English text as both halves is how the shared
    # bilingual_descriptions() already spells "no native translation".
    native = {
        str(trophy_id): (russian_by_id.get(trophy_id) or english_text, english_text)
        for trophy_id, english_text in to_fetch.items()
    }
    if permanently_unavailable:
        native = {key: (english, english) for key, (_ru, english) in native.items()}
    if native:
        resolved = await bilingual_descriptions(
            repo, anthropic_auth, Platform.PSN, title.np_communication_id, native
        )
        for trophy_id in to_fetch:
            pair = resolved.get(str(trophy_id))
            if pair is not None and pair[0] is not None:
                cached[trophy_id] = pair[0]

    _apply(earned, cached)


def _apply(earned: list[EarnedTrophy], resolved: dict[int, str]) -> None:
    for item in earned:
        russian_text = resolved.get(item.trophy_id)
        if russian_text is not None:
            item.trophy_detail = russian_text
