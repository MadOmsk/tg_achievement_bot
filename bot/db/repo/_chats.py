"""Chats, subscriptions, and per-chat publication targets — one mixin of
bot.db.repo.Repo (2026-09-09 split; see this package's own __init__.py).
Behavior is unchanged from before the split.
"""

from __future__ import annotations

import json

from bot.db.repo._models import ChatDailySettings, ChatTarget, UserChatRow
from bot.db.repo._sql import (
    CHAT_MEMBERS,
    GLOBAL_DIGEST_THRESHOLD,
    GLOBAL_RARE_THRESHOLD,
    HANDLE_SHOWN,
    PERSON_BY_TG,
)
from bot.i18n import DEFAULT_LOCALE, gettext
from bot.util import utcnow_iso


class _ChatsRepo:
    # -------------------------------------------------------- subscriptions

    async def delete_subscriptions_of_user(self, person_id: int) -> None:
        await self._conn.execute(
            "DELETE FROM subscriptions WHERE person_id = ?",
            (person_id,),
        )
        await self._conn.commit()

    async def delete_presence_state(self, xuid: str) -> None:
        await self._conn.execute("DELETE FROM presence_state WHERE xuid = ?", (xuid,))
        await self._conn.commit()

    async def chats_of_user(self, person_id: int) -> list[str]:
        cursor = await self._conn.execute(
            "SELECT c.title FROM subscriptions s JOIN chats c ON c.chat_id = s.chat_id "
            "WHERE s.person_id = ? AND c.is_active = 1",
            (person_id,),
        )
        return [
            row["title"] or gettext("util", "util-untitled-chat") for row in await cursor.fetchall()
        ]

    # --------------------------------------------------- chats and subscriptions

    async def upsert_chat(self, chat_id: int, title: str | None, added_by: int | None) -> None:
        now = utcnow_iso()
        await self._conn.execute(
            "INSERT INTO chats (chat_id, title, added_by, created_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(chat_id) DO UPDATE SET title = excluded.title, is_active = 1",
            (chat_id, title, added_by, now),
        )
        await self._conn.execute(
            "INSERT INTO chat_settings (chat_id) VALUES (?) ON CONFLICT DO NOTHING", (chat_id,)
        )
        await self._conn.commit()

    async def chat_exists(self, chat_id: int) -> bool:
        cursor = await self._conn.execute("SELECT 1 FROM chats WHERE chat_id = ?", (chat_id,))
        return await cursor.fetchone() is not None

    async def subscribe(self, chat_id: int, person_id: int) -> None:
        await self._conn.execute(
            "INSERT INTO subscriptions (chat_id, person_id, created_at) VALUES (?, ?, ?)"
            " ON CONFLICT DO NOTHING",
            (chat_id, person_id, utcnow_iso()),
        )
        await self._conn.commit()

    async def unsubscribe(self, chat_id: int, person_id: int) -> None:
        await self._conn.execute(
            "DELETE FROM subscriptions WHERE chat_id = ? AND person_id = ?",
            (chat_id, person_id),
        )
        await self._conn.commit()

    async def is_subscribed(self, chat_id: int, person_id: int) -> bool:
        cursor = await self._conn.execute(
            "SELECT 1 FROM subscriptions WHERE chat_id = ? AND person_id = ?",
            (chat_id, person_id),
        )
        return await cursor.fetchone() is not None

    async def user_chats(self, tg_id: int) -> list[UserChatRow]:
        """Every chat this person has ever touched (SPEC 6.2's "Мои чаты") —
        subscribed at some point, or just seen writing there, same membership
        `/online` uses (SPEC 6.3). A chat the bot got kicked from is left out:
        nothing to manage there any more."""
        cursor = await self._conn.execute(
            "SELECT c.chat_id, c.title, s.chat_id AS subscribed "
            "FROM chats c "
            "LEFT JOIN subscriptions s ON s.chat_id = c.chat_id AND s.person_id = "
            + PERSON_BY_TG
            + " "
            "WHERE c.is_active = 1 AND c.chat_id IN ("
            "  SELECT chat_id FROM " + CHAT_MEMBERS + " WHERE person_id = " + PERSON_BY_TG + ") "
            "ORDER BY CASE WHEN s.chat_id IS NOT NULL THEN 0 ELSE 1 END,"
            "  (SELECT MAX(cs.last_seen_at) FROM chat_seen cs"
            "    WHERE cs.chat_id = c.chat_id AND cs.tg_id = ?) DESC,"
            "  c.title",
            (tg_id, tg_id, tg_id),
        )
        return [
            UserChatRow(
                chat_id=row["chat_id"],
                title=row["title"],
                is_subscribed=row["subscribed"] is not None,
            )
            for row in await cursor.fetchall()
        ]

    async def forget_chat_membership(self, chat_id: int, tg_id: int) -> None:
        """ "Delete" a chat from a person's own list (SPEC 6.2) — resets him to
        as if he had never subscribed or been seen there. Not a ban: writing
        in the chat again, or subscribing again, brings it right back
        (`record_chat_seen`/`subscribe`) — there is no third state that
        blocks that."""
        await self._conn.execute(
            "DELETE FROM subscriptions WHERE chat_id = ? AND person_id = " + PERSON_BY_TG,
            (chat_id, tg_id),
        )
        await self._conn.execute(
            "DELETE FROM chat_seen WHERE chat_id = ? AND tg_id = ?", (chat_id, tg_id)
        )
        await self._conn.commit()

    async def deactivate_chat(self, chat_id: int) -> None:
        """Telegram answered 403 — the bot was kicked out (SPEC 5.5). Its chat
        admin goes with it (#232): whoever adds it back is the next one."""
        async with self.transaction():
            await self._conn.execute("UPDATE chats SET is_active = 0 WHERE chat_id = ?", (chat_id,))
            await self._conn.execute("DELETE FROM chat_admins WHERE chat_id = ?", (chat_id,))

    # ---------------------------------------------------------- chat admins

    async def chat_admin(self, chat_id: int) -> int | None:
        """The chat admin's Telegram id (#232), if the chat has one."""
        cursor = await self._conn.execute(
            "SELECT tg_id FROM chat_admins WHERE chat_id = ?", (chat_id,)
        )
        row = await cursor.fetchone()
        return int(row["tg_id"]) if row else None

    async def chats_admined_by(self, tg_id: int) -> list[int]:
        """The chats this Telegram account admins — active ones only."""
        cursor = await self._conn.execute(
            "SELECT a.chat_id FROM chat_admins a JOIN chats c ON c.chat_id = a.chat_id "
            "WHERE a.tg_id = ? AND c.is_active = 1",
            (tg_id,),
        )
        return [int(row["chat_id"]) for row in await cursor.fetchall()]

    async def set_chat_admin(self, chat_id: int, tg_id: int | None, granted_by: int | None) -> None:
        """Makes `tg_id` the chat's one admin, or leaves it with none."""
        if tg_id is None:
            await self._conn.execute("DELETE FROM chat_admins WHERE chat_id = ?", (chat_id,))
        else:
            await self._conn.execute(
                "INSERT INTO chat_admins (chat_id, tg_id, granted_by, granted_at) "
                "VALUES (?, ?, ?, ?) ON CONFLICT(chat_id) DO UPDATE SET "
                "tg_id = excluded.tg_id, granted_by = excluded.granted_by, "
                "granted_at = excluded.granted_at",
                (chat_id, tg_id, granted_by, utcnow_iso()),
            )
        await self._conn.commit()

    async def chat_admin_candidates(self, chat_id: int) -> list[tuple[int, int, str | None]]:
        """Who the role may go to: the chat's known members — subscribed or
        seen writing there — as (Telegram id, person id, nickname shown)."""
        cursor = await self._conn.execute(
            "SELECT u.tg_id, u.id AS person_id, " + HANDLE_SHOWN + " FROM users u "
            "WHERE u.tg_id IS NOT NULL AND u.is_excluded = 0 AND ("
            " u.id IN (SELECT person_id FROM subscriptions WHERE chat_id = ?)"
            " OR u.tg_id IN (SELECT tg_id FROM chat_seen WHERE chat_id = ?)) "
            "ORDER BY lower(u.handle_norm), u.id",
            (chat_id, chat_id),
        )
        return [
            (int(row["tg_id"]), int(row["person_id"]), row["handle"])
            for row in await cursor.fetchall()
        ]

    async def publication_targets(self, person_id: int) -> list[ChatTarget]:
        cursor = await self._conn.execute(
            "SELECT c.chat_id, c.title, s.muted_title_ids,"
            f"       {GLOBAL_RARE_THRESHOLD} AS rare_threshold_percent,"
            "       s.daily_summary_time, s.tz_offset_min, s.tz_name,"
            "       s.flood_limit, s.flood_window_minutes, s.locale,"
            f"       {GLOBAL_DIGEST_THRESHOLD} AS digest_threshold,"
            "       COALESCE(us.rarity_mode, 'all') AS rarity_mode "
            "FROM subscriptions sub "
            "JOIN chats c ON c.chat_id = sub.chat_id "
            "JOIN chat_settings s ON s.chat_id = c.chat_id "
            "LEFT JOIN user_settings us ON us.person_id = sub.person_id "
            "WHERE sub.person_id = ? AND c.is_active = 1 AND s.publishing = 1",
            (person_id,),
        )
        return [
            ChatTarget(
                chat_id=row["chat_id"],
                title=row["title"],
                muted_title_ids=json.loads(row["muted_title_ids"] or "[]"),
                rare_threshold_percent=row["rare_threshold_percent"],
                daily_summary_time=row["daily_summary_time"],
                tz_offset_min=row["tz_offset_min"],
                tz_name=row["tz_name"],
                flood_limit=row["flood_limit"],
                flood_window_minutes=row["flood_window_minutes"],
                locale=row["locale"],
                rarity_mode=row["rarity_mode"],
                digest_threshold=row["digest_threshold"],
            )
            for row in await cursor.fetchall()
        ]

    async def chat_locale(self, chat_id: int) -> str:
        """This chat's own language (#48). One value per chat, not per
        viewer — see schema.sql. A chat with no settings row yet (it is
        created by upsert_chat, so only a chat the bot has never really
        seen) reads as the default rather than raising: this is called on
        the render path for every group message."""
        cursor = await self._conn.execute(
            "SELECT locale FROM chat_settings WHERE chat_id = ?", (chat_id,)
        )
        row = await cursor.fetchone()
        return row["locale"] if row else DEFAULT_LOCALE

    async def get_chat_daily_settings(self, chat_id: int) -> ChatDailySettings:
        cursor = await self._conn.execute(
            f"SELECT {GLOBAL_RARE_THRESHOLD} AS rare_threshold_percent,"
            " daily_summary_time, tz_offset_min, tz_name, locale "
            "FROM chat_settings WHERE chat_id = ?",
            (chat_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            # A chat with no chat_settings row at all — should not happen
            # (every chat gets one via upsert_chat), the hardcoded defaults
            # are the same ones a brand new row would carry.
            return ChatDailySettings(10.0, "20:00", 180, DEFAULT_LOCALE)
        return ChatDailySettings(
            rare_threshold_percent=row["rare_threshold_percent"],
            daily_summary_time=row["daily_summary_time"],
            tz_offset_min=row["tz_offset_min"],
            locale=row["locale"],
            tz_name=row["tz_name"],
        )

    async def active_group_chats(self) -> list[tuple[int, str]]:
        """Every active group chat and its configured language, for release
        announcements.

        A chat that has no chat_settings row falls back to DEFAULT_LOCALE."""
        cursor = await self._conn.execute(
            "SELECT c.chat_id, COALESCE(s.locale, ?) AS locale "
            "FROM chats c "
            "LEFT JOIN chat_settings s ON s.chat_id = c.chat_id "
            "WHERE c.is_active = 1 AND c.chat_id < 0 "
            "ORDER BY c.chat_id",
            (DEFAULT_LOCALE,),
        )
        return [(int(row["chat_id"]), str(row["locale"])) for row in await cursor.fetchall()]
