"""Hidden achievements on a platform screen (#95): an explanation in the text,
"how to open them" as the top button, and a screen with the steps whose
"check again" reads the account anew."""

from __future__ import annotations

from bot.db.repo import Repo
from bot.services.profile_links import STEAM_PRIVACY_URL
from bot.views.panel import render_account_menu, render_privacy_howto

TG = 7


def _callbacks(screen) -> list[str | None]:
    return [b.callback_data for row in screen.keyboard.inline_keyboard for b in row]


async def test_hidden_steam_explains_itself_with_the_way_out_on_top(repo: Repo) -> None:
    await repo.ensure_user(TG, "igor")
    await repo.link_platform_account(
        await repo.person_id(TG), "steam", "76561197981065056", "Mad Omsk"
    )
    await repo.set_achievements_visible(await repo.person_id(TG), "steam", False)

    screen = await render_account_menu(repo, TG, "steam", locale="ru")

    assert screen is not None
    assert "Достижения в профиле Steam скрыты" in screen.text
    assert screen.keyboard.inline_keyboard[0][0].callback_data == "panel:howto:steam"


async def test_visible_steam_has_no_howto(repo: Repo) -> None:
    await repo.ensure_user(TG, "igor")
    await repo.link_platform_account(
        await repo.person_id(TG), "steam", "76561197981065056", "Mad Omsk"
    )
    await repo.set_achievements_visible(await repo.person_id(TG), "steam", True)

    screen = await render_account_menu(repo, TG, "steam", locale="ru")

    assert screen is not None
    assert "скрыты" not in screen.text
    assert "panel:howto:steam" not in _callbacks(screen)


async def test_only_the_hidden_psn_account_gets_a_howto(repo: Repo) -> None:
    await repo.ensure_user(TG, "igor")
    await repo.link_platform_account(await repo.person_id(TG), "psn", "acc-1", "SuperOmsk")
    await repo.link_platform_account(await repo.person_id(TG), "psn", "acc-2", "greyjedi2")
    await repo.set_achievements_visible(await repo.person_id(TG), "psn", True, external_id="acc-1")
    await repo.set_achievements_visible(await repo.person_id(TG), "psn", False, external_id="acc-2")

    screen = await render_account_menu(repo, TG, "psn", locale="ru")

    assert screen is not None
    assert "У аккаунта greyjedi2 трофеи скрыты" in screen.text
    assert "SuperOmsk трофеи скрыты" not in screen.text
    assert screen.keyboard.inline_keyboard[0][0].callback_data == "panel:howto:psn:acc-2"
    assert "panel:howto:psn:acc-1" not in _callbacks(screen)


async def test_the_howto_screens_check_again_and_go_back(repo: Repo) -> None:
    await repo.ensure_user(TG, "igor")
    await repo.link_platform_account(
        await repo.person_id(TG), "steam", "76561197981065056", "Mad Omsk"
    )
    await repo.link_platform_account(await repo.person_id(TG), "psn", "acc-2", "greyjedi2")

    steam = await render_privacy_howto(repo, TG, "steam", None, locale="ru")
    psn = await render_privacy_howto(repo, TG, "psn", "acc-2", locale="en")

    assert steam is not None and psn is not None
    assert STEAM_PRIVACY_URL in steam.text
    assert steam.keyboard.inline_keyboard[0][0].url == STEAM_PRIVACY_URL
    assert _callbacks(steam)[1:] == ["bf:steam", "panel:acc:steam"]
    assert "greyjedi2" in psn.text
    assert _callbacks(psn) == ["bf:psn:acc-2", "panel:acc:psn"]


async def test_a_howto_for_an_account_gone_is_none(repo: Repo) -> None:
    await repo.ensure_user(TG, "igor")
    assert await render_privacy_howto(repo, TG, "psn", "nope", locale="ru") is None
    assert await render_privacy_howto(repo, TG, "steam", None, locale="ru") is None
