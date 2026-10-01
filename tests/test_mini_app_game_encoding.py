"""bot/services/mini_app.py's game-ref encoding for a group's startapp value.

Telegram's own start/startapp parameter accepts only [A-Za-z0-9_-], 1-64
characters — a literal `platform:titleId` (the plain form the DM query
string still uses, which is percent-encoded via urlencode) silently broke
every group notification's deep link to a game (#145 review, 2026-09-30).
"""

from __future__ import annotations

import re

from bot.services.mini_app import mini_app_group_url, mini_app_start_param

_TELEGRAM_SAFE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def test_start_param_with_a_game_uses_only_telegrams_allowed_alphabet() -> None:
    param = mini_app_start_param(
        chat_id=-100123456789, person_id=987654321, game=("xbox_modern", "1234567890")
    )
    # Split off the leading c<chat_id>u<person_id> — a real digit/'-' prefix,
    # not part of what this test is about — and check only the 'g...' tail.
    g_index = param.index("g")
    game_token = param[g_index + 1 :]
    assert _TELEGRAM_SAFE.match(game_token), game_token
    # Guards the exact bug found live: a literal separator character.
    assert ":" not in game_token


def test_start_param_game_token_round_trips_through_base64url() -> None:
    import base64

    param = mini_app_start_param(chat_id=-100, game=("psn", "CUSA12345_00"))
    token = param[param.index("g") + 1 :]
    padded = token + "=" * (-len(token) % 4)
    decoded = base64.urlsafe_b64decode(padded).decode()
    assert decoded == "psn:CUSA12345_00"


def test_group_url_carries_no_raw_colon() -> None:
    url = mini_app_group_url("bot", chat_id=-100, person_id=42, game=("steam", "550"))
    # Only the scheme's own ':' (https:) may appear; none from the game ref.
    assert url.count(":") == 1


def test_stray_characters_in_a_title_id_still_encode_safely() -> None:
    # A title_id is normally digits/letters/underscores, but nothing stops a
    # stray character from reaching this function — the encoding must not
    # care what's inside. Kept short: length is a separate concern (Telegram
    # caps the whole start_param at 64 chars) from character-set safety,
    # which is all this test is about.
    weird = ":/?#&=щ"
    param = mini_app_start_param(chat_id=1, game=("p", weird))
    token = param[param.index("g") + 1 :]
    assert re.match(r"^[A-Za-z0-9_-]+$", token), token
