"""The old bot after production moved to a new one (#238).

Run on the old token alone (`python -m bot.moved`, unit `xbox-bot-moved`):
every private message is answered with where the bot went, and a command in
a group with a button that adds the new bot there. It has no database and
sends nothing on its own — without it the old bot would just go silent, and
people writing to it would never learn why.

Environment: `MOVED_BOT_TOKEN` (the old bot's token) and `MOVED_TO` (the new
bot's username).
"""

from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.i18n import gettext

log = logging.getLogger(__name__)

# No database here, so no chat's or person's own language: the default one.
LOCALE = "ru"


def dm_screen(new_bot: str) -> tuple[str, InlineKeyboardMarkup]:
    text = gettext("moved", "moved-dm", locale=LOCALE, bot=new_bot)
    button = InlineKeyboardButton(
        text=gettext("moved", "moved-open", locale=LOCALE, bot=new_bot),
        url=f"https://t.me/{new_bot}?start=moved",
    )
    return text, InlineKeyboardMarkup(inline_keyboard=[[button]])


def group_screen(new_bot: str) -> tuple[str, InlineKeyboardMarkup]:
    text = gettext("moved", "moved-group", locale=LOCALE, bot=new_bot)
    button = InlineKeyboardButton(
        text=gettext("moved", "moved-add", locale=LOCALE, bot=new_bot),
        url=f"https://t.me/{new_bot}?startgroup=moved",
    )
    return text, InlineKeyboardMarkup(inline_keyboard=[[button]])


def build_dispatcher(new_bot: str) -> Dispatcher:
    dp = Dispatcher()

    @dp.message(F.chat.type == "private")
    async def private(message: Message) -> None:
        text, keyboard = dm_screen(new_bot)
        await message.answer(text, reply_markup=keyboard)

    # In a group the bot sees only commands (privacy mode), which is exactly
    # when somebody expects it to answer.
    @dp.message(F.text.startswith("/"))
    async def group_command(message: Message) -> None:
        text, keyboard = group_screen(new_bot)
        await message.answer(text, reply_markup=keyboard)

    return dp


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s"
    )
    token = os.environ["MOVED_BOT_TOKEN"]
    new_bot = os.environ["MOVED_TO"].lstrip("@")
    bot = Bot(token, default=DefaultBotProperties(parse_mode="HTML"))
    me = await bot.me()
    log.info("moved-bot @%s points to @%s", me.username, new_bot)
    await build_dispatcher(new_bot).start_polling(bot, allowed_updates=["message"])


if __name__ == "__main__":
    asyncio.run(main())
