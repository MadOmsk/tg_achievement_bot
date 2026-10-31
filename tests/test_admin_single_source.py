"""One source for what the super-admin sees and changes (#176): the bot's
/admin and the Mini App's admin read the same services, so the same data
gives the same answer on both."""

from __future__ import annotations

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from bot.db.repo import Repo
from bot.services.admin_credentials import (
    AdminCredentials,
    CredentialInvalid,
    CredentialSetupError,
)
from bot.services.admin_registry import (
    GROUPS,
    SETTINGS,
    parse,
    set_value,
    settings_of,
)
from bot.services.admin_settings import (
    EMAIL_PROVIDER_DAILY_KEY,
    RARE_THRESHOLD_KEY,
    TOP_LIMIT_KEY,
    SettingValueError,
)
from bot.services.crypto import TokenCipher
from bot.services.psn import auth as psn_auth_module
from bot.services.psn.auth import PsnAuth
from bot.services.psn.client import PsnClientSetupError
from bot.services.smtp_auth import SmtpAuth
from bot.services.steam import auth as steam_auth_module
from bot.services.steam.auth import SteamAuth
from bot.services.translate.auth import AnthropicAuth
from bot.services.youtube.auth import YouTubeAuth
from bot.views.admin import render_keys
from bot.views.admin_home import render_admin_home
from bot.web.mini_api import cors_middleware, setup_mini_api

ADMIN_TG = 500
CHAT_ID = -100777


class _NoUsage:
    @staticmethod
    def api_usage() -> list[tuple[int, int, float]]:
        return [(3, 300, 300.0)]


def _credentials(repo: Repo, cipher: TokenCipher, settings) -> AdminCredentials:
    return AdminCredentials(
        psn=PsnAuth(repo, cipher),
        steam=SteamAuth(repo, cipher),
        anthropic=AnthropicAuth(repo, cipher),
        youtube=YouTubeAuth(repo, cipher),
        smtp=SmtpAuth(repo, cipher, settings),
    )


async def _client(repo: Repo, settings, credentials: AdminCredentials) -> TestClient:
    settings.superadmin_tg_ids = [ADMIN_TG]
    app = web.Application(middlewares=[cors_middleware()])
    setup_mini_api(
        app,
        settings,
        repo,
        admin_credentials=credentials,
        xbox_fetcher=_NoUsage(),  # type: ignore[arg-type]
        steam_fetcher=_NoUsage(),  # type: ignore[arg-type]
    )
    client = TestClient(TestServer(app))
    await client.start_server()
    admin = await repo.ensure_user(ADMIN_TG, "boss")
    assert admin is not None
    token = await repo.create_session(admin, "test")
    client.session.cookie_jar.update_cookies({"ab_session": token})
    return client


# ---------------------------------------------------------------- the registry


async def test_every_credential_is_listed_once_in_one_order(
    repo: Repo, cipher: TokenCipher, settings
) -> None:
    credentials = _credentials(repo, cipher, settings)

    states = await credentials.states()

    assert [s.name for s in states] == ["psn", "steam", "anthropic", "youtube", "smtp"]
    assert not any(s.configured for s in states)


async def test_a_refused_key_is_one_error_whatever_the_service(
    repo: Repo, cipher: TokenCipher, settings, monkeypatch
) -> None:
    async def _dead(api_key: str) -> bool:
        return False

    monkeypatch.setattr(steam_auth_module, "check_alive", _dead)
    credentials = _credentials(repo, cipher, settings)

    with pytest.raises(CredentialInvalid):
        await credentials.set("steam", "bad", 1)
    with pytest.raises(CredentialInvalid):
        await credentials.set("smtp", "one-word-only", 1)
    with pytest.raises(CredentialInvalid):
        await credentials.set("steam", "   ", 1)
    assert not (await credentials.state("steam")).configured


async def test_a_psn_client_that_cannot_be_built_is_not_blamed_on_the_npsso(
    repo: Repo, cipher: TokenCipher, settings, monkeypatch
) -> None:
    async def _broken(npsso: str, **kwargs):
        raise PsnClientSetupError("no temp dir")

    monkeypatch.setattr(psn_auth_module, "build_client", _broken)

    with pytest.raises(CredentialSetupError):
        await _credentials(repo, cipher, settings).set("psn", "npsso", 1)


async def test_set_and_clear_go_through_the_credentials_own_class(
    repo: Repo, cipher: TokenCipher, settings, monkeypatch
) -> None:
    async def _alive(api_key: str) -> bool:
        return True

    monkeypatch.setattr(steam_auth_module, "check_alive", _alive)
    credentials = _credentials(repo, cipher, settings)

    await credentials.set("steam", "  KEY  ", 1)
    state = await credentials.state("steam")
    assert (state.configured, state.status) == (True, "active")
    assert state.checked_at is not None

    await credentials.clear("steam", 1)
    assert not (await credentials.state("steam")).configured


