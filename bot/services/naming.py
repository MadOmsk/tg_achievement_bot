"""How a person and an account are named, everywhere (#51, 2026-09-12).

One chain per question, reused — never a new one invented at the call site.
CLAUDE.md's "Naming people and accounts" carries the rule and the reasoning;
this module is the only implementation of it.

Before this existed the bot held four slightly different answers to "what is
this person called" and three to "what is this account called", each written
at its own call site and each defensible on its own. The visible result was a
member showing up in the daily summary as a bare `id319472587` while the bot
held his Telegram name, his username and his PSN nickname all along — and
that exact symptom had already been fixed once (#38) and lost again in a
revert, because the fix lived per call site and so did its removal.

Nothing here decides *which* question a screen is asking. A row about a
person calls `person_name`; a row about one platform's account calls that
platform's own chain. Code that needs a specific value — a lookup key, a URL
field, a comparison against what a platform returned — reaches for the raw
column instead: a chain answers a display question, and that is not one.
"""

from __future__ import annotations

from collections.abc import Iterable

from bot.constants import Platform
from bot.db.repo import ChatSubscriber, PlatformLink, User

# Shown in place of a nickname a platform never gave us. Only the super-admin
# card falls back to a raw id instead (there it is diagnostic, not a label) —
# a 19-digit PSN account id reads as noise anywhere a human is named.
NO_NICKNAME = "—"


def person_name(
    *,
    tg_id: int,
    handle: str | None = None,
    username: str | None = None,
    xbox: str | None = None,
    steam: str | None = None,
    psn: str | None = None,
) -> str:
    """Who this person is: their nickname (#157) → `username` → any connected
    platform's nickname (Xbox → PlayStation → Steam) → `id<tg_id>`.

    Telegram's first and last names are not in the chain: a person is shown by
    the nickname they chose and by nothing else. Everybody has one (it is given
    at start-up and on first contact), so the steps after it are a net for a row
    read before that happened, not a second way to be named.

    The platform part follows the one display order every screen uses for a
    platform list (`constants.platform_display_rank`, owner decision
    2026-09-13).

    The username is returned bare, without an `@` — deliberately, everywhere
    (user request, 2026-09-12). A live mention pings its target, which is
    wrong in `/online` (it redraws every few minutes, and this was already
    reverted once for exactly that).
    """
    return handle or username or _first_real(xbox, psn, steam) or f"id{tg_id}"


def _first_real(*names: str | None) -> str | None:
    """The first name that actually names something.

    `NO_NICKNAME` is skipped as carefully as `None` is: the account chains
    below end at a dash because their own line has to render *something*,
    but inside the person chain that dash is an absence, and treating it as
    a value would stop the chain one step early — with a dash on screen,
    while a later platform's real nickname sat unused. Handled here rather
    than at the call sites so passing `xbox_nickname(...)` straight in is
    safe by construction."""
    return next((name for name in names if name and name != NO_NICKNAME), None)


def xbox_nickname(
    *, gamertag_modern: str | None, gamertag: str | None, xuid: str | None = None
) -> str:
    """`ModernGamertag` → `Gamertag` → XUID.

    The modern gamertag is the pretty, current form ("Mad Omsk"); the classic
    one is ASCII and globally unique ("MadOmsk"). The `#1234` suffix that
    disambiguates modern namesakes is never shown — in a chat this size there
    are none, and it reads as noise.

    Note that the profile *link* is built from the classic gamertag, not from
    whatever this returns: `account.xbox.com`'s own search is what has to
    accept it (services/profile_links.py).
    """
    return gamertag_modern or gamertag or xuid or NO_NICKNAME


def steam_nickname(*, persona_name: str | None, vanity: str | None, steam_id: str | None) -> str:
    """`personaname` → vanity → SteamID64.

    No vanity set means there is no vanity string at all — Steam's own
    `profileurl` simply degrades from `/id/<vanity>/` to `/profiles/<id>/`,
    so the last path segment is already this chain's last two steps.
    """
    return persona_name or vanity or steam_id or NO_NICKNAME


def psn_nickname(
    *, online_id: str | None, previous_online_id: str | None, account_id: str | None
) -> str:
    """Current `onlineId` → previous `onlineId` → `account_id`."""
    return online_id or previous_online_id or account_id or NO_NICKNAME


def account_nickname(
    platform: str, *, display_name: str | None, secondary_name: str | None, external_id: str | None
) -> str:
    """The `platform_links` dispatch (Steam/PSN) — Xbox has no row in that
    table and calls `xbox_nickname` directly. `secondary_name` is that
    platform's own middle step: Steam's vanity, PSN's previous online ID.
    """
    if platform == Platform.PSN:
        return psn_nickname(
            online_id=display_name,
            previous_online_id=secondary_name,
            account_id=external_id,
        )
    return steam_nickname(persona_name=display_name, vanity=secondary_name, steam_id=external_id)


def link_nickname(link: PlatformLink) -> str:
    """The account naming chain for a `PlatformLink` row (#78)."""
    return account_nickname(
        link.platform,
        display_name=link.display_name,
        secondary_name=link.secondary_name,
        external_id=link.external_id,
    )


def person_name_of(user: User, links: Iterable[PlatformLink] = ()) -> str:
    """`person_name` for the two shapes most call sites already hold: a
    `users` row and that person's `platform_links`. Keeps every caller from
    re-deriving which link is Steam and which is PSN."""
    by_platform: dict[str, PlatformLink] = {}
    for link in links:
        # The first PSN account linked names the person (#10), not the last.
        by_platform.setdefault(link.platform, link)
    return person_name(
        tg_id=user.tg_id,
        handle=user.handle,
        username=user.username,
        xbox=xbox_nickname(gamertag_modern=user.gamertag_modern, gamertag=user.gamertag),
        steam=_link_name(by_platform.get(Platform.STEAM)),
        psn=_link_name(by_platform.get(Platform.PSN)),
    )


def _link_name(link: PlatformLink | None) -> str | None:
    """A link's own nickname for use *inside the person chain*, where "no
    name" has to stay falsy so the chain moves on — unlike the account
    chains above, which end at a dash because their line is about that
    account and has to render something."""
    if link is None:
        return None
    return link.display_name or link.secondary_name or link.external_id or None


def subscriber_names(rows: Iterable[ChatSubscriber]) -> list[str]:
    """One subscriber list, named by the person chain and sorted by what is
    actually shown (#51) — the query used to sort by `gamertag`, a column a
    Steam/PSN-only member does not have."""
    names = [
        person_name(
            tg_id=row.tg_id,
            handle=row.handle,
            username=row.username,
            xbox=xbox_nickname(gamertag_modern=row.gamertag_modern, gamertag=row.gamertag),
            steam=row.steam_name,
            psn=row.psn_name,
        )
        for row in rows
    ]
    return sorted(names, key=str.casefold)
