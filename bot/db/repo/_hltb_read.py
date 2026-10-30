"""What HowLongToBeat says about a game, a version and a DLC, read through the
links (#147; owner, 2026-10-15) — nothing of it is copied into our tables:
a game takes the hours of its main game's entry, a version the row of its
platform, a DLC its entry's own hours and its platform's row."""

from __future__ import annotations

from typing import Any

from bot.services.hltb_platforms import hltb_platform, platforms_of_group

# `hltb_match.NOT_A_GAME` (a test keeps the two equal; importing it here would
# make the repo import the services that import the repo).
_ADDITIONAL = "('dlc', 'expansion', 'hack', 'mod')"


class _HltbReadRepo:
    async def hltb_entry(self, hltb_id: int) -> dict[str, Any] | None:
        """An entry as the mirror holds it, with the platforms it is on."""
        cursor = await self._conn.execute(
            "SELECT * FROM hltb_entries WHERE hltb_id = ?", (hltb_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        found = dict(row)
        cursor = await self._conn.execute(
            "SELECT platform FROM hltb_entry_platforms WHERE hltb_id = ? ORDER BY platform",
            (hltb_id,),
        )
        found["platforms"] = [r[0] for r in await cursor.fetchall()]
        return found

    async def set_hltb_summary_ru(self, hltb_id: int, summary_ru: str, of: str | None) -> None:
        """Our translation of an entry's summary, and which English text it
        was made from."""
        await self._conn.execute(
            "UPDATE hltb_entries SET summary_ru = ?, summary_ru_of = ? WHERE hltb_id = ?",
            (summary_ru, of, hltb_id),
        )
        await self._conn.commit()

    async def game_hltb(self, game_id: int) -> dict[str, Any] | None:
        """The HLTB entry of a game's main game: the entries its versions are
        linked to that are not additional content, the operator's link before
        an automatic one, then the surer match, then the one most versions
        share, then the lower id. `others`: the rest, as they are named."""
        cursor = await self._conn.execute(
            "SELECT e.*, MAX(CASE WHEN vh.source = 'manual' THEN 1 ELSE 0 END) AS manual,"
            " MAX(vh.score) AS score,"
            "  COUNT(DISTINCT vh.version_id) AS n_versions"
            " FROM versions v JOIN version_hltb vh ON vh.version_id = v.version_id"
            " JOIN hltb_entries e ON e.hltb_id = vh.hltb_id"
            f" WHERE v.game_id = ? AND vh.source <> 'rejected' AND e.game_type NOT IN {_ADDITIONAL}"
            " GROUP BY e.hltb_id"
            # The aggregates themselves: PostgreSQL reads an output name inside an
            # expression as the column, vh.score, not as this MAX.
            " ORDER BY manual DESC, MAX(vh.score) IS NULL, MAX(vh.score) DESC, n_versions DESC,"
            " e.hltb_id",
            (game_id,),
        )
        rows = [dict(r) for r in await cursor.fetchall()]
        if not rows:
            return None
        return {"entry": rows[0], "others": rows[1:]}

    async def version_hltb_platform(self, version_id: int) -> dict[str, Any] | None:
        """The HLTB entry a version is linked to, and the row of its
        platform: HLTB's own row for it, else the group of platforms that
        includes it. None when the version has no entry."""
        cursor = await self._conn.execute(
            "SELECT console FROM versions WHERE version_id = ?", (version_id,)
        )
        version = await cursor.fetchone()
        if version is None:
            return None
        cursor = await self._conn.execute(
            "SELECT e.*, vh.source AS link_source, vh.score AS link_score"
            " FROM version_hltb vh JOIN hltb_entries e ON e.hltb_id = vh.hltb_id"
            f" WHERE vh.version_id = ? AND vh.source <> 'rejected'"
            f" AND e.game_type NOT IN {_ADDITIONAL}"
            " ORDER BY vh.source = 'manual' DESC, vh.score IS NULL, vh.score DESC, e.hltb_id",
            (version_id,),
        )
        return await self._with_platform([dict(r) for r in await cursor.fetchall()], version[0])

    async def dlc_hltb_platform(self, dlc_id: int) -> dict[str, Any] | None:
        """The HLTB entry of a DLC (its own hours are the entry's), and the row
        of the platform of the version it belongs to."""
        cursor = await self._conn.execute(
            "SELECT v.console FROM dlcs d JOIN versions v ON v.version_id = d.version_id"
            " WHERE d.dlc_id = ?",
            (dlc_id,),
        )
        version = await cursor.fetchone()
        if version is None:
            return None
        cursor = await self._conn.execute(
            "SELECT e.*, dh.source AS link_source, NULL AS link_score"
            " FROM dlc_hltb dh JOIN hltb_entries e ON e.hltb_id = dh.hltb_id"
            " WHERE dh.dlc_id = ? AND dh.source <> 'rejected'"
            " ORDER BY dh.source = 'manual' DESC, e.hltb_id",
            (dlc_id,),
        )
        return await self._with_platform([dict(r) for r in await cursor.fetchall()], version[0])

    async def _with_platform(
        self, entries: list[dict[str, Any]], console: str | None
    ) -> dict[str, Any] | None:
        if not entries:
            return None
        platform = hltb_platform(console)
        for entry in entries:
            if platform is None:
                break
            cursor = await self._conn.execute(
                "SELECT * FROM hltb_platform_times WHERE hltb_id = ? AND platform = ?",
                (entry["hltb_id"], platform),
            )
            row = await cursor.fetchone()
            if row is not None:
                return {"entry": entry, "platform": platform, "row": dict(row), "group": None}
            cursor = await self._conn.execute(
                "SELECT * FROM hltb_platform_groups WHERE hltb_id = ?", (entry["hltb_id"],)
            )
            for group in await cursor.fetchall():
                if platform in platforms_of_group(group["platforms"]):
                    return {"entry": entry, "platform": platform, "row": None, "group": dict(group)}
        return {"entry": entries[0], "platform": platform, "row": None, "group": None}

    async def hltb_covers_to_fetch(self, limit: int | None = None) -> list[tuple[int, str]]:
        """Entries with a picture address and no file, never asked before;
        the ones something of ours reaches first."""
        cursor = await self._conn.execute(
            "SELECT e.hltb_id, e.image_url FROM hltb_entries e"
            " WHERE e.image_url IS NOT NULL AND e.image_path IS NULL"
            "  AND e.image_checked_at IS NULL"
            " ORDER BY (e.hltb_id IN (SELECT hltb_id FROM version_hltb"
            "  WHERE source <> 'rejected')) DESC, e.hltb_id"
            + (f" LIMIT {int(limit)}" if limit else "")
        )
        return [(int(r[0]), str(r[1])) for r in await cursor.fetchall()]

    async def set_hltb_cover(self, hltb_id: int, path: str | None, digest: str | None) -> None:
        """One visit's answer; stamped found or not, so a missing picture
        leaves the queue."""
        await self._conn.execute(
            "UPDATE hltb_entries SET image_path = ?, image_hash = ?,"
            " image_checked_at = to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD\"T\"HH24:MI:SS')"
            " WHERE hltb_id = ?",
            (path, digest, hltb_id),
        )
        await self._conn.commit()