# ------------------------------------------------------------ the registry


async def test_a_number_is_checked_the_same_from_text_or_json(repo: Repo) -> None:
    assert await set_value(repo, "global", TOP_LIMIT_KEY, "12", 1) == 12
    assert await set_value(repo, "global", TOP_LIMIT_KEY, 7.0, 1) == 7  # JSON's number
    for raw in ("1.5", "1,5", 2.5, True, "x"):
        with pytest.raises(SettingValueError) as caught:
            await set_value(repo, "global", TOP_LIMIT_KEY, raw, 1)
        assert caught.value.reason == "integer"
    with pytest.raises(SettingValueError) as caught:
        await set_value(repo, "global", TOP_LIMIT_KEY, "51", 1)
    assert (caught.value.reason, caught.value.maximum) == ("range", 50)
    assert await repo.get_app_setting(TOP_LIMIT_KEY) == "7"


async def test_the_rarity_threshold_takes_a_comma_and_refuses_the_rest(repo: Repo) -> None:
    assert await set_value(repo, "global", RARE_THRESHOLD_KEY, "2,5", 1) == 2.5
    assert await repo.get_app_setting(RARE_THRESHOLD_KEY) == "2.5"
    for raw in ("0", "101", "nan", "x", True):
        with pytest.raises(SettingValueError):
            await set_value(repo, "global", RARE_THRESHOLD_KEY, raw, 1)


async def test_a_chat_setting_takes_only_its_own_values(repo: Repo) -> None:
    await repo.upsert_chat(CHAT_ID, "Чат", 1)
    for key, bad in (
        ("tz_name", "Mars/Olympus"),  # no zone of this world
        ("tz_name", 180),  # an offset is no place
        ("daily_summary_time", "абв"),
        ("daily_summary_time", "20:30"),  # the summary goes out on the hour
        ("flood_limit", -5),
        ("flood_limit", 100000),
        ("locale", "de"),
    ):
        with pytest.raises(SettingValueError):
            await set_value(repo, "chat", key, bad, 1, chat_id=CHAT_ID)

    await set_value(repo, "chat", "tz_name", "Europe/Vilnius", 1, chat_id=CHAT_ID)
    await set_value(repo, "chat", "daily_summary_time", "21:00", 1, chat_id=CHAT_ID)
    await set_value(repo, "chat", "publishing", False, 1, chat_id=CHAT_ID)
    [chat] = [c for c in await repo.admin_chats() if c.chat_id == CHAT_ID]
    assert (chat.tz, chat.daily_summary_time, chat.publishing) == ("Europe/Vilnius", "21:00", False)
    assert chat.is_active  # the bot's own flag, no setting's


def test_every_default_is_a_value_its_setting_takes() -> None:
    for setting in SETTINGS:
        if setting.default is not None:
            assert parse(setting, setting.default) == setting.default, setting.key


# ------------------------------------------------- the two surfaces, one answer


async def test_the_bot_and_the_mini_app_show_the_same_home(
    repo: Repo, cipher: TokenCipher, settings
) -> None:
    credentials = _credentials(repo, cipher, settings)
    await repo.set_app_setting(EMAIL_PROVIDER_DAILY_KEY, "250")
    await repo.ensure_user(1, "someone")

    text, _markup = await render_admin_home(repo, credentials, locale="ru")
    client = await _client(repo, settings, credentials)
    try:
        home = await (await client.get("/api/mini/admin")).json()
    finally:
        await client.close()

    assert "за сутки 0/250" in text
    assert home["mail"] == {
        "hour": 0,
        "hour_limit": 100,
        "day": 0,
        "day_limit": 250,
        "server": None,
    }
    # Every usage line the Mini App gets is a line of the bot's own home.
    assert [row["label"] for row in home["usage"]][:4] == [
        "API XBOX (медиана/макс. на аккаунт)",
        "API Steam",
        "API PSN",
        "API Anthropic",
    ]
    for row in home["usage"]:
        assert f"{row['label']}: {row['value']}" in text
    assert [c["name"] for c in home["credentials"]] == credentials.names
    assert home["steam_key"] == home["psn_key"] == "not_configured"


