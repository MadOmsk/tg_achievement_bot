"""Reminders about a dead login (SPEC 5.1.1)."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.constants import TokenStatus
from bot.db.repo import Repo
from bot.i18n import translator

log = logging.getLogger(__name__)

MAX_REMINDERS = 3
REMINDER_INTERVAL_HOURS = 72


def keyboard(locale: str) -> InlineKeyboardMarkup:
    """Rendered in the *recipient's* language (#48) — this job runs on a
    schedule, so the only person in the picture is whoever the reminder is
    about."""
    _ = translator("reminders", locale)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("reminders-relogin"), callback_data="relogin")],
            [InlineKeyboardButton(text=_("reminders-optout"), callback_data="optout")],
        ]
    )


class ReminderJob:
    def __init__(self, bot: Bot, repo: Repo) -> None:
        self._bot = bot
        self._repo = repo

    async def run(self) -> None:
        candidates = await self._repo.tokens_needing_reminder(
            MAX_REMINDERS, REMINDER_INTERVAL_HOURS
        )
        for tg_id in candidates:
            try:
                locale = await self._repo.user_locale(tg_id)
                text = translator("reminders", locale)("reminders-text")
                await self._bot.send_message(tg_id, text, reply_markup=keyboard(locale))
            except TelegramForbiddenError:
                # Blocked the bot: stop counting attempts against him forever.
                log.info("tg_id=%s blocked the bot, no more reminders", tg_id)
                await self._repo.set_token_status(tg_id, TokenStatus.REVOKED)
                continue
            except Exception:
                log.exception("could not remind tg_id=%s", tg_id)
                continue
            await self._repo.mark_token_notified(tg_id)
