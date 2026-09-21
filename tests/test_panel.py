"""Panel text: Xbox/Steam login lines (SPEC 6.2, M-Steam-1)."""

from __future__ import annotations

from bot.db.repo import Repo
from bot.views.panel import render_panel

TG_ID = 1


async def test_no_accounts_shows_only_xbox_not_connected(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "someone")

    text, _markup = (await render_panel(repo, TG_ID)).as_pair()

    assert "Вход XBOX:   — не подключён" in text
    assert "Вход Steam" not in text


async def test_steam_linked_without_xbox_shows_both_lines(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "someone")
    await repo.link_platform_account(TG_ID, "steam", "76561197960287930", "Gabe")

    text, _markup = (await render_panel(repo, TG_ID)).as_pair()

    assert "Вход XBOX:   — не подключён" in text
    assert "Вход Steam:  Gabe" in text


async def test_steam_or_psn_only_person_still_gets_the_full_settings_body(repo: Repo) -> None:
    """Found live (2026-09-09, screenshot comparison): a Steam/PSN-only
    person's panel used to be a completely different, stripped-down body —
    no publication/timezone rows, no "Мои чаты"/"Синхронизировать"/profile-
    links-toggle buttons at all — because render_panel/panel_keyboard both
    hard-gated the whole body and keyboard on Xbox specifically, a leftover
    from before Steam/PSN existed. Every row/button now degrades per-
    platform instead of the whole screen switching on Xbox alone."""
    await repo.ensure_user(TG_ID, "psnonly")
    await repo.link_platform_account(TG_ID, "psn", "acc-1", "PsnOnly")

    text, markup = (await render_panel(repo, TG_ID)).as_pair()

    assert "Публикация:" in text
    assert "Часовой пояс:" in text
    callback_datas = {b.callback_data for row in markup.inline_keyboard for b in row}
    assert "panel:tz" in callback_datas
    assert "panel:chatlist" in callback_datas
    assert "panel:sync" in callback_datas
    assert "panel:linkstoggle" in callback_datas


async def test_xbox_connected_without_steam_has_no_steam_line(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "someone")
    await repo.link_xbox_account(TG_ID, "xuid-1", "Igor", 1000)

    text, _markup = (await render_panel(repo, TG_ID)).as_pair()

    assert "Вход XBOX:   " in text
    assert "Вход Steam" not in text


async def test_both_platforms_linked_show_both_lines(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "someone")
    await repo.link_xbox_account(TG_ID, "xuid-1", "Igor", 1000)
    await repo.link_platform_account(TG_ID, "steam", "76561197960287930", "Gabe")

    text, _markup = (await render_panel(repo, TG_ID)).as_pair()

    assert "Вход XBOX:   " in text
    assert "Вход Steam:  Gabe" in text


async def test_steam_status_shows_visibility_and_when_it_was_checked(repo: Repo) -> None:
    """(2026-09-08) Shared with the admin card (`visibility_status_text`) —
    "when checked" only shows once a check has actually happened; a fresh
    link with no check yet stays at the bare "не проверено"."""
    await repo.ensure_user(TG_ID, "someone")
    await repo.link_platform_account(TG_ID, "steam", "76561197960287930", "Gabe")

    text, _markup = (await render_panel(repo, TG_ID)).as_pair()
    assert "❓ не проверено" in text

    await repo.set_achievements_visible(TG_ID, "steam", True)
    text, _markup = (await render_panel(repo, TG_ID)).as_pair()
    assert "✅ ачивки видны · " in text


async def test_psn_linked_gets_its_own_profile_button(repo: Repo) -> None:
    """Follow-up 2026-09-06 — the panel's "👤 Профиль" row, same as XBOX and
    Steam already had (2026-09-05)."""
    await repo.ensure_user(TG_ID, "someone")
    await repo.link_xbox_account(TG_ID, "xuid-1", "Igor", 1000)
    await repo.link_platform_account(TG_ID, "psn", "internal-account-id", "superomsk")

    _text, markup = (await render_panel(repo, TG_ID)).as_pair()

    row = next(
        row
        for row in markup.inline_keyboard
        if any(b.callback_data == "psn:disconnectprompt" for b in row)
    )
    assert any(b.url == "https://psnprofiles.com/superomsk" for b in row)


