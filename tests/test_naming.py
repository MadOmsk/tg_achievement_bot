"""The naming chains (#51) — one chain per question, reused everywhere.

Pure functions, no database and no Telegram: what each screen *does* with
the answer is covered by that screen's own tests (test_daily, test_online_*,
test_stats_display, test_panel).
"""

from __future__ import annotations

from bot.db.repo import PlatformLink, User
from bot.services.naming import (
    NO_NICKNAME,
    account_nickname,
    link_nickname,
    person_name,
    person_name_of,
    psn_nickname,
    steam_nickname,
    xbox_nickname,
)

TG_ID = 319472587


def _user(**over) -> User:
    base = dict(
        tg_id=TG_ID,
        username=None,
        xuid=None,
        gamertag=None,
        gamerscore=None,
        is_excluded=False,
        last_online_at=None,
    )
    base.update(over)
    return User(**base)  # type: ignore[arg-type]


def _link(platform: str, **over) -> PlatformLink:
    base = dict(
        tg_id=TG_ID,
        platform=platform,
        external_id="external",
        display_name=None,
        linked_at="2026-09-12T00:00:00+00:00",
    )
    base.update(over)
    return PlatformLink(**base)  # type: ignore[arg-type]


# ------------------------------------------------------------- person chain


def test_a_person_is_their_nickname_else_their_id() -> None:
    """Owner, 2026-10-07: the nickname in the app, else `id<person id>` —
    nothing in between."""
    assert person_name(person_id=42, handle="RideTheSun#4821") == "RideTheSun#4821"
    assert person_name(person_id=42, handle=None) == "id42"
    assert person_name(person_id=42, handle="") == "id42"


def test_person_name_of_reads_only_the_nickname_and_the_id() -> None:
    """Telegram's username and a platform nickname are not steps any more:
    a person is called one name in the app and in Telegram."""
    user = _user(
        id=7,
        username="keimaks",
        first_name="k_maks",
        xuid="xuid-1",
        gamertag="MadOmsk",
        gamertag_modern="Mad Omsk",
        handle="Maks",
    )
    assert person_name_of(user) == "Maks"
    assert person_name_of(_user(id=7, username="keimaks", gamertag="MadOmsk")) == "id7"


# ------------------------------------------------------------ account chains


def test_xbox_chain() -> None:
    assert xbox_nickname(gamertag_modern="Mad Omsk", gamertag="MadOmsk") == "Mad Omsk"
    assert xbox_nickname(gamertag_modern=None, gamertag="MadOmsk") == "MadOmsk"
    assert xbox_nickname(gamertag_modern=None, gamertag=None, xuid="2533") == "2533"
    assert xbox_nickname(gamertag_modern=None, gamertag=None) == NO_NICKNAME


def test_steam_chain() -> None:
    assert steam_nickname(persona_name="Mad Omsk", vanity="madomsk", steam_id="765") == "Mad Omsk"
    assert steam_nickname(persona_name=None, vanity="madomsk", steam_id="765") == "madomsk"
    assert steam_nickname(persona_name=None, vanity=None, steam_id="765") == "765"


def test_psn_chain() -> None:
    assert psn_nickname(online_id="new", previous_online_id="old", account_id="213") == "new"
    assert psn_nickname(online_id=None, previous_online_id="old", account_id="213") == "old"
    assert psn_nickname(online_id=None, previous_online_id=None, account_id="213") == "213"


def test_account_nickname_dispatches_on_platform() -> None:
    """`secondary_name` is the same column for both platforms and means a
    different thing in each — Steam's vanity, PSN's previous online ID — so
    the dispatch is what keeps one column honest."""
    assert (
        account_nickname("steam", display_name=None, secondary_name="madomsk", external_id="765")
        == "madomsk"
    )
    assert (
        account_nickname("psn", display_name=None, secondary_name="oldname", external_id="213")
        == "oldname"
    )


def test_link_nickname_follows_platform_naming_chain() -> None:
    steam_link = PlatformLink(
        tg_id=1,
        platform="steam",
        external_id="76561198000000000",
        display_name=None,
        linked_at="2026-01-01T00:00:00Z",
        secondary_name="my_vanity",
    )
    assert link_nickname(steam_link) == "my_vanity"

    psn_link = PlatformLink(
        tg_id=1,
        platform="psn",
        external_id="2130000000000000000",
        display_name=None,
        linked_at="2026-01-01T00:00:00Z",
        secondary_name="old_psn_id",
    )
    assert link_nickname(psn_link) == "old_psn_id"

    psn_bare = PlatformLink(
        tg_id=1,
        platform="psn",
        external_id="2130000000000000000",
        display_name=None,
        linked_at="2026-01-01T00:00:00Z",
        secondary_name=None,
    )
    assert link_nickname(psn_bare) == "2130000000000000000"
