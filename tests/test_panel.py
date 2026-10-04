"""Panel text: Xbox/Steam login lines (SPEC 6.2, M-Steam-1)."""

from __future__ import annotations

from bot.db.repo import Repo
from bot.views.panel import render_account_menu, render_panel

TG_ID = 1


async def test_no_accounts_shows_every_platform_not_connected(repo: Repo) -> None:
    """Every platform has its login row, connected or not (owner, 2026-09-30)."""
    await repo.ensure_user(TG_ID, "someone")

    text, _markup = (await render_panel(repo, TG_ID)).as_pair()

    assert "Вход XBOX: 🔘 не подключён" in text
    assert "Вход Steam: 🔘 не подключён" in text
    assert "Вход PSN: 🔘 не подключён" in text


async def test_steam_linked_without_xbox_shows_both_lines(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "someone")
    await repo.link_platform_account(
        await repo.person_id(TG_ID), "steam", "76561197960287930", "Gabe"
    )

    text, _markup = (await render_panel(repo, TG_ID)).as_pair()

    assert "Вход XBOX: 🔘 не подключён" in text
    assert "Вход Steam: ❓ не проверено" in text
    assert "Gabe" not in text.split("\n\n", 1)[1]  # the nickname stays in the header


async def test_steam_or_psn_only_person_still_gets_the_full_settings_body(repo: Repo) -> None:
    """Found live (2026-09-09, screenshot comparison): a Steam/PSN-only
    person's panel used to be a completely different, stripped-down body —
    no publication/timezone rows, no "Мои чаты"/"Синхронизировать"/profile-
    links-toggle buttons at all — because render_panel/panel_keyboard both
    hard-gated the whole body and keyboard on Xbox specifically, a leftover
    from before Steam/PSN existed. Every row/button now degrades per-
    platform instead of the whole screen switching on Xbox alone."""
    await repo.ensure_user(TG_ID, "psnonly")
    await repo.link_platform_account(await repo.person_id(TG_ID), "psn", "acc-1", "PsnOnly")

    text, markup = (await render_panel(repo, TG_ID)).as_pair()

    assert "Публикация:" in text
    assert "Часовой пояс:" not in text  # on its button (owner, 2026-09-30)
    callback_datas = {b.callback_data for row in markup.inline_keyboard for b in row}
    assert "panel:tz" in callback_datas
    assert "panel:chatlist" in callback_datas
    assert "panel:sync" in callback_datas
    assert "panel:linkstoggle" not in callback_datas


async def test_xbox_connected_without_steam_has_no_steam_line(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "someone")
    await repo.link_xbox_account(await repo.person_id(TG_ID), "xuid-1", "Igor", 1000)

    text, _markup = (await render_panel(repo, TG_ID)).as_pair()

    assert "Вход XBOX: " in text
    assert "Вход Steam: 🔘 не подключён" in text


async def test_both_platforms_linked_show_both_lines(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "someone")
    await repo.link_xbox_account(await repo.person_id(TG_ID), "xuid-1", "Igor", 1000)
    await repo.link_platform_account(
        await repo.person_id(TG_ID), "steam", "76561197960287930", "Gabe"
    )

    text, _markup = (await render_panel(repo, TG_ID)).as_pair()

    assert "Вход XBOX: " in text
    assert "Вход Steam: ❓ не проверено" in text


async def test_steam_status_shows_visibility_and_when_it_was_checked(repo: Repo) -> None:
    """(2026-09-08) Shared with the admin card (`visibility_status_text`) —
    "when checked" only shows once a check has actually happened; a fresh
    link with no check yet stays at the bare "не проверено"."""
    await repo.ensure_user(TG_ID, "someone")
    await repo.link_platform_account(
        await repo.person_id(TG_ID), "steam", "76561197960287930", "Gabe"
    )

    text, _markup = (await render_panel(repo, TG_ID)).as_pair()
    assert "❓ не проверено" in text

    await repo.set_achievements_visible(await repo.person_id(TG_ID), "steam", True)
    text, _markup = (await render_panel(repo, TG_ID)).as_pair()
    # Only whether all is well — not when it was checked (owner, 2026-09-30).
    assert "Вход Steam: ✅ ачивки видны\n" in text


