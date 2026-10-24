"""The octopus's queue and what it reads to assemble a game (#215, migration
126)."""

from __future__ import annotations

from datetime import timedelta

from bot.util import utcnow, utcnow_iso

# A failed entry is asked again in an hour, and dropped after three tries; the
# source's own `fetch_state` keeps the error.
RETRY = timedelta(hours=1)
TRIES = 3


class _OctopusRepo:
    # ------------------------------------------------------------ the queue

    async def octopus_enqueue(self, key: str, reason: str = "") -> bool:
        """Put an entry in the queue, due now. Returns whether it was new."""
        now = utcnow_iso()
        cursor = await self._conn.execute(
            "INSERT OR IGNORE INTO octopus_queue (key, reason, due_at, created_at)"
            " VALUES (?, ?, ?, ?)",
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
