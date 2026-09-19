"""Automated release announcement to active group chats (2026-09-19).

Sent once per new version on startup. On production, links to the public
GitHub release notes in the chat's configured locale. On the test bot, sends
the test update notice without links.
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.db.repo import Repo
from bot.i18n import gettext
from bot.services.message_log import stats_category

log = logging.getLogger(__name__)

CHANGELOG_BASE_URL = "https://github.com/MadOmsk/tg_achievement_bot/blob/main/changelog"
APP_SETTING_KEY = "last_announced_version"


def base_version(full_version: str) -> str:
    """Extract A.B.C from A.B.C.D for changelog file names."""
    parts = full_version.split(".")
    return ".".join(parts[:3]) if len(parts) >= 3 else full_version


async def announce_release_if_needed(
    bot: Bot,
    repo: Repo,
    current_version: str,
    *,
    is_test: bool = False,
    sleep_delay: float = 0.05,
) -> int:
    """Announce the new release to all active group chats if not already announced.

    Returns the number of messages successfully delivered.
    """
    last_announced = await repo.get_app_setting(APP_SETTING_KEY)
    if last_announced == current_version:
        log.debug("release v%s already announced, skipping", current_version)
        return 0

    chats = await repo.active_group_chats()
    if not chats:
        log.info("no active group chats to announce release v%s to", current_version)
        await repo.set_app_setting(APP_SETTING_KEY, current_version)
        return 0

    base_ver = base_version(current_version)
    sent_count = 0

    for chat_id, locale in chats:
        if is_test:
            text = gettext(
                "main", "main-test-release-announced", locale=locale, version=current_version
            )
            markup = None
        else:
            text = gettext("main", "main-release-announced", locale=locale, version=current_version)
            btn_text = gettext("main", "main-release-button", locale=locale)
            url = f"{CHANGELOG_BASE_URL}/{base_ver}.{locale}.md"
            markup = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=btn_text, url=url)]]
            )

        try:
            with stats_category():
                await bot.send_message(
                    chat_id, text, parse_mode=ParseMode.HTML, reply_markup=markup
                )
            sent_count += 1
        except TelegramForbiddenError:
            log.info("bot was kicked from chat %s, deactivating", chat_id)
            await repo.deactivate_chat(chat_id)
        except Exception:
            log.warning("failed to send release announcement to chat %s", chat_id, exc_info=True)

        if sleep_delay > 0:
            await asyncio.sleep(sleep_delay)

    await repo.set_app_setting(APP_SETTING_KEY, current_version)
    log.info(
        "announced release v%s to %d/%d chat(s) (is_test=%s)",
        current_version,
        sent_count,
        len(chats),
        is_test,
    )
    return sent_count
