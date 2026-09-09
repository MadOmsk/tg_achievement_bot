"""Xbox title-history cache and the achievement-count aggregates behind
/stats, /admin's user list, and the daily summary — one mixin of
bot.db.repo.Repo (2026-09-09 split; see this package's own __init__.py).
Behavior is unchanged from before the split.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime

from bot.db.repo._models import TitleHistoryRow, _iso
from bot.util import utcnow_iso


class _StatsRepo:
    # --------------------------------------------------------- title history

    async def save_title_history(self, xuid: str, entries: Sequence[TitleHistoryRow]) -> None:
        now = utcnow_iso()
        for entry in entries:
            await self._conn.execute(
                "INSERT INTO title_history (xuid, title_id, current_gamerscore, max_gamerscore,"
                " achievements_unlocked, achievements_total, last_played_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(xuid, title_id) DO UPDATE SET "
                "  current_gamerscore = excluded.current_gamerscore,"
                "  max_gamerscore = excluded.max_gamerscore,"
                "  achievements_unlocked = excluded.achievements_unlocked,"
                "  achievements_total = excluded.achievements_total,"
                "  last_played_at = excluded.last_played_at,"
                "  updated_at = excluded.updated_at",
                (
                    xuid,
                    entry.title_id,
                    entry.current_gamerscore,
                    entry.max_gamerscore,
                    entry.achievements_unlocked,
                    entry.achievements_total,
                    entry.last_played_at,
                    now,
                ),
            )
            await self._conn.execute(
                "INSERT INTO titles (title_id, name, platform, updated_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(title_id) DO UPDATE SET name = excluded.name,"
                " platform = excluded.platform, updated_at = excluded.updated_at",
                (entry.title_id, entry.name, entry.platform, now),
            )
        await self._conn.commit()

    async def update_gamerscore(self, tg_id: int, gamerscore: int) -> None:
        await self._conn.execute(
            "UPDATE users SET gamerscore = ?, updated_at = ? WHERE tg_id = ?",
            (gamerscore, utcnow_iso(), tg_id),
        )
        await self._conn.commit()

    # ------------------------------------------------------------ aggregates

    async def _achievement_counts_by(
        self, column: str, value: object, since: datetime | None
    ) -> tuple[int, int]:
        """Shared shape behind `achievement_counts` (by xuid) and
        `achievement_counts_for_person` (by tg_id) below (2026-09-05
        refactor) — identical query, just which column identifies the rows.
        `column` is always one of the two literal strings those two pass,
        never anything derived from a request, so interpolating it here
        carries no injection risk despite not being a bound parameter."""
        query = (
            "SELECT COUNT(*), COALESCE(SUM(gamerscore), 0) "
            f"FROM seen_achievements WHERE {column} = ?"
        )
        params: list[object] = [value]
        if since is not None:
            query += " AND unlocked_at >= ?"
            params.append(_iso(since))
        cursor = await self._conn.execute(query, params)
        row = await cursor.fetchone()
        return (int(row[0]), int(row[1])) if row else (0, 0)

    async def achievement_counts(self, xuid: str, since: datetime | None) -> tuple[int, int]:
        """How many achievements and how much gamerscore since a moment.

        Counted regardless of `is_backfill` (SPEC 5.9). Timestamps are stored
        as UTC ISO strings of one shape, so a string comparison is a time
        comparison here.
        """
        return await self._achievement_counts_by("xuid", xuid, since)

    async def achievement_counts_for_person(
        self, tg_id: int, since: datetime | None
    ) -> tuple[int, int]:
        """Same as `achievement_counts`, but summed across every platform a
        person has connected (SPEC 9, M-Steam-2e) — `/stats`/`/summary`'s
        counters, not `achievement_counts`' own caller (`scripts/reconcile_
        achievements.py`, which deliberately stays per-Xbox-account: it
        checks one xuid's stored gamerscore against what Xbox itself
        reports for that xuid, a comparison that has no Steam side to sum
        in). `gamerscore` sums correctly here with no special-casing: a
        Steam row's gamerscore is always 0 (services/steam/achievements.py),
        so it never contributes to the sum, by construction, not by a check
        here."""
        return await self._achievement_counts_by("tg_id", tg_id, since)

    async def achievement_platform_breakdown(
        self, tg_id: int, since: datetime | None
    ) -> tuple[int, int, int]:
        """The (xbox, steam, psn) counts behind `achievement_counts_for_person`'s
        single combined total (2026-09-05 follow-up, reversal of "one number
        only" — SPEC 9 M-Steam-2e originally dropped a per-platform split on
        purpose; the parenthetical here doesn't touch that decision, the
        combined number still leads and still sorts). x360 counts as Xbox —
        there's no separate UI concept of "Xbox 360" anywhere outside the
        achievement message itself and the games table's own icon.

        PSN's own bucket was missing entirely until #32 (found live: the
        combined total already included PSN rows via the plain `tg_id`
        sum in `achievement_counts_for_person`, but this breakdown's two
        `CASE`s matched neither for a `psn` row, so it silently vanished
        from the parenthetical while still counting toward the total —
        the numbers next to each other didn't add up)."""
        query = (
            "SELECT SUM(CASE WHEN platform IN ('modern', 'x360') THEN 1 ELSE 0 END),"
            "       SUM(CASE WHEN platform = 'steam' THEN 1 ELSE 0 END),"
            "       SUM(CASE WHEN platform = 'psn' THEN 1 ELSE 0 END) "
            "FROM seen_achievements WHERE tg_id = ?"
        )
        params: list[object] = [tg_id]
        if since is not None:
            query += " AND unlocked_at >= ?"
            params.append(_iso(since))
        cursor = await self._conn.execute(query, params)
        row = await cursor.fetchone()
        return (int(row[0] or 0), int(row[1] or 0), int(row[2] or 0)) if row else (0, 0, 0)

    async def platform_achievement_count(self, tg_id: int, platform: str) -> int:
        """Lifetime count for one platform (SPEC 9, M-Steam-2e's /stats line
        next to each connected platform) — deliberately not offered for
        Xbox (`achievement_counts` never exposes a since=None total either,
        SPEC 5.4): a lifetime Steam count has no cap to worry about
        (backfill walks the whole owned-games library via GetOwnedGames),
        so it doesn't carry the same "could quietly undercount" risk."""
        cursor = await self._conn.execute(
            "SELECT COUNT(*) FROM seen_achievements WHERE tg_id = ? AND platform = ?",
            (tg_id, platform),
        )
        row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def xbox_achievement_count(self, tg_id: int) -> int:
        """A lifetime Xbox count, added to /stats' XBOX line (2026-09-08,
        user request, confirmed against the previous "never shown, could
        quietly undercount" call — see CLAUDE.md's Statistics rules for the
        current wording). Counts `seen_achievements` directly (modern +
        x360) rather than summing `title_history`: a broad Xbox-wide
        history endpoint feeds modern's backfill, not a per-title cap, so
        modern is trustworthy here. x360's own backfill is still a
        title-by-title pass driven by `title_history`'s own list, so an
        x360 game `title_history` never learned about remains a silent gap
        — accepted as the one remaining soft spot, not fixed by this."""
        cursor = await self._conn.execute(
            "SELECT COUNT(*) FROM seen_achievements "
            "WHERE tg_id = ? AND platform IN ('modern', 'x360')",
            (tg_id,),
        )
        row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def xbox_completed_games_count(self, xuid: str) -> int:
        """Games where every achievement has been earned (#19) — straight
        from the already-cached title_history, no new tracking needed."""
        cursor = await self._conn.execute(
            "SELECT COUNT(*) FROM title_history "
            "WHERE xuid = ? AND achievements_total > 0"
            " AND achievements_unlocked >= achievements_total",
            (xuid,),
        )
        row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def psn_platinum_count(self, tg_id: int) -> int:
        """PSN's own equivalent of "completed" (#19) — Sony only awards a
        platinum once every other trophy in that game is earned, so this
        already *is* a 100%-completed-games count, no extra tracking."""
        cursor = await self._conn.execute(
            "SELECT COUNT(*) FROM seen_achievements "
            "WHERE tg_id = ? AND platform = 'psn' AND trophy_type = 'platinum'",
            (tg_id,),
        )
        row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def steam_completed_games_count(self, tg_id: int) -> int:
        """Steam's own equivalent (#19) — harder than Xbox/PSN: there's no
        per-user, per-game "total achievements" cached directly. Joins a
        per-app achieved count (`seen_achievements`) against
        `steam_schema_cache`'s own per-app achievement list length, done in
        Python rather than a SQL JSON function — keeps this consistent with
        every other `steam_schema_cache` read in this codebase, all of which
        already `json.loads()` the blob in Python."""
        cursor = await self._conn.execute(
            "SELECT title_id, COUNT(*) FROM seen_achievements "
            "WHERE tg_id = ? AND platform = 'steam' GROUP BY title_id",
            (tg_id,),
        )
        achieved_by_app = {row[0]: row[1] for row in await cursor.fetchall()}
        if not achieved_by_app:
            return 0
        placeholders = ",".join("?" * len(achieved_by_app))
        cursor = await self._conn.execute(
            f"SELECT appid, achievements FROM steam_schema_cache WHERE appid IN ({placeholders})",
            list(achieved_by_app.keys()),
        )
        completed = 0
        for row in await cursor.fetchall():
            total = len(json.loads(row["achievements"]))
            if total > 0 and achieved_by_app[row["appid"]] >= total:
                completed += 1
        return completed

    async def achievement_counts_by_xuid(
        self, since: datetime | None
    ) -> dict[str, tuple[int, int]]:
        """The same numbers for everyone at once — one query for a whole page."""
        query = "SELECT xuid, COUNT(*), COALESCE(SUM(gamerscore), 0) FROM seen_achievements"
        params: list[object] = []
        if since is not None:
            query += " WHERE unlocked_at >= ?"
            params.append(_iso(since))
        cursor = await self._conn.execute(query + " GROUP BY xuid", params)
        return {row[0]: (int(row[1]), int(row[2])) for row in await cursor.fetchall()}

    async def achievement_counts_by_tg_id(
        self, since: datetime | None
    ) -> dict[int, tuple[int, int]]:
        """Same as `achievement_counts_by_xuid`, but summed across every
        platform a person has connected (SPEC 9, M-Steam-2e) — the admin
        users list's own combined counters (2026-09-05 follow-up): the list
        used to show `achievement_counts_by_xuid`'s Xbox-only numbers even
        for someone with Steam achievements too."""
        query = "SELECT tg_id, COUNT(*), COALESCE(SUM(gamerscore), 0) FROM seen_achievements"
        params: list[object] = []
        if since is not None:
            query += " WHERE unlocked_at >= ?"
            params.append(_iso(since))
        cursor = await self._conn.execute(query + " GROUP BY tg_id", params)
        return {row[0]: (int(row[1]), int(row[2])) for row in await cursor.fetchall()}
