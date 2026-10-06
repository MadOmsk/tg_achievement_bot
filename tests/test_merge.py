"""Merging two people into one (#162): the same human signed up by email and by
Telegram, and asks for the two to be one."""

from __future__ import annotations

import hashlib
import hmac
import time
from datetime import timedelta
from types import SimpleNamespace

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from bot.db.repo import AchievementRow, Repo
from bot.services.merge import MergeRefused, PeopleMerge
from bot.util import utcnow
from bot.web.mini_api import cors_middleware, setup_mini_api


def _row(achievement_id: str) -> AchievementRow:
    return AchievementRow(
        title_id="440",
        achievement_id=achievement_id,
        name=achievement_id,
        description="d",
        icon_url=None,
        unlocked_at=(utcnow() - timedelta(hours=1)).isoformat(timespec="seconds"),
        gamerscore=0,
        rarity_percent=50.0,
        platform="steam",
        title_name="TF2",
    )


def _merge(repo: Repo, admins: set[int] = frozenset()) -> PeopleMerge:
    return PeopleMerge(repo, lambda tg: tg is not None and tg in admins)


async def _email_person(repo: Repo, email: str = "ada@example.com") -> int:
    person = await repo.create_email_person(email)
    await repo.give_handle(person)
    return person


async def test_nothing_to_choose_moves_everything(repo: Repo) -> None:
    ada = await _email_person(repo)
    await repo.link_platform_account(ada, "steam", "s-ada", "AdaSteam")
    await repo.insert_new_achievements_steam(ada, "s-ada", [_row("a1")], is_backfill=False)

    tg = await repo.ensure_user(77, "ada_tg")
    friend = await repo.ensure_user(88, "friend")
    assert tg and friend
    await repo.link_xbox_account(tg, "xuid-ada", "AdaX", 100)
    await repo.save_refresh_token(tg, b"secret-token")
    await repo.upsert_chat(-100, "Chat", 77)
    await repo.subscribe(-100, tg)
    await repo.follow(tg, friend)
    await repo.follow(friend, tg)
    await repo.follow(tg, ada)  # becomes a self-follow: must vanish
    await repo.add_notification(tg, "new_follower", {"person_id": friend, "name": "friend"})
    await repo.create_session(tg, "phone")

    await _merge(repo).merge(ada, tg)

    assert await repo.get_user(tg) is None
    user = await repo.get_user(ada)
    assert user is not None
    assert (user.tg_id, user.email, user.xuid) == (77, "ada@example.com", "xuid-ada")
    assert (await repo.get_token(ada)) is not None
    assert await repo.get_platform_link(ada, "steam") is not None
    # History rides with the account.
    assert await repo.platform_achievement_count(ada, "steam") == 1
    assert await repo.chats_of_user(ada) == ["Chat"]
    assert (await repo.relation(ada, friend)).friends
    cursor = await repo._conn.execute(
        "SELECT COUNT(*) FROM follows WHERE follower_id = followee_id"
    )
    assert (await cursor.fetchone())[0] == 0
    assert len(await repo.notifications_of(ada)) == 1
    cursor = await repo._conn.execute(
        "SELECT COUNT(*) FROM web_sessions WHERE person_id = ?", (ada,)
    )
    assert (await cursor.fetchone())[0] == 1


async def test_two_xbox_accounts_are_a_choice_and_the_login_follows(repo: Repo) -> None:
    ada = await _email_person(repo)
    await repo.link_xbox_account(ada, "xuid-old", "Old", 1)
    await repo.save_refresh_token(ada, b"old-token")
    tg = await repo.ensure_user(77, "ada_tg")
    assert tg
    await repo.link_xbox_account(tg, "xuid-new", "New", 2)
    await repo.save_refresh_token(tg, b"new-token")
    merge = _merge(repo)

    preview = await merge.preview(ada, tg)
    assert preview is not None and set(preview["conflicts"]) == {"xbox"}
    with pytest.raises(MergeRefused):
        await merge.merge(ada, tg, {})  # a conflict must be answered

    await merge.merge(ada, tg, {"xbox": "absorb"})
    user = await repo.get_user(ada)
    assert user is not None and user.xuid == "xuid-new"
    token = await repo.get_token(ada)
    assert token is not None and token.refresh_token_enc == b"new-token"
    # The account not chosen is unlinked, not erased: its history waits.
    cursor = await repo._conn.execute(
        "SELECT is_active FROM account_links WHERE external_id = 'xuid-old'"
    )
    assert (await cursor.fetchone())[0] == 0


