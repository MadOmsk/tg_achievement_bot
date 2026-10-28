"""What the Mini App's game page reads (#147, stage 5; owner, 2026-10-25): a
game with its versions, achievement lists, editions, DLC, series and
relations; who here played it; the games a search finds; favorite games."""

from __future__ import annotations

from typing import Any

from bot.db.repo._sql import OWNED_BY_PERSON, earned_at
from bot.services import x360_frame
from bot.util import utcnow

# A merge chain is short; this only stops a cycle the operator could make.
_MERGE_HOPS = 10

# The roles that are the game itself, not its demo, tool or soundtrack.
_PLAYABLE_ROLES = "('version', 'enhanced')"


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
        game's own versions before a demo's or a tool's."""
        cursor = await self._conn.execute(
            "SELECT game_id FROM versions"
            " WHERE platform = ? AND title_id = ? AND game_id IS NOT NULL"
            f" ORDER BY role IN {_PLAYABLE_ROLES} DESC, version_id LIMIT 1",
            (platform, str(title_id)),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return await self.live_game_id(int(row["game_id"]))

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
            game = await self.create_game(name, None, versions[0])
            await self._conn.execute(
                f"UPDATE versions SET game_id = ?, role = 'version' WHERE version_id IN ({marks})"
                " AND game_id IS NULL",
                (game, *versions),
            )
        return game

    async def game_row(self, game_id: int) -> dict[str, Any] | None:
        cursor = await self._conn.execute("SELECT * FROM games WHERE game_id = ?", (game_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def game_page_versions(self, game_id: int) -> list[dict[str, Any]]:
        """Every version of the game with what its store said, earliest first."""
        cursor = await self._conn.execute(
            "SELECT version_id, store, product_id, console, platform, title_id, name, name_ru,"
            "  kind, role, developer, publisher, release_date, genres, also_on,"
            "  description_en, description_ru, media, on_sale, stand_in, store_ids"
            " FROM versions WHERE game_id = ?"
            " ORDER BY release_date IS NULL, release_date, version_id",
            (game_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def game_page_lists(self, game_id: int) -> list[dict[str, Any]]:
        """The game's achievement lists, each once, with its size: the
        platform's count, or the list read whole when that is larger."""
        cursor = await self._conn.execute(
            "SELECT DISTINCT a.platform, a.title_id, a.name, a.name_ru, a.name_en,"
            "  a.icon_url, a.platforms,"
            "  MAX(COALESCE(a.achievements_total, 0),"
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
        return [dict(row) for row in await cursor.fetchall()]

    async def game_page_dlcs(self, game_id: int) -> list[dict[str, Any]]:
        """Every DLC of every version, with its console and its HLTB entry's
        main-story time when it has one."""
        cursor = await self._conn.execute(
            "SELECT d.dlc_id, d.name, d.name_ru, d.kind, d.release_date, d.image_url,"
            "  d.on_sale, d.store_id, d.trophy_group_id, v.console, v.store,"
            "  (SELECT e.comp_main FROM dlc_hltb dh JOIN hltb_entries e ON e.hltb_id = dh.hltb_id"
            "    WHERE dh.dlc_id = d.dlc_id AND dh.source <> 'rejected' LIMIT 1) AS comp_main"
            " FROM dlcs d JOIN versions v ON v.version_id = d.version_id"
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
            " SELECT DISTINCT CAST(json_extract(j.value, '$[1]') AS INTEGER) FROM versions v,"
            "  json_each(v.store_ids) j"
            " WHERE v.game_id = ? AND json_extract(j.value, '$[0]') = 'steam_twin'",
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
                "INSERT OR IGNORE INTO favorite_games (person_id, game_id, anchor_key, created_at)"
                " VALUES (?, ?, ?, ?)",
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
            "WITH fav(appid) AS (SELECT value FROM json_each(?))"
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