async def test_show_profile_links_defaults_off(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "someone")
    await repo.link_xbox_account(TG_ID, "xuid-1", "Igor", 1000)

    _text, markup = (await render_panel(repo, TG_ID)).as_pair()

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

    _text, markup = (await render_panel(repo, TG_ID)).as_pair()

    toggle = next(
        b for row in markup.inline_keyboard for b in row if b.callback_data == "panel:linkstoggle"
    )
    assert "да" in toggle.text


async def test_header_shows_identity_and_per_platform_counts_not_daily_totals(repo: Repo) -> None:
    """#18: the header now carries identity + lifetime per-platform counts,
    and the 24h/30d rows and "последние достижения" list are gone."""
    await repo.ensure_user(TG_ID, "madomsk")
    await repo.link_xbox_account(TG_ID, "xuid-1", "MadXbox", 12345)

    text, _markup = (await render_panel(repo, TG_ID)).as_pair()

    # Identity, not "gamertag · gamerscore" — and bare, no "@" (#51).
    assert text.splitlines()[0] == "👤 madomsk"
    assert "🟢 XBOX: MadXbox" in text
    assert "gamerscore 12" in text  # thousands() formatting of the profile value
    assert "Сегодня:" not in text
    assert "За месяц:" not in text
    assert "Последние достижения" not in text
    # Kept (#18 decisions): current presence and the timezone text line.
    assert "Сейчас:" in text
    assert "Часовой пояс:" in text


async def test_header_lists_every_connected_platform(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, None, "Igor", "Petrov")
    await repo.link_xbox_account(TG_ID, "xuid-1", "MadXbox", 1000)
    await repo.link_platform_account(TG_ID, "steam", "76561197960287930", "SteamNick")
    await repo.link_platform_account(TG_ID, "psn", "acc-1", "PsnNick")
    await repo.set_psn_trophy_level(TG_ID, 42)

    text, _markup = (await render_panel(repo, TG_ID)).as_pair()

    assert text.splitlines()[0] == "👤 Igor Petrov"
    assert "🟢 XBOX: MadXbox" in text
    assert "⚫ Steam: SteamNick" in text
    # "PlayStation:", not "PSN:" — same label /stats' own shared header uses
    # (PLATFORM_LABEL, services/achievements.py) now that both are built by
    # the same function (#5).
    assert "🔵 PlayStation: PsnNick" in text
    assert "уровень 42" in text


async def test_now_row_names_the_platform_the_person_is_actually_playing_on(
    repo: Repo,
) -> None:
    """Issue #1's tail: the row used to read Xbox's presence only, so
    somebody playing on PlayStation looked offline on their own panel."""
    await repo.ensure_user(TG_ID, "someone")
    await repo.link_xbox_account(TG_ID, "xuid-1", "Igor", 1000)
    await repo.link_platform_account(TG_ID, "psn", "acc-1", "PsnOnly")
    await repo.save_presence_state("xuid-1", "Online", None, None, changed=True)
    await repo.save_psn_presence_state(
        "acc-1", "Online", "CUSA00001", "Ghost of Tsushima", changed=True
    )

    text, _markup = (await render_panel(repo, TG_ID)).as_pair()

    assert "Сейчас:      🔵 PlayStation  ·  играет — Ghost of Tsushima" in text


async def test_a_steam_only_person_gets_a_now_row_at_all(repo: Repo) -> None:
    """It was gated on `user.xuid`, so this row was simply absent for
    anyone without an Xbox account — the last Xbox-gated row on the panel."""
    await repo.ensure_user(TG_ID, "someone")
    await repo.link_platform_account(TG_ID, "steam", "76561197960287930", "Gabe")
    await repo.save_steam_presence_state("76561197960287930", 1, "570", "Dota 2", changed=True)

    text, _markup = (await render_panel(repo, TG_ID)).as_pair()

    assert "Сейчас:      ⚫ Steam  ·  играет — Dota 2" in text


