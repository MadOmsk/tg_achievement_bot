"""What delivers rather than renders (#63): editing the message a callback
came from, a private notice to somebody who is not the person being
answered, and the app's promo posted to a chat (the super-admin's action,
for both admin panels). A view returns a screen and stops there, so these live on
the handler side of the line.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardMarkup, Message

from bot.db.repo import AchievementRow, Repo
from bot.i18n import gettext
from bot.services import post_picture
from bot.services.message_log import stats_category
from bot.services.naming import person_name_of
from bot.views.notification import format_single
from bot.views.parts import platform_label
from bot.views.promo import promo_keyboard, promo_text

log = logging.getLogger(__name__)

# How far back a person's achievements are looked through for one per platform.
_SAMPLE_LOOKBACK = 300


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


async def send_picture_samples(
    bot: Bot, repo: Repo, person_id: int, chat_id: int, *, locale: str
) -> int:
    """The person's latest achievement on each platform, as a post in every
    picture style — as sent today, then each square style — to `chat_id`, the
    super-admin's DM (owner, 2026-10-10). Answers how many pictures went."""
    user = await repo.get_user(person_id)
    if user is None:
        return 0
    picked: dict[str, AchievementRow] = {}
    for row in await repo.person_recent(person_id, _SAMPLE_LOOKBACK, locale=locale):
        if not row.icon_url or row.platform in picked:
            continue
        picked[row.platform] = AchievementRow(
            title_id=row.title_id,
            achievement_id=row.achievement_id,
            name=row.name,
            description=row.description,
            icon_url=row.icon_url,
            unlocked_at=row.unlocked_at,
            gamerscore=row.gamerscore,
            rarity_percent=row.rarity_percent,
            platform=row.platform,
            title_name=row.game,
            is_secret=row.is_secret,
            trophy_type=row.trophy_type,
        )
    if not picked:
        return 0
    name = person_name_of(user)
    await bot.send_message(
        chat_id,
        gettext("admin", "admin-picture-test-intro", locale=locale, name=name, count=len(picked)),
    )
    sent = 0
    for item in picked.values():
        text = format_single(name, item, item.title_name, locale=locale)
        icon, cover = await post_picture.sources(repo, item)
        for style in post_picture.STYLES:
            data = await post_picture.build(icon, cover, style)
            if style != post_picture.STYLE_OFF and data is None:
                continue
            note = gettext("admin", f"admin-post-picture-{style}", locale=locale)
            try:
                await bot.send_photo(
                    chat_id,
                    photo=BufferedInputFile(data, filename="post.jpg") if data else icon[-1],
                    caption=f"{text}\n\n<i>{note}</i>",
                    parse_mode=ParseMode.HTML,
                    has_spoiler=item.is_secret,
                )
                sent += 1
            except Exception as exc:
                log.info("a picture sample (%s) did not go through: %r", style, exc)
            await asyncio.sleep(0.3)
    return sent
