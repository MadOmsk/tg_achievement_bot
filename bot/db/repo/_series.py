"""Game series (#147; migration 105): `series` and which games are in each
(`game_series`). The linker's proposals are `auto` rows, rewritten on every
rebuild; the operator's (`manual`) and the advisers' (`advisers`) rows are
never touched by it, and `member = 0` keeps a game out of a series."""

from __future__ import annotations

from collections import Counter
from typing import Any

from bot.util import utcnow_iso

# Whose word stands over whose on one (game, series) pair.
_RANK = {"auto": 0, "advisers": 1, "manual": 2}

Members = dict[int, tuple[float, str]]


class _SeriesRepo:
    async def series_inputs(self) -> dict[str, list[Any]]:
        """What series are proposed from: the live games, their relations,
        and the labels "another game of the series" between two games."""
        cursor = await self._conn.execute(
            "SELECT g.game_id, g.name, g.year, g.developer, g.publisher, g.kind FROM games g"
            " WHERE g.merged_into IS NULL"
            " AND EXISTS (SELECT 1 FROM versions v WHERE v.game_id = g.game_id)"
        )
        games = [dict(row) for row in await cursor.fetchall()]
        cursor = await self._conn.execute("SELECT game_id, related_id, kind FROM game_relations")
        relations = [tuple(row) for row in await cursor.fetchall()]
        cursor = await self._conn.execute(
            "SELECT DISTINCT ga.game_id, gb.game_id, d.decided_by FROM match_decisions d"
            " JOIN versions ga ON ga.version_id = d.version_id"
            " JOIN versions gb ON gb.version_id = d.other_id"
            " WHERE d.relation = 'series' AND ga.game_id <> gb.game_id"
        )
        labels = [tuple(row) for row in await cursor.fetchall()]
        return {"games": games, "relations": relations, "labels": labels}

    async def write_series(
        self, proposals: list[tuple[str, list[int], Members, str | None]]
    ) -> int:
        """The linker's proposals `(name, core games earliest first, every
        member's (p, reason), rule key)` over the previous ones, in one
        transaction: each proposal keeps the series anchored on one of its own
        games (two such series are merged), else takes a series the operator
        made of its games, else a new one anchored on its earliest game. A
        proposal with a rule key is its rule's series, found by the key, with
        no anchor, and never merged with another. Returns how many live
        series there are."""
        now = utcnow_iso()
        async with self.transaction():
            await self._fold_merged_games()
            cursor = await self._conn.execute(
                "SELECT series_id, anchor_game_id, merged_into, merged_by, name_source, name,"
                " rule_key FROM series"
            )
            series = {int(r["series_id"]): dict(r) for r in await cursor.fetchall()}

            def live(series_id: int) -> int:
                seen = set()
                while series[series_id]["merged_into"] and series_id not in seen:
                    seen.add(series_id)
                    series_id = int(series[series_id]["merged_into"])
                return series_id

            game_of = await self._live_games()
            # A series merged by the builder leads nowhere any more (owner,
            # 2026-10-24): its anchor sent another proposal's games back into
            # the series it was once chained to on every rebuild. One the
            # operator merged still leads to where they put it.
            anchors = {
                game_of.get(int(s["anchor_game_id"]), int(s["anchor_game_id"])): live(sid)
                for sid, s in series.items()
                if s["anchor_game_id"] is not None
                and not (s["merged_into"] and s["merged_by"] == "auto")
            }
            cursor = await self._conn.execute(
                "SELECT gs.game_id, gs.series_id FROM game_series gs"
                " JOIN series s ON s.series_id = gs.series_id"
                " WHERE gs.source <> 'auto' AND gs.member = 1"
                " AND s.anchor_game_id IS NULL AND s.merged_into IS NULL"
                " AND s.rule_key IS NULL"
            )
            made_by_hand: dict[int, list[int]] = {}
            for row in await cursor.fetchall():
                made_by_hand.setdefault(int(row[0]), []).append(int(row[1]))

            by_rule = {
                str(s["rule_key"]): sid
                for sid, s in series.items()
                if s["rule_key"] and not s["merged_into"]
            }
            wanted: dict[int, Members] = {}
            for name, core, members, rule_key in proposals:
                if rule_key is not None:
                    target = by_rule.get(rule_key)
                    if target is None:
                        cursor = await self._conn.execute(
                            "INSERT INTO series (name, anchor_game_id, rule_key, created_at,"
                            " updated_at) VALUES (?, NULL, ?, ?, ?) RETURNING series_id",
                            (name, rule_key, now, now),
                        )
                        target = int((await cursor.fetchone())[0])
                        by_rule[rule_key] = target
                        series[target] = {
                            "series_id": target,
                            "anchor_game_id": None,
                            "merged_into": None,
                            "name_source": "auto",
                            "name": name,
                            "rule_key": rule_key,
                        }
                    elif series[target]["name_source"] == "auto" and series[target]["name"] != name:
                        await self._conn.execute(
                            "UPDATE series SET name = ?, updated_at = ? WHERE series_id = ?",
                            (name, now, target),
                        )
                        series[target]["name"] = name
                    into = wanted.setdefault(target, {})
                    for game, (p, reason) in members.items():
                        if game not in into or into[game][0] < p:
                            into[game] = (p, reason)
                    continue
                hits = sorted({anchors[g] for g in core if g in anchors})
                if hits:
                    target = hits[0]
                    for other in hits[1:]:
                        await self._merge_series_rows(other, target, by="auto")
                        series[other]["merged_into"] = target
                        anchors = {g: (target if s == other else s) for g, s in anchors.items()}
                else:
                    by_hand = Counter(s for g in core for s in made_by_hand.get(g, []))
                    if by_hand:
                        target = by_hand.most_common(1)[0][0]
                        await self._conn.execute(
                            "UPDATE series SET anchor_game_id = ?, updated_at = ?"
                            " WHERE series_id = ? AND anchor_game_id IS NULL",
                            (core[0], now, target),
                        )
                    else:
                        # The anchor may still be held by a series the builder
                        # merged away: it no longer needs one (its id resolves).
                        await self._conn.execute(
                            "UPDATE series SET anchor_game_id = NULL"
                            " WHERE anchor_game_id = ? AND merged_by = 'auto'",
                            (core[0],),
                        )
                        cursor = await self._conn.execute(
                            "INSERT INTO series (name, anchor_game_id, created_at, updated_at)"
                            " VALUES (?, ?, ?, ?) RETURNING series_id",
                            (name, core[0], now, now),
                        )
                        target = int((await cursor.fetchone())[0])
                        series[target] = {
                            "series_id": target,
                            "anchor_game_id": core[0],
                            "merged_into": None,
                            "name_source": "auto",
                            "name": name,
                            "rule_key": None,
                        }
                    anchors[core[0]] = target
                # Named by the proposal holding its own anchor: a series the
                # operator merged takes several, and keeps its own name.
                anchor = series[target]["anchor_game_id"]
                own = anchor is None or game_of.get(int(anchor), int(anchor)) in core
                if (
                    own
                    and series[target]["name_source"] == "auto"
                    and series[target]["name"] != name
                ):
                    await self._conn.execute(
                        "UPDATE series SET name = ?, updated_at = ? WHERE series_id = ?",
                        (name, now, target),
                    )
                    series[target]["name"] = name
                into = wanted.setdefault(target, {})
                for game, (p, reason) in members.items():
                    if game not in into or into[game][0] < p:
                        into[game] = (p, reason)

            cursor = await self._conn.execute(
                "SELECT game_id, series_id FROM game_series WHERE source = 'auto'"
            )
            stale = [
                (int(g), int(s))
                for g, s in await cursor.fetchall()
                if int(g) not in wanted.get(int(s), {})
            ]
            await self._conn.executemany(
                "DELETE FROM game_series WHERE game_id = ? AND series_id = ? AND source = 'auto'",
                stale,
            )
            await self._conn.executemany(
                "INSERT INTO game_series (game_id, series_id, source, member, p, reason,"
                " created_at, updated_at) VALUES (?, ?, 'auto', 1, ?, ?, ?, ?)"
                " ON CONFLICT(game_id, series_id) DO UPDATE SET p = excluded.p,"
                "  reason = excluded.reason, updated_at = excluded.updated_at"
                " WHERE game_series.source = 'auto'"
                "  AND (game_series.p IS DISTINCT FROM excluded.p"
                "   OR game_series.reason IS DISTINCT FROM excluded.reason)",
                [
                    (game, sid, p, reason, now, now)
                    for sid, members in wanted.items()
                    for game, (p, reason) in members.items()
                ],
            )
            await self._drop_empty_series()
            cursor = await self._conn.execute(
                "SELECT COUNT(*) FROM series WHERE merged_into IS NULL"
            )
            return int((await cursor.fetchone())[0])

    async def _live_games(self) -> dict[int, int]:
        """`{merged game: the live game it went into}`."""
        cursor = await self._conn.execute(
            "SELECT game_id, merged_into FROM games WHERE merged_into IS NOT NULL"
        )
        into = {int(r[0]): int(r[1]) for r in await cursor.fetchall()}
        resolved: dict[int, int] = {}
        for game in into:
            target, seen = game, set()
            while target in into and target not in seen:
                seen.add(target)
                target = into[target]
            resolved[game] = target
        return resolved

    async def _fold_merged_games(self) -> None:
        """A game folded into another takes its series rows with it; where
        the kept game has its own row, the surer word stays."""
        for old, new in (await self._live_games()).items():
            cursor = await self._conn.execute("SELECT * FROM game_series WHERE game_id = ?", (old,))
            for row in await cursor.fetchall():
                await self._put_row(dict(row), game_id=new)
            await self._conn.execute("DELETE FROM game_series WHERE game_id = ?", (old,))

    async def _put_row(
        self, row: dict[str, Any], *, game_id: int | None = None, series_id: int | None = None
    ) -> None:
        """One membership row moved to another game or series, unless a
        surer one is there already."""
        game = game_id if game_id is not None else int(row["game_id"])
        sid = series_id if series_id is not None else int(row["series_id"])
        cursor = await self._conn.execute(
            "SELECT source FROM game_series WHERE game_id = ? AND series_id = ?", (game, sid)
        )
        there = await cursor.fetchone()
        if there is not None and _RANK.get(str(there[0]), 0) >= _RANK.get(str(row["source"]), 0):
            return
        await self._conn.execute(
            "INSERT INTO game_series (game_id, series_id, source, member, p, reason,"
            " decided_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (game_id, series_id) DO UPDATE SET source = excluded.source, member = "
            "excluded.member, p = excluded.p, reason = excluded.reason, decided_by = "
            "excluded.decided_by, created_at = excluded.created_at, updated_at = "
            "excluded.updated_at",
            (
                game,
                sid,
                row["source"],
                row["member"],
                row["p"],
                row["reason"],
                row["decided_by"],
                row["created_at"],
                utcnow_iso(),
            ),
        )

    async def _merge_series_rows(self, series_id: int, into: int, *, by: str) -> None:
        """Every row of one series moved into another; the old id resolves
        to the kept one. `by` is `operator` or `auto` (migration 125)."""
        cursor = await self._conn.execute(
            "SELECT * FROM game_series WHERE series_id = ?", (series_id,)
        )
        for row in await cursor.fetchall():
            await self._put_row(dict(row), series_id=into)
        await self._conn.execute("DELETE FROM game_series WHERE series_id = ?", (series_id,))
        await self._conn.execute(
            "UPDATE series SET merged_into = ?, merged_by = COALESCE(?, merged_by), updated_at = ?"
            " WHERE series_id = ? OR merged_into = ?",
            (into, by, utcnow_iso(), series_id, series_id),
        )

    async def _drop_empty_series(self) -> None:
        """A live series no game is in any more, that no old id leads to."""
        await self._conn.execute(
            "DELETE FROM series WHERE merged_into IS NULL"
            " AND NOT EXISTS (SELECT 1 FROM game_series gs"
            "  WHERE gs.series_id = series.series_id AND gs.member = 1)"
            " AND NOT EXISTS (SELECT 1 FROM series s WHERE s.merged_into = series.series_id)"
        )

    # ---------------------------------------------------------------- by hand

    async def create_series(self, name: str) -> int:
        """A series the operator names; it takes an anchor once a proposal
        meets its games."""
        now = utcnow_iso()
        cursor = await self._conn.execute(
            "INSERT INTO series (name, name_source, created_at, updated_at)"
            " VALUES (?, 'manual', ?, ?) RETURNING series_id",
            (name, now, now),
        )
        await self._conn.commit()
        return int((await cursor.fetchone())[0])

    async def rename_series(self, series_id: int, name: str, name_ru: str | None) -> None:
        await self._conn.execute(
            "UPDATE series SET name = ?, name_ru = COALESCE(?, name_ru), name_source = 'manual',"
            " updated_at = ? WHERE series_id = ?",
            (name, name_ru, utcnow_iso(), series_id),
        )
        await self._conn.commit()

    async def merge_series(self, series_id: int, into: int) -> None:
        """The operator's merge: one series' games go into another, and the
        old id keeps resolving to it — rebuilds keep them one."""
        if series_id == into:
            return
        async with self.transaction():
            await self._merge_series_rows(series_id, into, by="operator")

    async def series_exists(self, series_id: int) -> bool:
        cursor = await self._conn.execute(
            "SELECT 1 FROM series WHERE series_id = ? AND merged_into IS NULL", (series_id,)
        )
        return await cursor.fetchone() is not None

    async def series_name(self, series_id: int) -> str | None:
        cursor = await self._conn.execute(
            "SELECT name FROM series WHERE series_id = ?", (series_id,)
        )
        row = await cursor.fetchone()
        return str(row[0]) if row else None

    async def series_by_name(self, name: str) -> int | None:
        cursor = await self._conn.execute(
            "SELECT series_id FROM series WHERE merged_into IS NULL"
            " AND (lower(name) = lower(?) OR lower(name_ru) = lower(?)) ORDER BY series_id LIMIT 1",
            (name, name),
        )
        row = await cursor.fetchone()
        return int(row[0]) if row else None

    async def set_series_member(
        self,
        game_id: int,
        series_id: int,
        member: bool,
        *,
        source: str = "manual",
        decided_by: str = "viewer",
    ) -> None:
        """A game said to be in a series or not, by the operator (`manual`)
        or the advisers (`advisers`) — never over the operator's word."""
        now = utcnow_iso()
        await self.log_label(
            "series", "label", decided_by, game_id=game_id, series_id=series_id, member=member
        )
        await self._conn.execute(
            "INSERT INTO game_series (game_id, series_id, source, member, decided_by,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(game_id, series_id) DO UPDATE SET source = excluded.source,"
            "  member = excluded.member, decided_by = excluded.decided_by,"
            "  updated_at = excluded.updated_at"
            " WHERE game_series.source <> 'manual' OR excluded.source = 'manual'",
            (game_id, series_id, source, int(member), decided_by, now, now),
        )
        await self._conn.commit()

    async def uncertain_series_memberships(
        self, below_p: float, limit: int
    ) -> list[dict[str, Any]]:
        """The linker's least sure memberships nobody answered, each with
        up to ten other games of its series."""
        cursor = await self._conn.execute(
            "SELECT gs.game_id, g.name AS game_name, g.year, g.developer, g.publisher,"
            " gs.series_id, s.name AS series_name, gs.p, gs.reason FROM game_series gs"
            " JOIN games g ON g.game_id = gs.game_id"
            " JOIN series s ON s.series_id = gs.series_id"
            " WHERE gs.source = 'auto' AND gs.member = 1 AND s.merged_into IS NULL"
            " AND COALESCE(gs.p, 0) < ? ORDER BY gs.p, gs.series_id, gs.game_id LIMIT ?",
            (below_p, limit),
        )
        rows = [dict(row) for row in await cursor.fetchall()]
        for row in rows:
            cursor = await self._conn.execute(
                "SELECT g.game_id, g.name, g.year FROM game_series gs"
                " JOIN games g ON g.game_id = gs.game_id"
                " WHERE gs.series_id = ? AND gs.member = 1 AND gs.game_id <> ?"
                " ORDER BY COALESCE(g.year, 9999), g.game_id LIMIT 10",
                (row["series_id"], row["game_id"]),
            )
            row["others"] = [tuple(r) for r in await cursor.fetchall()]
        return rows
