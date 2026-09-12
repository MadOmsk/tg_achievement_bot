"""The screens nobody taps: what the bot *sends on its own*.

Same recording idea as capture.py — Telegram replaced by a session that
writes down every outgoing call — but driving the publisher, the summary
builder, the reminder job and the admin notifier against real production
rows instead of feeding updates to the dispatcher.
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

for _line in Path(sys.argv[3]).read_text(encoding="utf-8").splitlines():
    _line = _line.strip()
    if _line and not _line.startswith("#"):
        _key, _, _value = _line.partition("=")
        os.environ.setdefault(_key.strip(), _value.strip())

from aiogram import Bot  # noqa: E402
from aiogram.client.default import DefaultBotProperties  # noqa: E402
from aiogram.client.session.base import BaseSession  # noqa: E402
from aiogram.types import Chat, Message, User  # noqa: E402

from bot.config import get_settings  # noqa: E402
from bot.db.repo import Database, Repo  # noqa: E402

CHAT_ID = -1001103247578
ADMIN_ID = 188022193
PSN_ACCOUNT = "980050590411556652"  # SuperOmsk — rarity_mode=all in both chats,
#                                       so the card is not filtered out before rendering
XBOX_XUID = "2535446000925749"  # Whalerider84

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
    return str(value)


class RecordingSession(BaseSession):
    async def close(self) -> None:
        return None

    async def make_request(self, bot, method, timeout=None):  # noqa: ASYNC109 - aiogram's own signature
        name = type(method).__name__
        recorded.append(
            {
                "method": name,
                "payload": {
                    key: _plain(value)
                    for key, value in method.model_dump(exclude_none=True).items()
                    if key not in {"chat_id", "message_id", "business_connection_id"}
                },
            }
        )
        if name in {"SendMessage", "SendPhoto", "EditMessageText"}:
            return Message(
                message_id=9001, date=dt.datetime.now(dt.UTC), chat=Chat(id=CHAT_ID, type="group")
            )
        if name == "SendMediaGroup":
            return [
                Message(
                    message_id=9002 + i,
                    date=dt.datetime.now(dt.UTC),
                    chat=Chat(id=CHAT_ID, type="group"),
                )
                for i in range(len(getattr(method, "media", []) or [1]))
            ]
        if name == "GetMe":
            return User(id=7000000000, is_bot=True, first_name="Bot", username="bot")
        return True

    async def stream_content(self, *args, **kwargs):  # pragma: no cover
        yield b""


async def main() -> None:
    settings = get_settings()
    database = await Database(settings.db_path).connect()
    repo = Repo(database)

    from bot.i18n import build_i18n_middleware
    from bot.poller.daily import build_summary
    from bot.poller.publisher import Publisher
    from bot.poller.reminders import ReminderJob
    from bot.services.notify import AdminNotifier

    await build_i18n_middleware().core.startup()

    bot = Bot(
        token="7000000000:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        session=RecordingSession(),
        default=DefaultBotProperties(link_preview_is_disabled=True),
    )
    publisher = Publisher(bot, repo)
    await publisher.start()
    results: list[dict[str, Any]] = []

    async def record(title: str, ident: str, coro) -> None:
        recorded.clear()
        error = None
        try:
            await asyncio.wait_for(coro, timeout=30)
            # publish() only queues; the worker is what actually "sends".
            for _ in range(60):
                if publisher._queue.empty():
                    break
                await asyncio.sleep(0.1)
            await asyncio.sleep(0.4)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        results.append(
            {
                "id": ident,
                "title": title,
                "input": "—",
                "scope": "автоматическое сообщение",
                "calls": list(recorded),
                "error": error,
            }
        )
        print(f"{ident:<24} {len(recorded):>2} call(s) {error or ''}", flush=True)

    psn = await repo.recent_achievements(PSN_ACCOUNT, limit=4)
    xbox = await repo.recent_achievements(XBOX_XUID, limit=2)

    async def forget_publications() -> None:
        # publish() never repeats what `publications` already holds, and the
        # anti-flood filter would swallow the third capture in a row — this
        # is a throwaway copy of the dump, so both records are just cleared.
        await database.conn.execute("DELETE FROM publications")
        await database.conn.execute("DELETE FROM notification_throttle")
        await database.conn.commit()

    if psn:
        await forget_publications()
        await record(
            "Опубликованный трофей PSN (одиночный)",
            "post-psn-single",
            publisher.publish(188022193, PSN_ACCOUNT, "SuperOmsk", psn[:1], None),
        )
        await forget_publications()
        await record(
            "Дайджест трофеев PSN (порог дайджеста пройден)",
            "post-psn-digest",
            publisher.publish(188022193, PSN_ACCOUNT, "SuperOmsk", psn, None),
        )
        await forget_publications()
        await record(
            "Дайджест после антифлуда (смешанные платформы)",
            "post-flood-digest",
            publisher.publish_flood_digest(188022193, CHAT_ID, psn[:2] + xbox[:1]),
        )
    if xbox:
        await forget_publications()
        await record(
            "Опубликованное достижение Xbox (одиночное)",
            "post-xbox-single",
            publisher.publish(127383366, XBOX_XUID, "Whalerider84", xbox[:1], None),
        )

    chat = next(c for c in await repo.admin_chats() if c.chat_id == CHAT_ID)
    today = dt.datetime.now(dt.UTC).date()
    for ident, title, day, month in [
        ("post-daily", "Итог дня (плановая рассылка)", True, False),
        ("post-monthly", "Итоги за месяц (последний день месяца)", False, True),
    ]:
        recorded.clear()
        built = await build_summary(
            repo,
            CHAT_ID,
            chat.rare_threshold_percent,
            today,
            locale=chat.locale,
            tz_offset_min=chat.tz_offset_min,
            with_day=day,
            with_month=month,
        )
        if built is not None:
            text, markup = built
            await bot.send_message(CHAT_ID, text, reply_markup=markup)
        results.append(
            {
                "id": ident,
                "title": title,
                "input": "—",
                "scope": "автоматическое сообщение",
                "calls": list(recorded),
                "error": None if built else "build_summary вернул None",
            }
        )
        print(f"{ident:<24} {len(recorded):>2} call(s)", flush=True)

    await record(
        "Напоминание о протухшем входе Xbox", "post-reminder", ReminderJob(bot, repo).run()
    )
    await record(
        "Суперадмину: общий ключ платформы умер",
        "post-key-dead",
        AdminNotifier(bot, repo, settings.admin_tg_ids).service_key_dead("psn"),
    )
    await record(
        "Суперадмину: пользователь подключился",
        "post-user-connected",
        AdminNotifier(bot, repo, settings.admin_tg_ids).user_connected(
            319472587, "kmaks90", is_new=True
        ),
    )

    # The HowLongToBeat card renders straight from the cache, so it needs no
    # search and no network — only the shape of an I18nContext.
    from bot.handlers.hltb import _card
    from bot.i18n import translator
    from bot.services.crypto import TokenCipher
    from bot.services.hltb import resolve
    from bot.services.translate.auth import AnthropicAuth

    class _Shim:
        def __init__(self, locale: str) -> None:
            self.locale = locale
            self._t = translator("hltb", locale)

        def get(self, key: str, **kwargs) -> str:
            return self._t(key, **kwargs)

    anthropic_auth = AnthropicAuth(
        repo, TokenCipher(settings.fernet_key.get_secret_value()), env_key=None
    )
    for hltb_id, ident, title in [
        (162277, "hltb-card", "Карточка игры /hltb (с описанием)"),
        (129232, "hltb-card-no-description", "Карточка игры /hltb (описания нет)"),
    ]:
        recorded.clear()
        error = None
        try:
            result = await resolve(repo, hltb_id, anthropic_auth=anthropic_auth)
            await bot.send_photo(
                CHAT_ID,
                photo=result.image_url,
                caption=_card(result, _Shim("ru")),
                parse_mode="HTML",
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        results.append(
            {
                "id": ident,
                "title": title,
                "input": "/hltb → выбор игры",
                "scope": "карточка",
                "calls": list(recorded),
                "error": error,
            }
        )
        print(f"{ident:<24} {len(recorded):>2} call(s) {error or ''}", flush=True)

    await publisher.stop()
    OUT.write_text(  # noqa: ASYNC240 - a one-shot script, nothing else is waiting
        json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    await database.close()


asyncio.run(main())
