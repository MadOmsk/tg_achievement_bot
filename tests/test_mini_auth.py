"""Telegram Mini App Init Data validation — no live Telegram calls."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from bot.web.mini_auth import InitDataError, validate_init_data, validate_init_data_any

BOT_TOKEN = "123456:ABC-DEF"


def _signed_init_data(
    *, auth_date: int | None = None, user_id: int = 42, token: str = BOT_TOKEN
) -> str:
    """Build a blob whose hash matches aiogram's check_webapp_signature."""
    user = json.dumps(
        {"id": user_id, "first_name": "Ada", "username": "ada", "language_code": "ru"},
        separators=(",", ":"),
    )
    pairs = {
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
        "user": user,
    }
    data_check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    return urlencode(pairs)


def test_validate_init_data_accepts_a_fresh_signature() -> None:
    person = validate_init_data(_signed_init_data(), BOT_TOKEN)
    assert person.tg_id == 42
    assert person.username == "ada"
    assert person.first_name == "Ada"


def test_validate_init_data_rejects_a_tampered_hash() -> None:
    blob = _signed_init_data().replace("hash=", "hash=00")
    with pytest.raises(InitDataError, match="bad hash"):
        validate_init_data(blob, BOT_TOKEN)


def test_validate_init_data_rejects_an_expired_blob() -> None:
    blob = _signed_init_data(auth_date=int(time.time()) - 200_000)
    with pytest.raises(InitDataError, match="expired"):
        validate_init_data(blob, BOT_TOKEN, max_age_seconds=86_400)


OLD_TOKEN = "999:OLD-BOT"


def test_the_replaced_bots_signature_is_still_accepted() -> None:
    """#238: the Mini App opened from the old bot's posts is signed by it."""
    person = validate_init_data_any(_signed_init_data(token=OLD_TOKEN), [BOT_TOKEN, OLD_TOKEN])
    assert person.tg_id == 42


def test_a_signature_of_no_known_bot_is_refused() -> None:
    blob = _signed_init_data(token="777:STRANGER")
    with pytest.raises(InitDataError, match="bad hash"):
        validate_init_data_any(blob, [BOT_TOKEN, OLD_TOKEN])


def test_an_expired_blob_is_not_tried_against_other_tokens() -> None:
    blob = _signed_init_data(auth_date=int(time.time()) - 200_000)
    with pytest.raises(InitDataError, match="expired"):
        validate_init_data_any(blob, [BOT_TOKEN, OLD_TOKEN], max_age_seconds=86_400)


def test_legacy_tokens_come_after_the_bots_own() -> None:
    from bot.config import Settings

    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        bot_token=BOT_TOKEN,
        legacy_bot_tokens=f"{OLD_TOKEN}, 888:OLDER",
        azure_client_id="x",
        azure_client_secret="x",
        oauth_redirect_url="https://example.test/cb",
        fernet_key="x",
    )
    assert settings.mini_app_tokens() == [BOT_TOKEN, OLD_TOKEN, "888:OLDER"]
