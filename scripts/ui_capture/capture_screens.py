"""Capture every screen the production bot renders, without a network.

The real Dispatcher, the real routers, the real middlewares and a read-only
copy of the production database — only Telegram itself is replaced, by a
session that records each outgoing API call instead of performing it. So
what comes out is the exact payload the bot would have sent: text, parse
mode, inline keyboard, photo/media-group URLs.

Run from the production worktree with its own .env-shaped environment.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(sys.argv[1])
OUT = Path(sys.argv[2])
sys.path.insert(0, str(ROOT))

# The production commit's config.py reads ".env" and nothing else (BOT_ENV_FILE
# came later), so the capture environment is loaded into os.environ by hand.
for _line in Path(sys.argv[4]).read_text(encoding="utf-8").splitlines():
    _line = _line.strip()
    if _line and not _line.startswith("#"):
        _key, _, _value = _line.partition("=")
        os.environ.setdefault(_key.strip(), _value.strip())

from aiogram import Bot, Dispatcher  # noqa: E402
from aiogram.client.default import DefaultBotProperties  # noqa: E402
from aiogram.client.session.base import BaseSession  # noqa: E402
from aiogram.methods import TelegramMethod  # noqa: E402
from aiogram.types import (  # noqa: E402
    CallbackQuery,
    Chat,
    Message,
    Update,
    User,
)

from bot.config import get_settings  # noqa: E402
from bot.db.repo import Database, Repo  # noqa: E402
from bot.i18n import build_i18n_middleware  # noqa: E402
from bot.services.crypto import TokenCipher  # noqa: E402

ADMIN_ID = 188022193
BOT_ID = 7000000000

recorded: list[dict[str, Any]] = []


def _plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _plain(value.model_dump(exclude_none=True))
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)  # aiogram's Default sentinel, enums, datetimes


class RecordingSession(BaseSession):
    """Every call the bot makes to Telegram, written down and answered with
    the smallest plausible result the calling code will accept."""

    async def close(self) -> None:
        return None

    async def make_request(self, bot, method: TelegramMethod, timeout=None):  # type: ignore[override]
        name = type(method).__name__
        payload = {
            key: _plain(value)
            for key, value in method.model_dump(exclude_none=True).items()
            if key not in {"chat_id", "message_id", "business_connection_id"}
        }
        recorded.append({"method": name, "payload": payload})
        return self._result_for(name, method)

    def _result_for(self, name: str, method: TelegramMethod) -> Any:
        chat_id = getattr(method, "chat_id", ADMIN_ID) or ADMIN_ID
        if name in {"SendMessage", "SendPhoto", "EditMessageText", "EditMessageCaption"}:
            return Message(
                message_id=9001,
                date=dt.datetime.now(dt.UTC),
                chat=Chat(id=int(chat_id), type="private"),
            ).as_(bot=None)
        if name == "SendMediaGroup":
            return [
                Message(
                    message_id=9002 + index,
                    date=dt.datetime.now(dt.UTC),
                    chat=Chat(id=int(chat_id), type="private"),
                )
                for index in range(len(getattr(method, "media", []) or [1]))
            ]
        if name == "GetMe":
            return User(id=BOT_ID, is_bot=True, first_name="Achievement Bot", username="ach_bot")
        return True

    async def stream_content(self, *args, **kwargs):  # pragma: no cover - never used
        yield b""


def _user(tg_id: int = ADMIN_ID, username: str = "madomsk") -> User:
    return User(id=tg_id, is_bot=False, first_name="Igor", username=username)


def _message(text: str, *, chat_id: int, chat_type: str, tg_id: int = ADMIN_ID) -> Message:
    return Message(
        message_id=1,
        date=dt.datetime.now(dt.UTC),
        chat=Chat(id=chat_id, type=chat_type, title=None if chat_type == "private" else "XBOX CG"),
        from_user=_user(tg_id),
        text=text,
        entities=(
            [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]
            if text.startswith("/")
            else None
        ),
    )


def _callback(data: str, *, chat_id: int, chat_type: str, tg_id: int = ADMIN_ID) -> CallbackQuery:
    return CallbackQuery(
        id="1",
        from_user=_user(tg_id),
        chat_instance="1",
        data=data,
        message=Message(
            message_id=500,
            date=dt.datetime.now(dt.UTC),
            chat=Chat(
                id=chat_id,
                type=chat_type,
                title=None if chat_type == "private" else "XBOX CG",
            ),
            from_user=User(id=BOT_ID, is_bot=True, first_name="Bot"),
            text="—",
        ),
    )


RESTORE_SQL = None


async def restore(database) -> None:
    """Put every table back the way the dump had it, without reconnecting —
    the services and the dispatcher hold this one connection."""
    global RESTORE_SQL
    conn = database.conn
    if RESTORE_SQL is None:
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
        names = [row[0] for row in await cursor.fetchall()]
        RESTORE_SQL = names
    await conn.execute("PRAGMA foreign_keys = OFF")
    for name in RESTORE_SQL:
        await conn.execute(f"DELETE FROM {name}")
        await conn.execute(f"INSERT INTO {name} SELECT * FROM pristine.{name}")
    await conn.execute("PRAGMA foreign_keys = ON")
    await conn.commit()


async def main() -> None:
    settings = get_settings()
    database = await Database(settings.db_path).connect()
    repo = Repo(database)
    await database.conn.execute("ATTACH DATABASE ? AS pristine", (os.environ["PRISTINE_DB"],))
    cipher = TokenCipher(settings.fernet_key.get_secret_value())

    from bot.handlers import admin as admin_handlers
    from bot.handlers import chat as chat_handlers
    from bot.handlers import connect as connect_handlers
    from bot.handlers import hltb as hltb_handlers
    from bot.handlers import panel as panel_handlers
    from bot.handlers import psn as psn_handlers
    from bot.handlers import steam as steam_handlers
    from bot.handlers.chat import UsernameMiddleware
    from bot.poller.fetcher import Fetcher
    from bot.poller.psn_fetcher import PsnFetcher
    from bot.poller.publisher import Publisher
    from bot.poller.steam_fetcher import SteamFetcher
    from bot.services.connect import ConnectService
    from bot.services.notify import AdminNotifier
    from bot.services.psn.auth import PsnAuth
    from bot.services.steam.auth import SteamAuth
    from bot.services.translate.auth import AnthropicAuth
    from bot.services.xbox.auth import XboxAuthService
    from bot.services.xbox.client import XboxClient

    bot = Bot(
        token="7000000000:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        session=RecordingSession(),
        default=DefaultBotProperties(link_preview_is_disabled=True),
    )
    auth = XboxAuthService(settings, repo, cipher)
    await auth.start()
    notifier = AdminNotifier(bot, repo, settings.admin_tg_ids)
    psn_auth = PsnAuth(repo, cipher)
    steam_auth = SteamAuth(repo, cipher, env_key=None)
    anthropic_auth = AnthropicAuth(repo, cipher, env_key=None)
    publisher = Publisher(bot, repo)
    client = XboxClient(auth)
    fetcher = Fetcher(repo, client, publisher, 2, anthropic_auth=anthropic_auth)
    steam_fetcher = SteamFetcher(repo, steam_auth, publisher, 2, anthropic_auth=anthropic_auth)
    psn_fetcher = PsnFetcher(settings, repo, psn_auth, publisher, anthropic_auth=anthropic_auth)

    dispatcher = Dispatcher()
    dispatcher["repo"] = repo
    dispatcher["connect"] = ConnectService(auth, repo)
    dispatcher["fetcher"] = fetcher
    dispatcher["steam_fetcher"] = steam_fetcher
    dispatcher["settings"] = settings
    dispatcher["notifier"] = notifier
    dispatcher["psn_auth"] = psn_auth
    dispatcher["psn_fetcher"] = psn_fetcher
    dispatcher["steam_auth"] = steam_auth
    dispatcher["anthropic_auth"] = anthropic_auth
    dispatcher.message.outer_middleware(UsernameMiddleware(repo))
    i18n_middleware = build_i18n_middleware()
    i18n_middleware.setup(dispatcher=dispatcher)
    # Normally the dispatcher's own startup loads the .ftl bundles; nothing
    # here runs polling, so the core is started by hand or every key is a
    # KeyError on the locale itself.
    await i18n_middleware.core.startup()
    for router in (
        admin_handlers.router,
        connect_handlers.router,
        panel_handlers.router,
        chat_handlers.router,
        hltb_handlers.router,
        steam_handlers.router,
        psn_handlers.router,
    ):
        dispatcher.include_router(router)

    screens = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
    results = []
    for screen in screens:
        await restore(database)
        recorded.clear()
        kind = screen["kind"]
        chat_id = screen.get("chat_id", ADMIN_ID)
        chat_type = screen.get("chat_type", "private")
        tg_id = screen.get("tg_id", ADMIN_ID)
        if kind == "command":
            event = Update(
                update_id=1,
                message=_message(screen["input"], chat_id=chat_id, chat_type=chat_type, tg_id=tg_id),
            )
        else:
            event = Update(
                update_id=1,
                callback_query=_callback(
                    screen["input"], chat_id=chat_id, chat_type=chat_type, tg_id=tg_id
                ),
            )
        error = None
        try:
            await asyncio.wait_for(dispatcher.feed_update(bot, event), timeout=20)
        except Exception as exc:  # noqa: BLE001 - the report says which screens failed
            import traceback

            error = f"{type(exc).__name__}: {exc}"
            if os.environ.get("CAPTURE_TRACE"):
                traceback.print_exc()
        results.append(
            {
                "id": screen["id"],
                "title": screen["title"],
                "input": screen["input"],
                "scope": f"{kind} / {chat_type}",
                "calls": list(recorded),
                "error": error,
            }
        )
        print(f"{screen['id']:<34} {len(recorded):>2} call(s) {error or ''}", flush=True)

    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    await database.close()


asyncio.run(main())