async def test_psn_accounts_add_up_to_the_limit(repo: Repo) -> None:
    ada = await _email_person(repo)
    tg = await repo.ensure_user(77, "ada_tg")
    assert tg
    for person, ids in ((ada, ("p1", "p2")), (tg, ("p3", "p4"))):
        for account in ids:
            await repo.link_platform_account(person, "psn", account, account.upper())
    merge = _merge(repo)
    preview = await merge.preview(ada, tg)
    assert preview is not None and preview["conflicts"]["psn"]["max"] == 3
    with pytest.raises(MergeRefused):
        await merge.merge(ada, tg, {"psn": ["p1", "p2", "p3", "p4"]})
    await merge.merge(ada, tg, {"psn": ["p1", "p3", "p4"]})
    links = await repo.platform_links_for(ada, "psn")
    assert sorted(link.external_id for link in links) == ["p1", "p3", "p4"]


async def test_two_telegrams_and_a_super_admin(repo: Repo) -> None:
    ada = await repo.ensure_user(11, "ada_one")
    tg = await repo.ensure_user(22, "ada_two")
    assert ada and tg
    await repo.set_email(tg, "ada@example.com")
    await repo.upsert_chat(-100, "Chat", 22)
    await repo.record_chat_seen(-100, 22)

    # 22 is a super-admin: theirs is never the Telegram let go.
    with pytest.raises(MergeRefused) as refused:
        await _merge(repo, admins={22}).merge(ada, tg, {"telegram": "keep"})
    assert refused.value.reason == "admin"
    assert await repo.get_user(tg) is not None  # nothing happened

    await _merge(repo).merge(ada, tg, {"telegram": "keep"})
    user = await repo.get_user(ada)
    assert user is not None and (user.tg_id, user.email) == (11, "ada@example.com")
    # The Telegram let go is nobody's, as after removing it.
    assert await repo.person_id(22) is None
    assert await repo.user_chats(22) == []


async def test_settings_come_from_the_side_used_last(repo: Repo) -> None:
    ada = await _email_person(repo)
    tg = await repo.ensure_user(77, "ada_tg")
    assert tg
    await repo.update_user_settings(ada, rarity_mode="rare")
    await repo.update_user_settings(tg, rarity_mode="hidden", locale="en")
    await repo._conn.execute(
        "UPDATE users SET updated_at = '2000-01-01T00:00:00' WHERE id = ?", (ada,)
    )
    await repo._conn.execute(
        "UPDATE users SET updated_at = '2030-01-01T00:00:00' WHERE id = ?", (tg,)
    )
    await _merge(repo).merge(ada, tg)
    settings = await repo.get_user_settings(ada)
    assert settings is not None and (settings.rarity_mode, settings.locale) == ("hidden", "en")


def _widget(token: str, tg_id: int) -> dict[str, str]:
    fields = {
        "id": str(tg_id),
        "first_name": "T",
        "username": "t",
        "auth_date": str(int(time.time())),
    }
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hashlib.sha256(token.encode()).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return fields


