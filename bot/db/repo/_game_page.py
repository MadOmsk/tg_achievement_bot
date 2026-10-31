"""What the Mini App's game page reads (#147, stage 5; owner, 2026-10-25): a
game with its versions, achievement lists, editions, DLC, series and
relations; who here played it; the games a search finds; favorite games."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from bot.db.repo._sql import OWNED_BY_PERSON, earned_at, platform_is
from bot.services import x360_frame
from bot.util import utcnow, utcnow_iso

# A merge chain is short; this only stops a cycle the operator could make.
_MERGE_HOPS = 10

# The roles that are the game itself, not its demo, tool or soundtrack.
_PLAYABLE_ROLES = "('version', 'enhanced')"

# Any number, the same for every bot sharing the catalog.
_CATALOG_LINK_LOCK = 234001


class _GamePageRepo:
    async def earned_groups(self, platform: str, title_id: str) -> dict[str, str]:
        """Each achievement's group as somebody's earned row has it (`base` /
        `non_base` on Xbox) — the catalog's list often carries none."""
        cursor = await self._conn.execute(
            "SELECT achievement_id, MAX(trophy_group_id) FROM seen_achievements"
            " WHERE platform = ? AND title_id = ? AND trophy_group_id IS NOT NULL"
            " GROUP BY achievement_id",
            (platform, title_id),
        )
        return {str(row[0]): str(row[1]) for row in await cursor.fetchall()}

    async def list_dlc_names(self, platform: str, title_id: str) -> list[tuple[str, str | None]]:
        """The add-ons of a list's versions, by name (English, Russian)."""
        cursor = await self._conn.execute(
            "SELECT DISTINCT d.name, d.name_ru FROM dlcs d"
            " JOIN versions v ON v.version_id = d.version_id"
            " WHERE v.platform = ? AND v.title_id = ? AND d.name IS NOT NULL",
            (platform, title_id),
        )
        return [(row[0], row[1]) for row in await cursor.fetchall()]

    async def live_game_id(self, game_id: int) -> int | None:
        """The game an id names now: a merged game's id leads to the game it
        went into. None when there is no such game."""
        current = game_id
        for _ in range(_MERGE_HOPS):
            cursor = await self._conn.execute(
                "SELECT merged_into FROM games WHERE game_id = ?", (current,)
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            if row["merged_into"] is None:
                return current
            current = int(row["merged_into"])
        return current

    async def game_of_list(self, platform: str, title_id: str) -> int | None:
        """The game an achievement list belongs to, through its versions — the
        game's own versions before a demo's or a tool's. Any Xbox value finds
        either generation (`platform_is`)."""
        where, params = platform_is(platform)
        cursor = await self._conn.execute(
            "SELECT game_id FROM versions"
            f" WHERE {where} AND title_id = ? AND game_id IS NOT NULL"
            f" ORDER BY role IN {_PLAYABLE_ROLES} DESC, version_id LIMIT 1",
            (*params, str(title_id)),
        )
        row = await cursor.fetchone()
        if row is None:
            # Another id naming a version (`versions.store_ids`): a regional
            # twin of its list, or a PlayStation store title — what PSN's
            # presence names (CUSA…/PPSA…), never the trophy list.
            cursor = await self._conn.execute(
                "SELECT v.game_id FROM versions v, jsonb_array_elements(v.store_ids::jsonb) j"
                " WHERE v.game_id IS NOT NULL AND ("
                "  (j.value->>0 = 'list'"
                "   AND j.value->>1 = ?)"
                "  OR (j.value->>0 = 'psn_title'"
                "   AND (j.value->>1 = ?"
                "    OR j.value->>1 LIKE ? || '\\_%' ESCAPE '\\')))"
                f" ORDER BY v.role IN {_PLAYABLE_ROLES} DESC, v.version_id LIMIT 1",
                (f"{platform}:{title_id}", str(title_id), str(title_id)),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return await self.live_game_id(int(row["game_id"]))

    async def game_name_index(self) -> dict[str, int]:
        """Every name a catalog game goes by, as the matcher normalizes names
        (`game_match.name_key`: accents, ®, apostrophes, numerals) -> its live
        game: the game's own names and its playable versions' — what a game
        searched for in a store is found in the catalog by."""
        from bot.services.game_match import name_key

        index: dict[str, int] = {}
        cursor = await self._conn.execute(
            "SELECT game_id, name, name_ru FROM games WHERE merged_into IS NULL"
        )
        for row in await cursor.fetchall():
            for name in (row["name"], row["name_ru"]):
                key = name_key(name or "")
                if key:
                    index.setdefault(key, int(row["game_id"]))
        cursor = await self._conn.execute(
            "SELECT game_id, name, name_ru FROM versions"
            f" WHERE game_id IS NOT NULL AND role IN {_PLAYABLE_ROLES}"
        )
        for row in await cursor.fetchall():
            for name in (row["name"], row["name_ru"]):
                key = name_key(name or "")
                if key:
                    index.setdefault(key, int(row["game_id"]))
        # What the stores sell around a game we have — its DLC and editions —
        # is that game's too, never a game of its own to add.
        cursor = await self._conn.execute(
            "SELECT v.game_id, d.name, d.name_ru FROM dlcs d"
            " JOIN versions v ON v.version_id = d.version_id WHERE v.game_id IS NOT NULL"
            " UNION ALL"
            " SELECT v.game_id, e.name, NULL FROM editions e"
            " JOIN edition_items i ON i.edition_id = e.edition_id"
            " JOIN versions v ON v.version_id = i.version_id WHERE v.game_id IS NOT NULL"
        )
        for row in await cursor.fetchall():
            for name in (row["name"], row["name_ru"]):
                key = name_key(name or "")
                if key:
                    index.setdefault(key, int(row["game_id"]))
        return index

    async def add_manual_game(
        self, name: str, name_ru: str | None = None, key: str | None = None
    ) -> tuple[int, bool]:
        """A game the super-admin adds by hand while the stores have not been
        asked about it (owner, 2026-10-30), for a prize to point at: `(game id,
        made now)`. A game of that name already in the catalog is that game.
        It is one stand-in version of no store (a game with no version is
        dropped by the next rebuild), named by hand so the matcher leaves the
        name; the linker joins it to the real game once the stores bring one,
        and the old id resolves to it. Queued for the octopus by its name, or by
        `key` (a store link's)."""
        from bot.services.game_match import name_key
        from bot.services.stores import UNKNOWN_STORE, StoreVersion

        name = name.strip()
        # Never a second game of a name the catalog has (owner, 2026-10-30).
        known = (await self.game_name_index()).get(name_key(name))
        if known is not None:
            return await self.live_game_id(known) or known, False
        version_id = await self.save_version(
            StoreVersion(
                store=UNKNOWN_STORE,
                product_id=f"manual:{uuid.uuid4().hex[:12]}",
                console="pc",
                name=name,
                name_ru=name_ru,
                kind="game",
                stand_in=True,
            ),
            platform=None,
            title_id=None,
            origin="store",
            found=("manual", name),
        )
        async with self.transaction():
            game = await self.create_game(name, None, version_id)
            await self._conn.execute(
                "UPDATE versions SET game_id = ?, role = 'version' WHERE version_id = ?",
                (game, version_id),
            )
            await self._conn.execute(
                "UPDATE games SET name_source = 'manual', name_ru = ? WHERE game_id = ?",
                (name_ru, game),
            )
        # By what the admin gave: a store link's key names the game exactly.
        await self.octopus_enqueue(key or f"name:{name}", "manual")
        return game, True

    async def stand_in_versions_due(self, source: str, limit: int) -> list[int]:
        """Versions that are only a stand-in made from an achievement list, in
        a game, that `source` has not looked at lately (`fetch_state`) — the
        ones the linker may still put in a bigger game."""
        cursor = await self._conn.execute(
            "SELECT v.version_id FROM versions v LEFT JOIN fetch_state f"
            "  ON f.subject = 'version:' || v.version_id AND f.source = ?"
            " WHERE COALESCE(v.stand_in, 0) = 1 AND v.game_id IS NOT NULL"
            "   AND (f.next_check_at IS NULL OR f.next_check_at <= ?)"
            " ORDER BY f.next_check_at IS NOT NULL, f.next_check_at, v.version_id LIMIT ?",
            (source, utcnow_iso(), limit),
        )
        return [int(row["version_id"]) for row in await cursor.fetchall()]

    async def game_of_steam_app(self, appid: int) -> int | None:
        """The game a Steam app is: its Steam version, else a version that
        knows it as its twin (`steam_twin`) — what a developer's post is of."""
        cursor = await self._conn.execute(
            "SELECT v.game_id FROM versions v"
            " WHERE v.game_id IS NOT NULL AND ("
            "  (v.store = 'steam' AND v.product_id = ?)"
            "  OR EXISTS (SELECT 1 FROM jsonb_array_elements(v.store_ids::jsonb) j"
            "   WHERE j.value->>0 = 'steam_twin'"
            "    AND j.value->>1 = ?))"
            f" ORDER BY v.role IN {_PLAYABLE_ROLES} DESC, v.version_id LIMIT 1",
            (str(appid), str(appid)),
        )
        row = await cursor.fetchone()
        return await self.live_game_id(int(row["game_id"])) if row else None

    async def adopt_list_as_game(self, platform: str, title_id: str) -> int | None:
        """A list in no game yet (the linker has not reached it) becomes a
        game of its own, its versions in it — so its page opens now; the next
        linking puts it where it belongs, keeping the id by its anchor."""
        versions = await self.ensure_list_version(platform, title_id)
        if not versions:
            return None
        record = await self.title_record(platform, title_id) or {}
        name = str(record.get("name_en") or record.get("name") or title_id)
        marks = ",".join("?" * len(versions))
        async with self.transaction():
            # Two visits at once: the first one's game stands (the block holds
            # the connection, so this look and the insert are one step).
            cursor = await self._conn.execute(
                f"SELECT game_id FROM versions WHERE version_id IN ({marks})"
                " AND game_id IS NOT NULL LIMIT 1",
                versions,
            )
            taken = await cursor.fetchone()
            if taken is not None:
                return await self.live_game_id(int(taken[0]))
            # The game the catalog already has under this name is the one this
            # list is of (owner, 2026-10-30: a page only refers to a game, it
            # never makes a second one of a name): the list's version joins it.
            game = await self._game_named(record, name)
            if game is None:
                game = await self.create_game(name, None, versions[0])
            await self._conn.execute(
                f"UPDATE versions SET game_id = ?, role = 'version' WHERE version_id IN ({marks})"
                " AND game_id IS NULL",
                (game, *versions),
            )
        return game

    async def _game_named(self, record: dict[str, Any], name: str) -> int | None:
        """The live game that goes by any of an achievement list's names."""
        from bot.services.game_match import name_key

        index = await self.game_name_index()
        for candidate in (name, record.get("name"), record.get("name_ru")):
            known = index.get(name_key(str(candidate or "")))
            if known is not None:
                return await self.live_game_id(known) or known
        return None

    async def game_row(self, game_id: int) -> dict[str, Any] | None:
        cursor = await self._conn.execute("SELECT * FROM games WHERE game_id = ?", (game_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

    @asynccontextmanager
    async def catalog_link_lock(self) -> AsyncIterator[None]:
        """One linker at a time across the bots sharing the catalog. Tried and waited
        for, never blocked on: a bot has one connection, and it serves everybody."""
        while True:
            cursor = await self._conn.execute(
                "SELECT pg_try_advisory_lock(?::bigint)", (_CATALOG_LINK_LOCK,)
            )
            if (await cursor.fetchone())[0]:
                break
            await asyncio.sleep(1)
        try:
            yield
        finally:
            await self._conn.execute("SELECT pg_advisory_unlock(?::bigint)", (_CATALOG_LINK_LOCK,))

    async def games_to_translate_first(self) -> list[int]:
        """Every game, those played here first, the latest played first."""
        cursor = await self._conn.execute(
            "SELECT g.game_id FROM games g LEFT JOIN ("
            "  SELECT v.game_id, MAX(COALESCE(s.unlocked_at, s.created_at)) AS last_played"
            "  FROM seen_achievements s"
            "  JOIN versions v ON v.platform = s.platform AND v.title_id = s.title_id"
            "  GROUP BY v.game_id"
            ") played ON played.game_id = g.game_id"
            " ORDER BY played.last_played DESC NULLS LAST, g.game_id"
        )
        return [int(row["game_id"]) for row in await cursor.fetchall()]

    async def game_ids_after(self, after: int, limit: int) -> list[int]:
        """Games by id past `after`, for a walk over all of them."""
        cursor = await self._conn.execute(
            "SELECT game_id FROM games WHERE game_id > ? ORDER BY game_id LIMIT ?",
            (after, limit),
        )
        return [int(row["game_id"]) for row in await cursor.fetchall()]

    async def game_page_versions(self, game_id: int) -> list[dict[str, Any]]:
        """Every version of the game with what its store said, earliest first."""
        cursor = await self._conn.execute(
            "SELECT version_id, store, product_id, console, platform, title_id, name, name_ru,"
            "  kind, role, developer, publisher, release_date, genres, also_on,"
            "  description_en, description_ru, description_source, description_ru_of,"
            "  media, on_sale, stand_in, store_ids"
            " FROM versions WHERE game_id = ?"
            " ORDER BY release_date IS NULL, release_date, version_id",
            (game_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def set_version_art(self, version_id: int, art: dict[str, str]) -> None:
        """A version's library art of now (`steam_library_art`), merged into
        its `media` over what was there."""
        await self._conn.execute(
            "UPDATE versions SET media = (COALESCE(media, '{}')::jsonb || ?::jsonb)::text"
            " WHERE version_id = ?",
            (json.dumps(art), version_id),
        )
        await self._conn.commit()

    async def set_version_description_ru(
        self, version_id: int, translated: str, of: str | None
    ) -> None:
        """Our translation of a version's English description (#230), kept
        with a hash of the English it was made from; a store's own Russian
        is never replaced by it."""
        await self._conn.execute(
            "UPDATE versions SET description_ru = ?, description_source = 'llm',"
            "  description_ru_of = ?"
            " WHERE version_id = ? AND COALESCE(description_source, '') <> 'native'",
            (translated, of, version_id),
        )
        await self._conn.commit()

    async def game_page_lists(self, game_id: int) -> list[dict[str, Any]]:
        """The game's achievement lists, each once, with its size: the
        platform's count, or the list read whole when that is larger."""
        cursor = await self._conn.execute(
            "SELECT DISTINCT a.platform, a.title_id, a.name, a.name_ru, a.name_en,"
            "  a.icon_url, a.platforms,"
            "  GREATEST(COALESCE(a.achievements_total, 0),"
            "      (SELECT COUNT(*) FROM title_achievements ta"
            "        WHERE ta.platform = a.platform AND ta.title_id = a.title_id"
            "          AND ta.listed = 1)) AS total"
            " FROM versions v JOIN achievement_list_connectors a"
            "  ON a.platform = v.platform AND a.title_id = v.title_id"
            f" WHERE v.game_id = ? AND v.role IN {_PLAYABLE_ROLES}",
            (game_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def game_page_editions(self, game_id: int) -> list[dict[str, Any]]:
        """The packs the stores sell around this game's versions — its own
        editions, never a bundle of several games."""
        cursor = await self._conn.execute(
            "SELECT DISTINCT e.edition_id, e.store, e.store_id, e.name, e.kind, e.on_sale,"
            "  e.media, e.image_path"
            " FROM editions e JOIN edition_items i ON i.edition_id = e.edition_id"
            " JOIN versions v ON v.version_id = i.version_id"
            " WHERE v.game_id = ? AND e.scope = 'edition'"
            " ORDER BY e.edition_id",
            (game_id,),
        )
        editions = [dict(row) for row in await cursor.fetchall()]
        if not editions:
            return editions
        marks = ",".join("?" * len(editions))
        cursor = await self._conn.execute(
            "SELECT edition_id, name, item_kind, is_primary FROM edition_items"
            f" WHERE edition_id IN ({marks}) ORDER BY is_primary DESC, seq",
            [e["edition_id"] for e in editions],
        )
        items: dict[int, list[dict[str, Any]]] = {}
        for row in await cursor.fetchall():
            items.setdefault(int(row["edition_id"]), []).append(dict(row))
        for edition in editions:
            edition["items"] = items.get(int(edition["edition_id"]), [])
        return editions

    async def game_page_dlcs(self, game_id: int) -> list[dict[str, Any]]:
        """Every DLC of every version, with its console and its HLTB entry's
        main-story time when it has one."""
        cursor = await self._conn.execute(
            "SELECT d.dlc_id, d.name, d.name_ru, d.kind, d.release_date, d.image_url,"
            "  d.on_sale, d.store_id, d.trophy_group_id, d.description_en, v.console, v.store,"
            "  e.hltb_id, e.comp_main, e.comp_plus, e.comp_100, e.review_score,"
            "  e.rating_esrb, e.rating_pegi, e.comp_lvl_co, e.comp_lvl_mp"
            " FROM dlcs d JOIN versions v ON v.version_id = d.version_id"
            " LEFT JOIN hltb_entries e ON e.hltb_id = ("
            "   SELECT dh.hltb_id FROM dlc_hltb dh"
            "   WHERE dh.dlc_id = d.dlc_id AND dh.source <> 'rejected' LIMIT 1)"
            " WHERE v.game_id = ?"
            " ORDER BY d.release_date IS NULL, d.release_date, d.dlc_id",
            (game_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def game_page_series(self, game_id: int) -> list[dict[str, Any]]:
        """The series the game is in, each with its games' ids, the newest first."""
        cursor = await self._conn.execute(
            "SELECT s.series_id, s.name, s.name_ru FROM game_series gs"
            " JOIN series s ON s.series_id = gs.series_id"
            " WHERE gs.game_id = ? AND gs.member = 1 AND s.merged_into IS NULL"
            " ORDER BY s.rule_key IS NOT NULL, s.series_id",
            (game_id,),
        )
        series = [dict(row) for row in await cursor.fetchall()]
        for one in series:
            cursor = await self._conn.execute(
                "SELECT g.game_id FROM game_series gs JOIN games g ON g.game_id = gs.game_id"
                " WHERE gs.series_id = ? AND gs.member = 1 AND g.merged_into IS NULL"
                "   AND g.kind <> 'extra'"
                # Newest first (owner, 2026-10-26); a game of no known year last.
                " ORDER BY g.year IS NULL, g.year DESC, g.game_id DESC",
                (one["series_id"],),
            )
            one["game_ids"] = [int(row["game_id"]) for row in await cursor.fetchall()]
        return series

    async def game_page_relations(self, game_id: int) -> list[dict[str, Any]]:
        """How the game relates to others: `kind` from this game's side —
        `remaster_of` (this one is a remaster of `other`), `remastered_by`
        (`other` is its remaster), and so on."""
        cursor = await self._conn.execute(
            "SELECT kind, related_id AS other, 1 AS forward FROM game_relations WHERE game_id = ?"
            " UNION ALL"
            " SELECT kind, game_id AS other, 0 AS forward FROM game_relations WHERE related_id = ?",
            (game_id, game_id),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def game_cards(self, game_ids: list[int]) -> dict[int, dict[str, Any]]:
        """What a game's card needs — name, year, its versions' pictures and
        lists' icons — for many games at once (a series, a search, favorites)."""
        if not game_ids:
            return {}
        marks = ",".join("?" * len(game_ids))
        cursor = await self._conn.execute(
            f"SELECT game_id, name, name_ru, year, kind FROM games WHERE game_id IN ({marks})",
            game_ids,
        )
        cards = {
            int(row["game_id"]): {**dict(row), "media": [], "icons": []}
            for row in await cursor.fetchall()
        }
        cursor = await self._conn.execute(
            "SELECT v.game_id, v.store, v.product_id, v.console, v.media, a.icon_url,"
            "  a.platform AS list_platform"
            " FROM versions v LEFT JOIN achievement_list_connectors a"
            "  ON a.platform = v.platform AND a.title_id = v.title_id"
            f" WHERE v.game_id IN ({marks}) AND v.role IN {_PLAYABLE_ROLES}",
            game_ids,
        )
        for row in await cursor.fetchall():
            card = cards.get(int(row["game_id"]))
            if card is None:
                continue
            card["media"].append(
                {
                    "store": row["store"],
                    "product_id": row["product_id"],
                    "console": row["console"],
                    "media": row["media"],
                }
            )
            if row["icon_url"]:
                card["icons"].append(x360_frame.mark(row["icon_url"], row["list_platform"]))
        return cards

    async def game_steam_apps(self, game_id: int) -> list[int]:
        """The Steam apps of a game: its Steam versions, and the app found for
        any other version (`steam_twin`)."""
        cursor = await self._conn.execute(
            "SELECT DISTINCT CAST(product_id AS INTEGER) AS appid FROM versions"
            " WHERE game_id = ? AND store = 'steam'"
            " UNION"
            " SELECT DISTINCT (j.value->>1)::bigint FROM versions v,"
            "  jsonb_array_elements(v.store_ids::jsonb) j"
            " WHERE v.game_id = ? AND j.value->>0 = 'steam_twin'",
            (game_id, game_id),
        )
        return [int(row[0]) for row in await cursor.fetchall() if row[0]]

    async def game_players(self, game_id: int, person_ids: list[int]) -> list[dict[str, Any]]:
        """Of these people, who earned something in the game: how many, when
        last, and on which list most — the most first; `lists` holds every
        list each played, the most first (one game on Xbox and Steam)."""
        if not person_ids:
            return []
        marks = ",".join("?" * len(person_ids))
        cursor = await self._conn.execute(
            "SELECT al.person_id, s.platform, s.title_id, MAX(s.xuid) AS xuid, COUNT(*) AS n,"
            f"  MAX({earned_at('s.')}) AS last"
            " FROM seen_achievements s "
            f"{OWNED_BY_PERSON}"
            " JOIN versions v ON v.platform = s.platform AND v.title_id = s.title_id"
            f" WHERE v.game_id = ? AND al.person_id IN ({marks})"
            "   AND v.version_id = (SELECT MIN(v2.version_id) FROM versions v2"
            "     WHERE v2.platform = s.platform AND v2.title_id = s.title_id AND v2.game_id = ?)"
            " GROUP BY al.person_id, s.platform, s.title_id",
            (game_id, *person_ids, game_id),
        )
        best: dict[int, dict[str, Any]] = {}
        for row in await cursor.fetchall():
            person = int(row["person_id"])
            item = dict(row)
            current = best.get(person)
            if current is None:
                best[person] = {**item, "lists": [item]}
                continue
            current["lists"].append(item)
            last = max(item["last"] or "", current["last"] or "")
            if item["n"] > current["n"]:
                best[person] = {**item, "lists": current["lists"]}
            best[person]["last"] = last
        for row in best.values():
            row["lists"].sort(key=lambda r: -r["n"])
        return sorted(best.values(), key=lambda r: (-r["n"], r["person_id"]))

    async def game_search_names(self) -> list[tuple[int, str]]:
        """Every name a live game is known by — its own, its Russian one and
        its versions' — for a search to match in Python (SQLite folds only
        ASCII case)."""
        cursor = await self._conn.execute(
            "SELECT game_id, name FROM games WHERE merged_into IS NULL AND kind <> 'extra'"
            " UNION SELECT game_id, name_ru FROM games"
            "  WHERE merged_into IS NULL AND kind <> 'extra' AND name_ru IS NOT NULL"
            " UNION SELECT v.game_id, v.name FROM versions v JOIN games g ON g.game_id = v.game_id"
            f"  WHERE g.merged_into IS NULL AND g.kind <> 'extra' AND v.role IN {_PLAYABLE_ROLES}"
            "   AND v.name IS NOT NULL"
            # The platforms' own names of its lists: Steam and PSN name a game
            # in Russian too («Ведьмак 3: Дикая Охота»).
            " UNION SELECT v.game_id, a.name_ru FROM versions v"
            " JOIN games g ON g.game_id = v.game_id"
            " JOIN achievement_list_connectors a ON a.platform = v.platform"
            "  AND a.title_id = v.title_id"
            f"  WHERE g.merged_into IS NULL AND g.kind <> 'extra' AND v.role IN {_PLAYABLE_ROLES}"
            "   AND a.name_ru IS NOT NULL",
        )
        return [(int(row[0]), str(row[1])) for row in await cursor.fetchall() if row[1]]

    async def game_player_counts(self, game_ids: list[int]) -> dict[int, int]:
        """How many people here earned something in each game."""
        if not game_ids:
            return {}
        marks = ",".join("?" * len(game_ids))
        cursor = await self._conn.execute(
            "SELECT v.game_id, COUNT(DISTINCT al.person_id) AS n"
            " FROM seen_achievements s "
            f"{OWNED_BY_PERSON}"
            " JOIN versions v ON v.platform = s.platform AND v.title_id = s.title_id"
            f" WHERE v.game_id IN ({marks}) GROUP BY v.game_id",
            game_ids,
        )
        return {int(row["game_id"]): int(row["n"]) for row in await cursor.fetchall()}

    # ------------------------------------------------------------ favorites

    async def _anchor_key(self, game_id: int) -> str | None:
        cursor = await self._conn.execute(
            "SELECT v.store || ':' || v.product_id || ':' || v.console FROM games g"
            " JOIN versions v ON v.version_id = g.anchor_version_id WHERE g.game_id = ?",
            (game_id,),
        )
        row = await cursor.fetchone()
        return row[0] if row else None

    async def set_favorite(self, person_id: int, game_id: int, on: bool) -> None:
        if on:
            await self._conn.execute(
                "INSERT INTO favorite_games (person_id, game_id, anchor_key, created_at)"
                " VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING",
                (
                    person_id,
                    game_id,
                    await self._anchor_key(game_id),
                    utcnow().isoformat(timespec="seconds"),
                ),
            )
        else:
            # Every row of this person's that is this game now — one stored
            # under an id merged into it, or found by its anchor, included:
            # deleting by the id alone left such a heart on for good.
            stored = [
                row_game
                for person, row_game, game in await self._favorites_resolved(person_id)
                if person == person_id and game == game_id
            ]
            marks = ",".join("?" * len(stored))
            if stored:
                await self._conn.execute(
                    f"DELETE FROM favorite_games WHERE person_id = ? AND game_id IN ({marks})",
                    (person_id, *stored),
                )
        await self._conn.commit()

    async def _favorites_resolved(self, person_id: int | None = None) -> list[tuple[int, int, int]]:
        """`(person, stored game id, the game it is now)` of every favorite (or
        one person's), the latest first — found by its anchor first (a catalog
        carried over may give the same game another id, and the old id to
        another game), else by its id, a merged one leading to the game it
        went into. Rows whose game is gone are left out. Every reader of
        favorites goes through this, so a merge never splits what they see."""
        where, args = ("WHERE person_id = ?", (person_id,)) if person_id is not None else ("", ())
        cursor = await self._conn.execute(
            f"SELECT person_id, game_id, anchor_key FROM favorite_games {where}"
            " ORDER BY created_at DESC, game_id DESC",
            args,
        )
        resolved: list[tuple[int, int, int]] = []
        for row in await cursor.fetchall():
            game = None
            if row["anchor_key"]:
                store, product_id, console = [*str(row["anchor_key"]).split(":", 2), "", ""][:3]
                inner = await self._conn.execute(
                    "SELECT game_id FROM versions"
                    " WHERE store = ? AND product_id = ? AND console = ? AND game_id IS NOT NULL",
                    (store, product_id, console),
                )
                hit = await inner.fetchone()
                game = await self.live_game_id(int(hit[0])) if hit else None
            if game is None:
                game = await self.live_game_id(int(row["game_id"]))
            if game is not None:
                resolved.append((int(row["person_id"]), int(row["game_id"]), game))
        return resolved

    async def favorite_game_ids(self, person_id: int) -> list[int]:
        """A person's favorite games, the latest first, each as the game it is now."""
        found: list[int] = []
        for _person, _stored, game in await self._favorites_resolved(person_id):
            if game not in found:
                found.append(game)
        return found

    async def is_favorite(self, person_id: int, game_id: int) -> bool:
        return game_id in await self.favorite_game_ids(person_id)

    async def favorite_count(self, game_id: int) -> int:
        return len({p for p, _stored, game in await self._favorites_resolved() if game == game_id})

    async def favorite_steam_apps(self) -> list[int]:
        """The Steam apps of every game somebody keeps as a favorite."""
        apps: list[int] = []
        for game in dict.fromkeys(g for _p, _s, g in await self._favorites_resolved()):
            apps.extend(a for a in await self.game_steam_apps(game) if a not in apps)
        return apps

    async def favorite_apps_due(self, *, stale_before: str, limit: int) -> list[int]:
        """Favorites' Steam apps whose news were last read before `stale_before`
        (or never), the longest-waiting first."""
        apps = await self.favorite_steam_apps()
        if not apps:
            return []
        cursor = await self._conn.execute(
            "WITH fav(appid) AS (SELECT value::bigint FROM jsonb_array_elements_text(?::jsonb))"
            " SELECT fav.appid FROM fav LEFT JOIN steam_apps sa ON sa.appid = fav.appid"
            " WHERE sa.patches_checked_at IS NULL OR sa.patches_checked_at < ?"
            " ORDER BY sa.patches_checked_at IS NOT NULL, sa.patches_checked_at LIMIT ?",
            (f"[{','.join(str(a) for a in apps)}]", stale_before, limit),
        )
        return [int(row[0]) for row in await cursor.fetchall()]

    async def favoriters_of_app(self, appid: int) -> list[tuple[int, int, str]]:
        """Who keeps a game of this Steam app as a favorite:
        `(person_id, game_id, game name)`."""
        found: list[tuple[int, int, str]] = []
        apps_of: dict[int, list[int]] = {}
        for person, _stored, game in await self._favorites_resolved():
            if game not in apps_of:
                apps_of[game] = await self.game_steam_apps(game)
            if appid not in apps_of[game]:
                continue
            cursor = await self._conn.execute(
                "SELECT g.name FROM games g JOIN users u ON u.id = ? AND u.is_excluded = 0"
                " WHERE g.game_id = ?",
                (person, game),
            )
            row = await cursor.fetchone()
            if row is not None and (person, game, str(row[0])) not in found:
                found.append((person, game, str(row[0])))
        return found

    async def game_list_of(self, game_id: int) -> tuple[str, str] | None:
        """One achievement list of the game, for a link that needs one: the
        list most people here played, else its anchor's."""
        cursor = await self._conn.execute(
            "SELECT v.platform, v.title_id FROM versions v"
            f" WHERE v.game_id = ? AND v.platform IS NOT NULL AND v.role IN {_PLAYABLE_ROLES}"
            " ORDER BY (SELECT COUNT(*) FROM seen_achievements s"
            "   WHERE s.platform = v.platform AND s.title_id = v.title_id) DESC, v.version_id"
            " LIMIT 1",
            (game_id,),
        )
        row = await cursor.fetchone()
        return (str(row[0]), str(row[1])) if row else None
