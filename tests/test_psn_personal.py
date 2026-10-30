"""A player's own PSN token (#233): kept only for the account it opens, never
past its link, never logged; a dead one falls back without touching the
shared token's health."""

from __future__ import annotations

import logging

import pytest

from bot.constants import Platform
from bot.db.repo import Repo
from bot.services.crypto import TokenCipher
from bot.services.psn import personal
from bot.services.psn.auth import PsnAuth
from bot.services.psn.client import PsnApiError, PsnProfile, PsnTokenDeadError
from bot.services.psn.personal import (
    PsnPersonalAuth,
    TokenFormatInvalid,
    TokenMismatch,
    TokenNotLinked,
    TokenRefused,
    TokenUnavailable,
)

GOOD = "A" * 64
OTHER = "B" * 64
KEY = "jDzMk1H4D8_uG2bZqv0O1c0JxQb5ZQ0w6m3pX1Yf4kE="


async def _shared_set(self: object) -> str:
    return "active"


@pytest.fixture
def sony(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Which account each token opens; any request is counted."""
    state: dict[str, object] = {
        "accounts": {GOOD: PsnProfile("111", "Me"), OTHER: PsnProfile("222", "Them")},
        "requests": 0,
        "refuse": False,
        "down": False,
    }

    async def build_client(npsso: str, **_: object) -> str:
        return npsso

    async def own_profile(client: str) -> PsnProfile:
        state["requests"] = int(state["requests"]) + 1  # type: ignore[call-overload]
        if state["down"]:
            raise PsnApiError("unreachable")
        if state["refuse"]:
            raise PsnTokenDeadError("refused")
        return state["accounts"][client]  # type: ignore[index]

    async def check_alive(client: str, **_: object) -> bool:
        return not state["refuse"]

    monkeypatch.setattr(personal, "build_client", build_client)
    monkeypatch.setattr(personal, "own_profile", own_profile)
    monkeypatch.setattr(personal, "check_alive", check_alive)
    # A shared token is set: linking by a token needs the poller to run.
    monkeypatch.setattr(PsnAuth, "status", _shared_set)
    return state


async def _person_with_psn(repo: Repo, tg_id: int, account_id: str) -> int:
    person = await repo.ensure_user(tg_id, None)
    await repo.link_platform_account(person, Platform.PSN, account_id, "Me")
    return person


def _auth(repo: Repo) -> PsnPersonalAuth:
    return PsnPersonalAuth(repo, TokenCipher(KEY))


async def test_kept_for_the_account_it_opens(repo: Repo, sony) -> None:
    person = await _person_with_psn(repo, 1, "111")
    auth = _auth(repo)
    profile = await auth.add(person, "111", f'{{"npsso":"{GOOD}"}}')
    assert profile.account_id == "111"
    row = await repo.psn_token("111")
    assert row is not None and row.status == "active"
    assert GOOD.encode() not in row.npsso_enc  # encrypted
    assert await auth.client_for("111") == GOOD


async def test_the_format_is_checked_before_any_request(repo: Repo, sony) -> None:
    person = await _person_with_psn(repo, 1, "111")
    with pytest.raises(TokenFormatInvalid):
        await _auth(repo).add(person, "111", "not a token")
    assert sony["requests"] == 0


async def test_another_accounts_token_is_refused_and_not_stored(repo: Repo, sony) -> None:
    person = await _person_with_psn(repo, 1, "111")
    with pytest.raises(TokenMismatch) as refused:
        await _auth(repo).add(person, "111", OTHER)
    assert refused.value.online_id == "Them"
    assert await repo.psn_token("111") is None
    assert await repo.psn_token("222") is None


async def test_only_for_the_persons_own_account(repo: Repo, sony) -> None:
    await _person_with_psn(repo, 1, "111")
    stranger = await repo.ensure_user(2, None)
    with pytest.raises(TokenNotLinked):
        await _auth(repo).add(stranger, "111", GOOD)
    assert sony["requests"] == 0


async def test_a_refused_or_unreachable_token_is_not_stored(repo: Repo, sony) -> None:
    person = await _person_with_psn(repo, 1, "111")
    sony["refuse"] = True
    with pytest.raises(TokenRefused):
        await _auth(repo).add(person, "111", GOOD)
    sony["refuse"], sony["down"] = False, True
    with pytest.raises(TokenUnavailable):
        await _auth(repo).add(person, "111", GOOD)
    assert await repo.psn_token("111") is None


async def test_unlinking_deletes_the_token(repo: Repo, sony) -> None:
    person = await _person_with_psn(repo, 1, "111")
    await _auth(repo).add(person, "111", GOOD)
    await repo.unlink_account(person, Platform.PSN, "111")
    await repo.link_platform_account(person, Platform.PSN, "111", "Me")
    assert await repo.psn_token("111") is None


async def test_a_takeover_leaves_the_token_behind(repo: Repo, sony) -> None:
    person = await _person_with_psn(repo, 1, "111")
    auth = _auth(repo)
    await auth.add(person, "111", GOOD)
    taker = await repo.ensure_user(2, None)
    await repo.link_platform_account(taker, Platform.PSN, "111", "Me")
    assert await repo.psn_token("111") is None
    assert await auth.client_for("111") is None
    assert await repo.forget_unheld_psn_tokens() == 1


async def test_a_dead_token_falls_back_and_tells_its_owner_once(repo: Repo, sony) -> None:
    person = await _person_with_psn(repo, 1, "111")
    auth = _auth(repo)
    told: list[tuple[int, str]] = []

    async def on_dead(person_id: int, account_id: str) -> None:
        told.append((person_id, account_id))

    auth.on_dead = on_dead
    await auth.add(person, "111", GOOD)
    before = await repo.get_app_setting("psn_key_status")
    sony["refuse"] = True
    await auth.check_all()
    await auth.mark_dead("111", "refused again")
    assert told == [(person, "111")]
    assert await auth.client_for("111") is None
    # The shared token's health is not this token's business.
    assert await repo.get_app_setting("psn_key_status") == before
    assert await repo.psn_token_counts() == (0, 1)


async def test_replacing_a_dead_token_brings_it_back(repo: Repo, sony) -> None:
    person = await _person_with_psn(repo, 1, "111")
    auth = _auth(repo)
    await auth.add(person, "111", GOOD)
    await auth.mark_dead("111", "refused")
    await auth.add(person, "111", GOOD)
    assert await repo.psn_token_counts() == (1, 0)


async def test_the_token_never_reaches_the_log(
    repo: Repo, sony, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    person = await _person_with_psn(repo, 1, "111")
    auth = _auth(repo)
    await auth.add(person, "111", GOOD)
    with pytest.raises(TokenMismatch):
        await auth.add(person, "111", OTHER)
    await auth.check_all()
    assert GOOD not in caplog.text and OTHER not in caplog.text


async def test_presence_reads_an_account_with_its_own_token(
    repo: Repo, sony, settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An account with a live token is asked with it, at its normal step; a
    refusal marks only that token dead and the next read is the shared one's."""
    from bot.poller import psn_presence as presence_module
    from bot.poller.psn_presence import PsnPresencePoller
    from bot.services.psn.auth import PsnAuth
    from bot.services.psn.client import PsnPresenceSnapshot

    person = await _person_with_psn(repo, 1, "111")
    cipher = TokenCipher(KEY)
    psn_auth = PsnAuth(repo, cipher)
    psn_auth.personal = PsnPersonalAuth(repo, cipher)

    async def shared() -> str:
        return "shared"

    monkeypatch.setattr(psn_auth, "get_client", shared)
    await psn_auth.personal.add(person, "111", GOOD)

    used: list[object] = []
    refuse = {"own": True}

    async def get_presence(client: object, account_id: str) -> PsnPresenceSnapshot:
        used.append(client)
        if client == GOOD and refuse["own"]:
            raise PsnTokenDeadError("refused")
        return PsnPresenceSnapshot(
            state="Offline", title_id=None, title_name=None, online_id="Me", device=None
        )

    monkeypatch.setattr(presence_module, "get_presence", get_presence)
    poller = PsnPresencePoller(settings, repo, psn_auth)
    await poller.tick()
    assert used == [GOOD]
    assert await repo.psn_token_counts() == (0, 1)
    await repo._conn.execute("DELETE FROM psn_presence_state")
    await repo._conn.commit()
    await poller.tick()
    assert used == [GOOD, "shared"]


class _Bot:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.edited: list[str] = []

    async def send_message(self, chat_id: int, text: str, **_: object) -> None:
        self.sent.append(text)

    async def edit_message_text(self, text: str, **_: object) -> None:
        self.edited.append(text)


class _Message:
    def __init__(self, tg_id: int, text: str) -> None:
        self.from_user = type("U", (), {"id": tg_id, "username": None})()
        self.text = text
        self.deleted = False

    async def delete(self) -> None:
        self.deleted = True


class _Fetcher:
    async def backfill(self, *_: object, **__: object) -> None:
        return None

    def expect_relink_catch_up(self, *_: object) -> None:
        pass


def _i18n():
    from bot.i18n import static_i18n

    return static_i18n("psn")


async def test_a_pasted_token_is_deleted_and_kept(repo: Repo, sony) -> None:
    from bot.handlers import awaiting
    from bot.handlers.psn_token import EXPECT, token_pasted
    from bot.services.psn.auth import PsnAuth

    person = await _person_with_psn(repo, 7, "111")
    psn_auth = PsnAuth(repo, TokenCipher(KEY))
    psn_auth.personal = PsnPersonalAuth(repo, TokenCipher(KEY))
    awaiting.expect(7, EXPECT + "111")
    bot, message = _Bot(), _Message(7, GOOD)
    await token_pasted(message, repo, psn_auth, _Fetcher(), bot, _i18n())  # type: ignore[arg-type]
    assert message.deleted
    assert (await repo.psn_token("111")).person_id == person  # type: ignore[union-attr]
    assert awaiting.expected(7) is None
    assert GOOD not in " ".join(bot.sent + bot.edited)


async def test_a_token_of_another_account_says_whose_it_is(repo: Repo, sony) -> None:
    from bot.handlers import awaiting
    from bot.handlers.psn_token import EXPECT, token_pasted
    from bot.services.psn.auth import PsnAuth

    await _person_with_psn(repo, 7, "111")
    psn_auth = PsnAuth(repo, TokenCipher(KEY))
    psn_auth.personal = PsnPersonalAuth(repo, TokenCipher(KEY))
    awaiting.expect(7, EXPECT + "111")
    bot = _Bot()
    await token_pasted(_Message(7, OTHER), repo, psn_auth, _Fetcher(), bot, _i18n())  # type: ignore[arg-type]
    assert "Them" in bot.sent[-1]
    assert await repo.psn_token("111") is None


async def test_an_account_is_linked_by_its_token(
    repo: Repo, sony, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The token tells the account; it is linked and the token kept, with no
    nickname and no trophy-privacy check (its own token reads hidden ones)."""
    from bot.handlers import awaiting
    from bot.handlers import psn as psn_handlers
    from bot.handlers.psn_token import EXPECT, token_pasted
    from bot.services.psn.auth import PsnAuth

    async def no_backfill(*_: object, **__: object) -> None:
        return None

    monkeypatch.setattr(psn_handlers, "run_psn", no_backfill)
    await repo.ensure_user(8, None)
    psn_auth = PsnAuth(repo, TokenCipher(KEY))
    psn_auth.personal = PsnPersonalAuth(repo, TokenCipher(KEY))
    awaiting.expect(8, EXPECT + "new")
    await token_pasted(_Message(8, GOOD), repo, psn_auth, _Fetcher(), _Bot(), _i18n())  # type: ignore[arg-type]
    person = await repo.person_id(8)
    [link] = await repo.platform_links_for(person, Platform.PSN)
    assert link.external_id == "111"
    assert (await repo.psn_token("111")).status == "active"  # type: ignore[union-attr]


async def test_the_token_screens_render(repo: Repo, sony) -> None:
    from bot.views.panel import render_account_menu
    from bot.views.psn_token import render_token

    person = await _person_with_psn(repo, 9, "111")
    menu = await render_account_menu(repo, 9, Platform.PSN, locale="ru")
    assert menu is not None and "общий токен" in menu.text
    none = await render_token(repo, person, "111", locale="ru")
    assert none is not None and "Что даёт" in none.text
    auth = _auth(repo)
    await auth.add(person, "111", GOOD)
    alive = await render_token(repo, person, "111", locale="en")
    assert alive is not None and "working" in alive.text
    await auth.mark_dead("111", "refused")
    dead = await render_token(repo, person, "111", locale="ru")
    assert dead is not None and "не работает" in dead.text
    menu = await render_account_menu(repo, 9, Platform.PSN, locale="ru")
    assert menu is not None and "⚠️" in str(menu.keyboard)
    assert await render_token(repo, person, "999", locale="ru") is None


async def test_a_token_in_the_nickname_prompt_is_linked_as_a_token(
    repo: Repo, sony, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The token's button sits under the nickname prompt: a token pasted
    there is deleted and linked as a token, never searched, logged or echoed."""
    from bot.handlers import awaiting
    from bot.handlers import psn as psn_handlers
    from bot.services.psn.auth import PsnAuth

    async def no_backfill(*_: object, **__: object) -> None:
        return None

    async def searched(*_: object) -> None:
        raise AssertionError("a token went to Sony's search")

    monkeypatch.setattr(psn_handlers, "run_psn", no_backfill)
    monkeypatch.setattr(psn_handlers, "resolve_profile", searched)
    await repo.ensure_user(9, None)
    psn_auth = PsnAuth(repo, TokenCipher(KEY))
    psn_auth.personal = PsnPersonalAuth(repo, TokenCipher(KEY))
    awaiting.expect(9, "psn")
    message, bot = _Message(9, f'{{"npsso":"{GOOD}"}}'), _Bot()
    with caplog.at_level(logging.DEBUG):
        await psn_handlers.psn_link_provided(
            message,
            repo,
            psn_auth,
            _Fetcher(),
            bot,
            _i18n(),  # type: ignore[arg-type]
        )
    assert message.deleted
    [link] = await repo.platform_links_for(await repo.person_id(9), Platform.PSN)
    assert link.external_id == "111"
    assert GOOD not in caplog.text
    assert all(GOOD not in text for text in bot.sent + bot.edited)


async def test_tokens_tried_too_often_are_refused(repo: Repo, sony) -> None:
    auth = PsnPersonalAuth(repo, TokenCipher(KEY))
    for _ in range(personal.ATTEMPTS_PER_WINDOW):
        await auth.identify(GOOD, 5)
    with pytest.raises(personal.TokenTooOften):
        await auth.identify(GOOD, 5)
    await auth.identify(GOOD, 6)  # another person's tries are their own
    assert personal.looks_like_token(GOOD) and not personal.looks_like_token("RideTheSun")