async def test_the_app_offers_and_performs_the_merge(repo: Repo, settings) -> None:
    ada = await _email_person(repo)
    tg = await repo.ensure_user(77, "ada_tg")
    assert tg
    await repo.link_xbox_account(tg, "xuid-1", "AdaX", 1)
    app = web.Application(middlewares=[cors_middleware()])
    setup_mini_api(app, settings, repo)
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        client.session.cookie_jar.update_cookies(
            {"ab_session": await repo.create_session(ada, "t")}
        )
        token = settings.bot_token.get_secret_value()
        offered = await client.post("/api/mini/me/telegram", json=_widget(token, 77))
        body = await offered.json()
        assert (offered.status, body["error"]) == (409, "taken")
        assert body["merge"]["absorb"]["accounts"]["xbox"][0]["id"] == "xuid-1"
        assert (await (await client.get("/api/mini/me/logins")).json())["merge_pending"] is True

        done = await client.post("/api/mini/me/merge", json={"choices": {}})
        assert done.status == 200
        assert (await done.json())["telegram"]["linked"] is True
        assert await repo.get_user(tg) is None
        assert (await (await client.get("/api/mini/me/merge")).json())["merge"] is None
        again = await client.post("/api/mini/me/merge", json={})
        assert (await again.json())["error"] == "expired"
    finally:
        await client.close()


async def test_a_telegram_link_folds_in_a_person_with_nothing_to_lose(repo: Repo) -> None:
    from bot.handlers.connect import start_with_payload

    ada = await _email_person(repo)
    merge = _merge(repo)
    sent: list[str] = []

    class _Msg:
        from_user = SimpleNamespace(id=77, username="ada_tg")
        chat = SimpleNamespace(id=77, type="private")

        async def answer(self, text: str, **_kw) -> None:
            sent.append(text)

    i18n = SimpleNamespace(get=lambda key, **_kw: key)
    command = SimpleNamespace(args=f"link_{merge.link_token(ada)}")
    await start_with_payload(
        message=_Msg(),  # type: ignore[arg-type]
        command=command,  # type: ignore[arg-type]
        repo=repo,
        connect=None,  # type: ignore[arg-type]
        settings=None,  # type: ignore[arg-type]
        psn_auth=None,  # type: ignore[arg-type]
        steam_auth=None,  # type: ignore[arg-type]
        bot=None,  # type: ignore[arg-type]
        i18n=i18n,  # type: ignore[arg-type]
        merge=merge,
    )
    # /start made a person for this Telegram a moment ago; it is folded in.
    assert sent == ["connect-link-done"]
    assert await repo.person_id(77) == ada

    # A token is good once.
    await start_with_payload(
        message=_Msg(),  # type: ignore[arg-type]
        command=command,  # type: ignore[arg-type]
        repo=repo,
        connect=None,  # type: ignore[arg-type]
        settings=None,  # type: ignore[arg-type]
        psn_auth=None,  # type: ignore[arg-type]
        steam_auth=None,  # type: ignore[arg-type]
        bot=None,  # type: ignore[arg-type]
        i18n=i18n,  # type: ignore[arg-type]
        merge=merge,
    )
    assert sent[-1] == "connect-link-expired"


async def test_a_telegram_link_to_a_real_person_waits_for_the_app(repo: Repo) -> None:
    from bot.handlers.connect import start_with_payload

    ada = await _email_person(repo)
    tg = await repo.ensure_user(77, "ada_tg")
    assert tg
    await repo.link_platform_account(tg, "steam", "s-77", "AdaSteam")
    merge = _merge(repo)
    sent: list[str] = []

    class _Msg:
        from_user = SimpleNamespace(id=77, username="ada_tg")
        chat = SimpleNamespace(id=77, type="private")

        async def answer(self, text: str, **_kw) -> None:
            sent.append(text)

    await start_with_payload(
        message=_Msg(),  # type: ignore[arg-type]
        command=SimpleNamespace(args=f"link_{merge.link_token(ada)}"),  # type: ignore[arg-type]
        repo=repo,
        connect=None,  # type: ignore[arg-type]
        settings=None,  # type: ignore[arg-type]
        psn_auth=None,  # type: ignore[arg-type]
        steam_auth=None,  # type: ignore[arg-type]
        bot=None,  # type: ignore[arg-type]
        i18n=SimpleNamespace(get=lambda key, **_kw: key),  # type: ignore[arg-type]
        merge=merge,
    )
    # Opening somebody's link is not consent: the Telegram side is asked first,
    # and nothing waits in the app until it says yes.
    assert sent == ["connect-link-merge-confirm"]
    assert merge.pending(ada) is None
    assert await repo.person_id(77) == tg

    from bot.handlers.connect import link_merge_answer

    edited: list[str] = []

    async def _edit(_callback, text, _markup=None, **_kw) -> None:
        edited.append(text)

    import bot.handlers.connect as connect_module

    connect_module.safe_edit, original = _edit, connect_module.safe_edit
    try:

        async def _answer(*_a, **_kw) -> None:
            return None

        i18n = SimpleNamespace(get=lambda key, **_kw: key)
        # Somebody else's Telegram cannot answer for this one.
        stranger = SimpleNamespace(
            data="lnkm:yes", from_user=SimpleNamespace(id=78), answer=_answer
        )
        await link_merge_answer(stranger, repo, merge, i18n)  # type: ignore[arg-type]
        assert merge.pending(ada) is None and edited[-1] == "connect-link-expired"

        yes = SimpleNamespace(data="lnkm:yes", from_user=SimpleNamespace(id=77), answer=_answer)
        await link_merge_answer(yes, repo, merge, i18n)  # type: ignore[arg-type]
        assert edited[-1] == "connect-link-merge-in-app"
        assert merge.pending(ada) == tg
        assert await repo.person_id(77) == tg  # still the app person's word to give
    finally:
        connect_module.safe_edit = original


