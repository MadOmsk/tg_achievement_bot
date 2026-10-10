"""Games over versions (#147, stage 3; migration 092): which game each version
is, how, and who decided it. The matcher writes only `auto` rows; a `manual`
row — a rejection included — is the operator's and stays."""

from __future__ import annotations

import json
from typing import Any

from bot.util import utcnow_iso


class _GamesRepo:
    async def match_rows(self) -> list[dict[str, Any]]:
        """Every version as the matcher reads it: names, studio, year, store
        group and its HLTB entries. A few thousand rows — read whole."""
        cursor = await self._conn.execute(
            "SELECT v.version_id, v.store, v.product_id, v.console, v.platform, v.title_id,"
            "  v.name, v.name_ru, v.kind, v.developer, v.publisher, v.release_date,"
            "  v.store_group, v.stand_in, t.name AS list_name, t.name_en AS list_name_en,"
            "  (SELECT GROUP_CONCAT(vh.hltb_id) FROM version_hltb vh"
            "   WHERE vh.version_id = v.version_id) AS hltb_ids"
            " FROM versions v LEFT JOIN titles t ON t.platform = v.platform"
            "  AND t.title_id = v.title_id"
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def achievement_names(self, platform: str, title_id: str) -> list[str]:
        """The English names of a list's achievements (the platform's own),
        what tells one list from another across platforms."""
        cursor = await self._conn.execute(
            "SELECT COALESCE(name_en, name_ru) FROM title_achievements"
            " WHERE platform = ? AND title_id = ?",
            (platform, title_id),
        )
        names = [str(row[0]) for row in await cursor.fetchall() if row[0]]
        if names:
            return names
        # A list whose catalog was never read: what people here earned in it.
        cursor = await self._conn.execute(
            "SELECT DISTINCT name FROM seen_achievements WHERE platform = ? AND title_id = ?",
            (platform, title_id),
        )
        return [str(row[0]) for row in await cursor.fetchall() if row[0]]

    async def links_of(self, version_ids: list[int]) -> list[dict[str, Any]]:
        if not version_ids:
            return []
        marks = ",".join("?" * len(version_ids))
        cursor = await self._conn.execute(
            f"SELECT * FROM version_games WHERE version_id IN ({marks})",
            version_ids,
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def create_game(self, name: str, year: int | None) -> int:
        now = utcnow_iso()
        cursor = await self._conn.execute(
            "INSERT INTO games (name, year, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (name, year, now, now),
        )
        await self._conn.commit()
        return int(cursor.lastrowid)

    async def rename_game(self, game_id: int, name: str, name_ru: str | None, source: str) -> None:
        """A manual name is never renamed by the matcher."""
        await self._conn.execute(
            "UPDATE games SET name = ?, name_ru = COALESCE(?, name_ru), name_source = ?,"
            " updated_at = ? WHERE game_id = ? AND (name_source = 'auto' OR ? = 'manual')",
            (name, name_ru, source, utcnow_iso(), game_id, source),
        )
        await self._conn.commit()

    async def set_link(
        self,
        version_id: int,
        game_id: int,
        *,
        kind: str,
        state: str,
        source: str,
        score: float | None = None,
        reasons: list[str] | None = None,
        decided_by: str | None = None,
    ) -> None:
        """One version → game link. An `auto` write never replaces a
        `manual` row."""
        await self._conn.execute(
            "INSERT INTO version_games (version_id, game_id, kind, state, source, score, reasons,"
            "  decided_by, decided_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(version_id, game_id) DO UPDATE SET kind = excluded.kind,"
            "  state = excluded.state, source = excluded.source, score = excluded.score,"
            "  reasons = excluded.reasons, decided_by = excluded.decided_by,"
            "  decided_at = excluded.decided_at"
            " WHERE version_games.source = 'auto' OR excluded.source = 'manual'",
            (
                version_id,
                game_id,
                kind,
                state,
                source,
                score,
                json.dumps(reasons or [], ensure_ascii=False),
                decided_by,
                utcnow_iso(),
            ),
        )
        await self._conn.commit()

    async def drop_auto_links(self, version_id: int, keep_game: int | None, state: str) -> None:
        """The matcher's own rows of one state for this version, except the
        one to `keep_game`."""
        await self._conn.execute(
            "DELETE FROM version_games WHERE version_id = ? AND source = 'auto' AND state = ?"
            " AND game_id IS NOT ?",
            (version_id, state, keep_game),
        )
        await self._conn.commit()

    async def drop_empty_games(self) -> int:
        """Games no version is linked to any more (and nothing points at)."""
        cursor = await self._conn.execute(
            "DELETE FROM games WHERE NOT EXISTS (SELECT 1 FROM version_games vg"
            "  WHERE vg.game_id = games.game_id AND vg.state = 'linked')"
            " AND NOT EXISTS (SELECT 1 FROM version_games vg WHERE vg.game_id = games.game_id"
            "  AND vg.source = 'manual')"
            " AND NOT EXISTS (SELECT 1 FROM game_relations r"
            "  WHERE r.game_id = games.game_id OR r.related_id = games.game_id)"
            " AND NOT EXISTS (SELECT 1 FROM games g WHERE g.merged_into = games.game_id)"
            " AND merged_into IS NULL"
        )
        await self._conn.commit()
        return cursor.rowcount or 0

    async def relate_games(self, game_id: int, related_id: int, kind: str, source: str) -> None:
        await self._conn.execute(
            "INSERT OR IGNORE INTO game_relations (game_id, related_id, kind, source, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (game_id, related_id, kind, source, utcnow_iso()),
        )
        await self._conn.commit()

    async def merge_games(self, game_id: int, into: int) -> None:
        """Every link of `game_id` moves to `into` (a manual decision); the
        old id resolves to the new one."""
        async with self.transaction():
            # A version already under `into` (as a review, say) takes the row it
            # had in the merged game: merging says it is this game. Without this,
            # an ignored update and the delete below dropped its link.
            await self._conn.execute(
                "DELETE FROM version_games WHERE game_id = ? AND version_id IN"
                " (SELECT version_id FROM version_games WHERE game_id = ?)",
                (into, game_id),
            )
            await self._conn.execute(
                "UPDATE version_games SET game_id = ?, source = 'manual' WHERE game_id = ?",
                (into, game_id),
            )
            await self._conn.execute("DELETE FROM version_games WHERE game_id = ?", (game_id,))
            await self._conn.execute(
                "UPDATE games SET merged_into = ?, updated_at = ? WHERE game_id = ?",
                (into, utcnow_iso(), game_id),
            )

    async def linked_game_of(self, version_id: int) -> int | None:
        """The game a version is in (a manual link first)."""
        cursor = await self._conn.execute(
            "SELECT game_id FROM version_games WHERE version_id = ? AND state = 'linked'"
            " ORDER BY source = 'manual' DESC, game_id LIMIT 1",
            (version_id,),
        )
        row = await cursor.fetchone()
        return int(row["game_id"]) if row else None

    async def set_version_link(
        self, version_id: int, of_version_id: int, kind: str, source: str
    ) -> None:
        """Which version this one is of (`demo_of`). An `auto` write never
        replaces a `manual` one."""
        await self._conn.execute(
            "INSERT INTO version_links (version_id, of_version_id, kind, source, decided_at)"
            " VALUES (?, ?, ?, ?, ?) ON CONFLICT(version_id, kind) DO UPDATE SET"
            "  of_version_id = excluded.of_version_id, source = excluded.source,"
            "  decided_at = excluded.decided_at"
            " WHERE version_links.source = 'auto' OR excluded.source = 'manual'",
            (version_id, of_version_id, kind, source, utcnow_iso()),
        )
        await self._conn.commit()

    async def refresh_game_facts(self, game_ids: list[int] | None = None) -> None:
        """Each game's year, developer and publisher from its linked versions
        (`game_match.game_facts`); every game when none is named."""
        from bot.services.game_match import game_facts

        if game_ids is None:
            cursor = await self._conn.execute("SELECT game_id FROM games WHERE merged_into IS NULL")
            game_ids = [int(row[0]) for row in await cursor.fetchall()]
        for game_id in dict.fromkeys(game_ids):
            cursor = await self._conn.execute(
                # A version's own studio, else its HLTB entry's: a stand-in (a
                # 360 game) has none of its own.
                "SELECT v.name, v.release_date, vg.kind, h.release_year AS hltb_year,"
                " COALESCE(v.developer, h.developer) AS developer,"
                " COALESCE(v.publisher, h.publisher) AS publisher"
                " FROM version_games vg JOIN versions v ON v.version_id = vg.version_id"
                " LEFT JOIN hltb_games h ON h.hltb_id = (SELECT MIN(vh.hltb_id)"
                "  FROM version_hltb vh WHERE vh.version_id = v.version_id)"
                " WHERE vg.game_id = ? AND vg.state = 'linked'",
                (game_id,),
            )
            rows = [dict(row) for row in await cursor.fetchall()]
            if not rows:
                continue
            facts = game_facts(rows)
            values = (
                facts.year,
                facts.developer,
                facts.publisher,
                facts.last_year,
                int(facts.more_developers),
                int(facts.more_publishers),
            )
            await self._conn.execute(
                "UPDATE games SET year = ?, developer = ?, publisher = ?, last_year = ?,"
                " more_developers = ?, more_publishers = ?, updated_at = ?"
                " WHERE game_id = ? AND (year IS NOT ? OR developer IS NOT ?"
                "  OR publisher IS NOT ? OR last_year IS NOT ? OR more_developers IS NOT ?"
                "  OR more_publishers IS NOT ?)",
                (*values, utcnow_iso(), game_id, *values),
            )
        await self._conn.commit()

    async def games_of_version(self, version_id: int) -> list[int]:
        """Every game a version has a row with, whatever its state."""
        cursor = await self._conn.execute(
            "SELECT DISTINCT game_id FROM version_games WHERE version_id = ?", (version_id,)
        )
        return [int(row[0]) for row in await cursor.fetchall()]