async def test_the_mini_app_lists_and_sets_every_key_the_bot_does(
    repo: Repo, cipher: TokenCipher, settings, monkeypatch
) -> None:
    async def _dead(api_key: str) -> bool:
        return False

    monkeypatch.setattr(steam_auth_module, "check_alive", _dead)
    credentials = _credentials(repo, cipher, settings)
    _text, markup = await render_keys(credentials, repo, locale="ru")
    client = await _client(repo, settings, credentials)
    try:
        keys = (await (await client.get("/api/mini/admin/keys")).json())["keys"]
        refused = await client.put("/api/mini/admin/keys/steam", json={"value": "bad"})
        refused_body = await refused.json()
        unknown = await client.put("/api/mini/admin/keys/nope", json={"value": "x"})
    finally:
        await client.close()

    assert [k["name"] for k in keys] == ["psn", "steam", "anthropic", "youtube", "smtp"]
    smtp = keys[-1]
    assert smtp["label"] == "Почта (SMTP)" and smtp["hint"]
    buttons = {b.callback_data: b.text for row in markup.inline_keyboard for b in row}
    for key in keys:
        assert key["label"] in buttons[f"a:key:{key['name']}"]
    assert refused.status == 400 and refused_body["error"] == "invalid"
    assert unknown.status == 404


async def test_the_mini_app_draws_and_changes_what_the_bot_does(
    repo: Repo, cipher: TokenCipher, settings
) -> None:
    """The same rows, groups and bounds; a value the bot refuses is refused."""
    await repo.upsert_chat(CHAT_ID, "Чат", 1)
    client = await _client(repo, settings, _credentials(repo, cipher, settings))
    try:
        listed = await (await client.get("/api/mini/admin/settings")).json()
        bad = await client.patch(
            "/api/mini/admin/settings", json={"key": TOP_LIMIT_KEY, "value": 51}
        )
        half = await client.patch(
            "/api/mini/admin/settings", json={"key": TOP_LIMIT_KEY, "value": 2.5}
        )
        unknown = await client.patch("/api/mini/admin/settings", json={"key": "nope", "value": 1})
        good = await (
            await client.patch("/api/mini/admin/settings", json={"key": TOP_LIMIT_KEY, "value": 9})
        ).json()
        chat_url = f"/api/mini/admin/chats/{CHAT_ID}/settings"
        chat = await (await client.get(chat_url)).json()
        bad_tz = await client.patch(chat_url, json={"key": "tz_name", "value": "Mars/Olympus"})
        tz = await (
            await client.patch(chat_url, json={"key": "tz_name", "value": "Europe/Vilnius"})
        ).json()
    finally:
        await client.close()

    assert [g["id"] for g in listed["groups"]] == list(GROUPS["global"])
    keys = [i["key"] for g in listed["groups"] for i in g["items"]]
    assert keys == [str(s.key) for s in settings_of("global")]
    assert bad.status == half.status == unknown.status == 400
    [row] = [i for g in good["groups"] for i in g["items"] if i["key"] == TOP_LIMIT_KEY]
    assert (row["value"], row["zero_means"], row["min"], row["max"]) == (9, "unlimited", 0, 50)

    assert [g["id"] for g in chat["groups"]] == list(GROUPS["chat"])
    assert bad_tz.status == 400
    [zone] = [i for g in tz["groups"] for i in g["items"] if i["key"] == "tz_name"]
    assert zone["value"] == "Europe/Vilnius"
    assert any(
        o["value"] == "Europe/Moscow" and o["label"] == "(UTC+03:00) Москва, Санкт-Петербург"
        for o in zone["options"]
    )


def test_a_time_zone_is_a_place_and_keeps_its_summer_clock() -> None:
    """Owner, 2026-10-30: places, not offsets — Vilnius is UTC+2 in winter
    and UTC+3 in summer; a fixed zone kept from an offset reads as the offset."""
    from datetime import UTC, datetime

    from bot.services import time_zones
    from bot.services.admin_registry import find, value_label

    zone = find("chat", "tz_name")
    winter = datetime(2026, 1, 15, 12, tzinfo=UTC)
    summer = datetime(2026, 7, 15, 12, tzinfo=UTC)
    row = "Вильнюс, Киев, Рига, София, Таллин, Хельсинки"
    assert time_zones.label("Europe/Vilnius", "ru", winter) == f"(UTC+02:00) {row}"
    assert time_zones.label("Europe/Vilnius", "ru", summer) == f"(UTC+03:00) {row}"
    assert time_zones.row_of("Europe/Vilnius") == "Europe/Kyiv"
    assert time_zones.label("Etc/GMT-5", "ru") == "(UTC+05:00)"
    assert time_zones.label(330, "ru") == "(UTC+05:30)"
    assert value_label(zone, "Europe/Moscow", locale="ru") == "(UTC+03:00) Москва, Санкт-Петербург"
    # The month starts at local midnight, summer time and all.
    assert time_zones.midnight_utc(summer.date().replace(day=1), "Europe/Vilnius") == datetime(
        2026, 6, 30, 21, tzinfo=UTC
    )


def test_the_digest_is_a_global_setting() -> None:
    from bot.services.admin_registry import find

    assert find("global", "digest_threshold").group == "rules"
    with pytest.raises(KeyError):
        find("chat", "digest_threshold")