async def test_a_telegram_link_can_be_turned_down_in_the_bot(repo: Repo) -> None:
    from bot.handlers.connect import link_merge_answer, start_with_payload

    ada = await _email_person(repo)
    tg = await repo.ensure_user(77, "ada_tg")
    await repo.link_platform_account(tg, "steam", "s-77", "AdaSteam")
    merge = _merge(repo)

    class _Msg:
        from_user = SimpleNamespace(id=77, username="ada_tg")
        chat = SimpleNamespace(id=77, type="private")

        async def answer(self, text: str, **_kw) -> None:
            return None

    i18n = SimpleNamespace(get=lambda key, **_kw: key)
    await start_with_payload(
        message=_Msg(),  # type: ignore[arg-type]
        command=SimpleNamespace(args=f"link_{merge.link_token(ada)}"),  # type: ignore[arg-type]
        repo=repo,
        connect=None,  # type: ignore[arg-type]
        settings=None,  # type: ignore[arg-type]
        psn_auth=None,  # type: ignore[arg-type]
        steam_auth=None,  # type: ignore[arg-type]
        bot=None,  # type: ignore[arg-type]
        i18n=i18n,  # type: ignore[arg-type]
        merge=merge,
    )

    async def _answer(*_a, **_kw) -> None:
        return None

    no = SimpleNamespace(
        data="lnkm:no", from_user=SimpleNamespace(id=77), answer=_answer, message=None
    )
    await link_merge_answer(no, repo, merge, i18n)  # type: ignore[arg-type]
    assert merge.pending(ada) is None
    # Asked once: a later yes finds nothing to agree to.
    yes = SimpleNamespace(
        data="lnkm:yes", from_user=SimpleNamespace(id=77), answer=_answer, message=None
    )
    await link_merge_answer(yes, repo, merge, i18n)  # type: ignore[arg-type]
    assert merge.pending(ada) is None


async def test_the_link_to_the_bot_carries_a_one_time_token(repo: Repo, settings) -> None:
    ada = await _email_person(repo)
    app = web.Application(middlewares=[cors_middleware()])
    setup_mini_api(app, settings, repo)
    app["mini_bot_username"] = "achbot"
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        client.session.cookie_jar.update_cookies(
            {"ab_session": await repo.create_session(ada, "t")}
        )
        url = (await (await client.get("/api/mini/me/telegram/link")).json())["url"]
        assert url.startswith("https://t.me/achbot?start=link_")
        token = url.split("link_", 1)[1]
        assert app["mini_merge"].redeem(token) == ada
        assert app["mini_merge"].redeem(token) is None  # once

        await repo.set_telegram(ada, 77)
        already = await client.get("/api/mini/me/telegram/link")
        assert (await already.json())["error"] == "already"
    finally:
        await client.close()
