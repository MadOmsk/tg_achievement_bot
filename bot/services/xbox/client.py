"""Xbox Live requests: presence, achievements, title history (SPEC 4).

The library covers presence and titlehub. Achievements we do ourselves, because
`rarity` only exists on contract 4 and the library sends contract 1 or 2 — the
whole rarity feature depends on this one request being hand-written.

Nothing here knows about Telegram.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime

import httpx
from pydantic import ValidationError
from xbox.webapi.api.client import XboxLiveClient

from bot.constants import (
    Platform,
    PresenceState,
    XboxApiValue,
)
from bot.services.rate_limiter import RateLimiter
from bot.services.xbox.auth import XboxAuthService
from bot.services.xbox.models import (
    ParsedAchievement,
    continuation_token,
    parse_achievements,
    parse_rarity,
)

log = logging.getLogger(__name__)

ACHIEVEMENTS_URL = "https://achievements.xboxlive.com/users/xuid({xuid})/achievements"
PAGE_SIZE = 1000
MAX_ATTEMPTS = 3

# Microsoft's documented windows for the achievements service. We use about 1%
# of this, so the limiter is a guard against a bug in the poller, not a budget.
RATE_WINDOWS: tuple[tuple[int, float], ...] = ((100, 15.0), (300, 300.0))

X360_DEVICES = {"Xbox360", "Xbox 360"}

# A hard wall-clock ceiling on title_history() (2026-09-09) — see that
# method's own docstring for why httpx's session-level read timeout alone
# does not actually bound this call.
TITLE_HISTORY_DEADLINE_SECONDS = 60.0


class XboxApiError(Exception):
    """Expected failure — the poller logs it and moves to the next user."""


class ProfileUnavailableError(XboxApiError):
    """Private profile, or the account cannot be read with this token."""


@dataclass(slots=True)
class PresenceSnapshot:
    state: str
    title_id: str | None
    title_name: str | None
    platform: Platform
    last_seen_at: datetime | None
    device: str | None = None

    @property
    def in_game(self) -> bool:
        return self.state == PresenceState.ONLINE and self.title_id is not None


@dataclass(slots=True)
class TitleHistoryEntry:
    title_id: str
    name: str
    platform: Platform
    current_gamerscore: int | None
    max_gamerscore: int | None
    achievements_unlocked: int | None
    achievements_total: int | None
    last_played_at: str | None
    # The game's own box art (titlehub's own `display_image`) — not an
    # achievement icon. Only actually used as one, as a stand-in for Xbox
    # 360 (fetcher.py's ensure_title_icon): contract 1's achievement
    # payload carries a bare `imageId` int with no documented way to turn
    # it into a URL at all (verified live against the real API — the raw
    # response has nothing image-shaped besides that number).
    icon_url: str | None = None
    devices: list[str] = field(default_factory=list)


@dataclass(slots=True)
class XboxProfileSnapshot:
    """One profile request's worth of cacheable facts (#51) — the gamerscore
    this call has always been made for, plus the two gamertags that were
    already in the same response and used to be discarded."""

    gamerscore: int | None
    gamertag: str | None
    gamertag_modern: str | None
    #: The account's own picture (#55) — `GameDisplayPicRaw`, in the same
    #: fixed settings list this request already asks for, so it costs
    #: nothing and was simply being thrown away like the gamertags were.
    avatar_url: str | None = None


class XboxClient:
    def __init__(self, auth: XboxAuthService, limiter: RateLimiter | None = None) -> None:
        self._auth = auth
        self._limiter = limiter or RateLimiter(RATE_WINDOWS)

    def rate_limit_usage(self) -> list[tuple[int, int, float]]:
        """(used, limit, window_seconds) for each achievements-service window
        this client shares across every user (SPEC 4, 6.4)."""
        return self._limiter.usage()

    # ----------------------------------------------------------- presence

    async def presence(self, tg_id: int) -> PresenceSnapshot:
        """Ask a user about himself with his own token (SPEC 5.2).

        No batching and no friendship with a bot account: everyone can always
        see himself, whatever his privacy settings are.
        """
        manager = await self._auth.authenticated_manager(tg_id)
        client = XboxLiveClient(manager)
        await self._limiter.acquire()
        try:
            item = await client.presence.get_presence_own()
        except httpx.HTTPStatusError as exc:
            raise _translate(exc) from None
        except httpx.RequestError as exc:
            raise XboxApiError(f"presence request failed: {exc!r}") from None

        title_id, title_name, device = _current_title(item)
        last_seen = getattr(item, "last_seen", None)
        if device is None and last_seen is not None:
            device = last_seen.device_type
        return PresenceSnapshot(
            state=item.state or PresenceState.OFFLINE,
            title_id=title_id,
            title_name=title_name,
            platform=Platform.XBOX_360 if device in X360_DEVICES else Platform.XBOX_MODERN,
            last_seen_at=getattr(last_seen, "timestamp", None),
            device=device,
        )

    # -------------------------------------------------------- achievements

    async def title_achievements(
        self,
        tg_id: int,
        title_id: str,
        platform: Platform,
        *,
        language: str = "en-US",
        earned_only: bool = True,
    ) -> list[ParsedAchievement]:
        """Achievements of one game — the only request that carries rarity.

        `platform` is a hint from presence, and presence reports the *console*,
        not the game: an Xbox 360 title played through back-compat on a Series X
        arrives here as "xbox_modern". Contract 4 answers such a title with an empty
        list, while a modern title always returns its full set (including
        NotStarted), so an empty answer means "wrong contract", not "no
        achievements" — and we ask again as Xbox 360. Without this a whole
        back-compat session would be published as nothing at all.

        `language` (2026-09-09, bilingual descriptions) — this call was
        always hardcoded to `en-US` before; the caller can now ask for
        `ru-RU` too (poller/fetcher.py's own bilingual helper does, once per
        achievement ever — see that module) to tell a genuine Xbox
        Live localization apart from its documented fallback to the title's
        own default strings when no match exists for the requested locale.
        """
        unlocked, _total = await self.title_achievements_with_total(
            tg_id, title_id, platform, language=language, earned_only=earned_only
        )
        return unlocked

    async def title_achievements_with_total(
        self,
        tg_id: int,
        title_id: str,
        platform: Platform,
        *,
        language: str = "en-US",
        earned_only: bool = True,
    ) -> tuple[list[ParsedAchievement], int]:
        """The same call, also reporting **how many achievements the game
        has** — the unlocked ones and the size of the set they came from.

        The response lists every achievement of the title, locked ones
        included; `parse_achievements` keeps only the earned ones, so that
        count was being thrown away at the door. It is the one place the true
        total exists for a modern Xbox title: titlehub reports
        `totalAchievements = 0` for most of them (151 of 555 on a real
        account), which is why the "47/50" counter (#46) was missing from
        nearly every Xbox One/Series card.

        0 means "this answer does not say" — an empty contract-4 reply for a
        back-compat title, say — never "the game has no achievements".
        """
        params = {"titleId": title_id, "maxItems": str(PAGE_SIZE)}
        if platform == Platform.XBOX_360:
            payload = await self._get_achievements(tg_id, "1", params, language=language)
            return (
                parse_achievements(payload, Platform.XBOX_360, title_id, earned_only=earned_only),
                _total_in(payload),
            )

        payload = await self._get_achievements(tg_id, "4", params, language=language)
        if payload.get("achievements"):
            return (
                parse_achievements(
                    payload, Platform.XBOX_MODERN, title_id, earned_only=earned_only
                ),
                _total_in(payload),
            )

        log.info("title %s looks like Xbox 360, retrying on contract 1", title_id)
        payload = await self._get_achievements(tg_id, "1", params, language=language)
        return (
            parse_achievements(payload, Platform.XBOX_360, title_id, earned_only=earned_only),
            _total_in(payload),
        )

    async def title_rarity(self, tg_id: int, title_id: str) -> dict[str, float]:
        """Every achievement's rarity for one modern title, earned or not.

        The same contract-4 request `title_achievements` makes, kept for the
        one field in it that belongs to the achievement rather than to the
        caller. Any owner of the game can answer for all of them, which is
        what makes filling the shared cache one request per *title* instead
        of one per person per title.

        Empty for an Xbox 360 title (contract 4 answers those with nothing,
        and contract 1 has no rarity to give) — the caller treats that as
        "asked and there is none", not as a failure to retry.
        """
        payload = await self._get_achievements(
            tg_id, "4", {"titleId": title_id, "maxItems": str(PAGE_SIZE)}
        )
        return parse_rarity(payload)

    async def all_achievements(self, tg_id: int) -> list[ParsedAchievement]:
        """Every achievement of the player, for backfill only (SPEC 5.6).

        Contract 2, no titleId: rarity is missing here, and that is fine —
        these rows are never published, they only mark "already seen".
        """
        collected: list[ParsedAchievement] = []
        params = {"maxItems": str(PAGE_SIZE)}
        for _ in range(100):  # a hard stop; nobody has 100k achievements
            payload = await self._get_achievements(tg_id, "2", params)
            collected.extend(parse_achievements(payload, Platform.XBOX_MODERN))
            token = continuation_token(payload)
            if not token:
                break
            params = {"maxItems": str(PAGE_SIZE), "continuationToken": token}
        return collected

    async def _get_achievements(
        self, tg_id: int, contract: str, params: dict[str, str], *, language: str = "en-US"
    ) -> dict:
        manager = await self._auth.authenticated_manager(tg_id)
        assert manager.xsts_token is not None
        url = ACHIEVEMENTS_URL.format(xuid=manager.xsts_token.xuid)
        headers = {
            "Authorization": manager.xsts_token.authorization_header_value,
            "x-xbl-contract-version": contract,
            "Accept": "application/json",
            "Accept-Language": language,
        }

        for attempt in range(1, MAX_ATTEMPTS + 1):
            await self._limiter.acquire()
            try:
                response = await manager.session.get(url, params=params, headers=headers)
            except httpx.RequestError as exc:
                if attempt == MAX_ATTEMPTS:
                    raise XboxApiError(f"achievements request failed: {exc!r}") from None
                await asyncio.sleep(2**attempt)
                continue

            if response.status_code == 429:
                # Respect Retry-After when Microsoft bothers to send it.
                delay = _retry_after(response) or 2**attempt
                if attempt == MAX_ATTEMPTS:
                    raise XboxApiError("achievements rate limited")
                log.info("rate limited by Xbox Live, sleeping %.0fs", delay)
                await asyncio.sleep(delay)
                continue

            if response.status_code in (401, 403, 404):
                raise ProfileUnavailableError(f"achievements unavailable: {response.status_code}")
            if response.status_code >= 500:
                if attempt == MAX_ATTEMPTS:
                    raise XboxApiError(f"Xbox Live returned {response.status_code}")
                await asyncio.sleep(2**attempt)
                continue

            try:
                payload = response.json()
            except ValueError:
                raise XboxApiError("achievements response is not JSON") from None
            return payload if isinstance(payload, dict) else {}

        raise XboxApiError("achievements request gave up")

    async def profile(self, tg_id: int) -> XboxProfileSnapshot:
        """Gamerscore and both gamertags, from one profile request.

        The gamerscore is the real total from the profile: summing title
        history would understate it, since that request is capped and an
        account with more titles than the cap silently loses the rest.

        The two names ride along for free (#51). This call has always asked
        for `Gamertag`, `ModernGamertag`, `ModernGamertagSuffix` and
        `UniqueModernGamertag` — xbox-webapi-python puts them in its own
        fixed settings list — and threw all four away, which is why a
        gamertag written once at connect stayed stale forever and the
        profile link built from it went dead on a rename. The `#1234`
        suffix is deliberately not kept: it is never shown.
        """
        manager = await self._auth.authenticated_manager(tg_id)
        assert manager.xsts_token is not None
        client = XboxLiveClient(manager)
        await self._limiter.acquire()
        try:
            response = await client.profile.get_profile_by_xuid(manager.xsts_token.xuid)
        except httpx.HTTPStatusError as exc:
            raise _translate(exc) from None
        except httpx.RequestError as exc:
            raise XboxApiError(f"profile request failed: {exc!r}") from None

        wanted = {
            XboxApiValue.GAMERSCORE: None,
            XboxApiValue.GAMERTAG: None,
            XboxApiValue.MODERN_GAMERTAG: None,
            XboxApiValue.GAME_DISPLAY_PIC: None,
        }
        for user in getattr(response, "profile_users", None) or []:
            for setting in getattr(user, "settings", None) or []:
                key = getattr(setting, "id", None)
                if key in wanted:
                    wanted[key] = setting.value or None
        raw_score = wanted[XboxApiValue.GAMERSCORE]
        try:
            gamerscore = int(raw_score) if raw_score is not None else None
        except (TypeError, ValueError):
            gamerscore = None
        return XboxProfileSnapshot(
            gamerscore=gamerscore,
            gamertag=wanted[XboxApiValue.GAMERTAG],
            gamertag_modern=wanted[XboxApiValue.MODERN_GAMERTAG],
            avatar_url=wanted[XboxApiValue.GAME_DISPLAY_PIC],
        )

    async def resolve_title(self, tg_id: int, title_id: str) -> TitleHistoryEntry | None:
        """Look one game up by id.

        Presence returns an empty name for PC titles (seen live on
        WindowsOneCore), and a message saying "неизвестная игра" is worse than
        one extra request per new game — the answer is cached in `titles`.
        """
        manager = await self._auth.authenticated_manager(tg_id)
        client = XboxLiveClient(manager)
        await self._limiter.acquire()
        try:
            response = await client.titlehub.get_title_info(title_id)
        except httpx.HTTPStatusError as exc:
            raise _translate(exc) from None
        except httpx.RequestError as exc:
            raise XboxApiError(f"title info request failed: {exc!r}") from None
        except ValidationError as exc:
            # titlehub answers for some games with `detail.developerName:
            # null`, and xbox-webapi's own model demands a string — so a
            # perfectly good reply arrives as a validation error. Not an API
            # failure, not something to retry, and not ours to fix upstream:
            # the honest reading is "titlehub cannot describe this game",
            # which is what `None` already means here.
            #
            # Worth catching precisely because of where this is called from.
            # `Fetcher.ensure_title_name` catches XboxApiError and nothing
            # else, and `poll_title` calls it *after* storing the new rows
            # and *before* publishing them — so an escaping exception stored
            # somebody's achievements and silently never announced them,
            # which is the whole shape of #82 arriving by another road.
            # Found on 2026-09-19 by a backfill that died on its first title.
            log.info("titlehub could not describe title %s: %s", title_id, exc.error_count())
            return None

        for title in response.titles or []:
            return _as_entry(title)
        return None

    # -------------------------------------------------------- title history

    async def title_history(self, tg_id: int, max_items: int = 200) -> list[TitleHistoryEntry]:
        """Source of /stats and /online, of the x360 pass in backfill(), and of
        the "recent games" table.

        Not the source of the headline gamerscore anywhere — that is always
        `users.gamerscore` from the profile (SPEC 5.4), never a sum over this.
        The only thing this cap actually gates is backfill's x360 achievement
        sweep, and that only needs to cover what "За месяц" cares about: a
        person does not play 200+ distinct titles in 30 days, so 200 is not a
        corner cut, it is already generous. (A live account with 1091 titles
        briefly ran with max_items=2000 while chasing what looked like a gap
        in "Всего" — that turned out to be the wrong target, since "Всего" is
        a count, not a score; reverted once that was clear.)

        Wrapped in `asyncio.wait_for` on top of the session's own read
        timeout (found live, 2026-09-09): httpx's read timeout resets on
        every chunk received, it is not a ceiling on the *whole* response —
        a large title_history response trickling in slowly enough between
        chunks never trips it at all, and `startup_catch_up`'s otherwise-
        sequential loop over every Xbox user just stopped advancing, with
        no exception and no timeout, until the process was restarted. This
        is the actual hard deadline; the session's own read timeout only
        matters for a connection that goes fully silent mid-response.
        """
        manager = await self._auth.authenticated_manager(tg_id)
        assert manager.xsts_token is not None
        client = XboxLiveClient(manager)
        await self._limiter.acquire()
        try:
            response = await asyncio.wait_for(
                client.titlehub.get_title_history(manager.xsts_token.xuid, max_items=max_items),
                timeout=TITLE_HISTORY_DEADLINE_SECONDS,
            )
        except TimeoutError:
            raise XboxApiError(
                f"title history request exceeded {TITLE_HISTORY_DEADLINE_SECONDS:.0f}s overall"
            ) from None
        except httpx.HTTPStatusError as exc:
            raise _translate(exc) from None
        except httpx.RequestError as exc:
            raise XboxApiError(f"title history request failed: {exc!r}") from None

        return [_as_entry(title) for title in response.titles or []]


def _total_in(payload: dict[str, object]) -> int:
    """How many achievements the response listed, earned or not."""
    achievements = payload.get("achievements")
    return len(achievements) if isinstance(achievements, list) else 0


def _as_entry(title: object) -> TitleHistoryEntry:
    achievement = getattr(title, "achievement", None)
    history = getattr(title, "title_history", None)
    devices = getattr(title, "devices", None) or []
    return TitleHistoryEntry(
        title_id=str(title.title_id),
        name=title.name or "",
        platform=Platform.XBOX_360
        if any(d in X360_DEVICES for d in devices)
        else Platform.XBOX_MODERN,
        current_gamerscore=getattr(achievement, "current_gamerscore", None),
        max_gamerscore=getattr(achievement, "total_gamerscore", None),
        achievements_unlocked=getattr(achievement, "current_achievements", None),
        achievements_total=getattr(achievement, "total_achievements", None),
        last_played_at=_as_iso(getattr(history, "last_time_played", None)),
        icon_url=getattr(title, "display_image", None) or None,
        devices=list(devices),
    )


# Microsoft's own shell/app entries, not games — found live: "XBOX"
# (title_id 704208617) resolves via titlehub to 0 max_gamerscore and 0
# achievements at all, the Xbox app itself rather than something someone
# is playing (SPEC 5.2/5.3 — this fed straight into /online showing
# a generic playing-on-Xbox label instead of what the person was actually doing).
_SYSTEM_TITLE_NAMES = {"home", "xbox"}


def _current_title(item: object) -> tuple[str | None, str | None, str | None]:
    """The game a person is actually playing, not the dashboard/app behind it."""
    for device in getattr(item, "devices", None) or []:
        for title in getattr(device, "titles", None) or []:
            if getattr(title, "placement", None) != XboxApiValue.FULL:
                continue
            if getattr(title, "state", None) != XboxApiValue.ACTIVE:
                continue
            name = getattr(title, "name", None)
            if name and name.strip().lower() in _SYSTEM_TITLE_NAMES:
                continue
            return str(title.id), name, getattr(device, "type", None)
    return None, None, None


def _retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    try:
        return float(raw) if raw else None
    except ValueError:
        return None


def _translate(exc: httpx.HTTPStatusError) -> XboxApiError:
    status = exc.response.status_code
    if status in (401, 403, 404):
        return ProfileUnavailableError(f"profile unavailable: {status}")
    return XboxApiError(f"Xbox Live returned {status}")


def _as_iso(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return str(value)
