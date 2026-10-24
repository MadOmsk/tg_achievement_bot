"""The octopus's queue and the linker's dirty set (#215, migration 126)."""

from __future__ import annotations

from datetime import timedelta

from bot.util import utcnow, utcnow_iso

# A failed item is asked again in an hour, and dropped after three tries; the
# source's own `fetch_state` keeps the error.
RETRY = timedelta(hours=1)
TRIES = 3


class _OctopusRepo:
    async def octopus_enqueue(self, key: str, hops: int, reason: str = "") -> bool:
        """Put a key in the queue, due now; a key already waiting keeps the
        fewer hops. Returns whether it was new."""
        cursor = await self._conn.execute("SELECT hops FROM octopus_queue WHERE key = ?", (key,))
        row = await cursor.fetchone()
        if row is not None:
            if hops < int(row[0]):
                await self._conn.execute(
                    "UPDATE octopus_queue SET hops = ? WHERE key = ?", (hops, key)
                )
                await self._conn.commit()
            return False
        now = utcnow_iso()
        await self._conn.execute(
            "INSERT INTO octopus_queue (key, hops, reason, due_at, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (key, hops, reason, now, now),
        )
        await self._conn.commit()
        return True

    async def octopus_due(self, limit: int) -> list[tuple[str, int, str]]:
        """`(key, hops, reason)` due now, the nearest to what was asked first."""
        cursor = await self._conn.execute(
            "SELECT key, hops, reason FROM octopus_queue WHERE due_at <= ?"
            " ORDER BY hops, due_at, key LIMIT ?",
            (utcnow_iso(), limit),
        )
        return [(str(r[0]), int(r[1]), str(r[2] or "")) for r in await cursor.fetchall()]

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

    async def mark_dirty(self, version_ids: list[int]) -> None:
        now = utcnow_iso()
        await self._conn.executemany(
            "INSERT OR IGNORE INTO octopus_dirty (version_id, marked_at) VALUES (?, ?)",
            [(int(v), now) for v in dict.fromkeys(version_ids)],
        )
        await self._conn.commit()

    async def take_dirty(self) -> list[int]:
        """The dirty versions, taken: the set is empty after."""
        async with self.transaction():
            cursor = await self._conn.execute("SELECT version_id FROM octopus_dirty")
            ids = [int(r[0]) for r in await cursor.fetchall()]
            await self._conn.execute("DELETE FROM octopus_dirty")
        return ids

    async def octopus_lists_of_game(self, game_id: int) -> list[tuple[str, str]]:
        cursor = await self._conn.execute(
            "SELECT DISTINCT platform, title_id FROM versions"
            " WHERE game_id = ? AND platform IS NOT NULL AND title_id IS NOT NULL",
            (game_id,),
        )
        return [(str(r[0]), str(r[1])) for r in await cursor.fetchall()]

    async def octopus_hltb_of_game(self, game_id: int) -> list[int]:
        cursor = await self._conn.execute(
            "SELECT DISTINCT vh.hltb_id FROM version_hltb vh"
            " JOIN versions v ON v.version_id = vh.version_id WHERE v.game_id = ?",
            (game_id,),
        )
        return [int(r[0]) for r in await cursor.fetchall()]

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
