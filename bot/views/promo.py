"""Pinned promo message with Mini App entry (SPEC / User Request).

Very concise opening words for Telegram's pinned message bar header preview,
followed by project description and inline button to open the Mini App.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup

from bot.i18n import DEFAULT_LOCALE, gettext
from bot.services.mini_app import mini_app_open_markup


def promo_text(locale: str = DEFAULT_LOCALE) -> str:
    """The pinned message text.

    Telegram's pinned message bar shows only the first few words, so the
    opening line must be as concise as possible:
    '🎮 Игровой клуб' / '🎮 Gaming Club'.
    """
    return gettext("chat", "chat-promo-text", locale=locale)


def promo_keyboard(
    bot_username: str,
    chat_id: int,
    *,
    mini_app_url: str = "",
    is_group: bool = True,
    locale: str = DEFAULT_LOCALE,
) -> InlineKeyboardMarkup | None:
    """Inline keyboard with 'Открыть Mini App' button."""
    app_url = (mini_app_url or "").strip()
    if not app_url:
        return None
    button_text = gettext("chat", "chat-open-mini-app", locale=locale)
    return mini_app_open_markup(
        button_text,
        https_url=app_url,
        bot_username=bot_username,
        chat_id=chat_id,
        in_group=is_group,
    )