async def test_psn_linked_gets_its_own_profile_button(repo: Repo) -> None:
    """Follow-up 2026-09-06 — a PSN profile button, now on the PSN screen
    behind the panel's platform button (#10), named "PSN: nick"."""
    await repo.ensure_user(TG_ID, "someone")
    await repo.link_xbox_account(await repo.person_id(TG_ID), "xuid-1", "Igor", 1000)
    await repo.link_platform_account(
        await repo.person_id(TG_ID), "psn", "internal-account-id", "superomsk"
    )

    screen = await render_account_menu(repo, TG_ID, "psn", locale="ru")

    assert screen is not None
    buttons = [b for row in screen.keyboard.inline_keyboard for b in row]
    profile = next(b for b in buttons if b.url)
    assert profile.url == "https://psnprofiles.com/superomsk"
    assert profile.text == "👤 PSN: superomsk"
    assert "psn:unlink:internal-account-id" in [b.callback_data for b in buttons]


async def test_several_psn_accounts_each_get_a_line_and_their_own_switch(repo: Repo) -> None:
    """#10: one header and login line per PSN account; the panel's switch
    reads "Частично" when only some of them post, and the publication row
    names the muted one."""
    await repo.ensure_user(TG_ID, "someone")
    await repo.link_platform_account(await repo.person_id(TG_ID), "psn", "acc-1", "SuperOmsk")
    await repo.link_platform_account(await repo.person_id(TG_ID), "psn", "acc-2", "OmskSecond")
    await repo.set_account_publishes(await repo.person_id(TG_ID), "psn", "acc-2", False)
    await repo.upsert_chat(-100, "XBOX CG", None)
    await repo.subscribe(-100, await repo.person_id(TG_ID))

    text, markup = (await render_panel(repo, TG_ID)).as_pair()

    assert "Вход PSN1: " in text and "Вход PSN2: " in text
    assert text.index("SuperOmsk") < text.index("OmskSecond")
    assert "без PSN: OmskSecond" in text
    buttons = {b.callback_data: b.text for row in markup.inline_keyboard for b in row}
    assert buttons["panel:acc:psn"] == "🔵 PSN (2) ▸"
    assert buttons["panel:pub:psn"] == "🔔 Частично"

    screen = await render_account_menu(repo, TG_ID, "psn", locale="ru")
    assert screen is not None
    assert "2 аккаунта из 3" in screen.text
    datas = [b.callback_data for row in screen.keyboard.inline_keyboard for b in row]
    assert "panel:psnpub:acc-2" in datas and "psn:add" in datas


async def test_a_dead_xbox_login_opens_its_screen_with_reconnect_first(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "someone")
    await repo.link_xbox_account(await repo.person_id(TG_ID), "xuid-1", "Igor", 1000)
    await repo.save_refresh_token(await repo.person_id(TG_ID), b"encrypted")
    await repo.set_token_status(await repo.person_id(TG_ID), "invalid")

    screen = await render_account_menu(repo, TG_ID, "xbox", locale="ru")

    assert screen is not None
    assert screen.keyboard.inline_keyboard[0][0].callback_data == "relogin"


async def test_header_shows_identity_and_per_platform_counts_not_daily_totals(repo: Repo) -> None:
    """#18: the header now carries identity + lifetime per-platform counts,
    and the 24h/30d rows and "последние достижения" list are gone."""
    await repo.ensure_user(TG_ID, "madomsk")
    await repo.link_xbox_account(await repo.person_id(TG_ID), "xuid-1", "MadXbox", 12345)

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
    assert "Часовой пояс:" not in text


