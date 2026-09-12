"""Self-dedup bookkeeping for /panel, /summary, /recent and a person's own
/stats (each replacing its own previous copy), /recent's own query,
recent-games lookups, daily-report/publication markers, and bot-message
cleanup tracking — one mixin of bot.db.repo.Repo (2026-09-09 split; see
this package's own __init__.py). Behavior is unchanged from before the
split.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from bot.db.repo._models import DeletableMessage, RecentAchievement, TopGame, User, _as_user, _iso
from bot.util import utcnow_iso


class _MessagesRepo:
    # --------------------------------------------------- self-dedup messages

    async def tracked_message(self, chat_id: int, kind: str, subject_id: int = 0) -> int | None:
        """The message_id this (chat, kind, subject) last sent, if any
        (Follow-up 2026-09-06) — /panel, /summary, /recent and a specific
        person's /stats card each replace their own previous copy instead
        of accumulating (see tracked_messages in schema.sql for the exact
        scope of `kind`/`subject_id`)."""
        cursor = await self._conn.execute(
            "SELECT message_id FROM tracked_messages "
            "WHERE chat_id = ? AND kind = ? AND subject_id = ?",
            (chat_id, kind, subject_id),
        )
        row = await cursor.fetchone()
        return row["message_id"] if row else None

    async def set_tracked_message(
        self, chat_id: int, kind: str, subject_id: int, message_id: int
    ) -> None:
        await self._conn.execute(
            "INSERT INTO tracked_messages (chat_id, kind, subject_id, message_id, updated_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(chat_id, kind, subject_id) DO UPDATE SET"
            " message_id = excluded.message_id, updated_at = excluded.updated_at",
            (chat_id, kind, subject_id, message_id, utcnow_iso()),
        )
        await self._conn.commit()

    async def record_chat_seen(self, chat_id: int, tg_id: int) -> None:
        """A message from a *known* tg_id in this group — feeds /online's
        membership list (SPEC 6.3). The `SELECT ... WHERE EXISTS` guard keeps
        the same "never create a user row just for writing a message" rule
        as `update_username`: someone the bot has no `users` row for yet
        leaves no trace here either."""
        await self._conn.execute(
            "INSERT INTO chat_seen (chat_id, tg_id, last_seen_at) "
            "SELECT ?, ?, ? WHERE EXISTS (SELECT 1 FROM users WHERE tg_id = ?) "
            "ON CONFLICT (chat_id, tg_id) DO UPDATE SET last_seen_at = excluded.last_seen_at",
            (chat_id, tg_id, utcnow_iso(), tg_id),
        )
        await self._conn.commit()

    async def chat_subscriber_names(self, chat_id: int) -> list[str]:
        cursor = await self._conn.execute(
            "SELECT u.gamertag, u.tg_id FROM subscriptions s "
            "JOIN users u ON u.tg_id = s.tg_id "
            "WHERE s.chat_id = ? AND u.is_excluded = 0 "
            "ORDER BY u.gamertag",
            (chat_id,),
        )
        return [row["gamertag"] or f"id{row['tg_id']}" for row in await cursor.fetchall()]

    async def chat_recent(self, chat_id: int, limit: int) -> list[RecentAchievement]:
        cursor = await self._conn.execute(
            # Every field the person chain needs (#51) — this used to select
            # `u.gamertag` alone, so a member with no Xbox account was
            # rendered as the literal word "кто-то".
            "SELECT u.tg_id, u.gamertag, u.gamertag_modern, u.username, u.first_name,"
            "       u.last_name, steam.display_name AS steam_name,"
            "       psn.display_name AS psn_name,"
            "       s.name, t.name AS game, s.gamerscore, s.rarity_percent,"
            "       s.platform, s.unlocked_at, s.is_secret "
            "FROM subscriptions sub "
            "JOIN users u ON u.tg_id = sub.tg_id "
            "LEFT JOIN platform_links steam ON steam.tg_id = u.tg_id AND steam.platform = 'steam' "
            "LEFT JOIN platform_links psn ON psn.tg_id = u.tg_id AND psn.platform = 'psn' "
            # tg_id, not xuid (SPEC 9, M-Steam-2a): xuid is Xbox-only on
            # `users`, always NULL for a Steam-only person and never the
            # SteamID64 `seen_achievements.xuid` holds for a Steam row even
            # for someone with both platforms — this join saw Xbox rows only.
            "JOIN seen_achievements s ON s.tg_id = u.tg_id "
            "LEFT JOIN titles t ON t.title_id = s.title_id "
            "WHERE sub.chat_id = ? AND u.is_excluded = 0 AND s.unlocked_at IS NOT NULL "
            "ORDER BY s.unlocked_at DESC LIMIT ?",
            (chat_id, limit),
        )
        return [
            RecentAchievement(
                tg_id=row["tg_id"],
                gamertag=row["gamertag"],
                gamertag_modern=row["gamertag_modern"],
                username=row["username"],
                first_name=row["first_name"],
                last_name=row["last_name"],
                steam_name=row["steam_name"],
                psn_name=row["psn_name"],
                name=row["name"],
                game=row["game"],
                gamerscore=int(row["gamerscore"] or 0),
                rarity_percent=row["rarity_percent"],
                platform=row["platform"],
                unlocked_at=row["unlocked_at"],
                is_secret=bool(row["is_secret"]),
            )
            for row in await cursor.fetchall()
        ]

    async def recent_games(
        self, external_id: str, since: datetime, limit: int = 15
    ) -> list[TopGame]:
        """Games actually played recently, not the biggest lifetime scores —
        a person's five favourite old games would otherwise crowd out
        whatever they are playing this month, every time.

        `external_id` despite the historical name isn't Xbox-specific:
        `seen_achievements.xuid` is the generic per-platform external id
        (SPEC 9, M-Steam-2a) — a SteamID64 works here exactly as well as an
        xuid, already scoped to that one account's own rows.

        `limit == 0` means "no cap" (admin-configurable, SPEC 6.4) — passed
        to SQLite as -1, its own documented spelling of "unbounded LIMIT",
        rather than branching the query string for one case.
        """
        cursor = await self._conn.execute(
            "SELECT t.name, COALESCE(SUM(s.gamerscore), 0) AS score, COUNT(*) AS unlocked,"
            " MAX(s.platform) AS platform "
            "FROM seen_achievements s LEFT JOIN titles t ON t.title_id = s.title_id "
            "WHERE s.xuid = ? AND s.unlocked_at >= ? "
            # Score ties on every Steam game (no gamerscore there at all) —
            # unlocked count as the tiebreaker instead of SQLite's undefined
            # order among equal scores.
            "GROUP BY s.title_id ORDER BY score DESC, unlocked DESC LIMIT ?",
            (external_id, _iso(since), limit or -1),
        )
        return [
            TopGame(
                name=row["name"],
                gamerscore=row["score"],
                unlocked=row["unlocked"],
                platform=row["platform"],
            )
            for row in await cursor.fetchall()
        ]

    async def chat_recent_games(self, chat_id: int, limit: int = 10) -> list[str]:
        """Distinct game names the chat's known members have actually played
        recently, most-recent first — quick-pick shortcuts for /hltb so the
        common case ("what does everyone here keep talking about") needs no
        typing at all (SPEC 6.6). Same membership as /online and /who: the
        union of who publishes here and who's just been seen writing here,
        not only publishers."""
        cursor = await self._conn.execute(
            "SELECT t.name AS name, MAX(th.last_played_at) AS last_played "
            "FROM title_history th "
            "JOIN titles t ON t.title_id = th.title_id "
            "WHERE th.xuid IN ("
            "  SELECT u.xuid FROM users u "
            "  WHERE u.xuid IS NOT NULL AND u.tg_id IN ("
            "    SELECT tg_id FROM subscriptions WHERE chat_id = ? "
            "    UNION "
            "    SELECT tg_id FROM chat_seen WHERE chat_id = ?"
            "  )"
            ") AND th.last_played_at IS NOT NULL "
            "GROUP BY t.name "
            "ORDER BY last_played DESC LIMIT ?",
            (chat_id, chat_id, limit),
        )
        return [row["name"] for row in await cursor.fetchall() if row["name"]]

    async def find_user_by_username(self, username: str) -> User | None:
        cursor = await self._conn.execute(
            "SELECT * FROM users WHERE lower(username) = lower(?)", (username.lstrip("@"),)
        )
        row = await cursor.fetchone()
        return _as_user(row) if row else None

    async def daily_report_sent(self, chat_id: int, report_date: str) -> bool:
        cursor = await self._conn.execute(
            "SELECT 1 FROM daily_reports WHERE chat_id = ? AND report_date = ?",
            (chat_id, report_date),
        )
        return await cursor.fetchone() is not None

    async def mark_daily_report_sent(self, chat_id: int, report_date: str) -> None:
        await self._conn.execute(
            "INSERT OR IGNORE INTO daily_reports (chat_id, report_date, sent_at) VALUES (?, ?, ?)",
            (chat_id, report_date, utcnow_iso()),
        )
        await self._conn.commit()

    async def log_bot_message(
        self,
        chat_id: int,
        message_id: int,
        *,
        is_system: bool = True,
        preview: str | None = None,
    ) -> None:
        """Called from the request middleware (bot/services/message_log.py)
        for every message the bot sends *or edits* in a group — the only
        record that lets the admin panel's "стереть сообщения бота" find
        anything to delete (SPEC 6.4). Upserts rather than INSERT OR IGNORE
        (2026-09-05 follow-up, is_system): an edit refreshes both sent_at
        and is_system, on purpose — /hltb's own multi-step flow, for one,
        edits the same message from a search prompt into the final result
        card, and that edit must both reclassify it as "stats" and reset its
        auto-delete clock, not leave it tagged (and aging out) as whatever
        it was first logged as.

        `preview` (2026-09-09) is the first couple of lines of the
        message's own text/caption, for /delete_last's own "Удалено: ..."
        confirmation (`last_non_system_bot_message` below) — also
        refreshed on an edit, same reasoning as is_system above.
        """
        await self._conn.execute(
            "INSERT INTO bot_messages (chat_id, message_id, sent_at, is_system, preview) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(chat_id, message_id) DO UPDATE SET"
            " sent_at = excluded.sent_at, is_system = excluded.is_system,"
            " preview = excluded.preview",
            (chat_id, message_id, utcnow_iso(), 1 if is_system else 0, preview),
        )
        await self._conn.commit()

    async def bot_messages_since(self, chat_id: int, since: datetime) -> list[int]:
        cursor = await self._conn.execute(
            "SELECT message_id FROM bot_messages WHERE chat_id = ? AND sent_at >= ?",
            (chat_id, _iso(since)),
        )
        return [row[0] for row in await cursor.fetchall()]

    async def system_bot_messages_since(self, chat_id: int, since: datetime) -> list[int]:
        """Same as `bot_messages_since`, restricted to is_system rows — the
        admin panel's "удалить системные сообщения за 24 часа" (2026-09-05
        follow-up), a narrower sibling of the unconditional 24h wipe that
        leaves published achievements/stats/summaries untouched."""
        cursor = await self._conn.execute(
            "SELECT message_id FROM bot_messages WHERE chat_id = ? AND sent_at >= ? "
            "AND is_system = 1",
            (chat_id, _iso(since)),
        )
        return [row[0] for row in await cursor.fetchall()]

    async def all_system_bot_messages(self, chat_id: int) -> list[int]:
        """Unbounded version of `system_bot_messages_since` — the admin
        panel's "удалить все системные сообщения" (2026-09-05 follow-up),
        for whenever the 24h window isn't enough."""
        cursor = await self._conn.execute(
            "SELECT message_id FROM bot_messages WHERE chat_id = ? AND is_system = 1",
            (chat_id,),
        )
        return [row[0] for row in await cursor.fetchall()]

    async def due_system_messages(self, cutoff: datetime) -> list[tuple[int, int]]:
        """System messages old enough to auto-delete (poller/message_cleanup.py,
        2026-09-05 follow-up) — across every chat, not one at a time, since
        the cleanup tick sweeps the whole bot in one pass."""
        cursor = await self._conn.execute(
            "SELECT chat_id, message_id FROM bot_messages WHERE is_system = 1 AND sent_at <= ?",
            (_iso(cutoff),),
        )
        return [(row[0], row[1]) for row in await cursor.fetchall()]

    async def last_bot_message(self, chat_id: int) -> int | None:
        """For the admin panel's unconditional 24h wipe — deliberately not
        filtered by is_system, unlike `last_non_system_bot_message` below."""
        cursor = await self._conn.execute(
            "SELECT message_id FROM bot_messages WHERE chat_id = ? "
            "ORDER BY message_id DESC LIMIT 1",
            (chat_id,),
        )
        row = await cursor.fetchone()
        return row[0] if row else None

    async def last_non_system_bot_message(self, chat_id: int) -> DeletableMessage | None:
        """For /delete_last (SPEC 6.4's follow-up, narrowed 2026-09-05):
        skips past trailing system messages (prompts, /help, the hub) to
        the last actual result — those are what "oops, wrong one just now"
        is almost always about, and a system message a few seconds old is
        about to clean itself up regardless. Telegram message_ids are
        assigned sequentially per chat, so the highest one logged here *is*
        the most recent, no timestamp-tie ambiguity the way sent_at alone
        would have (same-second messages are common right after a poll tick
        publishes more than one).

        Returns the row's own `preview` alongside the id (2026-09-09) — the
        caller's own confirmation names what it's about to delete, rather
        than deleting silently; `None` there just means an older row or a
        message with no text/caption, never a reason to fail the delete.
        """
        cursor = await self._conn.execute(
            "SELECT message_id, preview FROM bot_messages WHERE chat_id = ? AND is_system = 0 "
            "ORDER BY message_id DESC LIMIT 1",
            (chat_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return DeletableMessage(message_id=row["message_id"], preview=row["preview"])

    async def forget_bot_messages(self, chat_id: int, message_ids: Sequence[int]) -> None:
        """Drops the log rows after an actual delete attempt — called
        regardless of whether Telegram could delete every one of them (some
        may already be gone), since there is nothing more to do about those
        either way."""
        await self._conn.executemany(
            "DELETE FROM bot_messages WHERE chat_id = ? AND message_id = ?",
            [(chat_id, message_id) for message_id in message_ids],
        )
        await self._conn.commit()
