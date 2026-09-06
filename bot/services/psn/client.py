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
    services/psn/achievements.py's fetch_unlocked (SPEC 9, M-PSN-2), which
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


async def build_client(npsso: str) -> PSNAWP:
    """Constructs the client object — this does NOT exchange the NPSSO for
    a real token (verified live 2026-09-06: psnawp_api's constructor
    "succeeds" instantly even for complete garbage input, no network call
    at all — the actual exchange only happens on the first real API call).
    services/psn/auth.py's set_npsso() makes a real verification call
    right after this for exactly that reason — never trust this function
    alone to mean "the NPSSO works"."""
    try:
        return await _call(PSNAWP, npsso)
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
    if this one game's detail is hidden — the caller decides what that
    means (recent_earned_trophies skips just this game, not the whole
    screen; the poller does the same, SPEC 9, M-PSN-2)."""
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
                    include_progress=True,
                )
            )
        )
    except PSNAWPForbiddenError:
        raise PsnPrivateProfileError(account_id) from None
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
            trophy_rarity=trophy.trophy_rarity,
            trophy_earn_rate=_as_float(trophy.trophy_earn_rate),
            earned_date_time=(
                trophy.earned_date_time.isoformat() if trophy.earned_date_time else None
            ),
        )
        for trophy in trophies
        if trophy.earned
    ]


async def recent_earned_trophies(
    client: PSNAWP, account_id: str, limit: int
) -> list[EarnedTrophy]:
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
