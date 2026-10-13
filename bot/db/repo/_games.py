"""Games over versions (#147; migrations 092, 099). The operator's decisions
are labels on pairs of versions (`match_decisions`, input); which game each
version is in (`game_versions`) and how games relate (`game_relations`) are
the matcher's output, rebuilt from the labels and the model — so a decision
outlives every rebuild."""

from __future__ import annotations

import json
from typing import Any

from bot.util import utcnow_iso


class _GamesRepo:
    async def match_rows(self) -> list[dict[str, Any]]:
        """Every version as the matcher reads it: names, studio, year, store
        group and cross-gen set, its HLTB entries. Read whole."""
        cursor = await self._conn.execute(
            "SELECT v.version_id, v.store, v.product_id, v.console, v.platform, v.title_id,"
            "  v.name, v.name_ru, v.kind, v.developer, v.publisher, v.release_date,"
            "  v.store_group, v.cross_gen_set, v.stand_in, t.name AS list_name,"
            "  t.name_en AS list_name_en,"
            "  (SELECT GROUP_CONCAT(vh.hltb_id) FROM version_hltb vh"
            "   WHERE vh.version_id = v.version_id) AS hltb_ids,"
            "  (SELECT MIN(h.release_year) FROM version_hltb vh JOIN hltb_games h"
            "   ON h.hltb_id = vh.hltb_id WHERE vh.version_id = v.version_id) AS hltb_year,"
            "  (SELECT GROUP_CONCAT(h.game_type) FROM version_hltb vh JOIN hltb_games h"
            "   ON h.hltb_id = vh.hltb_id WHERE vh.version_id = v.version_id) AS hltb_types"
            " FROM versions v LEFT JOIN titles t ON t.platform = v.platform"
            "  AND t.title_id = v.title_id"
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def achievement_names(self, platform: str, title_id: str) -> list[str]:
        """The English names of a list's achievements (the platform's own),
        what tells one list from another across platforms."""
        found = await self.achievement_names_of([(platform, title_id)])
        return found.get((platform, title_id), [])

    async def achievement_names_of(
        self, lists: list[tuple[str, str]]
    ) -> dict[tuple[str, str], list[str]]:
        """Many lists' names at once, a batch per platform; a list whose
        catalog was never read gives what people here earned in it."""
        found: dict[tuple[str, str], list[str]] = {}
        by_platform: dict[str, list[str]] = {}
        for platform, title_id in dict.fromkeys(lists):
            by_platform.setdefault(platform, []).append(title_id)
        for platform, ids in by_platform.items():
            for start in range(0, len(ids), 500):
                batch = ids[start : start + 500]
                marks = ",".join("?" * len(batch))
                for table, column in (
                    ("title_achievements", "COALESCE(name_en, name_ru)"),
                    ("seen_achievements", "name"),
                ):
                    missing = [t for t in batch if (platform, t) not in found]
                    if not missing:
                        break
                    marks = ",".join("?" * len(missing))
                    cursor = await self._conn.execute(
                        f"SELECT DISTINCT title_id, {column} FROM {table}"
                        f" WHERE platform = ? AND title_id IN ({marks})",
                        (platform, *missing),
                    )
                    for row in await cursor.fetchall():
                        if row[1]:
                            found.setdefault((platform, str(row[0])), []).append(str(row[1]))
        return found

    # ---------------------------------------------------------------- labels

    async def decisions_among(self, version_ids: list[int]) -> list[dict[str, Any]]:
        """The operator's labels with either side among these versions."""
        rows: list[dict[str, Any]] = []
        ids = list(dict.fromkeys(version_ids))
        for start in range(0, len(ids), 400):
            batch = ids[start : start + 400]
            marks = ",".join("?" * len(batch))
            cursor = await self._conn.execute(
                "SELECT * FROM match_decisions"
                f" WHERE version_id IN ({marks}) OR other_id IN ({marks})",
                (*batch, *batch),
            )
            rows += [dict(row) for row in await cursor.fetchall()]
        return list({(r["version_id"], r["other_id"]): r for r in rows}.values())

    async def save_decision(
        self,
        version_id: int,
        other_id: int,
        relation: str,
        *,
        features: dict[str, float] | None,
        model: str | None,
        decided_by: str,
    ) -> None:
        """The operator's label on a pair; a pair has one label, whichever way
        round it was given."""
        async with self.transaction():
            await self._conn.execute(
                "DELETE FROM match_decisions WHERE version_id = ? AND other_id = ?",
                (other_id, version_id),
            )
            await self._conn.execute(
                "INSERT INTO match_decisions (version_id, other_id, relation, features, model,"
                " decided_by, decided_at, subject_key, other_key) VALUES (?, ?, ?, ?, ?, ?, ?,"
                " (SELECT store || ':' || product_id || ':' || console FROM versions"
                "  WHERE version_id = ?),"
                " (SELECT store || ':' || product_id || ':' || console FROM versions"
                "  WHERE version_id = ?))"
                " ON CONFLICT(version_id, other_id) DO UPDATE SET relation = excluded.relation,"
                "  features = excluded.features, model = excluded.model,"
                "  decided_by = excluded.decided_by, decided_at = excluded.decided_at,"
                "  subject_key = excluded.subject_key, other_key = excluded.other_key",
                (
                    version_id,
                    other_id,
                    relation,
                    json.dumps(features) if features is not None else None,
                    model,
                    decided_by,
                    utcnow_iso(),
                    version_id,
                    other_id,
                ),
            )
            await self._conn.execute(
                "DELETE FROM match_pairs WHERE (version_id = ? AND other_id = ?)"
                " OR (version_id = ? AND other_id = ?)",
                (version_id, other_id, other_id, version_id),
            )

    # ---------------------------------------------------------------- output

    async def memberships(self, version_ids: list[int]) -> dict[int, dict[str, Any]]:
        found: dict[int, dict[str, Any]] = {}
        ids = list(dict.fromkeys(version_ids))
        for start in range(0, len(ids), 500):
            batch = ids[start : start + 500]
            marks = ",".join("?" * len(batch))
            cursor = await self._conn.execute(
                f"SELECT * FROM game_versions WHERE version_id IN ({marks})", batch
            )
            found.update({int(r["version_id"]): dict(r) for r in await cursor.fetchall()})
        return found

    async def versions_of_games(self, game_ids: list[int]) -> list[int]:
        ids = list(dict.fromkeys(game_ids))
        found: list[int] = []
        for start in range(0, len(ids), 500):
            batch = ids[start : start + 500]
            marks = ",".join("?" * len(batch))
            cursor = await self._conn.execute(
                f"SELECT version_id FROM game_versions WHERE game_id IN ({marks})", batch
            )
            found += [int(r[0]) for r in await cursor.fetchall()]
        return found

    async def games_anchored_in(self, version_ids: list[int]) -> dict[int, int]:
        """`{anchor version: game}` for the games anchored on these versions."""
        found: dict[int, int] = {}
        ids = list(dict.fromkeys(version_ids))
        for start in range(0, len(ids), 500):
            batch = ids[start : start + 500]
            marks = ",".join("?" * len(batch))
            cursor = await self._conn.execute(
                "SELECT anchor_version_id, game_id FROM games"
                f" WHERE merged_into IS NULL AND anchor_version_id IN ({marks})",
                batch,
            )
            found.update({int(r[0]): int(r[1]) for r in await cursor.fetchall()})
        return found

    async def game_names(self, game_ids: list[int]) -> dict[int, tuple[str, str]]:
        """`{game: (name, name_source)}`."""
        found: dict[int, tuple[str, str]] = {}
        ids = list(dict.fromkeys(game_ids))
        for start in range(0, len(ids), 500):
            batch = ids[start : start + 500]
            marks = ",".join("?" * len(batch))
            cursor = await self._conn.execute(
                f"SELECT game_id, name, name_source FROM games WHERE game_id IN ({marks})", batch
            )
            found.update({int(r[0]): (str(r[1]), str(r[2])) for r in await cursor.fetchall()})
        return found

    async def create_game(
        self, name: str, year: int | None, anchor_version_id: int | None = None
    ) -> int:
        now = utcnow_iso()
        cursor = await self._conn.execute(
            "INSERT INTO games (name, year, anchor_version_id, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (name, year, anchor_version_id, now, now),
        )
        await self._conn.commit()
        return int(cursor.lastrowid)

    async def rename_game(self, game_id: int, name: str, name_ru: str | None, source: str) -> None:
        """A manual name is never renamed by the matcher."""
        await self._conn.execute(
            "UPDATE games SET name = ?, name_ru = COALESCE(?, name_ru), name_source = ?,"
            " updated_at = ? WHERE game_id = ? AND (name_source = 'auto' OR ? = 'manual')"
            " AND (name IS NOT ? OR name_source IS NOT ?)",
            (name, name_ru, source, utcnow_iso(), game_id, source, name, source),
        )
        await self._conn.commit()

    async def merge_game_into(self, game_id: int, into: int) -> None:
        """The matcher found one game where there were two: the old id
        resolves to the kept one, its manual name goes with it if the kept
        one has none."""
        await self._conn.execute(
            "UPDATE games SET name = (SELECT g.name FROM games g WHERE g.game_id = ?),"
            " name_ru = COALESCE(name_ru, (SELECT g.name_ru FROM games g WHERE g.game_id = ?)),"
            " name_source = 'manual', updated_at = ?"
            " WHERE game_id = ? AND name_source = 'auto'"
            " AND (SELECT g.name_source FROM games g WHERE g.game_id = ?) = 'manual'",
            (game_id, game_id, utcnow_iso(), into, game_id),
        )
        await self._conn.execute(
            "UPDATE games SET merged_into = ?, anchor_version_id = NULL, updated_at = ?"
            " WHERE game_id = ?",
            (into, utcnow_iso(), game_id),
        )
        await self._conn.execute(
            "UPDATE games SET merged_into = ? WHERE merged_into = ?", (into, game_id)
        )
        await self._conn.commit()

    async def set_game_kinds(self, kinds: dict[int, str]) -> None:
        """The linker's word on what each game is; the operator's stands."""
        await self._conn.executemany(
            "UPDATE games SET kind = ?, updated_at = ? WHERE game_id = ?"
            " AND kind_source = 'auto' AND kind IS NOT ?",
            [(kind, utcnow_iso(), game_id, kind) for game_id, kind in kinds.items()],
        )
        await self._conn.commit()

    async def set_game_kind_manual(self, game_id: int, kind: str | None) -> None:
        """The operator says what a game is (game / compilation / extra);
        None gives the choice back to the linker."""
        await self._conn.execute(
            "UPDATE games SET kind = COALESCE(?, kind), kind_source = ?, updated_at = ?"
            " WHERE game_id = ?",
            (kind, "manual" if kind else "auto", utcnow_iso(), game_id),
        )
        await self._conn.commit()

    async def set_anchor(self, game_id: int, version_id: int) -> None:
        await self._conn.execute(
            "UPDATE games SET anchor_version_id = NULL"
            " WHERE anchor_version_id = ? AND game_id <> ?",
            (version_id, game_id),
        )
        await self._conn.execute(
            "UPDATE games SET anchor_version_id = ? WHERE game_id = ?", (version_id, game_id)
        )
        await self._conn.commit()

    async def write_members(
        self, members: dict[int, tuple[int, str, int | None, float | None]]
    ) -> None:
        """`{version: (game, role, of_version, p)}` — these versions' rows,
        replaced."""
        now = utcnow_iso()
        await self._conn.executemany(
            "INSERT INTO game_versions (version_id, game_id, role, of_version_id, p, linked_at)"
            " VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(version_id) DO UPDATE SET"
            "  game_id = excluded.game_id, role = excluded.role,"
            "  of_version_id = excluded.of_version_id, p = excluded.p,"
            "  linked_at = CASE WHEN game_versions.game_id = excluded.game_id"
            "   THEN game_versions.linked_at ELSE excluded.linked_at END",
            [(vid, g, role, of, p, now) for vid, (g, role, of, p) in members.items()],
        )
        await self._conn.commit()

    async def write_relations(
        self, game_ids: list[int], relations: list[tuple[int, int, str, str, float | None]]
    ) -> None:
        """These games' relations, rebuilt: `(game, related, kind, source, p)`."""
        ids = list(dict.fromkeys(game_ids))
        for start in range(0, len(ids), 400):
            batch = ids[start : start + 400]
            marks = ",".join("?" * len(batch))
            await self._conn.execute(
                f"DELETE FROM game_relations WHERE game_id IN ({marks}) OR related_id IN ({marks})",
                (*batch, *batch),
            )
        now = utcnow_iso()
        await self._conn.executemany(
            "INSERT OR REPLACE INTO game_relations"
            " (game_id, related_id, kind, source, created_at, p)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [(g, r, kind, source, now, p) for g, r, kind, source, p in relations if g != r],
        )
        await self._conn.commit()

    async def write_review(
        self, version_ids: list[int], pairs: list[tuple[int, int, str, float, dict, dict, str]]
    ) -> None:
        """The doubtful pairs around these versions, replaced:
        `(subject, other, relation, p, probs, features, model)`."""
        ids = list(dict.fromkeys(version_ids))
        for start in range(0, len(ids), 400):
            batch = ids[start : start + 400]
            marks = ",".join("?" * len(batch))
            await self._conn.execute(
                f"DELETE FROM match_pairs WHERE version_id IN ({marks}) OR other_id IN ({marks})",
                (*batch, *batch),
            )
        now = utcnow_iso()
        await self._conn.executemany(
            "INSERT OR REPLACE INTO match_pairs (version_id, other_id, relation, p, probs,"
            " features, model, scored_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (s, o, rel, p, json.dumps(probs), json.dumps(feats), model, now)
                for s, o, rel, p, probs, feats, model in pairs
            ],
        )
        await self._conn.commit()

    async def pair_features(self, version_id: int, other_id: int) -> tuple[dict | None, str | None]:
        """The signs the model last saw for a pair, if it was in review."""
        cursor = await self._conn.execute(
            "SELECT features, model FROM match_pairs WHERE (version_id = ? AND other_id = ?)"
            " OR (version_id = ? AND other_id = ?)",
            (version_id, other_id, other_id, version_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return None, None
        return json.loads(row["features"]), str(row["model"])

    async def drop_empty_games(self) -> int:
        """Games no version is in any more, that nothing points at."""
        cursor = await self._conn.execute(
            "DELETE FROM games WHERE NOT EXISTS (SELECT 1 FROM game_versions gv"
            "  WHERE gv.game_id = games.game_id)"
            " AND NOT EXISTS (SELECT 1 FROM games g WHERE g.merged_into = games.game_id)"
            " AND merged_into IS NULL"
        )
        await self._conn.commit()
        return cursor.rowcount or 0

    async def linked_game_of(self, version_id: int) -> int | None:
        """The game a version is in."""
        cursor = await self._conn.execute(
            "SELECT game_id FROM game_versions WHERE version_id = ?", (version_id,)
        )
        row = await cursor.fetchone()
        return int(row["game_id"]) if row else None

    async def anchor_of(self, game_id: int) -> int | None:
        """A version that stands for the game: its anchor, else any of its."""
        cursor = await self._conn.execute(
            "SELECT COALESCE(g.anchor_version_id,"
            " (SELECT MIN(gv.version_id) FROM game_versions gv WHERE gv.game_id = g.game_id))"
            " FROM games g WHERE g.game_id = ?",
            (game_id,),
        )
        row = await cursor.fetchone()
        return int(row[0]) if row and row[0] is not None else None

    async def refresh_game_facts(self, game_ids: list[int] | None = None) -> None:
        """Each game's year, developer and publisher from its versions
        (`game_match.game_facts`); every game when none is named."""
        from bot.services.game_match import game_facts

        if game_ids is None:
            cursor = await self._conn.execute("SELECT game_id FROM games WHERE merged_into IS NULL")
            game_ids = [int(row[0]) for row in await cursor.fetchall()]
        for game_id in dict.fromkeys(game_ids):
            cursor = await self._conn.execute(
                # A version's own studio, else its HLTB entry's: a stand-in (a
                # 360 game) has none of its own.
                "SELECT v.name, v.release_date, gv.role AS kind, v.stand_in,"
                " h.release_year AS hltb_year,"
                " COALESCE(v.developer, h.developer) AS developer,"
                " COALESCE(v.publisher, h.publisher) AS publisher"
                " FROM game_versions gv JOIN versions v ON v.version_id = gv.version_id"
                " LEFT JOIN hltb_games h ON h.hltb_id = (SELECT MIN(vh.hltb_id)"
                "  FROM version_hltb vh WHERE vh.version_id = v.version_id)"
                " WHERE gv.game_id = ?",
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

    async def delete_decision(self, version_id: int, other_id: int) -> None:
        """The operator takes an answer back (either way round): the pair is
        the model's again."""
        await self._conn.execute(
            "DELETE FROM match_decisions WHERE (version_id = ? AND other_id = ?)"
            " OR (version_id = ? AND other_id = ?)",
            (version_id, other_id, other_id, version_id),
        )
        await self._conn.commit()

    async def all_decisions(self) -> list[dict[str, Any]]:
        """Every label, for fitting the weights."""
        cursor = await self._conn.execute("SELECT * FROM match_decisions ORDER BY decided_at")
        return [dict(row) for row in await cursor.fetchall()]
