"""PSN client (SPEC 9, M-PSN-1) — thin async wrapper over `psnawp_api`.

Unlike services/steam/client.py, PSN has no documented public API at all:
`psnawp_api` is a reverse-engineered wrapper over the same private endpoints
the PlayStation App itself uses — the same class of dependency as
xbox-webapi-python is for Xbox, not a "тащить лишнюю зависимость" call
(CLAUDE.md): reimplementing PSN's auth exchange and GraphQL search ourselves
would buy nothing.

`psnawp_api` is also fully synchronous (built on `requests`), so every call
in this module goes through `asyncio.to_thread` — nothing here may block the
event loop (CLAUDE.md: "Всё async. Никаких блокирующих вызовов в event loop").

One service-wide client, not per-user OAuth (services/psn/auth.py owns the
single NPSSO-derived instance) — the whole design bet behind this file was
verified live against real accounts, 2026-09-05/06 (SPEC 9, M-PSN-1
checklist item 1): one account's token reads another (non-friend) public
profile's trophies with no PSNAWPForbiddenError.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass

from psnawp_api import PSNAWP
from psnawp_api.core.psnawp_exceptions import (
    PSNAWPAuthenticationError,
    PSNAWPForbiddenError,
    PSNAWPNotFoundError,
)
from psnawp_api.models.trophies import TrophyTitle
from psnawp_api.models.trophies.trophy_constants import PlatformType, TrophyRarity, TrophyType

from bot.constants import PresenceState
from bot.services.rate_limiter import RateLimiter

log = logging.getLogger(__name__)

# Real limits are undocumented anywhere (SPEC 9, M-PSN-1 checklist item 4) —
# this window only guards against a runaway bug, same reasoning as Steam's
# own hardcoded cap (services/steam/client.py). The admin panel shows the
# raw count below, never a "used/limit" ratio — a ratio would imply a limit
# we don't actually know.
RATE_WINDOWS: tuple[tuple[int, float], ...] = ((20_000, 86400.0),)
_limiter = RateLimiter(RATE_WINDOWS)


def request_count_today() -> int:
    """The admin panel's PSN counterpart of Steam's rate_limit_usage() —
    just a count, no denominator (see RATE_WINDOWS above for why)."""
    return _limiter.usage()[0][0]


class PsnApiError(Exception):
    """Expected failure — unresolvable Online ID, a request that couldn't
    complete. Same "log it, tell the user, never crash" treatment as
    SteamApiError/XboxApiError."""


class PsnTokenDeadError(PsnApiError):
    """The service NPSSO/refresh token no longer works — the admin needs to
    paste a fresh NPSSO (SPEC 9, M-PSN-1's active health-check paragraph)."""


class PsnPrivateProfileError(PsnApiError):
    """Resolved fine, but trophies are not visible to the service account —
    PSN's own privacy setting (checklist item 3). Distinct from "not found"
    so the person gets an actionable message, same split Steam already has
    (get_profile's is_public)."""


class PsnTitleUnavailableError(PsnApiError):
    """This one game's trophy detail 404s on Sony's own side — not a
    privacy setting. Found live 2026-09-06: a real account's backfill hit
    `PSNAWPNotFoundError: Resource not found (trophyGroupId='default')` for
    one specific title and, uncaught, took down the *entire* backfill —
    every retry hit the same game and failed identically, so the account
    could never finish linking. Callers skip just this one game, the same
    "isolate the one bad title, not the whole account" treatment
    PsnPrivateProfileError already gets."""


class PsnClientSetupError(PsnApiError):
    """Something failed while constructing the PSNAWP client object itself
    — before we even got to whether the NPSSO is any good. Almost always
    the environment, not the admin's input (found live 2026-09-06: psnawp
    needs a writable temp dir for its own rate-limiter bucket, which a
    hardened systemd unit — ProtectSystem=strict with no PrivateTmp — was
    silently denying it). Kept distinct from PsnTokenDeadError so an admin
    isn't sent chasing a "bad NPSSO" that was never the actual problem."""


@dataclass(slots=True)
class PsnProfile:
    account_id: str
    online_id: str


@dataclass(slots=True)
class EarnedTrophy:
    """One trophy this account has actually earned — used by the admin
    panel's live "Трофеи PSN" test screen (display only) and by
    services/psn/achievements.py's sync_account (SPEC 9, M-PSN-2), which
    needs `trophy_id` specifically: it's the real per-title identifier
    (`trophy_name` is not guaranteed unique and is shown, never keyed on)."""

    trophy_id: int
    title_name: str
    title_icon_url: str | None
    trophy_name: str
    trophy_detail: str | None
    trophy_icon_url: str | None
    trophy_type: TrophyType
    trophy_hidden: bool
    trophy_rarity: TrophyRarity | None
    trophy_earn_rate: float | None
    earned_date_time: str | None
    # Which group of the title's trophy list this belongs to — 'default' for
    # the base game, '001'... per DLC (#46). psnawp reports it on the trophy
    # itself, so it costs no extra request.
    trophy_group_id: str | None = None


@dataclass(slots=True)
class GameTrophyProgress:
    """One game's trophy tally for account_trophy_overview() below — plain
    ints, not psnawp's own TrophySet, since this shape exists purely to be
    rendered (Follow-up 2026-09-06, services/psn/view.py)."""

    title_name: str
    progress: int
    earned_total: int
    defined_total: int
    earned_bronze: int
    earned_silver: int
    earned_gold: int
    earned_platinum: int
    last_updated: str | None


@dataclass(slots=True)
class AccountTrophyOverview:
    """A full, unlimited per-game breakdown for one account — deliberately
    the expensive, complete picture (unlike services/psn/achievements.py's
    poller, which stays windowed to a handful of recent games). Built for
    the admin test screen's own separate trophy table (Follow-up
    2026-09-06), ahead of deciding whether/how to merge it into /stats."""

    online_id: str
    trophy_level: int
    progress: int
    earned_bronze: int
    earned_silver: int
    earned_gold: int
    earned_platinum: int
    games: list[GameTrophyProgress]


async def _call[T](fn: Callable[..., T], *args: object, **kwargs: object) -> T:
    await _limiter.acquire()
    return await asyncio.to_thread(fn, *args, **kwargs)


def _as_float(value: object) -> float | None:
    """psnawp_api types `Trophy.trophy_earn_rate` as `float | None` but its
    own TrophyBuilder just does `trophy_dict.get("trophyEarnedRate")` with no
    cast (verified in the installed library, 2026-09-06) — Sony's API hands
    that field back as a numeric *string* (e.g. "34.5"), so the annotation
    lies. Found live sending a real test notification: `rarity_badge()`'s
    `<=` comparison crashed on a `str` the moment a trophy with a real earn
    rate went through `format_single`, meaning any live PSN trophy carrying
    rarity data would have silently vanished (poll_account's own broad
    except catches it and only logs — SPEC 9, M-PSN-2). Cast defensively
    rather than trust either the annotation or the runtime type."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# A second PSNAWP client, built from the same NPSSO but with these headers
# instead of the library's own defaults, is the only way to ask Sony for a
# Russian trophy_name/trophy_detail at all (2026-09-09, PSN's own dual-locale
# bilingual-description fetch, #48) — verified live that PSNAWP's default
# headers are a static "Accept-Language: en-US,en;q=0.9, Country: US", not
# tied to the shared account's own language as first assumed. Unlike Xbox
# (a per-request `language=` kwarg) or Steam (a per-request `l=` param),
# psnawp bakes locale into the client object's own constructor headers, so
# there is no cheaper way to ask for a second language on this platform.
# services/psn/auth.py::PsnAuth.get_translation_client owns the single
# lazily-built instance of this second client.
TRANSLATION_HEADERS: dict[str, str] = {"Accept-Language": "ru-RU,ru;q=0.9", "Country": "RU"}


async def build_client(npsso: str, *, headers: dict[str, str] | None = None) -> PSNAWP:
    """Constructs the client object — this does NOT exchange the NPSSO for
    a real token (verified live 2026-09-06: psnawp_api's constructor
    "succeeds" instantly even for complete garbage input, no network call
    at all — the actual exchange only happens on the first real API call).
    services/psn/auth.py's set_npsso() makes a real verification call
    right after this for exactly that reason — never trust this function
    alone to mean "the NPSSO works".

    `headers` (2026-09-09) lets a caller override PSNAWP's own defaults —
    only PsnAuth.get_translation_client() (services/psn/auth.py) passes
    one; every other caller keeps the library's own en-US/US defaults
    exactly as before."""
    try:
        if headers is None:
            return await _call(PSNAWP, npsso)
        return await _call(PSNAWP, npsso, headers=headers)
    except PSNAWPAuthenticationError as exc:
        raise PsnTokenDeadError(str(exc)) from None
    except PsnApiError:
        raise
    except Exception as exc:
        # Anything else (found live: a sandboxed temp dir psnawp's own
        # rate-limiter couldn't write to) is almost certainly not about
        # this particular NPSSO at all — kept as its own class so the
        # admin isn't told to blame a token that was never the problem.
        raise PsnClientSetupError(str(exc)) from exc


async def check_alive(client: PSNAWP) -> bool:
    """The service account's own profile — the cheapest authenticated call
    available. `client.me()` alone proves nothing (found live 2026-09-06:
    it never touches the network by itself, same lazy pattern as PSNAWP's
    own constructor — it "succeeds" instantly regardless of whether the
    NPSSO is any good). The actual authenticated request only fires on the
    first *property* access afterward — `.online_id` is the cheapest one.

    Catches more than PSNAWPAuthenticationError on purpose (found live
    2026-09-06: an admin pasted non-Latin1 text as an NPSSO, which made the
    request layer itself raise a bare UnicodeEncodeError trying to encode
    it into a header — not an auth error, but just as clearly not a real
    NPSSO). This function's whole job is "is this client good", so any
    failure to answer that question honestly means "no" — the caller
    (set_npsso) then reports it the same simple way either way: this
    input didn't work, try again.
    """
    try:
        await _call(lambda: client.me().online_id)
    except PSNAWPAuthenticationError:
        return False
    except Exception:
        log.info("check_alive: unexpected failure verifying the client", exc_info=True)
        return False
    return True


async def resolve_profile(client: PSNAWP, online_id: str) -> PsnProfile:
    try:
        user = await _call(client.user, online_id=online_id)
    except PSNAWPNotFoundError:
        raise PsnApiError(f"PSN has no profile named {online_id!r}") from None
    except PSNAWPAuthenticationError as exc:
        raise PsnTokenDeadError(str(exc)) from None
    return PsnProfile(account_id=user.account_id, online_id=user.online_id)


async def is_trophy_visible(client: PSNAWP, account_id: str) -> bool:
    """Whether the service account can actually see this profile's trophies
    — checked once at /connect_psn time, mirroring Steam's own is_public
    check (services/steam/client.py's get_profile). A closed profile isn't
    an error, just "no" — the person fixes their own PSN privacy setting
    and tries again, same UX as Steam's private-profile case."""
    try:
        user = await _call(client.user, account_id=account_id)
        await _call(user.trophy_summary)
    except (PSNAWPForbiddenError, PSNAWPNotFoundError):
        return False
    except PSNAWPAuthenticationError as exc:
        raise PsnTokenDeadError(str(exc)) from None
    return True


# How many of a person's most-recently-touched games to look into for the
# "recent trophies" test screen — trophy_titles() has no "sort by trophy
# recency" of its own, only by title, so recency is approximated the same
# way PSNProfiles-style trackers do: assume the last few *played* titles
# hold the last earned trophies, then sort what actually came back by each
# trophy's own earned_date_time (verified live: last_updated_datetime on
# TrophyTitle already reflects the latest trophy activity in that game).
_RECENT_TITLES_TO_SCAN = 5


@dataclass(slots=True)
class PsnPresenceSnapshot:
    """One `get_presence()` reading, normalized into the same shape
    presence.py already uses for Xbox (`state`/`title_id`/`title_name`) —
    issue #1's own "/online" piece. `get_presence()` returns a raw,
    undocumented dict (no model class in psnawp_api), verified live against
    real linked accounts (2026-09-08):

        offline: {"basicPresence": {"availability": "unavailable",
                   "primaryPlatformInfo": {"onlineStatus": "offline", ...}}}
        online, in a game: {"basicPresence": {"availability": "availableToPlay",
                   "gameTitleInfoList": [{"npTitleId": ..., "titleName": ...}],
                   "primaryPlatformInfo": {"onlineStatus": "online", ...}}}

    Only 3 real accounts were online-observable during that check, and all
    3 were offline at the time — the in-game shape above comes from
    psnawp's own documented example, not a live capture; `gameTitleInfoList`
    empty-but-online (no title) has never been directly observed either.
    Treated as "online, not in a game" if that ever occurs, same as Xbox/
    Steam's own idle state."""

    state: str  # PresenceState.ONLINE / OFFLINE
    title_id: str | None
    title_name: str | None
    # The account's current online ID (#51). Building the User object to ask
    # for presence already fetches /profiles/<account_id>, whose `onlineId`
    # is the current one — a rename is visible here for free, and PSN used
    # to store the nickname once at connect and never again.
    online_id: str | None = None


LEGACY_PROFILE_URL = "https://us-prof.np.community.playstation.net/userProfile/v1/users"


async def legacy_profile(client: PSNAWP, online_id: str) -> dict[str, str] | None:
    """Sony's legacy profile blob for one nickname (#51) — the only place a
    *previous* online ID is exposed, and only for an account that was
    actually renamed: `currentOnlineId` is absent otherwise, and `onlineId`
    is then simply the current name.

    Addressed by nickname rather than by account_id, which is why the modern
    `/profiles/<account_id>` path the rest of this module uses cannot answer
    the question. Raw HTTP through psnawp's own authenticator: the library
    reads these fields in `User.from_online_id` and throws the previous one
    away, and `User.prev_online_id` is a copy of the current id rather than a
    real previous value in this version.

    None on any failure — this is a best-effort enrichment, never a reason to
    fail a backfill run.
    """
    try:
        user = await _call(client.user, online_id=online_id)
        response = await _call(
            lambda: user.authenticator.get(
                url=f"{LEGACY_PROFILE_URL}/{online_id}/profile2",
                params={"fields": "accountId,onlineId,currentOnlineId"},
            )
        )
        return response.json().get("profile") or None
    except Exception as exc:  # every failure here simply means "no answer"
        log.info("legacy PSN profile unavailable for %s: %s", online_id, exc)
        return None


async def get_presence(client: PSNAWP, account_id: str) -> PsnPresenceSnapshot:
    """A private profile's presence is invisible to the shared service
    account (`PSNAWPForbiddenError`) — not fatal, same "no data" treatment
    every other platform gets when nothing is known yet; the caller stores
    nothing and leaves the account showing "нет данных" in /online rather
    than crashing the whole poll tick over one person's privacy setting."""
    try:
        user = await _call(client.user, account_id=account_id)
        payload = await _call(user.get_presence)
    except PSNAWPNotFoundError:
        raise PsnApiError(f"PSN profile {account_id!r} not found") from None
    except PSNAWPForbiddenError:
        raise PsnPrivateProfileError(account_id) from None
    except PSNAWPAuthenticationError as exc:
        raise PsnTokenDeadError(str(exc)) from None

    basic = payload.get("basicPresence") or {}
    primary = basic.get("primaryPlatformInfo") or {}
    state = (
        PresenceState.ONLINE if primary.get("onlineStatus") == "online" else PresenceState.OFFLINE
    )
    titles = basic.get("gameTitleInfoList") or []
    title_id = titles[0].get("npTitleId") if titles else None
    title_name = titles[0].get("titleName") if titles else None
    return PsnPresenceSnapshot(
        state=state,
        title_id=title_id,
        title_name=title_name,
        online_id=getattr(user, "online_id", None) or None,
    )


async def trophy_titles_for_account(
    client: PSNAWP, account_id: str, limit: int | None = None
) -> list[TrophyTitle]:
    """Resolves the account and returns its recent trophy_titles() — shared
    by the admin test screen (recent_earned_trophies below) and the trophy
    poller (services/psn/achievements.py, SPEC 9, M-PSN-2)."""
    try:
        user = await _call(client.user, account_id=account_id)
        return await _call(lambda: list(user.trophy_titles(limit=limit)))
    except PSNAWPNotFoundError:
        raise PsnApiError(f"PSN profile {account_id!r} not found") from None
    except PSNAWPForbiddenError:
        raise PsnPrivateProfileError(account_id) from None
    except PSNAWPAuthenticationError as exc:
        raise PsnTokenDeadError(str(exc)) from None


async def trophies_for_title(
    client: PSNAWP, account_id: str, title: TrophyTitle
) -> list[EarnedTrophy]:
    """Full detail (name/tier/rarity/hidden/icon) for every *earned* trophy
    in one game — the per-title body recent_earned_trophies below and the
    trophy poller (SPEC 9, M-PSN-2) both need. Raises PsnPrivateProfileError
    if this one game's detail is hidden, or PsnTitleUnavailableError if
    Sony's own API 404s on it — the caller decides what that means
    (recent_earned_trophies skips just this game, not the whole screen; the
    poller does the same, SPEC 9, M-PSN-2)."""
    try:
        user = await _call(client.user, account_id=account_id)
    except PSNAWPNotFoundError:
        raise PsnApiError(f"PSN profile {account_id!r} not found") from None
    except PSNAWPAuthenticationError as exc:
        raise PsnTokenDeadError(str(exc)) from None

    platform = next(iter(title.title_platform), PlatformType.PS4)
    try:
        trophies = await _call(
            lambda: list(
                user.trophies(
                    np_communication_id=title.np_communication_id,
                    platform=platform,
                    # 'all', not psnawp's own default of 'default' (#46,
                    # found while adding the per-group line): a PlayStation
                    # trophy list is split into the base game plus one group
                    # per DLC, and 'default' is *only the base game* — so
                    # every DLC trophy anyone ever earned was invisible to
                    # this bot: never published, never counted in /stats,
                    # while the game's own total (titles.achievements_total)
                    # has always included them. One request either way.
                    trophy_group_id="all",
                    include_progress=True,
                )
            )
        )
    except PSNAWPForbiddenError:
        raise PsnPrivateProfileError(account_id) from None
    except PSNAWPNotFoundError as exc:
        # Found live 2026-09-06: Sony 404s "trophyGroupId='default'" for a
        # specific title (not the account, not private — just this one
        # game's data on Sony's own side). Uncaught, this took down an
        # entire backfill every single retry — the same game every time.
        raise PsnTitleUnavailableError(str(exc)) from None
    except PSNAWPAuthenticationError as exc:
        raise PsnTokenDeadError(str(exc)) from None

    return [
        EarnedTrophy(
            trophy_id=trophy.trophy_id,
            title_name=title.title_name or "?",
            title_icon_url=title.title_icon_url,
            trophy_name=trophy.trophy_name or "?",
            trophy_detail=trophy.trophy_detail,
            trophy_icon_url=trophy.trophy_icon_url,
            trophy_type=trophy.trophy_type,
            trophy_hidden=bool(trophy.trophy_hidden),
            trophy_group_id=getattr(trophy, "trophy_group_id", None),
            trophy_rarity=trophy.trophy_rarity,
            trophy_earn_rate=_as_float(trophy.trophy_earn_rate),
            earned_date_time=(
                trophy.earned_date_time.isoformat() if trophy.earned_date_time else None
            ),
        )
        for trophy in trophies
        if trophy.earned
    ]


@dataclass(slots=True)
class TrophyGroup:
    """One section of a title's trophy list: the base game ('default'), then
    one per DLC ('001'...). #46's second notification line names it and says
    how far through it the person is."""

    group_id: str
    name: str | None
    total: int


async def trophy_groups_for_title(
    client: PSNAWP, account_id: str, title: TrophyTitle
) -> list[TrophyGroup]:
    """The groups a game's trophy list is split into — id, name and size.

    Deliberately `include_progress=False`: how many of them *this* person
    has is already in `seen_achievements`, and asking Sony for it would cost
    a second request (psnawp's own warning) to learn something the bot
    already knows. What comes back here is a fact about the game, so it is
    cached forever in `title_groups` and fetched once per game, ever.

    Returns [] instead of raising on every expected failure: the group line
    is cosmetic, and a missing one must never be the reason a title's
    trophies go unstored.
    """
    try:
        user = await _call(client.user, account_id=account_id)
        platform = next(iter(title.title_platform), PlatformType.PS4)
        summary = await _call(
            lambda: user.trophy_groups_summary(
                np_communication_id=title.np_communication_id,
                platform=platform,
                include_progress=False,
            )
        )
    except Exception:
        log.info(
            "psn trophy groups for title %s unavailable", title.np_communication_id, exc_info=True
        )
        return []

    groups: list[TrophyGroup] = []
    for group in summary.trophy_groups:
        if group.trophy_group_id is None:
            continue
        defined = group.defined_trophies
        groups.append(
            TrophyGroup(
                group_id=group.trophy_group_id,
                name=group.trophy_group_name,
                total=defined.bronze + defined.silver + defined.gold + defined.platinum,
            )
        )
    return groups


async def recent_earned_trophies(client: PSNAWP, account_id: str, limit: int) -> list[EarnedTrophy]:
    """Live, uncached (SPEC 1.5's cache-only rule carve-out — same one the
    admin panel's "Обновить данные" button already gets) — only the admin
    panel's "🏆 Трофеи PSN (тест)" screen calls this, nothing here is stored.
    """
    titles = await trophy_titles_for_account(client, account_id, limit=_RECENT_TITLES_TO_SCAN)

    earned: list[EarnedTrophy] = []
    for title in titles:
        try:
            earned.extend(await trophies_for_title(client, account_id, title))
        except PsnPrivateProfileError:
            continue  # this one game's detail is hidden — skip it, not the whole screen
        except PsnTitleUnavailableError:
            continue  # Sony 404s this one game's own data — same isolation

    earned.sort(key=lambda t: t.earned_date_time or "", reverse=True)
    return earned[:limit]


async def account_trophy_level(client: PSNAWP, account_id: str) -> int:
    """Just the account-wide level (Follow-up 2026-09-06, /stats' own PSN
    line, shown next to the achievement count per user request) — one
    `trophy_summary()` call, cheap compared to account_trophy_overview()
    below, which also does a full per-game scan. poller/psn_fetcher.py
    calls this after finding new trophies (level can only change when a
    trophy is earned) and once after backfill, then caches the result on
    `platform_links.psn_trophy_level` — /stats itself never calls this
    directly (CLAUDE.md: "Кэш" — handlers only read from the database)."""
    try:
        user = await _call(client.user, account_id=account_id)
    except PSNAWPNotFoundError:
        raise PsnApiError(f"PSN profile {account_id!r} not found") from None
    except PSNAWPAuthenticationError as exc:
        raise PsnTokenDeadError(str(exc)) from None

    try:
        summary = await _call(user.trophy_summary)
    except PSNAWPForbiddenError:
        raise PsnPrivateProfileError(account_id) from None
    except PSNAWPAuthenticationError as exc:
        raise PsnTokenDeadError(str(exc)) from None
    return summary.trophy_level


async def account_trophy_overview(client: PSNAWP, account_id: str) -> AccountTrophyOverview:
    """Every game this account has ever earned a trophy in, plus the
    account-wide level/progress — live, uncached, no limit (2026-09-06:
    verified against a real account that its cross-game sum matches this
    same account's own trophy_summary() total exactly, 17 == 17 — this
    isn't an approximation). Used by the admin test screen's separate
    trophy table (services/psn/view.py), not by the regular poller."""
    try:
        user = await _call(client.user, account_id=account_id)
    except PSNAWPNotFoundError:
        raise PsnApiError(f"PSN profile {account_id!r} not found") from None
    except PSNAWPAuthenticationError as exc:
        raise PsnTokenDeadError(str(exc)) from None

    try:
        summary = await _call(user.trophy_summary)
        titles = await _call(lambda: list(user.trophy_titles(limit=None)))
    except PSNAWPForbiddenError:
        raise PsnPrivateProfileError(account_id) from None
    except PSNAWPAuthenticationError as exc:
        raise PsnTokenDeadError(str(exc)) from None

    games = [
        GameTrophyProgress(
            title_name=title.title_name or "?",
            progress=title.progress or 0,
            earned_total=(
                title.earned_trophies.bronze
                + title.earned_trophies.silver
                + title.earned_trophies.gold
                + title.earned_trophies.platinum
            ),
            defined_total=(
                title.defined_trophies.bronze
                + title.defined_trophies.silver
                + title.defined_trophies.gold
                + title.defined_trophies.platinum
            ),
            earned_bronze=title.earned_trophies.bronze,
            earned_silver=title.earned_trophies.silver,
            earned_gold=title.earned_trophies.gold,
            earned_platinum=title.earned_trophies.platinum,
            last_updated=(
                title.last_updated_datetime.isoformat() if title.last_updated_datetime else None
            ),
        )
        for title in titles
        if (title.progress or 0) > 0  # untouched games are noise, same spirit as /stats
    ]
    games.sort(key=lambda g: g.last_updated or "", reverse=True)

    return AccountTrophyOverview(
        online_id=user.online_id,
        trophy_level=summary.trophy_level,
        progress=summary.progress,
        earned_bronze=summary.earned_trophies.bronze,
        earned_silver=summary.earned_trophies.silver,
        earned_gold=summary.earned_trophies.gold,
        earned_platinum=summary.earned_trophies.platinum,
        games=games,
    )