async def test_header_lists_every_connected_platform(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, None, "Igor", "Petrov")
    await repo.change_handle(await repo.person_id(TG_ID), "IgorP")
    await repo.link_xbox_account(await repo.person_id(TG_ID), "xuid-1", "MadXbox", 1000)
    await repo.link_platform_account(
        await repo.person_id(TG_ID), "steam", "76561197960287930", "SteamNick"
    )
    await repo.link_platform_account(await repo.person_id(TG_ID), "psn", "acc-1", "PsnNick")
    await repo.set_psn_trophy_level(await repo.person_id(TG_ID), 42)

    text, _markup = (await render_panel(repo, TG_ID)).as_pair()

    assert text.splitlines()[0] == "👤 IgorP"
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
    await repo.link_xbox_account(await repo.person_id(TG_ID), "xuid-1", "Igor", 1000)
    await repo.link_platform_account(await repo.person_id(TG_ID), "psn", "acc-1", "PsnOnly")
    await repo.save_presence_state("xuid-1", "Online", None, None, changed=True)
    await repo.save_psn_presence_state(
        "acc-1", "Online", "CUSA00001", "Ghost of Tsushima", changed=True
    )

    text, _markup = (await render_panel(repo, TG_ID)).as_pair()

    assert "Сейчас: 🔵 PlayStation  ·  играет — Ghost of Tsushima" in text


async def test_a_steam_only_person_gets_a_now_row_at_all(repo: Repo) -> None:
    """It was gated on `user.xuid`, so this row was simply absent for
    anyone without an Xbox account — the last Xbox-gated row on the panel."""
    await repo.ensure_user(TG_ID, "someone")
    await repo.link_platform_account(
        await repo.person_id(TG_ID), "steam", "76561197960287930", "Gabe"
    )
    await repo.save_steam_presence_state("76561197960287930", 1, "570", "Dota 2", changed=True)

    text, _markup = (await render_panel(repo, TG_ID)).as_pair()

    assert "Сейчас: ⚫ Steam  ·  играет — Dota 2" in text


async def test_an_offline_now_row_names_no_platform(repo: Repo) -> None:
    """Same call /online's own rows make (#51): once the answer is
    "offline", there is no "where" left for a platform name to answer, and
    picking one of three equally-offline platforms says nothing."""
    await repo.ensure_user(TG_ID, "someone")
    await repo.link_platform_account(
        await repo.person_id(TG_ID), "steam", "76561197960287930", "Gabe"
    )
    await repo.save_steam_presence_state("76561197960287930", 0, None, None, changed=True)

    text, _markup = (await render_panel(repo, TG_ID)).as_pair()

    assert "Сейчас: не в сети" in text
    assert "Steam  ·  не в сети" not in text


async def test_panel_steam_header_uses_naming_chain_fallback(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "someone")
    await repo.link_platform_account(
        await repo.person_id(TG_ID), "steam", "76561197960287930", None
    )
    await repo.set_platform_secondary_name(await repo.person_id(TG_ID), "steam", "gaben_vanity")

    text, _ = (await render_panel(repo, TG_ID)).as_pair()
    assert "Steam: gaben_vanity" in text


async def test_panel_psn_header_uses_naming_chain_fallback(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "someone")
    await repo.link_platform_account(
        await repo.person_id(TG_ID), "psn", "2130000000000000000", None
    )
    await repo.set_platform_secondary_name(await repo.person_id(TG_ID), "psn", "old_psn_tag")

    text, _ = (await render_panel(repo, TG_ID)).as_pair()
    assert "PlayStation: old_psn_tag" in text


async def test_panel_has_delete_account_button_above_sync(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "someone")
    _text, markup = (await render_panel(repo, TG_ID)).as_pair()
    rows = markup.inline_keyboard
    delete_i = next(
        i for i, r in enumerate(rows) if any(b.callback_data == "panel:delete_account" for b in r)
    )
    sync_i = next(i for i, r in enumerate(rows) if any(b.callback_data == "panel:sync" for b in r))
    assert sync_i == delete_i + 1


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
    assert await repo.get_user(await repo.person_id(TG_ID)) is None


