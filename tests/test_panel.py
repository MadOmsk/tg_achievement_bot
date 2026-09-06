"""Panel text: Xbox/Steam login lines (SPEC 6.2, M-Steam-1)."""

from __future__ import annotations

from bot.db.repo import Repo
from bot.handlers.panel import render_panel

TG_ID = 1


async def test_no_accounts_shows_only_xbox_not_connected(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "someone")

    text, _markup = await render_panel(repo, TG_ID)

    assert "Вход XBOX: — не подключён" in text
    assert "Вход Steam" not in text


async def test_steam_linked_without_xbox_shows_both_lines(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "someone")
    await repo.link_platform_account(TG_ID, "steam", "76561197960287930", "Gabe")

    text, _markup = await render_panel(repo, TG_ID)

    assert "Вход XBOX: — не подключён" in text
    assert "Вход Steam: Gabe" in text


async def test_xbox_connected_without_steam_has_no_steam_line(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "someone")
    await repo.link_xbox_account(TG_ID, "xuid-1", "Igor", 1000)

    text, _markup = await render_panel(repo, TG_ID)

    assert "Вход XBOX:   " in text
    assert "Вход Steam" not in text


async def test_both_platforms_linked_show_both_lines(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "someone")
    await repo.link_xbox_account(TG_ID, "xuid-1", "Igor", 1000)
    await repo.link_platform_account(TG_ID, "steam", "76561197960287930", "Gabe")

    text, _markup = await render_panel(repo, TG_ID)

    assert "Вход XBOX:   " in text
    assert "Вход Steam:  Gabe" in text


async def test_psn_linked_gets_its_own_profile_button(repo: Repo) -> None:
    """Follow-up 2026-09-06 — the panel's "👤 Профиль" row, same as XBOX and
    Steam already had (2026-09-05)."""
    await repo.ensure_user(TG_ID, "someone")
    await repo.link_xbox_account(TG_ID, "xuid-1", "Igor", 1000)
    await repo.link_platform_account(TG_ID, "psn", "internal-account-id", "superomsk")

    _text, markup = await render_panel(repo, TG_ID)

    row = next(
        row
        for row in markup.inline_keyboard
        if any(b.callback_data == "psn:disconnectprompt" for b in row)
    )
    assert any(b.url == "https://my.playstation.com/profile/superomsk" for b in row)


async def test_show_profile_links_defaults_off(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "someone")
    await repo.link_xbox_account(TG_ID, "xuid-1", "Igor", 1000)

    _text, markup = await render_panel(repo, TG_ID)

    toggle = next(
        b for row in markup.inline_keyboard for b in row if b.callback_data == "panel:linkstoggle"
    )
    assert "нет" in toggle.text


async def test_show_profile_links_admin_default_applies_to_new_users(repo: Repo) -> None:
    """Repo.ensure_user reads app_settings['default_show_profile_links'] the
    same way subscribe() reads default_rarity_mode — an admin-picked
    starting point for someone who has never had a user_settings row
    before (Follow-up 2026-09-06)."""
    await repo.set_app_setting("default_show_profile_links", "1")
    await repo.ensure_user(TG_ID, "someone")
    await repo.link_xbox_account(TG_ID, "xuid-1", "Igor", 1000)

    _text, markup = await render_panel(repo, TG_ID)

    toggle = next(
        b for row in markup.inline_keyboard for b in row if b.callback_data == "panel:linkstoggle"
    )
    assert "да" in toggle.text
