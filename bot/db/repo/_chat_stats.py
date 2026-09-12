"""Per-chat leaderboards, the monthly games block, /online's merged
presence, and /online's own auto-refresh bookkeeping — one mixin of
bot.db.repo.Repo (2026-09-09 split; see this package's own __init__.py).
Behavior is unchanged from before the split.
"""

from __future__ import annotations

from datetime import datetime

from bot.db.repo._models import (
    ChatMemberStat,
    ChatPresenceRow,
    ChatTopGame,
    OnlineAutoRefreshRow,
    _iso,
)
from bot.util import utcnow_iso


class _ChatStatsRepo:
    # ------------------------------------------------------------ chat stats

    async def chat_member_stats(
        self,
        chat_id: int,
        since: datetime,
        rare_threshold: float,
        until: datetime | None = None,
    ) -> list[ChatMemberStat]:
        """Per-person totals for a chat over a period.

        Excluded users drop out here; everyone else appears even with a zero,
        including rows the feed filtered out — the summary is a report, not
        the feed (SPEC 7.3). The date filter lives in the JOIN, not WHERE: a
        WHERE on the right-hand table turns a LEFT JOIN back into an INNER
        JOIN, which is exactly the bug that used to hide zero-scorers.

        `psn_count` was missing until #32 — this is a separate query from
        `achievement_platform_breakdown` (which feeds /stats' own per-person
        counters) with its own independent xbox/steam `CASE`s, so it needed
        the identical fix a second time: `cnt`'s combined total already
        included PSN rows (plain `tg_id` sum), the per-platform split next
        to it silently didn't.
        """
        date_bound = "AND s.unlocked_at >= ?"
        date_params: list[object] = [_iso(since)]
        if until is not None:
            date_bound += " AND s.unlocked_at < ?"
            date_params.append(_iso(until))

        cursor = await self._conn.execute(
            # Every field the person chain needs, not just the Xbox one
            # (#51): a member with no Xbox account used to have no name here
            # at all and rendered as a bare "id319472587", which is exactly
            # what #38 fixed and a revert took back out.
            "SELECT u.tg_id, u.gamertag, u.gamertag_modern, u.username, u.first_name,"
            "       u.last_name, u.xuid,"
            "       steam.display_name AS steam_name, psn.display_name AS psn_name,"
            "       COUNT(s.achievement_id) AS cnt,"
            "       COALESCE(SUM(s.gamerscore), 0) AS score,"
            "       SUM(CASE WHEN s.rarity_percent IS NOT NULL AND s.rarity_percent <= ?"
            "                THEN 1 ELSE 0 END) AS rare,"
            "       SUM(CASE WHEN s.platform IN ('xbox_modern', 'xbox_360') THEN 1 ELSE 0 END)"
            "           AS xbox_count,"
            "       SUM(CASE WHEN s.platform = 'steam' THEN 1 ELSE 0 END) AS steam_count,"
            "       SUM(CASE WHEN s.platform = 'psn' THEN 1 ELSE 0 END) AS psn_count "
            "FROM subscriptions sub "
            "JOIN users u ON u.tg_id = sub.tg_id "
            # tg_id, not xuid (SPEC 9, M-Steam-2e) — sums every platform's
            # achievements for this person into one count, since
            # seen_achievements.tg_id is on every row regardless of platform
            # (2a). gamerscore stays Xbox-only automatically: a Steam row's
            # gamerscore is always 0 (services/steam/achievements.py).
            "LEFT JOIN seen_achievements s ON s.tg_id = u.tg_id " + date_bound + " "
            "LEFT JOIN platform_links steam ON steam.tg_id = u.tg_id AND steam.platform = 'steam' "
            "LEFT JOIN platform_links psn ON psn.tg_id = u.tg_id AND psn.platform = 'psn' "
            "WHERE sub.chat_id = ? AND u.is_excluded = 0 "
            "GROUP BY u.tg_id ORDER BY cnt DESC, score DESC",
            [rare_threshold, *date_params, chat_id],
        )
        return [
            ChatMemberStat(
                tg_id=row["tg_id"],
                gamertag=row["gamertag"],
                xuid=row["xuid"],
                gamertag_modern=row["gamertag_modern"],
                username=row["username"],
                first_name=row["first_name"],
                last_name=row["last_name"],
                steam_name=row["steam_name"],
                psn_name=row["psn_name"],
                count=int(row["cnt"]),
                score=int(row["score"]),
                rare=int(row["rare"] or 0),
                xbox_count=int(row["xbox_count"] or 0),
                steam_count=int(row["steam_count"] or 0),
                psn_count=int(row["psn_count"] or 0),
            )
            for row in await cursor.fetchall()
        ]

    async def chat_top_games(
        self, chat_id: int, since: datetime, limit: int = 15
    ) -> list[ChatTopGame]:
        """Games the chat's subscribed members played this window, ranked by
        total achievements/trophies earned across all of them combined (#7,
        monthly summary's own new block) — same "report, not the feed"
        subscribers-only scope `chat_member_stats` above uses, joined by
        title instead of by person. `titles` already covers every platform
        (Xbox, Steam, and PSN all upsert into it on their own achievement
        inserts), so one COALESCE covers "no cached name yet" for all three
        the same way /stats' own games list does.

        `limit == 0` means "no cap" (same convention as the admin's own
        summary_top_limit setting, SPEC 6.4) — SQLite's own `LIMIT 0` would
        instead mean "zero rows", so that case skips the clause entirely
        rather than passing 0 through literally.

        Grouped by `(title_id, platform)`, not `title_id` alone — two
        different platforms' own id namespaces are not guaranteed disjoint
        (a Steam appid and an Xbox title_id are both bare numeric strings),
        so grouping by title_id only could in principle fold two unrelated
        games from different platforms into one row."""
        query = (
            "SELECT s.title_id, s.platform, t.name,"
            "       COUNT(*) AS cnt, COALESCE(SUM(s.gamerscore), 0) AS score,"
            "       SUM(CASE WHEN s.trophy_type = 'bronze' THEN 1 ELSE 0 END) AS bronze,"
            "       SUM(CASE WHEN s.trophy_type = 'silver' THEN 1 ELSE 0 END) AS silver,"
            "       SUM(CASE WHEN s.trophy_type = 'gold' THEN 1 ELSE 0 END) AS gold,"
            "       SUM(CASE WHEN s.trophy_type = 'platinum' THEN 1 ELSE 0 END) AS platinum "
            "FROM seen_achievements s "
            "JOIN subscriptions sub ON sub.tg_id = s.tg_id AND sub.chat_id = ? "
            "LEFT JOIN titles t ON t.title_id = s.title_id "
            "WHERE s.unlocked_at >= ? "
            "GROUP BY s.title_id, s.platform "
            "ORDER BY cnt DESC"
        )
        params: list[object] = [chat_id, _iso(since)]
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        cursor = await self._conn.execute(query, params)
        return [
            ChatTopGame(
                title_id=row["title_id"],
                platform=row["platform"],
                name=row["name"],
                count=int(row["cnt"]),
                score=int(row["score"] or 0),
                bronze=int(row["bronze"] or 0),
                silver=int(row["silver"] or 0),
                gold=int(row["gold"] or 0),
                platinum=int(row["platinum"] or 0),
            )
            for row in await cursor.fetchall()
        ]

    async def chat_member_presence(self, chat_id: int) -> list[ChatPresenceRow]:
        """Every connected, non-excluded member *known to be in this chat*,
        with his last known presence — for /online (SPEC 6.3). "Known to be
        in this chat" is the union of who publishes here (`subscriptions`)
        and who has just been seen writing here (`chat_seen`) — publishing
        and being a member are not the same thing, and /online listing only
        publishers made it look like nobody else was playing. Playing-now
        first, then online, then the rest, so the people actually worth
        pinging float to the top.

        Merges Xbox and Steam presence (SPEC 9, M-Steam-2e) by activity
        level first, freshness only as a tiebreaker — **not** "whichever
        updated more recently wins" outright: found live, that version
        showed someone as idle-on-Xbox instead of actively-playing-on-
        Steam simply because Xbox happened to get polled a moment later,
        which every poll does regardless of whether anything changed
        (`save_presence_state`/`save_steam_presence_state` bump
        `updated_at` on every tick). "Playing" always beats "online",
        which always beats "offline/no data", on whichever platform it's
        true on; `updated_at` only decides between two platforms tied at
        the *same* level (both playing, or both merely online) — matching
        the "играет > онлайн > офлайн" rule this was designed to have from
        the start.

        Normalized into the same `state`/`title_id`/`title_name` shape
        Xbox always used, so the "playing/online/offline" wording
        (`_presence_text`, `handlers/chat.py`) never needs to know Steam
        presence exists. `platform` is reported alongside it too, only for
        the icon colour next to the name (`_presence_icon`) — falls back
        to whichever platform the person actually has connected when
        neither has any presence data at all. A person known only through
        Steam now appears here too — used to require `u.xuid IS NOT NULL`,
        which silently dropped Steam-only members entirely.

        PSN presence is wired in the same way Steam was (issue #1) —
        `psn_presence_state`, populated by its own tiny poller
        (poller/psn_presence.py), no achievement-poll coupling at all
        (trophy sync has never been presence-driven on PSN, see that
        table's own schema.sql comment).

        The row's *label* (Follow-up 2026-09-08, reverting an earlier
        Telegram-identity attempt that pinged people every auto-refresh —
        see #38's revert) is the platform-specific nickname of whichever
        platform `winner` points at: the one currently being played, or —
        while offline — whichever connected platform has *real tracked
        presence* and was polled more recently ("last active platform").
        Using freshness here is safe even though the docstring above warns
        against it for *deciding who's online*: this branch only runs once
        every candidate is already known-offline, so there is no "wrongly
        looks active" failure mode left to worry about, only which idle
        nickname to show. Ties (including a genuine 3-way tie at the same
        activity level) are broken by a single ranked sub-select rather
        than hand-enumerated pairwise comparisons, so adding PSN as a third
        candidate didn't need a third copy of the same tie-break logic.
        `winner = 'none'` means no tracked presence exists at all on any
        platform (an account never polled yet) — `online_view.py` falls
        back to the Telegram name there, plain (no "@"), so nobody gets
        pinged by the auto-refreshing table.
        """
        cursor = await self._conn.execute(
            "WITH member AS ("
            "  SELECT tg_id FROM subscriptions WHERE chat_id = ? "
            "  UNION "
            "  SELECT tg_id FROM chat_seen WHERE chat_id = ?"
            "), presence AS ("
            "  SELECT u.tg_id, u.gamertag, u.gamertag_modern, u.username, u.first_name,"
            "         u.last_name, u.xuid,"
            "         xp.state AS xbox_state, xp.title_id AS xbox_title_id,"
            "         xp.title_name AS xbox_title_name, xp.updated_at AS xbox_updated_at,"
            "         sp.persona_state AS steam_persona_state, sp.gameid AS steam_gameid,"
            "         sp.game_name AS steam_game_name, sp.updated_at AS steam_updated_at,"
            "         steam.external_id AS steam_external_id,"
            "         steam.display_name AS steam_display_name,"
            "         psn.external_id AS psn_external_id, psn.display_name AS psn_display_name,"
            "         pp.state AS psn_state, pp.title_id AS psn_title_id,"
            "         pp.title_name AS psn_title_name, pp.updated_at AS psn_updated_at,"
            "         CASE WHEN xp.state = 'Online' AND xp.title_id IS NOT NULL THEN 2"
            "              WHEN xp.state = 'Online' THEN 1"
            "              ELSE 0 END AS xbox_level,"
            "         CASE WHEN sp.persona_state IS NOT NULL AND sp.persona_state != 0"
            "                   AND sp.gameid IS NOT NULL THEN 2"
            "              WHEN sp.persona_state IS NOT NULL AND sp.persona_state != 0 THEN 1"
            "              ELSE 0 END AS steam_level,"
            "         CASE WHEN pp.state = 'Online' AND pp.title_id IS NOT NULL THEN 2"
            "              WHEN pp.state = 'Online' THEN 1"
            "              ELSE 0 END AS psn_level"
            "  FROM member"
            "  JOIN users u ON u.tg_id = member.tg_id"
            "  LEFT JOIN presence_state xp ON xp.xuid = u.xuid"
            "  LEFT JOIN platform_links steam ON steam.tg_id = u.tg_id AND steam.platform = 'steam'"
            "  LEFT JOIN steam_presence_state sp ON sp.steam_id = steam.external_id"
            "  LEFT JOIN platform_links psn ON psn.tg_id = u.tg_id AND psn.platform = 'psn'"
            "  LEFT JOIN psn_presence_state pp ON pp.account_id = psn.external_id"
            "  WHERE (u.xuid IS NOT NULL OR steam.external_id IS NOT NULL"
            "         OR psn.external_id IS NOT NULL) AND u.is_excluded = 0"
            "), decided AS ("
            "  SELECT *, MAX(xbox_level, steam_level, psn_level) AS top_level"
            "  FROM presence"
            "), picked AS ("
            "  SELECT decided.*, ("
            "    SELECT platform FROM ("
            "      SELECT 'xbox_modern' AS platform, xbox_level AS level, xbox_updated_at AS ts"
            "      UNION ALL SELECT 'steam', steam_level, steam_updated_at"
            "      UNION ALL SELECT 'psn', psn_level, psn_updated_at"
            "    ) candidates"
            "    WHERE candidates.level = decided.top_level"
            "    ORDER BY candidates.ts IS NULL, candidates.ts DESC"
            "    LIMIT 1"
            "  ) AS ranked_winner"
            "  FROM decided"
            "), final AS ("
            "  SELECT *, CASE"
            # Nothing tracked anywhere at all (never polled on any
            # platform) — Telegram identity fallback, not an arbitrary
            # pick among three equally-empty candidates.
            "    WHEN top_level = 0 AND xbox_state IS NULL"
            "         AND steam_persona_state IS NULL AND psn_state IS NULL THEN 'none'"
            "    ELSE ranked_winner"
            "    END AS winner"
            "  FROM picked"
            ") "
            "SELECT tg_id, gamertag, gamertag_modern, username, first_name, last_name, xuid,"
            "       CASE winner"
            "         WHEN 'steam' THEN"
            "           CASE WHEN steam_persona_state != 0 THEN 'Online' ELSE 'Offline' END"
            "         WHEN 'xbox_modern' THEN xbox_state"
            "         WHEN 'psn' THEN psn_state"
            "         ELSE NULL END AS state,"
            "       CASE winner WHEN 'steam' THEN steam_gameid"
            "                   WHEN 'xbox_modern' THEN xbox_title_id"
            "                   WHEN 'psn' THEN psn_title_id ELSE NULL END AS title_id,"
            "       CASE winner WHEN 'steam' THEN steam_game_name"
            "                   WHEN 'xbox_modern' THEN xbox_title_name"
            "                   WHEN 'psn' THEN psn_title_name ELSE NULL END AS title_name,"
            "       winner AS platform, steam_display_name, psn_display_name "
            "FROM final "
            "ORDER BY "
            "  CASE WHEN state = 'Online' AND title_id IS NOT NULL THEN 0 "
            "       WHEN state = 'Online' THEN 1 "
            "       ELSE 2 END, "
            # By the label the table actually renders (#51) — this used to
            # order by `gamertag` alone, i.e. by an Xbox nickname that a
            # Steam/PSN row does not even have and that /online never shows.
            "  CASE winner WHEN 'steam' THEN steam_display_name"
            "              WHEN 'psn' THEN psn_display_name"
            "              ELSE COALESCE(gamertag_modern, gamertag) END COLLATE NOCASE",
            (chat_id, chat_id),
        )
        return [
            ChatPresenceRow(
                tg_id=row["tg_id"],
                gamertag=row["gamertag"],
                gamertag_modern=row["gamertag_modern"],
                xuid=row["xuid"],
                state=row["state"],
                title_id=row["title_id"],
                title_name=row["title_name"],
                platform=row["platform"],
                steam_display_name=row["steam_display_name"],
                psn_display_name=row["psn_display_name"],
                username=row["username"],
                first_name=row["first_name"],
                last_name=row["last_name"],
            )
            for row in await cursor.fetchall()
        ]

    async def start_online_auto_refresh(self, chat_id: int, message_id: int) -> None:
        """A fresh /online supersedes whatever was auto-refreshing in this
        chat before (Follow-up 2026-09-05, poller/online_refresh.py) — the
        old message just goes stale, nothing needs to actively stop it.
        Both timestamps reset: created_at is the 3h cutoff's own clock,
        independent of whatever the previous table's age was."""
        now = utcnow_iso()
        await self._conn.execute(
            "INSERT INTO online_auto_refresh (chat_id, message_id, created_at, last_updated_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(chat_id) DO UPDATE SET"
            " message_id = excluded.message_id, created_at = excluded.created_at,"
            " last_updated_at = excluded.last_updated_at",
            (chat_id, message_id, now, now),
        )
        await self._conn.commit()

    async def touch_online_auto_refresh(self, chat_id: int) -> None:
        await self._conn.execute(
            "UPDATE online_auto_refresh SET last_updated_at = ? WHERE chat_id = ?",
            (utcnow_iso(), chat_id),
        )
        await self._conn.commit()

    async def delete_online_auto_refresh(self, chat_id: int) -> None:
        await self._conn.execute("DELETE FROM online_auto_refresh WHERE chat_id = ?", (chat_id,))
        await self._conn.commit()

    async def all_online_auto_refreshes(self) -> list[OnlineAutoRefreshRow]:
        cursor = await self._conn.execute(
            "SELECT chat_id, message_id, created_at, last_updated_at FROM online_auto_refresh"
        )
        return [
            OnlineAutoRefreshRow(
                chat_id=row["chat_id"],
                message_id=row["message_id"],
                created_at=row["created_at"],
                last_updated_at=row["last_updated_at"],
            )
            for row in await cursor.fetchall()
        ]

    async def get_online_auto_refresh(self, chat_id: int) -> OnlineAutoRefreshRow | None:
        """Follow-up 2026-09-06: /online now deletes its own previous copy
        before posting a new one (same "don't spam the chat" rule as
        tracked_messages below) — needs the old message_id before
        start_online_auto_refresh overwrites the row with the new one."""
        cursor = await self._conn.execute(
            "SELECT chat_id, message_id, created_at, last_updated_at "
            "FROM online_auto_refresh WHERE chat_id = ?",
            (chat_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return OnlineAutoRefreshRow(
            chat_id=row["chat_id"],
            message_id=row["message_id"],
            created_at=row["created_at"],
            last_updated_at=row["last_updated_at"],
        )
