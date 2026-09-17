"""Draw any screen on demand, and optionally send it to the owner's DM (#63).

This replaced the hand-written mockups. A picture of a screen stops being a
document you maintain the moment it can be produced from the code that draws
it: every view in bot/views/ is callable without Telegram, so this names one,
renders it against the real database, and either prints it or sends it as a
real message from the bot — the form the owner actually reviews, keyboard and
all.

    python scripts/render_screen.py --list
    python scripts/render_screen.py panel
    python scripts/render_screen.py admin-user-card --tg-id 319472587 --send
    python scripts/render_screen.py achievement --locale en --send

Nothing here writes: it reads the database the .env points at and, with
--send, posts to the first id in ADMIN_TG_IDS. Point DB_PATH at a copy when
rendering against production data — and keep that copy in backups/, which is
the one place a database copy may live (see CLAUDE.md's Operations).

A copy rendered with a *different* FERNET_KEY than the one that filled it
degrades honestly rather than failing: the shared credentials come back as
"not configured", because that is exactly what the bot itself would conclude
about a secret it cannot open.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import InputMediaPhoto

from bot.config import Settings
from bot.constants import Platform
from bot.db.repo import AchievementRow, Database, Repo, TitleProgress
from bot.i18n import i18n_for
from bot.services.admin_settings import TOP_LIMIT_KEY
from bot.services.crypto import TokenCipher
from bot.services.psn.auth import PsnAuth
from bot.services.steam.auth import SteamAuth
from bot.services.translate.auth import AnthropicAuth
from bot.views import Screen
from bot.views.admin import (
    render_chat_card as render_admin_chat_card,
)
from bot.views.admin import (
    render_chat_list as render_admin_chat_list,
)
from bot.views.admin import (
    render_keys,
    render_limit,
    render_limits,
    render_new_user_defaults,
    render_user_card,
    render_user_list,
)
from bot.views.admin_home import render_admin_home
from bot.views.chat import (
    build_stats_text,
    help_text,
    hub_keyboard,
    hub_text,
    recent_list,
)
from bot.views.notification import format_digest, format_single
from bot.views.online import render_online_table
from bot.views.panel import (
    render_chat_card,
    render_chat_list,
    render_panel,
)
from bot.views.summary import build_summary


@dataclass(frozen=True)
class Context:
    """Whoever and whichever chat the screen is about. Both default to the
    first plausible row in the database — most screens are the same shape for
    anybody, and a screen that genuinely needs a particular person is told
    which with --tg-id."""

    repo: Repo
    settings: Settings
    tg_id: int
    chat_id: int
    locale: str


Builder = Callable[[Context], Awaitable[Screen | None]]
SCREENS: dict[str, Builder] = {}


def screen(name: str) -> Callable[[Builder], Builder]:
    def register(fn: Builder) -> Builder:
        SCREENS[name] = fn
        return fn

    return register


# ------------------------------------------------------------------ the user's own


@screen("panel")
async def _panel(ctx: Context) -> Screen:
    return await render_panel(ctx.repo, ctx.tg_id, locale=ctx.locale)


@screen("panel-chats")
async def _panel_chats(ctx: Context) -> Screen:
    return await render_chat_list(ctx.repo, ctx.tg_id, locale=ctx.locale)


@screen("panel-chat-card")
async def _panel_chat_card(ctx: Context) -> Screen | None:
    return await render_chat_card(ctx.repo, ctx.tg_id, ctx.chat_id, locale=ctx.locale)


# ---------------------------------------------------------------------- the group


@screen("stats")
async def _stats(ctx: Context) -> Screen | None:
    user = await ctx.repo.get_user(ctx.tg_id)
    if user is None:
        return None
    text = await build_stats_text(ctx.repo, user, ctx.chat_id, await i18n_for(ctx.locale))
    return Screen(text) if text else None


@screen("recent")
async def _recent(ctx: Context) -> Screen:
    rows = await ctx.repo.chat_recent(ctx.chat_id, 10, locale=ctx.locale)
    return Screen(recent_list(rows, await i18n_for(ctx.locale)))


@screen("help")
async def _help(ctx: Context) -> Screen:
    return Screen(help_text(await i18n_for(ctx.locale)))


@screen("hub")
async def _hub(ctx: Context) -> Screen:
    i18n = await i18n_for(ctx.locale)
    return Screen(
        await hub_text(ctx.repo, ctx.chat_id, i18n),
        hub_keyboard("tg_achievement_bot", ctx.chat_id, i18n),
    )


@screen("online")
async def _online(ctx: Context) -> Screen:
    rows = await ctx.repo.chat_member_presence(ctx.chat_id)
    return Screen(render_online_table(rows, "12:34", ctx.locale))


@screen("summary")
async def _summary(ctx: Context) -> Screen | None:
    chat = await ctx.repo.get_chat_daily_settings(ctx.chat_id)
    built = await build_summary(
        ctx.repo,
        ctx.chat_id,
        chat.rare_threshold_percent,
        date.today(),
        locale=ctx.locale,
        tz_offset_min=chat.tz_offset_min,
    )
    return Screen(*built) if built else None


# --------------------------------------------------------------- what gets posted


def _example_rows() -> list[AchievementRow]:
    """A constructed example rather than a real unlock.

    The published card is the one screen whose input is a *row plus the
    chat it is going to*, and reading somebody's newest trophy out of the
    database to look at a layout would mean picking a person at random. The
    numbers below are a real shape: Spider-Man is 74 trophies in five
    groups, 51 of them in the base game.
    """
    icon = "https://image.api.playstation.com/trophy/np/NPWR09167_00/1.PNG"
    return [
        AchievementRow(
            title_id="NPWR09167_00",
            achievement_id=f"{index}",
            name=name,
            description=description,
            icon_url=icon,
            unlocked_at="2026-09-15T11:10:00",
            gamerscore=0,
            rarity_percent=rarity,
            platform=Platform.PSN,
            title_name="Marvel's Spider-Man",
            is_secret=False,
            trophy_type=tier,
            trophy_group_id=group,
        )
        for index, (name, description, rarity, tier, group) in enumerate(
            (
                ("Ограбление", "Завершите все задания Ограбления.", 14.6, "gold", "002"),
                ("Взломщик", "Взломайте десять сейфов.", 32.1, "bronze", "002"),
                ("Паутинных дел мастер", "Изготовьте все гаджеты.", 21.4, "silver", "default"),
            )
        )
    ]


@screen("achievement")
async def _achievement(ctx: Context) -> Screen:
    row = _example_rows()[0]
    text = format_single(
        "drunkzero",
        row,
        row.title_name,
        locale=ctx.locale,
        progress=TitleProgress(
            unlocked=47,
            total=74,
            group_name="Город, который никогда не спит: Ограбление",
            group_unlocked=3,
            group_total=7,
        ),
    )
    return Screen(text, photo=row.icon_url)


@screen("digest")
async def _digest(ctx: Context) -> Screen:
    items = _example_rows()
    text = format_digest(
        "drunkzero",
        items[0].title_name,
        items,
        locale=ctx.locale,
        progress={
            (items[0].platform, items[0].title_id, None): TitleProgress(unlocked=47, total=74)
        },
    )
    icons = tuple(dict.fromkeys(item.icon_url for item in items if item.icon_url))
    return Screen(text, media=icons)


# ----------------------------------------------------------------- the admin panel


class _NoUsage:
    """The card's API-usage line reads a rate limiter's in-memory counters,
    which belong to the running bot's own process — this script has none.
    Rendering it as "нет данных" is what the real card shows right after a
    restart, and is honest; inventing numbers for a mockup would not be."""

    @staticmethod
    def api_usage() -> list[tuple[int, int, float]]:
        return []


@screen("admin-home")
async def _admin_home(ctx: Context) -> Screen:
    cipher = TokenCipher(ctx.settings.fernet_key.get_secret_value())
    steam_key = ctx.settings.steam_api_key
    text, markup = await render_admin_home(
        ctx.repo,
        _NoUsage(),
        _NoUsage(),
        PsnAuth(ctx.repo, cipher),
        SteamAuth(ctx.repo, cipher, env_key=steam_key.get_secret_value() if steam_key else None),
        locale=ctx.locale,
    )
    return Screen(text, markup)


@screen("admin-keys")
async def _admin_keys(ctx: Context) -> Screen:
    cipher = TokenCipher(ctx.settings.fernet_key.get_secret_value())
    steam_key = ctx.settings.steam_api_key
    return Screen(
        *await render_keys(
            SteamAuth(
                ctx.repo, cipher, env_key=steam_key.get_secret_value() if steam_key else None
            ),
            PsnAuth(ctx.repo, cipher),
            AnthropicAuth(ctx.repo, cipher),
            locale=ctx.locale,
        )
    )


@screen("admin-users")
async def _admin_users(ctx: Context) -> Screen:
    return Screen(*await render_user_list(ctx.repo, 0, locale=ctx.locale))


@screen("admin-user-card")
async def _admin_user_card(ctx: Context) -> Screen:
    return Screen(*await render_user_card(ctx.repo, ctx.tg_id, locale=ctx.locale))


@screen("admin-chats")
async def _admin_chats(ctx: Context) -> Screen:
    return Screen(*await render_admin_chat_list(ctx.repo, locale=ctx.locale))


@screen("admin-chat-card")
async def _admin_chat_card(ctx: Context) -> Screen | None:
    built = await render_admin_chat_card(ctx.repo, ctx.chat_id, locale=ctx.locale)
    return Screen(*built) if built else None


@screen("admin-limits")
async def _admin_limits(ctx: Context) -> Screen:
    return await render_limits(ctx.repo, locale=ctx.locale)


@screen("admin-limit")
async def _admin_limit(ctx: Context) -> Screen:
    """One setting's own input screen. Any of them would do — this one
    allows 0, which is the branch that was broken for four days."""
    return await render_limit(ctx.repo, TOP_LIMIT_KEY, locale=ctx.locale)


@screen("admin-defaults")
async def _admin_defaults(ctx: Context) -> Screen:
    return Screen(*await render_new_user_defaults(ctx.repo, locale=ctx.locale))


# ---------------------------------------------------------------------- delivery


def to_terminal(name: str, built: Screen) -> None:
    # A Windows console defaults to cp1251 here, and every screen in this
    # bot is Russian with emoji in it.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(f"----- {name} -----")
    if built.photo:
        print(f"[photo] {built.photo}")
    if built.media:
        print(f"[gallery] {len(built.media)} image(s)")
    print(built.text)
    if built.keyboard:
        for row in built.keyboard.inline_keyboard:
            print("  " + "  ".join(f"[ {button.text} ]" for button in row))


async def to_telegram(bot: Bot, chat_id: int, built: Screen) -> None:
    if built.media:
        media = [
            InputMediaPhoto(media=url, caption=built.text if index == 0 else None)
            for index, url in enumerate(built.media)
        ]
        await bot.send_media_group(chat_id, media)
        return
    if built.photo:
        await bot.send_photo(chat_id, built.photo, caption=built.text, reply_markup=built.keyboard)
        return
    await bot.send_message(chat_id, built.text, reply_markup=built.keyboard)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("screens", nargs="*", help="screen names, or none with --list")
    parser.add_argument("--list", action="store_true", help="print every known screen")
    parser.add_argument("--locale", default="ru")
    parser.add_argument("--tg-id", type=int, help="whose screen (default: the first admin)")
    parser.add_argument("--chat-id", type=int, help="which chat (default: the first known)")
    parser.add_argument("--send", action="store_true", help="send to the admin's DM")
    args = parser.parse_args()

    if args.list or not args.screens:
        print("\n".join(sorted(SCREENS)))
        return 0

    unknown = [name for name in args.screens if name not in SCREENS]
    if unknown:
        parser.error(f"unknown screen(s): {', '.join(unknown)}")

    settings = Settings()
    database = await Database(Path(settings.db_path)).connect()
    try:
        repo = Repo(database)
        admin_id = settings.admin_tg_ids[0]
        chats = await repo.admin_chats()
        ctx = Context(
            repo=repo,
            settings=settings,
            tg_id=args.tg_id or admin_id,
            chat_id=args.chat_id or (chats[0].chat_id if chats else 0),
            locale=args.locale,
        )
        built = [(name, await SCREENS[name](ctx)) for name in args.screens]
    finally:
        await database.close()

    missing = [name for name, screen in built if screen is None]
    if missing:
        print(f"no data to render: {', '.join(missing)}", file=sys.stderr)

    if not args.send:
        for name, screen in built:
            if screen is not None:
                to_terminal(name, screen)
        return 0

    bot = Bot(
        settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        for _name, screen in built:
            if screen is not None:
                await to_telegram(bot, admin_id, screen)
    finally:
        await bot.session.close()
    print(f"sent {sum(1 for _, s in built if s is not None)} screen(s) to {admin_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
