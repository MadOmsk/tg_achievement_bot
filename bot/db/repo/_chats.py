"""Chats, subscriptions, and per-chat publication targets — one mixin of
bot.db.repo.Repo (2026-09-09 split; see this package's own __init__.py).
Behavior is unchanged from before the split.
"""

from __future__ import annotations

import json

from bot.constants import RarityMode
from bot.db.repo._models import ChatDailySettings, ChatTarget, UserChatRow
from bot.i18n import DEFAULT_LOCALE, gettext
from bot.util import utcnow_iso


class _ChatsRepo:
    # -------------------------------------------------------- subscriptions

    async def delete_subscriptions_of_user(self, tg_id: int) -> None:
        await self._conn.execute("DELETE FROM subscriptions WHERE tg_id = ?", (tg_id,))
        await self._conn.commit()

    async def delete_presence_state(self, xuid: str) -> None:
        await self._conn.execute("DELETE FROM presence_state WHERE xuid = ?", (xuid,))
        await self._conn.commit()

    async def chats_of_user(self, tg_id: int) -> list[str]:
        cursor = await self._conn.execute(
            "SELECT c.title FROM subscriptions s JOIN chats c ON c.chat_id = s.chat_id "
            "WHERE s.tg_id = ? AND c.is_active = 1",
            (tg_id,),
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
            "INSERT OR IGNORE INTO chat_settings (chat_id) VALUES (?)", (chat_id,)
        )
        await self._conn.commit()

    async def chat_exists(self, chat_id: int) -> bool:
        cursor = await self._conn.execute("SELECT 1 FROM chats WHERE chat_id = ?", (chat_id,))
        return await cursor.fetchone() is not None

    async def subscribe(self, chat_id: int, tg_id: int) -> None:
        # rarity_mode is explicit here, not left to the column's own
        # DEFAULT 'all' — an admin-configurable starting point
        # (app_settings['default_rarity_mode'], handlers/admin.py) now
        # decides it instead of a value baked into the schema. The column
        # default stays 'all' regardless, as a safety net for any insert
        # that (today or in the future) doesn't go through this method.
        default_rarity_mode = await self.get_app_setting("default_rarity_mode", RarityMode.ALL)
        await self._conn.execute(
            "INSERT OR IGNORE INTO subscriptions (chat_id, tg_id, created_at, rarity_mode) "
            "VALUES (?, ?, ?, ?)",
            (chat_id, tg_id, utcnow_iso(), default_rarity_mode),
        )
        await self._conn.commit()

    async def unsubscribe(self, chat_id: int, tg_id: int) -> None:
        await self._conn.execute(
            "DELETE FROM subscriptions WHERE chat_id = ? AND tg_id = ?", (chat_id, tg_id)
        )
        await self._conn.commit()

    async def is_subscribed(self, chat_id: int, tg_id: int) -> bool:
        cursor = await self._conn.execute(
            "SELECT 1 FROM subscriptions WHERE chat_id = ? AND tg_id = ?", (chat_id, tg_id)
        )
        return await cursor.fetchone() is not None

    async def user_chats(self, tg_id: int) -> list[UserChatRow]:
        """Every chat this person has ever touched (SPEC 6.2's "Мои чаты") —
        subscribed at some point, or just seen writing there, same membership
        `/online` uses (SPEC 6.3). A chat the bot got kicked from is left out:
        nothing to manage there any more. `rarity_mode`/`digest_threshold`
        come along too (SPEC 9, M-Steam-2e's follow-up, and 2026-09-05's for
        digest_threshold — both live per subscription now), NULL when not
        currently subscribed."""
        cursor = await self._conn.execute(
            "SELECT c.chat_id, c.title, s.rarity_mode, s.digest_threshold "
            "FROM chats c "
            "LEFT JOIN subscriptions s ON s.chat_id = c.chat_id AND s.tg_id = ? "
            "WHERE c.is_active = 1 AND c.chat_id IN ("
            "  SELECT chat_id FROM subscriptions WHERE tg_id = ?"
            "  UNION "
            "  SELECT chat_id FROM chat_seen WHERE tg_id = ?"
            ") ORDER BY c.title",
            (tg_id, tg_id, tg_id),
        )
        return [
            UserChatRow(
                chat_id=row["chat_id"],
                title=row["title"],
                is_subscribed=row["rarity_mode"] is not None,
                rarity_mode=row["rarity_mode"],
                digest_threshold=row["digest_threshold"],
            )
            for row in await cursor.fetchall()
        ]

    async def update_subscription_rarity_mode(
        self, chat_id: int, tg_id: int, rarity_mode: str
    ) -> None:
        """The person's own rarity choice for one specific chat (SPEC 9,
        M-Steam-2e's follow-up — panel.py's "Мои чаты" card, not the main
        panel screen any more)."""
        await self._conn.execute(
            "UPDATE subscriptions SET rarity_mode = ? WHERE chat_id = ? AND tg_id = ?",
            (rarity_mode, chat_id, tg_id),
        )
        await self._conn.commit()

    async def update_subscription_digest_threshold(
        self, chat_id: int, tg_id: int, digest_threshold: int
    ) -> None:
        """The person's own digest threshold for one specific chat
        (Follow-up, 2026-09-05 — panel.py's "Мои чаты" card, not the main
        panel screen any more, same move as rarity_mode above)."""
        await self._conn.execute(
            "UPDATE subscriptions SET digest_threshold = ? WHERE chat_id = ? AND tg_id = ?",
            (digest_threshold, chat_id, tg_id),
        )
        await self._conn.commit()

    async def forget_chat_membership(self, chat_id: int, tg_id: int) -> None:
        """ "Delete" a chat from a person's own list (SPEC 6.2) — resets him to
        as if he had never subscribed or been seen there. Not a ban: writing
        in the chat again, or subscribing again, brings it right back
        (`record_chat_seen`/`subscribe`) — there is no third state that
        blocks that."""
        await self._conn.execute(
            "DELETE FROM subscriptions WHERE chat_id = ? AND tg_id = ?", (chat_id, tg_id)
        )
        await self._conn.execute(
            "DELETE FROM chat_seen WHERE chat_id = ? AND tg_id = ?", (chat_id, tg_id)
        )
        await self._conn.commit()

    async def deactivate_chat(self, chat_id: int) -> None:
        """Telegram answered 403 — the bot was kicked out (SPEC 5.5)."""
        await self._conn.execute("UPDATE chats SET is_active = 0 WHERE chat_id = ?", (chat_id,))
        await self._conn.commit()

    async def publication_targets(self, tg_id: int) -> list[ChatTarget]:
        cursor = await self._conn.execute(
            "SELECT c.chat_id, c.title, s.min_gamerscore, s.muted_title_ids,"
            "       s.rare_threshold_percent, s.daily_summary_time, s.tz_offset_min,"
            "       s.flood_limit, s.flood_window_minutes, s.locale,"
            "       sub.rarity_mode, sub.digest_threshold "
            "FROM subscriptions sub "
            "JOIN chats c ON c.chat_id = sub.chat_id "
            "JOIN chat_settings s ON s.chat_id = c.chat_id "
            "WHERE sub.tg_id = ? AND c.is_active = 1",
            (tg_id,),
        )
        return [
            ChatTarget(
                chat_id=row["chat_id"],
                title=row["title"],
                min_gamerscore=row["min_gamerscore"],
                muted_title_ids=json.loads(row["muted_title_ids"] or "[]"),
                rare_threshold_percent=row["rare_threshold_percent"],
                daily_summary_time=row["daily_summary_time"],
                tz_offset_min=row["tz_offset_min"],
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
            "SELECT rare_threshold_percent, daily_summary_time, tz_offset_min, locale "
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
        )
