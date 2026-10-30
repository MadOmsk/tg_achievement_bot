"""Games over versions (#147; migrations 092, 099). The operator's decisions
are labels on pairs of versions (`match_decisions`, input); which game each
version is in (`versions.game_id`, 108) and how games relate (`game_relations`) are
the matcher's output, rebuilt from the labels and the model — so a decision
outlives every rebuild."""

from __future__ import annotations

import json
from typing import Any

from bot.db.repo._sql import NOT_SPREAD
from bot.util import utcnow_iso

# Who the operator is in `decided_by` (the catalog viewer)
OPERATOR = "viewer"


class _GamesRepo:
    async def match_rows(self) -> list[dict[str, Any]]:
        """Every version as the matcher reads it: names, studio, year, store
        group and cross-gen set, its HLTB entries (never a spread one:
        `_sql.NOT_SPREAD`). Read whole."""
        cursor = await self._conn.execute(
            "SELECT v.version_id, v.store, v.product_id, v.console, v.platform, v.title_id,"
            "  v.name, v.name_ru, v.kind, v.developer, v.publisher, v.release_date,"
            "  v.store_group, v.cross_gen_set, v.stand_in, t.name AS list_name,"
            "  v.genres, v.description_en,"
            "  (SELECT string_agg(h.summary_en, ' ') FROM version_hltb vh JOIN hltb_entries h"
            "   ON h.hltb_id = vh.hltb_id WHERE vh.version_id = v.version_id"
            "   AND vh.source <> 'rejected' AND " + NOT_SPREAD + ") AS hltb_summary,"
            "  t.name_en AS list_name_en,"
            "  (SELECT string_agg(vh.hltb_id::text, ',') FROM version_hltb vh"
            "   WHERE vh.version_id = v.version_id AND vh.source <> 'rejected'"
            "   AND " + NOT_SPREAD + ") AS hltb_ids,"
            "  (SELECT MIN(h.release_year) FROM version_hltb vh JOIN hltb_entries h"
            "   ON h.hltb_id = vh.hltb_id WHERE vh.version_id = v.version_id"
            "   AND vh.source <> 'rejected' AND " + NOT_SPREAD + ") AS hltb_year,"
            "  (SELECT string_agg(h.game_type, ',') FROM version_hltb vh JOIN hltb_entries h"
            "   ON h.hltb_id = vh.hltb_id WHERE vh.version_id = v.version_id"
            "   AND vh.source <> 'rejected' AND " + NOT_SPREAD + ") AS hltb_types"
            " FROM versions v LEFT JOIN achievement_list_connectors t ON t.platform = v.platform"
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

    # --------------------------------------------------------------- weights

    async def active_match_weights(self) -> tuple[int, dict[str, dict[str, float]]] | None:
        """The fitted weights the linker uses (129), with their id; None: the
        hand weights."""
        cursor = await self._conn.execute(
            "SELECT weights_id, weights FROM match_weights WHERE active = 1"
            " ORDER BY weights_id DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        return (int(row[0]), json.loads(row[1])) if row else None

    async def match_weights_list(self) -> list[dict[str, Any]]:
        cursor = await self._conn.execute(
            "SELECT weights_id, gate_before, gate_after, labels, note, created_at, active"
            " FROM match_weights ORDER BY weights_id DESC"
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def add_match_weights(
        self,
        weights: dict[str, dict[str, float]],
        *,
        gate_before: float | None,
        gate_after: float | None,
        labels: int,
        note: str | None = None,
        activate: bool = False,
    ) -> int:
        async with self.transaction():
            cursor = await self._conn.execute(
                "INSERT INTO match_weights (weights, gate_before, gate_after, labels, note,"
                " created_at) VALUES (?, ?, ?, ?, ?, ?) RETURNING weights_id",
                (json.dumps(weights), gate_before, gate_after, labels, note, utcnow_iso()),
            )
            weights_id = int((await cursor.fetchone())[0])
            if activate:
                await self._activate_match_weights(weights_id)
        return weights_id

    async def activate_match_weights(self, weights_id: int | None) -> None:
        """Make one set active (None: back to the hand weights)."""
        async with self.transaction():
            await self._activate_match_weights(weights_id)

    async def _activate_match_weights(self, weights_id: int | None) -> None:
        await self._conn.execute("UPDATE match_weights SET active = 0 WHERE active = 1")
        if weights_id is not None:
            await self._conn.execute(
                "UPDATE match_weights SET active = 1 WHERE weights_id = ?", (weights_id,)
            )

    # ---------------------------------------------------------------- labels

    async def labels_by_key(self) -> list[dict[str, Any]]:
        """Every label with its two versions named by a key that holds in any
        copy of the catalog (`store:product id:console`), not by an id."""
        cursor = await self._conn.execute(
            "SELECT COALESCE(va.store || ':' || va.product_id || ':' || va.console,"
            " d.subject_key) AS a,"
            " COALESCE(vb.store || ':' || vb.product_id || ':' || vb.console, d.other_key) AS b,"
            " d.relation, d.decided_by, d.decided_at FROM match_decisions d"
            " LEFT JOIN versions va ON va.version_id = d.version_id"
            " LEFT JOIN versions vb ON vb.version_id = d.other_id"
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def version_by_key(self, key: str) -> int | None:
        """The version a label's key names: its product on its console, or —
        a stand-in that became a store product since — the achievement list
        it stood in for."""
        store, _, rest = key.partition(":")
        product_id, _, console = rest.rpartition(":")
        cursor = await self._conn.execute(
            "SELECT version_id FROM versions WHERE store = ? AND product_id = ? AND console = ?"
            " UNION ALL SELECT version_id FROM versions WHERE title_id = ? AND console = ?"
            " LIMIT 1",
            (store, product_id, console, product_id, console),
        )
        row = await cursor.fetchone()
        return int(row[0]) if row else None

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
        overrule: bool = False,
        decided_at: str | None = None,
    ) -> None:
        """A label on a pair; a pair has one label that counts, whichever way
        round it was given, and every one is kept in `label_log`. The
        operator's (`viewer`) is never replaced by anybody else's: theirs is
        logged as `refused` (the training audit, 2026-10-24: an adviser's
        answer and the operator's could not be compared) — unless the
        operator asked for it (`overrule`; owner, 2026-10-24: the web's
        answer over theirs on enhanced editions they had called remasters)."""
        async with self.transaction():
            cursor = await self._conn.execute(
                "SELECT decided_by FROM match_decisions WHERE (version_id = ? AND other_id = ?)"
                " OR (version_id = ? AND other_id = ?)",
                (version_id, other_id, other_id, version_id),
            )
            held = await cursor.fetchone()
            refused = (
                held is not None and held[0] == OPERATOR and decided_by != OPERATOR and not overrule
            )
            await self.log_label(
                "pair",
                "refused" if refused else "label",
                decided_by,
                version_id=version_id,
                other_id=other_id,
                relation=relation,
            )
            if refused:
                return
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
                    decided_at or utcnow_iso(),
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
                "SELECT version_id, game_id, role, of_version_id, link_p AS p, linked_at"
                f" FROM versions WHERE game_id IS NOT NULL AND version_id IN ({marks})",
                batch,
            )
            found.update({int(r["version_id"]): dict(r) for r in await cursor.fetchall()})
        return found

    async def save_adviser_label(
        self, run: str, question: str, decision: str, value: str, source: str, said: dict
    ) -> None:
        await self._conn.execute(
            "INSERT INTO adviser_labels"
            " (run, question, decision, value, source, said, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (run, question, decision) DO UPDATE SET value = excluded.value, source "
            "= excluded.source, said = excluded.said, created_at = excluded.created_at",
            (
                run,
                question,
                decision,
                value,
                source,
                json.dumps(said, ensure_ascii=False),
                utcnow_iso(),
            ),
        )
        await self._conn.commit()

    async def decision_of_pair(self, a: int, b: int) -> dict | None:
        """The label on a pair of versions, whichever way round it was given."""
        cursor = await self._conn.execute(
            "SELECT * FROM match_decisions WHERE (version_id = ? AND other_id = ?)"
            " OR (version_id = ? AND other_id = ?)",
            (a, b, b, a),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def game_anchor(self, game_id: int) -> int | None:
        """The version a game is anchored on (following a merge)."""
        card = await self.game_card(game_id)
        if card is None:
            return None
        if card.get("anchor_version_id"):
            return int(card["anchor_version_id"])
        cursor = await self._conn.execute(
            "SELECT MIN(version_id) FROM versions WHERE game_id = ?", (card["game_id"],)
        )
        row = await cursor.fetchone()
        return int(row[0]) if row and row[0] else None

    async def game_card(self, game_id: int) -> dict | None:
        """A game's own row, following a merge to the game it went into."""
        for _ in range(10):
            cursor = await self._conn.execute("SELECT * FROM games WHERE game_id = ?", (game_id,))
            row = await cursor.fetchone()
            if row is None:
                return None
            if not row["merged_into"]:
                return dict(row)
            game_id = int(row["merged_into"])
        return None

    async def psn_concepts_of_game(self, game_id: int) -> set[str]:
        """The PlayStation store concepts the versions of a game belong to."""
        cursor = await self._conn.execute(
            "SELECT store_ids FROM versions WHERE game_id = ? AND store = 'psn'", (game_id,)
        )
        found: set[str] = set()
        for row in await cursor.fetchall():
            for kind, value in json.loads(row[0] or "[]"):
                if kind == "psn_concept":
                    found.add(str(value))
        return found

    async def game_ids_for_sweep(self, which: str) -> list[int]:
        """The games a sweep goes through: `all`, `singles` (one release) or
        `stand-ins` (a release with no store page)."""
        sql = {
            "all": "SELECT game_id FROM games WHERE merged_into IS NULL",
            "singles": "SELECT game_id FROM versions WHERE game_id IS NOT NULL"
            " GROUP BY game_id HAVING COUNT(*) = 1",
            "stand-ins": "SELECT DISTINCT game_id FROM versions WHERE stand_in = 1"
            " AND game_id IS NOT NULL",
        }[which]
        cursor = await self._conn.execute(sql + " ORDER BY 1")
        return [int(r[0]) for r in await cursor.fetchall()]

    async def lone_versions(self) -> list[int]:
        """Versions in no game — there should be none (#204, step 12)."""
        cursor = await self._conn.execute("SELECT version_id FROM versions WHERE game_id IS NULL")
        return [int(r[0]) for r in await cursor.fetchall()]

    async def versions_of_games(self, game_ids: list[int]) -> list[int]:
        ids = list(dict.fromkeys(game_ids))
        found: list[int] = []
        for start in range(0, len(ids), 500):
            batch = ids[start : start + 500]
            marks = ",".join("?" * len(batch))
            cursor = await self._conn.execute(
                f"SELECT version_id FROM versions WHERE game_id IN ({marks})", batch
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
            " VALUES (?, ?, ?, ?, ?) RETURNING game_id",
            (name, year, anchor_version_id, now, now),
        )
        await self._conn.commit()
        return int((await cursor.fetchone())[0])

    async def rename_game(self, game_id: int, name: str, name_ru: str | None, source: str) -> None:
        """A manual name is never renamed by the matcher."""
        await self._conn.execute(
            "UPDATE games SET name = ?, name_ru = COALESCE(?, name_ru), name_source = ?,"
            " updated_at = ? WHERE game_id = ? AND (name_source = 'auto' OR ? = 'manual')"
            " AND (name IS DISTINCT FROM ? OR name_source IS DISTINCT FROM ?)",
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
            " AND kind_source = 'auto' AND kind IS DISTINCT FROM ?",
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
        # All the right-hand sides read the row as it was: `linked_at` stays
        # while the version stays in its game.
        await self._conn.executemany(
            "UPDATE versions SET game_id = ?, role = ?, of_version_id = ?, link_p = ?,"
            " linked_at = CASE WHEN game_id IS NOT DISTINCT FROM ? THEN COALESCE(linked_at, ?)"
            " ELSE ? END"
            " WHERE version_id = ?",
            [(g, role, of, p, g, now, now, vid) for vid, (g, role, of, p) in members.items()],
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
            "INSERT INTO game_relations"
            " (game_id, related_id, kind, source, created_at, p)"
            " VALUES (?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (game_id, related_id, kind) DO UPDATE SET source = excluded.source, "
            "created_at = excluded.created_at, p = excluded.p",
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
            "INSERT INTO match_pairs (version_id, other_id, relation, p, probs,"
            " features, model, scored_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (version_id, other_id) DO UPDATE SET relation = excluded.relation, p = "
            "excluded.p, probs = excluded.probs, features = excluded.features, model = "
            "excluded.model, scored_at = excluded.scored_at",
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
            "DELETE FROM games WHERE NOT EXISTS (SELECT 1 FROM versions v"
            "  WHERE v.game_id = games.game_id)"
            " AND NOT EXISTS (SELECT 1 FROM games g WHERE g.merged_into = games.game_id)"
            " AND merged_into IS NULL"
        )
        await self._conn.commit()
        return cursor.rowcount or 0

    async def linked_game_of(self, version_id: int) -> int | None:
        """The game a version is in."""
        cursor = await self._conn.execute(
            "SELECT game_id FROM versions WHERE version_id = ?", (version_id,)
        )
        row = await cursor.fetchone()
        return int(row["game_id"]) if row and row["game_id"] is not None else None

    async def game_of_version(self, version_id: int) -> int | None:
        """The game a version is in now (a relink may have given it another)."""
        cursor = await self._conn.execute(
            "SELECT game_id FROM versions WHERE version_id = ?", (version_id,)
        )
        row = await cursor.fetchone()
        return int(row[0]) if row and row[0] is not None else None

    async def anchor_of(self, game_id: int) -> int | None:
        """A version that stands for the game: its anchor, else any of its."""
        cursor = await self._conn.execute(
            "SELECT COALESCE(g.anchor_version_id,"
            " (SELECT MIN(v.version_id) FROM versions v WHERE v.game_id = g.game_id))"
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
                "SELECT v.name, v.release_date, v.role AS kind, v.stand_in,"
                " h.release_year AS hltb_year,"
                " COALESCE(v.developer, h.developer) AS developer,"
                " COALESCE(v.publisher, h.publisher) AS publisher"
                " FROM versions v"
                " LEFT JOIN hltb_entries h ON h.hltb_id = (SELECT MIN(vh.hltb_id)"
                "  FROM version_hltb vh WHERE vh.version_id = v.version_id"
                "  AND vh.source <> 'rejected')"
                # A fixed order: two versions of one year must not trade the
                # studio from one rebuild to the next.
                " WHERE v.game_id = ? ORDER BY v.release_date IS NULL, v.release_date,"
                " v.version_id",
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
                " WHERE game_id = ? AND (year IS DISTINCT FROM ? OR developer IS DISTINCT FROM ?"
                "  OR publisher IS DISTINCT FROM ? OR last_year IS DISTINCT FROM ? OR"
                " more_developers IS DISTINCT FROM ?"
                "  OR more_publishers IS DISTINCT FROM ?)",
                (*values, utcnow_iso(), game_id, *values),
            )
        await self._conn.commit()

    async def delete_decision(self, version_id: int, other_id: int) -> None:
        """The operator takes an answer back (either way round): the pair is
        the model's again; the log keeps what was taken back."""
        async with self.transaction():
            cursor = await self._conn.execute(
                "SELECT version_id, other_id, relation FROM match_decisions"
                " WHERE (version_id = ? AND other_id = ?) OR (version_id = ? AND other_id = ?)",
                (version_id, other_id, other_id, version_id),
            )
            for row in await cursor.fetchall():
                await self.log_label(
                    "pair",
                    "undo",
                    OPERATOR,
                    version_id=int(row[0]),
                    other_id=int(row[1]),
                    relation=str(row[2]),
                )
            await self._conn.execute(
                "DELETE FROM match_decisions WHERE (version_id = ? AND other_id = ?)"
                " OR (version_id = ? AND other_id = ?)",
                (version_id, other_id, other_id, version_id),
            )

    async def log_label(
        self,
        subject: str,
        event: str,
        decided_by: str,
        *,
        version_id: int | None = None,
        other_id: int | None = None,
        relation: str | None = None,
        game_id: int | None = None,
        series_id: int | None = None,
        member: bool | None = None,
        note: str | None = None,
    ) -> None:
        """One event of `label_log`, appended; never changed afterwards."""
        await self._conn.execute(
            "INSERT INTO label_log (subject, event, version_id, other_id, relation, game_id,"
            " series_id, member, decided_by, decided_at, note)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                subject,
                event,
                version_id,
                other_id,
                relation,
                game_id,
                series_id,
                None if member is None else int(member),
                decided_by,
                utcnow_iso(),
                note,
            ),
        )
        await self._conn.commit()

    async def all_decisions(self) -> list[dict[str, Any]]:
        """Every label, for fitting the weights."""
        cursor = await self._conn.execute("SELECT * FROM match_decisions ORDER BY decided_at")
        return [dict(row) for row in await cursor.fetchall()]
