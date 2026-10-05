"""Where is this person right now, across every platform they have linked
(issue #1's own tail).

/online has answered this since Steam was added, but the answer lives in
`chat_member_presence`'s SQL, which is built around a whole chat's roster —
three left joins and a ranked sub-select per member. /panel needs the same
answer for exactly one person whose presence rows the handler already holds,
so the *rule* is shared here rather than the query.

The rule itself is the one /online settled on and must not drift from it:
**playing beats online, which beats offline, on whichever platform it is
true; `updated_at` only breaks a tie between platforms at the same level.**
Freshness alone was tried first there and was wrong — every poll bumps
`updated_at` whether or not anything changed, so someone actively playing on
Steam showed up as idle-on-Xbox purely because Xbox was polled a second
later.
"""

from __future__ import annotations

from dataclasses import dataclass

from bot.constants import Platform, PresenceState
from bot.db.repo import PresenceRow, PsnPresenceRow, SteamPresenceRow


@dataclass(frozen=True)
class CurrentPresence:
    platform: str
    online: bool
    # The game, when one is known. `None` while idle — and also while online
    # in *something* the platform would not name (Steam reports a `gameid`
    # with no name for a game outside its own store; Xbox names no PC title
    # at all), which the caller resolves from its own title cache.
    game: str | None
    title_id: str | None
    updated_at: str


def _level(online: bool, title_id: str | None) -> int:
    if not online:
        return 0
    return 2 if title_id else 1


def pick_presence(
    *,
    xbox: PresenceRow | None = None,
    steam: SteamPresenceRow | None = None,
    psn: PsnPresenceRow | None = None,
) -> CurrentPresence | None:
    """`None` means no platform has ever been polled for this person — which
    is not the same as being offline everywhere, and the two read differently
    ("нет данных" vs "не в сети"). A platform the person has not linked at
    all simply arrives here as `None` and never competes."""
    candidates: list[CurrentPresence] = []
    if xbox is not None:
        candidates.append(
            CurrentPresence(
                platform=Platform.XBOX_MODERN,
                online=xbox.state == PresenceState.ONLINE,
                game=xbox.title_name,
                title_id=xbox.title_id,
                updated_at=xbox.updated_at,
            )
        )
    if steam is not None:
        candidates.append(
            CurrentPresence(
                platform=Platform.STEAM,
                # Steam's own enum: 0 is offline, every other value is some
                # shade of online (away, busy, looking to trade...).
                online=(steam.persona_state or 0) != 0,
                game=steam.game_name,
                title_id=steam.gameid,
                updated_at=steam.updated_at,
            )
        )
    if psn is not None:
        candidates.append(
            CurrentPresence(
                platform=Platform.PSN,
                online=psn.state == PresenceState.ONLINE,
                game=psn.title_name,
                title_id=psn.title_id,
                updated_at=psn.updated_at,
            )
        )
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda row: (_level(row.online, row.title_id), row.updated_at or ""),
    )
