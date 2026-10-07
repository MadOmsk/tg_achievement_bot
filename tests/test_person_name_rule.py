"""A person is their nickname in the app, else `id<person id>` (owner,
2026-10-07); the super-admin's cards list every way a person signs in."""

from __future__ import annotations

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from bot.db.repo import Repo
from bot.services.logins import logins_of
from bot.views.admin import render_user_card
from bot.web.mini_api import cors_middleware, setup_mini_api

ADMIN_TG = 500


async def test_a_person_without_a_username_is_named_when_a_platform_is_linked(
    repo: Repo,
) -> None:
    person = await repo.ensure_user(1, None)
    assert person is not None
    assert (await repo.get_user(person)).handle is None  # type: ignore[union-attr]

    await repo.link_platform_account(person, "steam", "76561190000000001", "Mad Omsk")

    user = await repo.get_user(person)
    assert user is not None and user.handle == "MadOmsk"


async def test_a_person_with_a_nickname_keeps_it_when_a_platform_is_linked(
    repo: Repo,
) -> None:
    person = await repo.ensure_user(1, "rider")
    assert person is not None
    await repo.link_platform_account(person, "steam", "76561190000000001", "Other")

    user = await repo.get_user(person)
    assert user is not None and user.handle == "rider"


async def test_logins_list_every_kind_linked_or_not(repo: Repo) -> None:
    telegram_only = await repo.ensure_user(188022193, "madomsk")
    by_email = await repo.create_email_person("ada@example.com")
    assert telegram_only is not None

    first = logins_of(await repo.get_user(telegram_only))  # type: ignore[arg-type]
    second = logins_of(await repo.get_user(by_email))  # type: ignore[arg-type]

    assert [(item.kind, item.linked) for item in first] == [("telegram", True), ("email", False)]
    assert (first[0].username, first[0].ident) == ("madomsk", "188022193")
    assert [(item.kind, item.linked) for item in second] == [("telegram", False), ("email", True)]
    assert second[1].ident == "ada@example.com"


async def test_the_bot_card_names_the_person_and_lists_the_logins(repo: Repo) -> None:
    person = await repo.ensure_user(188022193, "madomsk")
    assert person is not None
    await repo.link_platform_account(person, "steam", "76561190000000001", "Mad Omsk")

    text, _markup = await render_user_card(repo, person, locale="ru")

    assert text.startswith(f"👤 madomsk · id {person}\n")
    assert "  Telegram: @madomsk, id 188022193" in text
    assert "  Почта: — нет" in text
    assert "@188022193" not in text


async def test_the_mini_app_card_lists_the_same_logins(repo: Repo, settings) -> None:
    ada = await repo.create_email_person("ada@example.com")
    await repo.give_handle(ada)
    await repo.link_platform_account(ada, "steam", "76561190000000001", "AdaSteam")
    admin = await repo.ensure_user(ADMIN_TG, "boss")
    assert admin is not None
    settings.superadmin_tg_ids = [ADMIN_TG]
    app = web.Application(middlewares=[cors_middleware()])
    setup_mini_api(app, settings, repo)
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        token = await repo.create_session(admin, "test")
        client.session.cookie_jar.update_cookies({"ab_session": token})
        card = await (await client.get(f"/api/mini/admin/users/p{ada}")).json()
    finally:
        await client.close()

    assert card["logins"] == [
        {"kind": "telegram", "label": "Telegram", "linked": False, "value": None},
        {"kind": "email", "label": "Почта", "linked": True, "value": "ada@example.com"},
    ]
