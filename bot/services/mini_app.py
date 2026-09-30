"""Mini App deep-link URLs for group teasers and Open buttons.

Query params (`c`, `u`, `t`, `g`) are what the SPA reads on a WebApp URL.
Groups cannot use `web_app` inline buttons — Telegram answers
BUTTON_TYPE_INVALID — so those Open buttons are a `t.me/bot?startapp=`
link instead. The SPA already parses the same payload from
`initDataUnsafe.start_param` (`c<id>u<id>t<tab>g<encoded game>`).
"""

from __future__ import annotations

import base64
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

# (platform, title_id) — the game to open straight to, bypassing chat/tab.
GameRef = tuple[str, str]


def _encode_game(game: GameRef) -> str:
    """`platform:titleId`, base64url with the `=` padding stripped.

    Telegram's own `start`/`startapp` parameter accepts only
    `[A-Za-z0-9_-]`, 1-64 characters (found live, 2026-09-30, review of
    #145: a literal `platform:titleId` — the plain form `mini_app_open_url`
    still uses in its query string, which *is* percent-encoded — silently
    broke every group notification's deep link to a game, since ':' falls
    outside that set). base64url's own alphabet is exactly that set, so it
    needs no further escaping once padding is gone; `webapp/src/App.tsx`'s
    `launchContext()` decodes the same way and must stay in sync.
    """
    raw = f"{game[0]}:{game[1]}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def mini_app_open_url(
    base: str,
    *,
    chat_id: int,
    person_id: int | None = None,
    tab: str | None = None,
    game: GameRef | None = None,
) -> str:
    parts = urlsplit(base.strip())
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["c"] = str(chat_id)
    if person_id is not None:
        query["u"] = str(person_id)
    if tab:
        query["t"] = tab
    if game:
        query["g"] = f"{game[0]}:{game[1]}"
    path = parts.path or "/"
    return urlunsplit((parts.scheme, parts.netloc, path, urlencode(query), parts.fragment))


def mini_app_start_param(
    *,
    chat_id: int,
    person_id: int | None = None,
    tab: str | None = None,
    game: GameRef | None = None,
) -> str:
    """Compact start_param — must stay in sync with webapp launchContext()."""
    param = f"c{chat_id}"
    if person_id is not None:
        param += f"u{person_id}"
    if tab:
        param += f"t{tab}"
    if game:
        param += f"g{_encode_game(game)}"
    return param


def mini_app_group_url(
    bot_username: str,
    *,
    chat_id: int,
    person_id: int | None = None,
    tab: str | None = None,
    game: GameRef | None = None,
) -> str:
    name = bot_username.lstrip("@")
    param = mini_app_start_param(chat_id=chat_id, person_id=person_id, tab=tab, game=game)
    return f"https://t.me/{name}?startapp={param}"


def mini_app_open_markup(
    text: str,
    *,
    https_url: str,
    bot_username: str,
    chat_id: int,
    person_id: int | None = None,
    tab: str | None = None,
    game: GameRef | None = None,
    in_group: bool = True,
) -> InlineKeyboardMarkup | None:
    https_url = (https_url or "").strip()
    name = (bot_username or "").lstrip("@")
    if not https_url:
        return None
    if in_group:
        if not name:
            return None
        button = InlineKeyboardButton(
            text=text,
            url=mini_app_group_url(name, chat_id=chat_id, person_id=person_id, tab=tab, game=game),
        )
    else:
        button = InlineKeyboardButton(
            text=text,
            web_app=WebAppInfo(
                url=mini_app_open_url(
                    https_url, chat_id=chat_id, person_id=person_id, tab=tab, game=game
                )
            ),
        )
    return InlineKeyboardMarkup(inline_keyboard=[[button]])
