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


async def _call[T](fn: Callable[..., T], *args: object, **kwargs: object) -> T:
    await _limiter.acquire()
    return await asyncio.to_thread(fn, *args, **kwargs)


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
    """Cheapest authenticated call available — the service account's own
    profile (poller/service_health.py)."""
    try:
        await _call(client.me)
    except PSNAWPAuthenticationError:
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
            trophy_earn_rate=trophy.trophy_earn_rate,
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
