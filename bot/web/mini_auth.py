"""Validate Telegram Mini App ``initData`` via aiogram's checker.

We used to hand-roll HMAC and strip ``signature`` before hashing. Current
Telegram Android initData includes ``signature`` in the bot-token HMAC
payload — excluding it yields a permanent ``bad hash`` (seen live on
Telegram-Android/12.10). aiogram's ``check_web_app_signature`` only drops
``hash``, matching Telegram.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

from aiogram.utils.web_app import check_webapp_signature

# How long a signed initData blob stays acceptable. Telegram re-issues it
# every open; a day is generous for a long-lived WebView without being forever.
DEFAULT_MAX_AGE_SECONDS = 86_400

log = logging.getLogger(__name__)


class InitDataError(ValueError):
    """Signature missing/wrong, or the blob is too old."""


@dataclass(frozen=True, slots=True)
class MiniAppUser:
    tg_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    language_code: str | None
    is_premium: bool


def validate_init_data(
    init_data: str,
    bot_token: str,
    *,
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
    now: int | None = None,
) -> MiniAppUser:
    """Return the signed user, or raise ``InitDataError``."""
    init_data = init_data.strip().strip('"').strip("'")
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    keys = sorted(pairs)
    token_bot_id = bot_token.split(":", 1)[0]

    if "hash" not in pairs:
        raise InitDataError("missing hash")

    if not check_webapp_signature(bot_token, init_data):
        # Safe diagnostics only — never log initData, hash, or the token.
        log.info(
            "mini initData bad hash: keys=%s has_signature=%s len=%s token_bot_id=%s",
            keys,
            "signature" in pairs,
            len(init_data),
            token_bot_id,
        )
        raise InitDataError("bad hash")

    try:
        auth_date = int(pairs["auth_date"])
    except (KeyError, ValueError) as exc:
        raise InitDataError("missing auth_date") from exc

    clock = int(time.time()) if now is None else now
    age = clock - auth_date
    if age > max_age_seconds:
        log.info("mini initData expired: age_s=%s max=%s", age, max_age_seconds)
        raise InitDataError("initData expired")

    raw_user = pairs.get("user")
    if not raw_user:
        raise InitDataError("missing user")
    try:
        user = json.loads(raw_user)
    except json.JSONDecodeError as exc:
        raise InitDataError("bad user json") from exc

    try:
        tg_id = int(user["id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise InitDataError("missing user id") from exc

    log.info(
        "mini initData ok: tg_id=%s token_bot_id=%s keys=%s age_s=%s",
        tg_id,
        token_bot_id,
        keys,
        age,
    )
    return MiniAppUser(
        tg_id=tg_id,
        username=user.get("username"),
        first_name=user.get("first_name"),
        last_name=user.get("last_name"),
        language_code=user.get("language_code"),
        is_premium=bool(user.get("is_premium")),
    )
