"""Which platform answers "where is this person right now" (issue #1).

The same rule /online's own SQL settled on, in the form /panel needs it.
"""

from __future__ import annotations

from bot.constants import Platform
from bot.db.repo import PresenceRow, PsnPresenceRow, SteamPresenceRow
from bot.services.presence_view import pick_presence


def _xbox(state: str, title_id: str | None, updated_at: str) -> PresenceRow:
    return PresenceRow(
        xuid="xuid-1", state=state, title_id=title_id, title_name=None, updated_at=updated_at
    )


def _steam(persona_state: int, gameid: str | None, updated_at: str) -> SteamPresenceRow:
    return SteamPresenceRow(
        steam_id="76561197960287930",
        persona_state=persona_state,
        gameid=gameid,
        game_name="Dota 2" if gameid else None,
        updated_at=updated_at,
    )


def _psn(state: str, title_id: str | None, updated_at: str) -> PsnPresenceRow:
    return PsnPresenceRow(
        account_id="acc-1",
        state=state,
        title_id=title_id,
        title_name="Ghost of Tsushima" if title_id else None,
        updated_at=updated_at,
    )


def test_nothing_polled_yet_is_not_the_same_as_offline() -> None:
    """ "нет данных" and "не в сети" are different answers, and the caller
    can only tell them apart if this returns None rather than a made-up
    offline row."""
    assert pick_presence() is None


def test_playing_beats_a_more_recent_idle_on_another_platform() -> None:
    """The failure /online was built around: every poll bumps updated_at
    whether anything changed or not, so "freshest wins" showed an idle
    platform over the one being played on."""
    picked = pick_presence(
        xbox=_xbox("Online", None, "2026-09-15T12:00:05"),
        steam=_steam(1, "570", "2026-09-15T12:00:00"),
    )

    assert picked is not None
    assert picked.platform == Platform.STEAM
    assert picked.game == "Dota 2"


def test_online_beats_offline_however_stale() -> None:
    picked = pick_presence(
        xbox=_xbox("Offline", None, "2026-09-15T12:00:05"),
        psn=_psn("Online", None, "2026-09-15T09:00:00"),
    )

    assert picked is not None
    assert picked.platform == Platform.PSN
    assert picked.online


def test_freshness_decides_between_two_platforms_at_the_same_level() -> None:
    picked = pick_presence(
        xbox=_xbox("Online", "title-1", "2026-09-15T12:00:00"),
        psn=_psn("Online", "CUSA00001", "2026-09-15T12:05:00"),
    )

    assert picked is not None
    assert picked.platform == Platform.PSN


def test_steam_persona_states_other_than_zero_are_all_online() -> None:
    """Away, busy, snoozing, looking to trade — Steam's enum has six
    flavours of "not offline" and only 0 means offline."""
    picked = pick_presence(steam=_steam(3, None, "2026-09-15T12:00:00"))

    assert picked is not None
    assert picked.online
