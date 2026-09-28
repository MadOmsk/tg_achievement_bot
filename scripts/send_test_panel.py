"""Sends the interactive test panel directly to admin's private chat.

Usage:
    python scripts/send_test_panel.py [--env .env.test]
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from aiogram import Bot

from bot.config import Settings
from bot.handlers.test_panel import get_mock_state
from bot.views.test_panel import render_screen


async def main() -> None:
    parser = argparse.ArgumentParser(description="Send test panel to admin PM")
    parser.add_argument("--env", default=".env.test", help="Path to env file (default: .env.test)")
    parser.add_argument(
        "--screen",
        default="home",
        help="Screen to render (default: home)",
    )
    args = parser.parse_args()

    os.environ["BOT_ENV_FILE"] = args.env
    settings = Settings(_env_file=args.env)  # type: ignore[call-arg]

    if not settings.admin_tg_ids:
        print(f"ERROR: No ADMIN_TG_IDS defined in {args.env}")
        sys.exit(1)

    admin_id = settings.admin_tg_ids[0]
    bot = Bot(token=settings.bot_token.get_secret_value())

    try:
        me = await bot.get_me()
        print(f"Using bot: @{me.username} ({me.id})")
        state = get_mock_state(admin_id)
        text, reply_markup = render_screen(args.screen, state)
        msg = await bot.send_message(
            chat_id=admin_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
        print(f"SUCCESS: Test panel sent to admin ID {admin_id} (msg_id={msg.message_id})")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
