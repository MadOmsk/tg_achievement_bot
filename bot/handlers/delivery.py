"""What delivers rather than renders (#63): editing the message a callback
came from, a private notice to somebody who is not the person being
answered, and the app's promo posted to a chat (the super-admin's action,
for both admin panels). A view returns a screen and stops there, so these live on
the handler side of the line.
"""

from __future__ import annotations

import contextlib

from aiogram import Bot
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot.i18n import gettext
from bot.services.message_log import stats_category
from bot.views.parts import platform_label
from bot.views.promo import promo_keyboard, promo_text


async def safe_edit(
    callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup | None = None, **kwargs: object
) -> None:
    """Edit the callback's own message in place, tolerating the two routine
    failures every caller already needs to: the message isn't a real,
    editable Message (gone, or not accessible), or Telegram refuses an
    edit that changes nothing. Never calls callback.answer() itself —
    callers keep picking their own toast text, or none at all, same as
    before this existed."""
    if isinstance(callback.message, Message):
        with contextlib.suppress(Exception):
            await callback.message.edit_text(text, reply_markup=markup, **kwargs)


async def notify_previous_owner(
    bot: Bot, tg_id: int, platform: str, name: str, *, locale: str
) -> None:
    """Tell whoever just lost an account that they lost it (#52, owner
    decision) — deliberately without naming who took it: that is somebody
    else's Telegram identity, and the person who lost the account can sort
    it out with the account itself, not with a name we volunteered.

    Best-effort: they may have blocked the bot, and a failed notice must not
    fail the linking that triggered it.
    """
    with contextlib.suppress(Exception):
        await bot.send_message(
            tg_id,
            gettext(
                "connect",
                "connect-account-taken",
                locale=locale,
                platform=platform_label(platform, locale),
                name=name,
            ),
        )


async def send_promo(bot: Bot, chat_id: int, locale: str, mini_app_url: str | None) -> None:
    """The app's promo, in the chat's language, with its open buttons. Raises
    what Telegram raises — the caller words it."""
    from aiogram.enums import ParseMode

    me = await bot.me()
    markup = promo_keyboard(
        me.username or "", chat_id, mini_app_url=mini_app_url or "", is_group=True, locale=locale
    )
    with stats_category():
        await bot.send_message(
            chat_id, promo_text(locale=locale), parse_mode=ParseMode.HTML, reply_markup=markup
        )
