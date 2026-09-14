"""Telegram command menus: private stays empty; groups get /app.

Telegram remembers a previously published "/" list until we delete it.
"""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeAllGroupChats, BotCommandScopeChatMember

from bot.db.repo import Repo

log = logging.getLogger(__name__)


def private_commands(
    *,
    xbox_connected: bool,
    steam_connected: bool,
    psn_connected: bool,
) -> list:
    """No slash commands — the Mini App is the UI."""
    del xbox_connected, steam_connected, psn_connected
    return []


def group_commands(*, locale: str = "ru") -> list[BotCommand]:
    """Group `/` menu: open the Mini App (via a WebApp button)."""
    if locale == "en":
        return [
            BotCommand(command="app", description="Open the club app"),
        ]
    return [
        BotCommand(command="app", description="Открыть приложение"),
    ]


async def publish_group_commands(bot: Bot) -> None:
    try:
        await bot.set_my_commands(group_commands(), scope=BotCommandScopeAllGroupChats())
        await bot.set_my_commands(
            group_commands(locale="en"),
            scope=BotCommandScopeAllGroupChats(),
            language_code="en",
        )
    except Exception:
        log.warning("could not publish group command menu", exc_info=True)


async def refresh_private_commands(bot: Bot, repo: Repo, tg_id: int) -> None:
    """Clear a leftover personalized "/" menu for this person."""
    del repo
    try:
        await bot.delete_my_commands(scope=BotCommandScopeChatMember(chat_id=tg_id, user_id=tg_id))
    except Exception:
        log.warning("could not clear private commands for tg_id=%s", tg_id, exc_info=True)