async def test_panel_refresh_touches_last_online(repo: Repo, i18n, monkeypatch) -> None:
    from types import SimpleNamespace

    from bot.handlers import panel as panel_handlers

    await repo.ensure_user(TG_ID, "someone")

    async def fake_edit(callback, text, markup=None, **kwargs):
        pass

    monkeypatch.setattr(panel_handlers, "safe_edit", fake_edit)

    class _Cb:
        def __init__(self, tg_id: int):
            self.from_user = SimpleNamespace(id=tg_id)
            self.answers: list[str] = []

        async def answer(self, text: str = "", **kwargs):
            self.answers.append(text)

    cb = _Cb(TG_ID)
    await panel_handlers.panel_refresh(cb, repo, i18n)  # type: ignore[arg-type]

    user = await repo.get_user(await repo.person_id(TG_ID))
    assert user is not None
    assert user.last_online_at is not None


async def test_panel_sync_without_platforms_warns(repo: Repo, settings, i18n, monkeypatch) -> None:
    from types import SimpleNamespace

    from bot.handlers import panel as panel_handlers

    await repo.ensure_user(TG_ID, "someone")

    async def fake_edit(callback, text, markup=None, **kwargs):
        pass

    monkeypatch.setattr(panel_handlers, "safe_edit", fake_edit)

    class _Cb:
        def __init__(self, tg_id: int):
            self.from_user = SimpleNamespace(id=tg_id)
            self.answers: list[tuple[str, bool]] = []

        async def answer(self, text: str = "", show_alert: bool = False):
            self.answers.append((text, show_alert))

    cb = _Cb(TG_ID)
    await panel_handlers.panel_sync(
        cb,  # type: ignore[arg-type]
        repo,
        fetcher=None,  # type: ignore[arg-type]
        steam_fetcher=None,  # type: ignore[arg-type]
        psn_fetcher=None,  # type: ignore[arg-type]
        steam_auth=None,  # type: ignore[arg-type]
        settings=settings,
        i18n=i18n,
    )
    assert len(cb.answers) == 1
    assert cb.answers[0][1] is True  # show_alert


