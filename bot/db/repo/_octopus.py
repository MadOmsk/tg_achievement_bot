"""The octopus's queue and what it reads to assemble a game (#215, migration
126)."""

from __future__ import annotations

from datetime import timedelta

from bot.util import utcnow, utcnow_iso

# A failed entry is asked again in an hour, and dropped after three tries; the
# source's own `fetch_state` keeps the error.
RETRY = timedelta(hours=1)
TRIES = 3
# How long a taken entry is held: longer than any one assembly runs.
HOLD = timedelta(minutes=30)


class _OctopusRepo:
    # ------------------------------------------------------------ the queue

    async def octopus_enqueue(self, key: str, reason: str = "") -> bool:
        """Put an entry in the queue, due now. Returns whether it was new."""
        now = utcnow_iso()
        cursor = await self._conn.execute(
            "INSERT INTO octopus_queue (key, reason, due_at, created_at)"
            " VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING",
            (key, reason, now, now),
        )
        await self._conn.commit()
        return cursor.rowcount == 1

    async def octopus_due(self, limit: int) -> list[tuple[str, str]]:
        """`(key, reason)` due now, the oldest first."""
        cursor = await self._conn.execute(
            "SELECT key, reason FROM octopus_queue WHERE due_at <= ?"
            " ORDER BY due_at, created_at, key LIMIT ?",
            (utcnow_iso(), limit),
        )
        return [(str(r[0]), str(r[1] or "")) for r in await cursor.fetchall()]

    async def octopus_take(self) -> tuple[str, str] | None:
        """The oldest entry due now, held for `HOLD` so another bot on the
        shared games database (#229) does not take it too: the hold is a
        conditional update, which only one of two bots can win. A run that
        dies leaves it due again when the hold runs out. No `RETURNING`: an
        unfinished one is a write in progress, and every other coroutine's
        commit on the connection fails while it is (2026-10-28)."""
        for _ in range(3):
            now = utcnow_iso()
            cursor = await self._conn.execute(
                "SELECT key, reason FROM octopus_queue WHERE due_at <= ?"
                " ORDER BY due_at, created_at, key LIMIT 1",
                (now,),
            )
            row = await cursor.fetchone()
            await cursor.close()
            if row is None:
                return None
            held = (utcnow() + HOLD).isoformat(timespec="seconds")
            cursor = await self._conn.execute(
                "UPDATE octopus_queue SET due_at = ? WHERE key = ? AND due_at <= ?",
                (held, row[0], now),
            )
            await self._conn.commit()
            if cursor.rowcount == 1:
                return str(row[0]), str(row[1] or "")
        return None

    async def octopus_done(self, key: str) -> None:
        await self._conn.execute("DELETE FROM octopus_queue WHERE key = ?", (key,))
        await self._conn.commit()

    async def octopus_failed(self, key: str, error: str) -> None:
        await self._conn.execute(
            "UPDATE octopus_queue SET attempts = attempts + 1, last_error = ?, due_at = ?"
            " WHERE key = ?",
            (error[:500], (utcnow() + RETRY).isoformat(timespec="seconds"), key),
        )
        await self._conn.execute(
            "DELETE FROM octopus_queue WHERE key = ? AND attempts >= ?", (key, TRIES)
        )
        await self._conn.commit()

    async def octopus_waiting(self) -> int:
        cursor = await self._conn.execute("SELECT COUNT(*) FROM octopus_queue")
        return int((await cursor.fetchone())[0])

    async def octopus_retrying(self) -> int:
        """Entries that failed at least once and wait to be tried again."""
        cursor = await self._conn.execute("SELECT COUNT(*) FROM octopus_queue WHERE attempts > 0")
        return int((await cursor.fetchone())[0])

    # ------------------------------------------------------- entry → anchor

    async def _ids(self, sql: str, args: tuple) -> list[int]:
        cursor = await self._conn.execute(sql, args)
        return [int(r[0]) for r in await cursor.fetchall()]

    async def versions_of_store_product(self, store: str, product_id: str) -> list[int]:
        return await self._ids(
            "SELECT version_id FROM versions WHERE store = ? AND product_id = ?"
            " ORDER BY version_id",
            (store, product_id),
        )

    async def version_of_dlc(self, dlc_id: int) -> int | None:
        found = await self._ids("SELECT version_id FROM dlcs WHERE dlc_id = ?", (dlc_id,))
        return found[0] if found else None

    async def versions_by_store_id(self, kind: str, value: str) -> list[int]:
        """The versions a store id names (`versions.store_ids`: a PSN title
        id, an Xbox product id, …), case aside."""
        return await self._ids(
            "SELECT DISTINCT v.version_id FROM versions v,"
            " jsonb_array_elements(v.store_ids::jsonb) j"
            " WHERE j.value->>0 = ?"
            " AND UPPER(j.value->>1) = UPPER(?) ORDER BY v.version_id",
            (kind, value),
        )

    # ----------------------------------------------------- spreading entries

    async def octopus_edition_versions(self, edition_id: int) -> list[int]:
        """The versions a bundle or an edition holds, its main game first."""
        return await self._ids(
            "SELECT version_id FROM edition_items"
            " WHERE edition_id = ? AND version_id IS NOT NULL"
            " GROUP BY version_id"
            " ORDER BY MIN(CASE WHEN COALESCE(role, 'main') <> 'main' THEN 1 ELSE 0 END),"
            " MAX(is_primary) DESC, version_id",
            (edition_id,),
        )

    async def octopus_series_games(self, series_id: int) -> tuple[str | None, list[int]]:
        """A series' name and its games (those said not to be in it left out)."""
        cursor = await self._conn.execute(
            "SELECT name FROM series WHERE series_id = ?", (series_id,)
        )
        row = await cursor.fetchone()
        games = await self._ids(
            "SELECT game_id FROM game_series WHERE series_id = ? AND member = 1 ORDER BY game_id",
            (series_id,),
        )
        return (str(row[0]) if row else None), games

    async def octopus_account_lists(self, platform: str, external_id: str) -> list[tuple[str, str]]:
        """Every achievement list an account earned something in, as
        `(platform, title_id)`; an Xbox account covers both generations."""
        platforms = ("xbox_modern", "xbox_360") if platform == "xbox" else (platform,)
        marks = ",".join("?" * len(platforms))
        cursor = await self._conn.execute(
            f"SELECT DISTINCT platform, title_id FROM seen_achievements"
            f" WHERE xuid = ? AND platform IN ({marks}) ORDER BY platform, title_id",
            (external_id, *platforms),
        )
        return [(str(r[0]), str(r[1])) for r in await cursor.fetchall()]

    # --------------------------------------------------------- the assembly

    async def octopus_names_of_game(self, game_id: int) -> list[str]:
        """Every name the game is known by (#215: one name found too little):
        its own, the Russian one, its versions' store names, its editions',
        its HLTB entries' and their aliases — in that order, raw."""
        cursor = await self._conn.execute(
            "SELECT name, name_ru FROM games WHERE game_id = ?", (game_id,)
        )
        row = await cursor.fetchone()
        names = [str(x) for x in (row or ()) if x]
        for sql in (
            "SELECT name FROM versions WHERE game_id = ? AND name IS NOT NULL",
            "SELECT e.name FROM editions e JOIN edition_items i ON i.edition_id = e.edition_id"
            " JOIN versions v ON v.version_id = i.version_id"
            " WHERE v.game_id = ? AND e.name IS NOT NULL",
            "SELECT h.name FROM hltb_entries h JOIN version_hltb vh ON vh.hltb_id = h.hltb_id"
            " JOIN versions v ON v.version_id = vh.version_id WHERE v.game_id = ?",
            "SELECT h.alias FROM hltb_entries h JOIN version_hltb vh ON vh.hltb_id = h.hltb_id"
            " JOIN versions v ON v.version_id = vh.version_id"
            " WHERE v.game_id = ? AND h.alias IS NOT NULL AND h.alias <> ''",
        ):
            cursor = await self._conn.execute(sql, (game_id,))
            names += [str(r[0]) for r in await cursor.fetchall()]
        return names

    async def octopus_gaps(self, game_id: int) -> dict[str, int]:
        """What a game assembled still lacks: stand-ins (a list with no store
        product), and how many of its versions have an HLTB entry."""
        cursor = await self._conn.execute(
            "SELECT COUNT(*) AS versions, COALESCE(SUM(stand_in), 0) AS stand_ins,"
            " (SELECT COUNT(*) FROM version_hltb vh JOIN versions w"
            "   ON w.version_id = vh.version_id WHERE w.game_id = ?) AS hltb"
            " FROM versions WHERE game_id = ?",
            (game_id, game_id),
        )
        row = await cursor.fetchone()
        return {k: int(row[k] or 0) for k in ("versions", "stand_ins", "hltb")}
