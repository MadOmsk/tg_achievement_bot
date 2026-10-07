"""One source for what the super-admin sees and changes (#176): the bot's
/admin and the Mini App's admin read the same services, so the same data
gives the same answer on both."""

from __future__ import annotations

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from bot.db.repo import Repo
from bot.services import admin_settings
from bot.services.admin_credentials import (
    AdminCredentials,
    CredentialInvalid,
    CredentialSetupError,
)
from bot.services.admin_settings import (
    EMAIL_PROVIDER_DAILY_KEY,
    RARE_THRESHOLD_KEY,
    TOP_LIMIT_KEY,
    SettingValueError,
    set_numeric_setting,
    set_rare_threshold,
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


# ------------------------------------------------------------ numeric settings


async def test_a_numeric_setting_is_checked_the_same_from_text_or_json(repo: Repo) -> None:
    assert await set_numeric_setting(repo, TOP_LIMIT_KEY, "12", 1) == 12
    assert await set_numeric_setting(repo, TOP_LIMIT_KEY, 7.0, 1) == 7  # JSON's number
    for raw in ("1.5", "1,5", 2.5, True, "x"):
        with pytest.raises(SettingValueError) as caught:
            await set_numeric_setting(repo, TOP_LIMIT_KEY, raw, 1)
        assert caught.value.reason == "integer"
    with pytest.raises(SettingValueError) as caught:
        await set_numeric_setting(repo, TOP_LIMIT_KEY, "51", 1)
    assert (caught.value.reason, caught.value.maximum) == ("range", 50)
    assert await repo.get_app_setting(TOP_LIMIT_KEY) == "7"


async def test_the_rarity_threshold_takes_a_comma_and_refuses_the_rest(repo: Repo) -> None:
    assert await set_rare_threshold(repo, "2,5", 1) == 2.5
    assert await repo.get_app_setting(RARE_THRESHOLD_KEY) == "2.5"
    for raw in ("0", "101", "nan", "x", True):
        with pytest.raises(SettingValueError):
            await set_rare_threshold(repo, raw, 1)


def test_every_zero_label_has_a_meaning_for_the_mini_app() -> None:
    for spec in admin_settings.NUMERIC_SETTINGS.values():
        if spec.min == 0:
            assert spec.zero_means is not None


# ------------------------------------------------- the two surfaces, one answer


async def test_the_bot_and_the_mini_app_show_the_same_home(
    repo: Repo, cipher: TokenCipher, settings
) -> None:
    credentials = _credentials(repo, cipher, settings)
    await repo.set_app_setting(EMAIL_PROVIDER_DAILY_KEY, "250")
    await repo.ensure_user(1, "someone")

    text, _markup = await render_admin_home(repo, _NoUsage(), _NoUsage(), credentials, locale="ru")  # type: ignore[arg-type]
    client = await _client(repo, settings, credentials)
    try:
        home = await (await client.get("/api/mini/admin")).json()
    finally:
        await client.close()

    assert "за сутки 0/250" in text
    assert home["mail"] == {"hour": 0, "hour_limit": 100, "day": 0, "day_limit": 250}
    assert home["xbox_usage"] in text
    assert [c["name"] for c in home["credentials"]] == credentials.names
    assert home["steam_key"] == home["psn_key"] == "not_configured"


async def test_the_mini_app_lists_and_sets_every_key_the_bot_does(
    repo: Repo, cipher: TokenCipher, settings, monkeypatch
) -> None:
    async def _dead(api_key: str) -> bool:
        return False

    monkeypatch.setattr(steam_auth_module, "check_alive", _dead)
    credentials = _credentials(repo, cipher, settings)
    text, markup = await render_keys(credentials, locale="ru")
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
    for key in keys:
        assert key["label"] in text
        assert f"a:keyset:{key['name']}" in {
            b.callback_data for row in markup.inline_keyboard for b in row
        }
    assert refused.status == 400 and refused_body["error"] == "invalid"
    assert unknown.status == 404


async def test_a_limit_out_of_range_is_refused_by_the_mini_app_as_by_the_bot(
    repo: Repo, cipher: TokenCipher, settings
) -> None:
    client = await _client(repo, settings, _credentials(repo, cipher, settings))
    try:
        bad = await client.patch("/api/mini/admin/limits", json={"key": TOP_LIMIT_KEY, "value": 51})
        half = await client.patch(
            "/api/mini/admin/limits", json={"key": TOP_LIMIT_KEY, "value": 2.5}
        )
        good = await client.patch("/api/mini/admin/limits", json={"key": TOP_LIMIT_KEY, "value": 9})
        items = (await good.json())["items"]
    finally:
        await client.close()

    assert bad.status == half.status == 400
    [row] = [item for item in items if item["key"] == TOP_LIMIT_KEY]
    assert (row["value"], row["zero_means"]) == (9, "unlimited")
