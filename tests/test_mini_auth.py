"""Telegram Mini App Init Data validation — no live Telegram calls."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from bot.web.mini_auth import InitDataError, validate_init_data

BOT_TOKEN = "123456:ABC-DEF"


def _signed_init_data(*, auth_date: int | None = None, user_id: int = 42) -> str:
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
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
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