async def test_panel_sync_multi_platform_and_cooldown(
    repo: Repo, settings, i18n, monkeypatch
) -> None:
    from datetime import UTC, datetime
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from aiogram.types import Message
    from pydantic import SecretStr

    from bot.handlers import panel as panel_handlers
    from bot.services.steam.client import RecentlyPlayedGame

    panel_handlers._last_sync.clear()

    await repo.ensure_user(TG_ID, "triathlete")
    await repo.link_xbox_account(await repo.person_id(TG_ID), "xuid-1", "Igor", 1000)
    await repo.save_refresh_token(await repo.person_id(TG_ID), b"encrypted-token")
    await repo.link_platform_account(
        await repo.person_id(TG_ID), "steam", "76561197960287930", "Gabe"
    )
    await repo.link_platform_account(await repo.person_id(TG_ID), "psn", "acc-psn-1", "Kaz")

    edits: list[str] = []

    async def fake_edit(callback, text, markup=None, **kwargs):
        edits.append(text)

    monkeypatch.setattr(panel_handlers, "safe_edit", fake_edit)

    xbox_calls = []
    steam_calls = []
    psn_calls = []

    class FakeFetcher:
        async def catch_up(self, tg_id, xuid, gamertag, since, window_hours, max_titles):
            xbox_calls.append((tg_id, xuid))
            return (1, 2)  # 1 title, 2 published

    class FakeSteamFetcher:
        async def poll_title(self, tg_id, steam_id, persona_name, appid, game_name, **kwargs):
            steam_calls.append((tg_id, steam_id, appid))
            return 3  # 3 published

    class FakePsnFetcher:
        async def poll_account(self, tg_id, account_id, online_id):
            psn_calls.append((tg_id, account_id))
            return 1  # 1 published

    class FakeSteamAuth:
        async def get_key(self):
            return SecretStr("fake_key")

    now_ts = int(datetime.now(UTC).timestamp())

    async def fake_recently_played(api_key, steam_id, count=10):
        return [
            RecentlyPlayedGame(
                appid="550",
                name="L4D2",
                playtime_2weeks=10,
                playtime_forever=100,
                last_played=now_ts,
            )
        ]

    monkeypatch.setattr(
        panel_handlers.steam_client, "get_recently_played_games", fake_recently_played
    )

    messages_sent = []

    msg = MagicMock(spec=Message)

    async def fake_answer(text: str, **kwargs):
        messages_sent.append(text)

    msg.answer = fake_answer

    class _Cb:
        def __init__(self, tg_id: int):
            self.from_user = SimpleNamespace(id=tg_id)
            self.message = msg
            self.answers: list[str] = []

        async def answer(self, text: str = "", **kwargs):
            self.answers.append(text)

    cb = _Cb(TG_ID)
    await panel_handlers.panel_sync(
        cb,  # type: ignore[arg-type]
        repo,
        fetcher=FakeFetcher(),  # type: ignore[arg-type]
        steam_fetcher=FakeSteamFetcher(),  # type: ignore[arg-type]
        psn_fetcher=FakePsnFetcher(),  # type: ignore[arg-type]
        steam_auth=FakeSteamAuth(),  # type: ignore[arg-type]
        settings=settings,
        i18n=i18n,
    )

    # 1. All platforms were queried:
    assert xbox_calls == [(TG_ID, "xuid-1")]
    assert steam_calls == [(TG_ID, "76561197960287930", "550")]
    assert psn_calls == [(TG_ID, "acc-psn-1")]

    # 2. User last_online_at was touched:
    user = await repo.get_user(await repo.person_id(TG_ID))
    assert user is not None and user.last_online_at is not None

    # 3. Summary message was sent:
    assert len(messages_sent) == 1
    # 1 xbox title + 1 steam candidate = 2 titles; 2 xbox + 3 steam + 1 psn = 6 published
    assert "2" in messages_sent[0]
    assert "6" in messages_sent[0]

    # 4. Immediate second call hits cooldown and does NOT query platforms again:
    cb2 = _Cb(TG_ID)
    await panel_handlers.panel_sync(
        cb2,  # type: ignore[arg-type]
        repo,
        fetcher=FakeFetcher(),  # type: ignore[arg-type]
        steam_fetcher=FakeSteamFetcher(),  # type: ignore[arg-type]
        psn_fetcher=FakePsnFetcher(),  # type: ignore[arg-type]
        steam_auth=FakeSteamAuth(),  # type: ignore[arg-type]
        settings=settings,
        i18n=i18n,
    )
    # Fetcher calls did not increase:
    assert len(xbox_calls) == 1
    assert len(steam_calls) == 1
    assert len(psn_calls) == 1
    # Toast informed about cooldown:
    assert any("мин" in a for a in cb2.answers)


async def test_a_platform_whose_achievements_are_hidden_gets_a_mark(repo: Repo) -> None:
    """❗ on the platform's own button (owner, 2026-09-30) — for PSN, when any
    one of its accounts is hidden."""
    await repo.ensure_user(TG_ID, "someone")
    await repo.link_platform_account(
        await repo.person_id(TG_ID), "steam", "76561197960287930", "Gabe"
    )
    await repo.link_platform_account(await repo.person_id(TG_ID), "psn", "acc-1", "One")
    await repo.link_platform_account(await repo.person_id(TG_ID), "psn", "acc-2", "Two")
    await repo.set_achievements_visible(await repo.person_id(TG_ID), "steam", True)
    await repo.set_achievements_visible(
        await repo.person_id(TG_ID), "psn", True, external_id="acc-1"
    )
    await repo.set_achievements_visible(
        await repo.person_id(TG_ID), "psn", False, external_id="acc-2"
    )

    text, markup = (await render_panel(repo, TG_ID)).as_pair()

    buttons = {b.callback_data: b.text for row in markup.inline_keyboard for b in row}
    assert buttons["panel:acc:steam"] == "⚫ Steam ▸"
    assert buttons["panel:acc:psn"] == "🔵 PSN (2) ❗ ▸"
    assert "Вход PSN2: ⚠️ ачивки скрыты" in text
