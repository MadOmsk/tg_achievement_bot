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


def test_person_chain_order() -> None:
    """Имя Фамилия → username → platform → id. Digits last, most human
    form first."""
    everything = dict(
        tg_id=TG_ID, first_name="Igor", last_name="Petrov", username="mad", xbox="MadXbox"
    )
    assert person_name(**everything) == "Igor Petrov"
    assert person_name(**{**everything, "last_name": None}) == "Igor"
    assert person_name(**{**everything, "first_name": None, "last_name": None}) == "mad"
    assert person_name(tg_id=TG_ID, username=None, xbox="MadXbox") == "MadXbox"


def test_person_chain_prefers_xbox_then_steam_then_psn() -> None:
    assert person_name(tg_id=TG_ID, xbox="X", steam="S", psn="P") == "X"
    assert person_name(tg_id=TG_ID, steam="S", psn="P") == "S"
    assert person_name(tg_id=TG_ID, psn="P") == "P"


def test_person_chain_never_renders_an_at_sign() -> None:
    """No live mentions anywhere (#51, user request) — /online redraws every
    few minutes, and one rule beats remembering which screen is safe."""
    assert person_name(tg_id=TG_ID, username="mad") == "mad"


def test_person_chain_last_resort_is_the_id() -> None:
    assert person_name(tg_id=TG_ID) == f"id{TG_ID}"


def test_person_chain_steps_over_an_empty_platform_nickname() -> None:
    """An account chain ends at a dash because its own line has to render
    something; inside the person chain that dash is an absence. Stopping on
    it would print "—" while a real nickname sat one step further down —
    which is the shape of the bug this whole issue is about."""
    empty_xbox = xbox_nickname(gamertag_modern=None, gamertag=None)
    assert empty_xbox == NO_NICKNAME
    assert person_name(tg_id=TG_ID, xbox=empty_xbox, psn="PsnNick") == "PsnNick"


def test_person_name_of_reads_a_user_and_their_links() -> None:
    """The real shape behind the screenshot that started #51: no Xbox at
    all, a Telegram first name, a username and a PSN nickname — and the
    summary rendered a bare id."""
    user = _user(username="keimaks", first_name="k_maks")
    links = [_link("psn", display_name="kmaks90")]
    assert person_name_of(user, links) == "k_maks"

    nameless = _user()
    assert person_name_of(nameless, links) == "kmaks90"
    assert person_name_of(nameless) == f"id{TG_ID}"


def test_person_name_of_prefers_the_modern_gamertag() -> None:
    user = _user(xuid="xuid-1", gamertag="MadOmsk", gamertag_modern="Mad Omsk")
    assert person_name_of(user) == "Mad Omsk"


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