async def test_an_offline_now_row_names_no_platform(repo: Repo) -> None:
    """Same call /online's own rows make (#51): once the answer is
    "offline", there is no "where" left for a platform name to answer, and
    picking one of three equally-offline platforms says nothing."""
    await repo.ensure_user(TG_ID, "someone")
    await repo.link_platform_account(TG_ID, "steam", "76561197960287930", "Gabe")
    await repo.save_steam_presence_state("76561197960287930", 0, None, None, changed=True)

    text, _markup = (await render_panel(repo, TG_ID)).as_pair()

    assert "Сейчас:      не в сети" in text
    assert "Steam  ·  не в сети" not in text


async def test_panel_steam_row_uses_naming_chain_fallback(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "someone")
    await repo.link_platform_account(TG_ID, "steam", "76561197960287930", None)
    await repo.set_platform_secondary_name(TG_ID, "steam", "gaben_vanity")

    text, _ = (await render_panel(repo, TG_ID)).as_pair()
    assert "Вход Steam:  gaben_vanity" in text


async def test_panel_psn_row_uses_naming_chain_fallback(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "someone")
    await repo.link_platform_account(TG_ID, "psn", "2130000000000000000", None)
    await repo.set_platform_secondary_name(TG_ID, "psn", "old_psn_tag")

    text, _ = (await render_panel(repo, TG_ID)).as_pair()
    assert "Вход PSN:    old_psn_tag" in text


async def test_panel_has_delete_account_button_above_refresh(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "someone")
    _text, markup = (await render_panel(repo, TG_ID)).as_pair()
    rows = markup.inline_keyboard
    delete_i = next(
        i for i, r in enumerate(rows) if any(b.callback_data == "panel:delete_account" for b in r)
    )
    refresh_i = next(
        i for i, r in enumerate(rows) if any(b.callback_data == "panel:refresh" for b in r)
    )
    assert refresh_i == delete_i + 1


async def test_panel_delete_account_screens() -> None:
    from bot.views.panel import render_panel_delete_confirm_1, render_panel_delete_confirm_2

    screen1 = await render_panel_delete_confirm_1(locale="ru")
    cb1 = [b.callback_data for row in screen1.keyboard.inline_keyboard for b in row]
    assert "panel:delete:step1" in cb1
    assert "panel:refresh" in cb1

    screen2 = await render_panel_delete_confirm_2(locale="ru")
    cb2 = [b.callback_data for row in screen2.keyboard.inline_keyboard for b in row]
    assert "panel:delete:step2" in cb2
    assert "panel:refresh" in cb2


async def test_panel_delete_account_flow(repo: Repo, i18n, monkeypatch) -> None:
    from types import SimpleNamespace

    from bot.handlers import panel as panel_handlers

    await repo.ensure_user(TG_ID, "someone")
    edits: list[tuple[str, object]] = []

    async def fake_edit(callback, text, markup=None, **kwargs):
        edits.append((text, markup))

    monkeypatch.setattr(panel_handlers, "safe_edit", fake_edit)

    class _Cb:
        def __init__(self, data: str, tg_id: int):
            self.data = data
            self.from_user = SimpleNamespace(id=tg_id)
            self.answers: list[tuple[str, bool]] = []

        async def answer(self, text: str = "", show_alert: bool = False):
            self.answers.append((text, show_alert))

    # Step 1
    cb1 = _Cb("panel:delete_account", TG_ID)
    await panel_handlers.panel_delete_account_step1(cb1, i18n)  # type: ignore[arg-type]
    assert len(edits) == 1
    assert "panel:delete:step1" in [
        b.callback_data for row in edits[-1][1].inline_keyboard for b in row
    ]

    # Step 2
    cb2 = _Cb("panel:delete:step1", TG_ID)
    await panel_handlers.panel_delete_account_step2(cb2, i18n)  # type: ignore[arg-type]
    assert len(edits) == 2
    assert "panel:delete:step2" in [
        b.callback_data for row in edits[-1][1].inline_keyboard for b in row
    ]

    # Confirm
    cb3 = _Cb("panel:delete:step2", TG_ID)
    await panel_handlers.panel_delete_account_confirmed(cb3, repo, i18n)  # type: ignore[arg-type]
    assert len(edits) == 3
    assert edits[-1][1] is None  # no keyboard on final message
    assert cb3.answers[0][1] is True  # show_alert=True
    assert await repo.get_user(TG_ID) is None
