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
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot.config import Settings
from bot.db.repo import AchievementRow, Repo
from bot.i18n import gettext
from bot.services import post_picture
from bot.services.message_log import stats_category
from bot.views.parts import platform_label
from bot.views.promo import promo_keyboard, promo_text

log = logging.getLogger(__name__)


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
    bot: Bot, repo: Repo, settings: Settings, chat_id: int, *, locale: str
) -> int:
    """The newest achievement on each platform, whoever earned it, as the
    whole post a chat would get — as today, then on each ground with the
    admin's card and scale — to `chat_id`, the super-admin's DM (owner,
    2026-10-10). A high-resolution picture goes as it is, so it is sent
    once, said so. Answers how many posts went."""
    from bot.poller.publisher import Publisher

    latest = await repo.latest_per_platform(locale=locale)
    if not latest:
        return 0
    await bot.send_message(
        chat_id, gettext("admin", "admin-picture-test-intro", locale=locale, count=len(latest))
    )
    publisher = Publisher(bot, repo, settings)
    sent = 0
    for row in latest:
        if row.person_id is None:
            continue
        item = AchievementRow(
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
            xuid=row.xuid or None,
            trophy_group_id=row.trophy_group_id,
            device=row.device,
            game_platforms=row.game_platforms,
        )
        icon, cover = await post_picture.sources(repo, item)
        # One per distinct picture: with no card the two grounds draw the same.
        styles: list[str] = []
        drawn: set[bytes] = set()
        for style in (post_picture.STYLE_COLOR, post_picture.STYLE_COVER):
            data = await post_picture.build(icon, cover, await post_picture.look_of(repo, style))
            if data is not None and data not in drawn:
                drawn.add(data)
                styles.append(style)
        first = "admin-post-picture-off" if styles else "admin-picture-test-high-res"
        for style, key in [(post_picture.STYLE_OFF, first)] + [
            (style, f"admin-post-picture-{style}") for style in styles
        ]:
            try:
                if await publisher.sample(
                    item,
                    row.person_id,
                    chat_id,
                    locale=locale,
                    style=style,
                    note=gettext("admin", key, locale=locale),
                ):
                    sent += 1
            except Exception as exc:
                log.info("a picture sample (%s) did not go through: %r", style, exc)
            await asyncio.sleep(0.3)
    return sent
