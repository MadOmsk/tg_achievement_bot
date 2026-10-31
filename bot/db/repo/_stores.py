"""The store side of a game (#147, migration 091): versions, their store ids
and DLC, the new HLTB entries, each source's last answer and when to ask it
again."""

from __future__ import annotations

import hashlib
import json
import zlib
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from bot.db.repo._sql import platform_is
from bot.util import looks_russian, utcnow, utcnow_iso


def native_ru(russian: str | None, english: str | None) -> str | None:
    """A store's Russian description, when it is one (#230): Cyrillic, and
    not the English handed back for the Russian request."""
    if not russian or not looks_russian(russian):
        return None
    if english and russian.strip() == english.strip():
        return None
    return russian


if TYPE_CHECKING:
    from bot.services.stores import StoreDlc, StoreVersion
    from bot.services.stores.hltb_page import HltbEntry

# How long an answer is trusted, in days: it doubles while nothing changes
# and falls back to the first step when something does — so a live-service
# game, which keeps changing, keeps being asked about (owner, 2026-10-09).
INTERVALS = (7, 14, 30, 90)
# A failure is retried an hour later; after this many in a row the source is
# given up on for a month.
FAILURES_BEFORE_GIVING_UP = 3
GAVE_UP_DAYS = 30
RETRY_HOURS = 1


def _read_store_ids(raw: object) -> list[tuple[str, str]]:
    """A version's `store_ids` column as `(kind, id)` pairs."""
    try:
        found = json.loads(str(raw or "[]"))
    except ValueError:
        return []
    if not isinstance(found, list):
        return []
    return [(str(k), str(i)) for k, i in found]


class _StoresRepo:
    # ------------------------------------------------------------ fetch state

    async def fetch_due(self, subject: str, source: str) -> bool:
        cursor = await self._conn.execute(
            "SELECT next_check_at FROM fetch_state WHERE subject = ? AND source = ?",
            (subject, source),
        )
        row = await cursor.fetchone()
        return row is None or row["next_check_at"] <= utcnow_iso()

    async def record_fetch(
        self,
        subject: str,
        source: str,
        *,
        status: str,
        changed: bool = False,
        error: str | None = None,
        soon: bool = False,
    ) -> None:
        """What one ask of a source came to. `ok`: the interval steps up
        unless the answer changed (or `soon`: there is more to read, or the
        game just had a patch), which sets it back to the first step.
        `not_found` waits the longest step. A failure is retried in an hour,
        and given up on for a month after three in a row."""
        now = utcnow()
        cursor = await self._conn.execute(
            "SELECT attempts, interval_days FROM fetch_state WHERE subject = ? AND source = ?",
            (subject, source),
        )
        row = await cursor.fetchone()
        attempts = int(row["attempts"]) if row else 0
        interval = int(row["interval_days"]) if row else INTERVALS[0]
        if status == "ok":
            attempts = 0
            if changed or soon or row is None:
                interval = INTERVALS[0]
            else:
                interval = next((step for step in INTERVALS if step > interval), INTERVALS[-1])
            next_check = now + timedelta(days=interval)
            if soon:
                next_check = now + timedelta(hours=RETRY_HOURS)
        elif status == "not_found":
            attempts = 0
            interval = INTERVALS[-1]
            next_check = now + timedelta(days=interval)
        else:
            attempts += 1
            if attempts >= FAILURES_BEFORE_GIVING_UP:
                status = "gave_up"
                next_check = now + timedelta(days=GAVE_UP_DAYS)
            else:
                next_check = now + timedelta(hours=RETRY_HOURS)
        await self._conn.execute(
            "INSERT INTO fetch_state (subject, source, status, attempts, interval_days,"
            "  checked_at, next_check_at, last_error) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(subject, source) DO UPDATE SET status = excluded.status,"
            "  attempts = excluded.attempts, interval_days = excluded.interval_days,"
            "  checked_at = excluded.checked_at, next_check_at = excluded.next_check_at,"
            "  last_error = excluded.last_error",
            (
                subject,
                source,
                status,
                attempts,
                interval,
                now.isoformat(timespec="seconds"),
                next_check.isoformat(timespec="seconds"),
                error,
            ),
        )
        await self._conn.commit()

    # ------------------------------------------------------------ payloads

    async def save_payload(
        self, subject: str, source: str, payload: Any, *, fetched_at: str | None = None
    ) -> bool:
        """Keep a source's answer (compressed, the latest only). True when it
        differs from the one kept — the signal that the game changed.
        `fetched_at`: when it was given, for an answer rewritten later (a
        re-parse keeps its time; otherwise it is now)."""
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        cursor = await self._conn.execute(
            "SELECT sha256 FROM source_payloads WHERE subject = ? AND source = ?",
            (subject, source),
        )
        row = await cursor.fetchone()
        if row is not None and row["sha256"] == digest:
            return False
        await self._conn.execute(
            "INSERT INTO source_payloads (subject, source, fetched_at, sha256, payload)"
            " VALUES (?, ?, ?, ?, ?) ON CONFLICT(subject, source) DO UPDATE SET"
            "  fetched_at = excluded.fetched_at, sha256 = excluded.sha256,"
            "  payload = excluded.payload",
            (
                subject,
                source,
                fetched_at or utcnow_iso(),
                digest,
                zlib.compress(text.encode("utf-8"), 9),
            ),
        )
        await self._conn.commit()
        return row is not None

    async def payload_subjects(self, source: str, prefix: str) -> list[str]:
        """The subjects of one source's kept answers that start so."""
        cursor = await self._conn.execute(
            "SELECT subject FROM source_payloads WHERE source = ? AND subject LIKE ?"
            " ORDER BY subject",
            (source, prefix.replace("%", "") + "%"),
        )
        return [str(row[0]) for row in await cursor.fetchall()]

    async def payload(self, subject: str, source: str) -> Any | None:
        cursor = await self._conn.execute(
            "SELECT payload FROM source_payloads WHERE subject = ? AND source = ?",
            (subject, source),
        )
        row = await cursor.fetchone()
        return json.loads(zlib.decompress(row["payload"]).decode("utf-8")) if row else None

    async def payload_fetched_at(self, subject: str, source: str) -> str | None:
        """When the kept answer was given."""
        cursor = await self._conn.execute(
            "SELECT fetched_at FROM source_payloads WHERE subject = ? AND source = ?",
            (subject, source),
        )
        row = await cursor.fetchone()
        return str(row[0]) if row else None

    # ------------------------------------------------------------ versions

    async def save_version(
        self,
        version: StoreVersion,
        *,
        platform: str | None,
        title_id: str | None,
        origin: str = "played",
        found: tuple[str, str] | None = None,
    ) -> int:
        """Store a version as its store describes it, and every id that names
        it; its achievement list is kept once known, never blanked. `found`
        is how it came here and what found it (migration 116), kept from the
        first time."""
        russian = native_ru(version.description_ru, version.description_en)
        found_how, found_via = found or (None, None)
        now = utcnow_iso()
        if platform and title_id and not version.stand_in:
            # The list's stand-in becomes this product, row and id alike, so
            # what was decided about it (`match_decisions`) stays with it.
            await self._conn.execute(
                "UPDATE versions SET store = ?, product_id = ?, console = ?, stand_in = 0,"
                " found_how = 'played', found_via = ? || ':' || ?, found_at = ?"
                " WHERE version_id = (SELECT version_id FROM versions WHERE platform = ?"
                "  AND title_id = ? AND stand_in = 1 ORDER BY version_id LIMIT 1)"
                " AND NOT EXISTS (SELECT 1 FROM versions WHERE store = ? AND product_id = ?"
                "  AND console = ?)",
                (
                    version.store,
                    version.product_id,
                    version.console,
                    platform,
                    title_id,
                    now,
                    platform,
                    title_id,
                    version.store,
                    version.product_id,
                    version.console,
                ),
            )
        await self._conn.execute(
            "INSERT INTO versions (store, product_id, console, platform, title_id, name, name_ru,"
            "  kind, developer, publisher, release_date, genres, also_on, store_group,"
            "  description_en, description_ru, media, live_service, origin, updated_at, stand_in,"
            "  on_sale, cross_gen_set, found_how, found_via, found_at, description_source)"
            f" VALUES ({', '.join('?' * 27)})"
            " ON CONFLICT(store, product_id, console) DO UPDATE SET"
            # The first list proved stays the version's; another (a
            # regional twin) is kept beside it as an id, never in its place.
            "  platform = COALESCE(versions.platform, excluded.platform),"
            "  title_id = COALESCE(versions.title_id, excluded.title_id),"
            "  name = COALESCE(excluded.name, versions.name),"
            "  name_ru = COALESCE(excluded.name_ru, versions.name_ru),"
            "  kind = COALESCE(excluded.kind, versions.kind),"
            "  developer = COALESCE(excluded.developer, versions.developer),"
            "  publisher = COALESCE(excluded.publisher, versions.publisher),"
            "  release_date = COALESCE(excluded.release_date, versions.release_date),"
            "  genres = excluded.genres, also_on = excluded.also_on,"
            "  store_group = COALESCE(excluded.store_group, versions.store_group),"
            "  description_en = COALESCE(excluded.description_en, versions.description_en),"
            # The store's own Russian replaces anything; with none, our
            # translation stays (#230).
            "  description_ru = COALESCE(excluded.description_ru, versions.description_ru),"
            "  description_source = CASE WHEN excluded.description_ru IS NOT NULL"
            "   THEN 'native' ELSE versions.description_source END,"
            "  description_ru_of = CASE WHEN excluded.description_ru IS NOT NULL"
            "   THEN NULL ELSE versions.description_ru_of END,"
            # Steam's library art comes from a request of its own
            # (`steam_store.library_art`): an answer without it — a re-parse
            # of the kept `appdetails` — keeps what was found.
            "  media = CASE WHEN versions.media IS NULL THEN excluded.media ELSE ("
            "   jsonb_strip_nulls("
            "   jsonb_build_object('poster', versions.media::jsonb->'poster',"
            "    'hero', versions.media::jsonb->'hero'))"
            "   || excluded.media::jsonb)::text END,"
            "  live_service = excluded.live_service,"
            # A version somebody here plays stays `played` once it is.
            "  origin = CASE WHEN versions.origin = 'played' THEN 'played'"
            "   ELSE excluded.origin END,"
            "  updated_at = excluded.updated_at,"
            "  on_sale = COALESCE(excluded.on_sale, versions.on_sale),"
            "  cross_gen_set = COALESCE(excluded.cross_gen_set, versions.cross_gen_set),"
            # How it was found is the first way, never a later look's.
            "  found_how = COALESCE(versions.found_how, excluded.found_how),"
            "  found_via = COALESCE(versions.found_via, excluded.found_via),"
            "  found_at = COALESCE(versions.found_at, excluded.found_at)",
            (
                version.store,
                version.product_id,
                version.console,
                platform,
                title_id,
                version.name,
                version.name_ru,
                version.kind,
                version.developer,
                version.publisher,
                version.release_date,
                json.dumps(version.genres, ensure_ascii=False),
                json.dumps(version.also_on),
                version.store_group,
                version.description_en,
                russian,
                json.dumps(version.media, ensure_ascii=False),
                1 if version.live_service else 0,
                origin,
                now,
                1 if version.stand_in else 0,
                None if version.on_sale is None else int(version.on_sale),
                version.cross_gen_set,
                found_how,
                found_via,
                now if found_how else None,
                "native" if russian else None,
            ),
        )
        cursor = await self._conn.execute(
            "SELECT version_id FROM versions WHERE store = ? AND product_id = ? AND console = ?",
            (version.store, version.product_id, version.console),
        )
        version_id = int((await cursor.fetchone())["version_id"])
        ids = list(version.store_ids)
        if platform and title_id:
            # Every list proved to be this version, the first one included.
            ids.append(("list", f"{platform}:{title_id}"))
        await self.add_store_ids(version_id, ids)
        await self._conn.commit()
        return version_id

    async def store_ids_of(self, version_id: int) -> list[tuple[str, str]]:
        """Every id naming a version, `(kind, id)`, in the order they came."""
        cursor = await self._conn.execute(
            "SELECT store_ids FROM versions WHERE version_id = ?", (version_id,)
        )
        row = await cursor.fetchone()
        return _read_store_ids(row[0] if row else None)

    async def add_store_ids(self, version_id: int, ids: list[tuple[str, str]]) -> None:
        """These ids joined to the version's own, each once. No commit."""
        known = await self.store_ids_of(version_id)
        merged = list(dict.fromkeys([*known, *ids]))
        if merged != known:
            await self._conn.execute(
                "UPDATE versions SET store_ids = ? WHERE version_id = ?",
                (json.dumps(merged), version_id),
            )

    async def versions_of_title(self, platform: str, title_id: str) -> list[dict[str, Any]]:
        cursor = await self._conn.execute(
            "SELECT * FROM versions WHERE platform = ? AND title_id = ? ORDER BY console",
            (platform, title_id),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def store_ids_of_title(self, platform: str, title_id: str, store: str) -> list[str]:
        """The ids of one kind (`psn_title`, …) its versions are known by."""
        cursor = await self._conn.execute(
            "SELECT store_ids FROM versions WHERE platform = ? AND title_id = ?",
            (platform, title_id),
        )
        found = [
            sid
            for row in await cursor.fetchall()
            for kind, sid in _read_store_ids(row[0])
            if kind == store
        ]
        return list(dict.fromkeys(found))

    async def psn_holder_of(self, np_communication_id: str) -> str | None:
        """A PSN account somebody holds that earned something in this trophy
        list — Sony answers about a store title only to an account that has
        it."""
        cursor = await self._conn.execute(
            "SELECT s.xuid FROM seen_achievements s"
            " JOIN account_links al ON al.platform = 'psn' AND al.external_id = s.xuid"
            "  AND al.is_active = 1"
            " WHERE s.platform = 'psn' AND s.title_id = ? LIMIT 1",
            (np_communication_id,),
        )
        row = await cursor.fetchone()
        return str(row[0]) if row else None

    # ------------------------------------------------------------ DLC

    async def dlc_ids_named(self, version_id: int) -> set[str]:
        cursor = await self._conn.execute(
            "SELECT store_id FROM dlcs WHERE version_id = ? AND store_id IS NOT NULL"
            " AND name IS NOT NULL",
            (version_id,),
        )
        return {str(row[0]) for row in await cursor.fetchall()}

    async def save_dlc(self, version_id: int, dlc: StoreDlc) -> None:
        await self._conn.execute(
            "INSERT INTO dlcs (version_id, store_id, name, kind, release_date, description_en,"
            "  image_url, updated_at, on_sale) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(version_id, store_id) WHERE store_id IS NOT NULL DO UPDATE SET"
            "  name = COALESCE(excluded.name, dlcs.name),"
            "  kind = COALESCE(excluded.kind, dlcs.kind),"
            "  release_date = COALESCE(excluded.release_date, dlcs.release_date),"
            "  description_en = COALESCE(excluded.description_en, dlcs.description_en),"
            "  image_url = COALESCE(excluded.image_url, dlcs.image_url),"
            "  updated_at = excluded.updated_at,"
            "  on_sale = COALESCE(excluded.on_sale, dlcs.on_sale)",
            (
                version_id,
                dlc.store_id,
                dlc.name,
                dlc.kind,
                dlc.release_date,
                dlc.description_en,
                dlc.image_url,
                utcnow_iso(),
                None if dlc.on_sale is None else int(dlc.on_sale),
            ),
        )
        await self._conn.commit()

    async def psn_concept_versions(
        self, origin: str | None = None
    ) -> dict[str, list[tuple[int, str]]]:
        """`{concept id: [(version id, console)]}` of the PlayStation versions
        a store concept names; only those of this `origin` when it is given
        (`played`: a list somebody here has)."""
        cursor = await self._conn.execute(
            "SELECT version_id, console, store_ids FROM versions WHERE store = 'psn'"
            + (" AND origin = ?" if origin else ""),
            (origin,) if origin else (),
        )
        found: dict[str, list[tuple[int, str]]] = {}
        for row in await cursor.fetchall():
            for kind, concept_id in json.loads(row["store_ids"] or "[]"):
                if kind == "psn_concept":
                    found.setdefault(str(concept_id), []).append(
                        (int(row["version_id"]), str(row["console"]))
                    )
        return found

    async def delete_dlcs(self, version_id: int, store_ids: list[str]) -> None:
        """These add-ons are not this version's (another game's, an edition
        of several bundled): their rows here go, with their HLTB links."""
        if not store_ids:
            return
        marks = ",".join("?" * len(store_ids))
        async with self.transaction():
            await self._conn.execute(
                "DELETE FROM dlc_hltb WHERE dlc_id IN (SELECT dlc_id FROM dlcs"
                f" WHERE version_id = ? AND store_id IN ({marks}))",
                (version_id, *store_ids),
            )
            await self._conn.execute(
                f"DELETE FROM dlcs WHERE version_id = ? AND store_id IN ({marks})",
                (version_id, *store_ids),
            )

    async def save_trophy_group_dlcs(self, version_id: int, np_communication_id: str) -> int:
        """A PSN version's DLC with trophies of their own: its trophy groups
        past the base game (`title_groups`, already stored)."""
        cursor = await self._conn.execute(
            "SELECT group_id, name, name_ru FROM title_groups"
            " WHERE title_id = ? AND group_id <> 'default'",
            (np_communication_id,),
        )
        groups = await cursor.fetchall()
        for group in groups:
            await self._conn.execute(
                "INSERT INTO dlcs (version_id, trophy_group_id, name, name_ru, kind, updated_at)"
                " VALUES (?, ?, ?, ?, 'dlc', ?)"
                " ON CONFLICT(version_id, trophy_group_id) WHERE trophy_group_id IS NOT NULL"
                " DO UPDATE SET name = excluded.name, name_ru = excluded.name_ru,"
                "  updated_at = excluded.updated_at",
                (version_id, group["group_id"], group["name"], group["name_ru"], utcnow_iso()),
            )
        await self._conn.commit()
        return len(groups)

    # ------------------------------------------------------------ HLTB

    async def save_hltb_page(self, entry: HltbEntry) -> None:
        """An entry from its own page — every field, its platform rows, its
        groups of platforms, its platforms, its users' scores, the entries it
        names — and the entries its page names (its additional content, or on
        a DLC's page its game) as far as that page tells. An entry's own page
        is the only one that sets its type, parent and hours (`page_read_at`):
        another page's row of it — a game's on its DLC's page, with averages
        only — fills an entry no page of its own was read for, and never
        overwrites one (2026-10-12: four games' times were the averages their
        DLC's page listed)."""
        now = utcnow_iso()
        row = {k: v for k, v in entry.row.items() if k != "hltb_id"}
        columns = ["hltb_id", *row, "checked_at", "page_read_at"]
        async with self.transaction():
            # A translation made before `summary_ru_of` knew its English text is
            # of the text that was there: a changed summary is translated again.
            from bot.services.stores.hltb_page import summary_hash

            cursor = await self._conn.execute(
                "SELECT summary_en FROM hltb_entries WHERE hltb_id = ?"
                " AND summary_ru IS NOT NULL AND summary_ru_of IS NULL",
                (entry.hltb_id,),
            )
            old = await cursor.fetchone()
            if old is not None and old[0]:
                await self._conn.execute(
                    "UPDATE hltb_entries SET summary_ru_of = ? WHERE hltb_id = ?",
                    (summary_hash(old[0]), entry.hltb_id),
                )
            await self._conn.execute(
                f"INSERT INTO hltb_entries ({', '.join(columns)})"
                f" VALUES ({', '.join('?' * len(columns))})"
                " ON CONFLICT(hltb_id) DO UPDATE SET "
                + ", ".join(f"{c} = excluded.{c}" for c in columns[1:]),
                (entry.hltb_id, *row.values(), now, now),
            )
            for table in (
                "hltb_platform_times",
                "hltb_platform_groups",
                "hltb_entry_platforms",
                "hltb_review_scores",
                "hltb_related",
            ):
                await self._conn.execute(f"DELETE FROM {table} WHERE hltb_id = ?", (entry.hltb_id,))
            await self._conn.executemany(
                "INSERT INTO hltb_platform_times (hltb_id, platform, comp_main,"
                " comp_plus, comp_100, comp_low, comp_high, count_comp, count_total)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT (hltb_id, platform) DO UPDATE SET comp_main = excluded.comp_main, "
                "comp_plus = excluded.comp_plus, comp_100 = excluded.comp_100, comp_low = "
                "excluded.comp_low, comp_high = excluded.comp_high, count_comp = "
                "excluded.count_comp, count_total = excluded.count_total",
                [
                    (
                        entry.hltb_id,
                        r["platform"],
                        r["comp_main"],
                        r["comp_plus"],
                        r["comp_100"],
                        r["comp_low"],
                        r["comp_high"],
                        r["count_comp"],
                        r["count_total"],
                    )
                    for r in entry.platform_rows
                ],
            )
            await self._conn.executemany(
                "INSERT INTO hltb_platform_groups (hltb_id, platforms, comp_main,"
                " comp_plus, comp_100, comp_all, compare, count_comp)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT (hltb_id, platforms) DO UPDATE SET comp_main = excluded.comp_main, "
                "comp_plus = excluded.comp_plus, comp_100 = excluded.comp_100, comp_all = "
                "excluded.comp_all, compare = excluded.compare, count_comp = excluded.count_comp",
                [
                    (
                        entry.hltb_id,
                        g["platforms"],
                        g["comp_main"],
                        g["comp_plus"],
                        g["comp_100"],
                        g["comp_all"],
                        g["compare"],
                        g["count_comp"],
                    )
                    for g in entry.groups
                ],
            )
            await self._conn.executemany(
                "INSERT INTO hltb_entry_platforms (hltb_id, platform) VALUES (?, ?)"
                " ON CONFLICT DO NOTHING",
                [(entry.hltb_id, p) for p in entry.platforms],
            )
            await self._conn.executemany(
                "INSERT INTO hltb_review_scores (hltb_id, score, votes)"
                " VALUES (?, ?, ?)"
                " ON CONFLICT (hltb_id, score) DO UPDATE SET votes = excluded.votes",
                [(entry.hltb_id, score, votes) for score, votes in entry.reviews.items()],
            )
            await self._conn.executemany(
                "INSERT INTO hltb_related (hltb_id, related_id) VALUES (?, ?)"
                " ON CONFLICT DO NOTHING",
                [(entry.hltb_id, item.hltb_id) for item in entry.others],
            )
            unread = "hltb_entries.page_read_at IS NULL"
            stats = (
                "comp_main",
                "comp_plus",
                "comp_100",
                "comp_all",
                "comp_all_count",
                "count_backlog",
                "review_score",
            )
            for item in [*entry.children, *entry.others, *([entry.parent] if entry.parent else [])]:
                await self._conn.execute(
                    "INSERT INTO hltb_entries (hltb_id, name, game_type, parent_hltb_id,"
                    f"  {', '.join(stats)}, checked_at)"
                    f" VALUES (?, ?, ?, ?, {', '.join('?' * len(stats))}, ?)"
                    " ON CONFLICT(hltb_id) DO UPDATE SET"
                    f"  name = CASE WHEN {unread} THEN excluded.name ELSE hltb_entries.name END,"
                    f"  game_type = CASE WHEN {unread}"
                    "   THEN COALESCE(excluded.game_type, hltb_entries.game_type)"
                    "   ELSE hltb_entries.game_type END,"
                    # A child's parent is this page; the parent's own parent is
                    # not this page's to say, but its having been taken for this
                    # page's child (the old reading) is undone.
                    f"  parent_hltb_id = CASE WHEN NOT ({unread}) THEN hltb_entries.parent_hltb_id"
                    "   WHEN excluded.parent_hltb_id IS NOT NULL THEN excluded.parent_hltb_id"
                    "   WHEN hltb_entries.parent_hltb_id = ? THEN NULL"
                    "   ELSE hltb_entries.parent_hltb_id END,"
                    + ", ".join(
                        f" {c} = CASE WHEN {unread} THEN excluded.{c} ELSE hltb_entries.{c} END"
                        for c in stats
                    )
                    + f", checked_at = CASE WHEN {unread} THEN excluded.checked_at"
                    "   ELSE hltb_entries.checked_at END",
                    (
                        item.hltb_id,
                        item.name,
                        item.game_type,
                        item.parent_hltb_id,
                        *(item.row.get(c) for c in stats),
                        now,
                        entry.hltb_id,
                    ),
                )

    async def hltb_pages_to_read(self, limit: int | None = None) -> list[int]:
        """The entries whose own page was never read and that something of ours
        reaches: linked to one of our versions or DLC, or additional content of an
        entry linked to a version (the DLC of a game we have). The pages a full
        poll reads (`scripts/poll_hltb.py`)."""
        cursor = await self._conn.execute(
            "SELECT e.hltb_id FROM hltb_entries e WHERE e.page_read_at IS NULL AND ("
            " e.hltb_id IN (SELECT hltb_id FROM version_hltb WHERE source <> 'rejected')"
            " OR e.hltb_id IN (SELECT hltb_id FROM dlc_hltb WHERE source <> 'rejected')"
            " OR e.parent_hltb_id IN (SELECT hltb_id FROM version_hltb"
            "  WHERE source <> 'rejected'))"
            # A link to an entry nothing read yet has no row at all (a database
            # that has the links and not the mirror, as production first does).
            " UNION SELECT hltb_id FROM version_hltb WHERE source <> 'rejected'"
            "  AND hltb_id NOT IN (SELECT hltb_id FROM hltb_entries)"
            " UNION SELECT hltb_id FROM dlc_hltb WHERE source <> 'rejected'"
            "  AND hltb_id NOT IN (SELECT hltb_id FROM hltb_entries)"
            " ORDER BY 1" + (f" LIMIT {int(limit)}" if limit else "")
        )
        return [int(r[0]) for r in await cursor.fetchall()]

    async def hltb_game_row(self, hltb_id: int) -> dict | None:
        cursor = await self._conn.execute(
            "SELECT * FROM hltb_entries WHERE hltb_id = ?", (hltb_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def unnamed_lists(self, platforms: tuple[str, ...]) -> list[tuple[str, str]]:
        """`(platform, title_id)` of the lists whose name was never learned:
        none, "?", or the id itself."""
        marks = ",".join("?" * len(platforms))
        cursor = await self._conn.execute(
            "SELECT platform, title_id FROM achievement_list_connectors"
            f" WHERE platform IN ({marks}) AND (name IS NULL OR name = '' OR name = '?'"
            "  OR name = title_id) ORDER BY platform, title_id",
            platforms,
        )
        return [(str(r[0]), str(r[1])) for r in await cursor.fetchall()]

    async def name_list(self, platform: str, title_id: str, name: str) -> None:
        """A name for a list that had none (the stand-ins follow, 117's
        trigger); a list with a name of its own keeps it."""
        await self._conn.execute(
            "UPDATE achievement_list_connectors SET name = ?,"
            " name_en = COALESCE(name_en, ?) WHERE platform = ? AND title_id = ?"
            " AND (name IS NULL OR name = '' OR name = '?' OR name = title_id)",
            (name, name, platform, title_id),
        )
        await self._conn.commit()

    async def psn_account_with_title(self, np_communication_id: str) -> str | None:
        """A PSN account that has earned something in this list."""
        cursor = await self._conn.execute(
            "SELECT xuid FROM seen_achievements WHERE platform = 'psn' AND title_id = ?"
            " GROUP BY xuid ORDER BY COUNT(*) DESC LIMIT 1",
            (np_communication_id,),
        )
        row = await cursor.fetchone()
        return str(row[0]) if row else None

    async def lists_without_whole_list(self, platform: str) -> list[str]:
        """The lists of a platform whose whole list of achievements was never
        read (no `listed` row in the catalog)."""
        cursor = await self._conn.execute(
            "SELECT t.title_id FROM achievement_list_connectors t WHERE t.platform = ?"
            " AND NOT EXISTS (SELECT 1 FROM title_achievements a WHERE a.platform = t.platform"
            "  AND a.title_id = t.title_id AND a.listed = 1) ORDER BY t.title_id",
            (platform,),
        )
        return [str(r[0]) for r in await cursor.fetchall()]

    async def achievement_list_ids(self, platform: str) -> list[str]:
        """Every achievement list of a platform, by id."""
        cursor = await self._conn.execute(
            "SELECT title_id FROM achievement_list_connectors WHERE platform = ? ORDER BY title_id",
            (platform,),
        )
        return [str(r[0]) for r in await cursor.fetchall()]

    async def stand_in_lists(self, platform: str) -> list[str]:
        """The achievement lists of a platform that only stand in for
        themselves: no store product describes them yet."""
        cursor = await self._conn.execute(
            "SELECT DISTINCT title_id FROM versions WHERE platform = ? AND stand_in = 1"
            " AND title_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM versions o"
            "  WHERE o.platform = versions.platform AND o.title_id = versions.title_id"
            "  AND o.stand_in = 0) ORDER BY title_id",
            (platform,),
        )
        return [str(r[0]) for r in await cursor.fetchall()]

    async def hltb_spread_rows(self, game_ids: list[int] | None = None) -> list[dict[str, Any]]:
        """Every version of these games (all games: None) with its HLTB links
        (refusals included) and, per linked entry, the platforms HLTB lists
        for it — what `game_link.spread_hltb` decides from."""
        where = ""
        args: tuple = ()
        if game_ids is not None:
            if not game_ids:
                return []
            where = f" AND v.game_id IN ({','.join('?' * len(game_ids))})"
            args = tuple(game_ids)
        cursor = await self._conn.execute(
            "SELECT v.version_id, v.game_id, v.console, v.store, v.kind, v.role, v.name,"
            " v.name_ru, vh.hltb_id, vh.source, vh.score, e.game_type,"
            " (SELECT string_agg(platform, '|') FROM ("
            "   SELECT platform FROM hltb_entry_platforms p WHERE p.hltb_id = vh.hltb_id"
            "   UNION SELECT platform FROM hltb_platform_times t WHERE t.hltb_id = vh.hltb_id"
            " ) AS named) AS entry_platforms"
            " FROM versions v LEFT JOIN version_hltb vh ON vh.version_id = v.version_id"
            " LEFT JOIN hltb_entries e ON e.hltb_id = vh.hltb_id"
            f" WHERE v.game_id IS NOT NULL{where} ORDER BY v.game_id, v.version_id",
            args,
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def steam_versions_with_hltb_by_app(self) -> list[dict[str, Any]]:
        """Steam versions with no HLTB link at all (not even a refusal) beside
        every entry whose page names their app: `steam_appid` first, `steam_alt`
        second. The entry's own page is the evidence."""
        cursor = await self._conn.execute(
            "SELECT v.version_id, v.product_id, v.kind, v.role, v.name, v.name_ru,"
            " v.release_date, h.hltb_id, h.name AS entry_name, h.game_type, h.release_year,"
            " (h.steam_appid = CAST(v.product_id AS INTEGER)) AS is_main_app"
            " FROM versions v JOIN hltb_entries h"
            "  ON h.steam_appid = CAST(v.product_id AS INTEGER)"
            "  OR h.steam_alt = CAST(v.product_id AS INTEGER)"
            " WHERE v.store = 'steam' AND NOT EXISTS (SELECT 1 FROM version_hltb x"
            "  WHERE x.version_id = v.version_id)"
            " ORDER BY v.version_id, is_main_app DESC, h.hltb_id"
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def hltb_children(self, hltb_id: int) -> list[dict[str, Any]]:
        """An HLTB game's DLC and expansions as stored (its page's relations,
        their own pages where read)."""
        cursor = await self._conn.execute(
            "SELECT hltb_id, name, steam_appid, game_type FROM hltb_entries"
            " WHERE parent_hltb_id = ? ORDER BY hltb_id",
            (hltb_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def dlcs_under_hltb(self, hltb_id: int) -> list[dict[str, Any]]:
        """Our DLC of every version this HLTB entry stands for, with their
        version's store and name."""
        cursor = await self._conn.execute(
            "SELECT d.dlc_id, v.store, d.store_id, d.name, v.name AS version_name"
            " FROM version_hltb vh JOIN versions v ON v.version_id = vh.version_id"
            " JOIN dlcs d ON d.version_id = v.version_id WHERE vh.hltb_id = ?"
            " AND vh.source <> 'rejected' ORDER BY d.dlc_id",
            (hltb_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def replace_dlc_hltb(self, dlc_ids: list[int], links: dict[int, int]) -> None:
        """These DLC's automatic HLTB links, rewritten; the operator's stay."""
        async with self.transaction():
            for start in range(0, len(dlc_ids), 400):
                batch = dlc_ids[start : start + 400]
                marks = ",".join("?" * len(batch))
                await self._conn.execute(
                    f"DELETE FROM dlc_hltb WHERE source = 'auto' AND dlc_id IN ({marks})", batch
                )
            await self._conn.executemany(
                "INSERT INTO dlc_hltb (dlc_id, hltb_id, source) VALUES (?, ?, 'auto')"
                " ON CONFLICT DO NOTHING",
                sorted(links.items()),
            )

    async def link_dlc_hltb(self, dlc_id: int, hltb_id: int) -> None:
        """The operator's (or the advisers') word that this DLC is this HLTB
        entry: kept through every check, replacing a refusal."""
        await self._conn.execute(
            "INSERT INTO dlc_hltb (dlc_id, hltb_id, source) VALUES (?, ?, 'manual')"
            " ON CONFLICT(dlc_id, hltb_id) DO UPDATE SET source = 'manual'",
            (dlc_id, hltb_id),
        )
        await self._conn.commit()

    async def set_edition_kind(self, edition_id: int, kind: str) -> None:
        await self._conn.execute(
            "UPDATE editions SET kind = ? WHERE edition_id = ?", (kind, edition_id)
        )
        await self._conn.commit()

    async def detach_edition_from_game(self, edition_id: int, game_id: int) -> int:
        """An edition said not to hold this game: its items stop pointing at
        the game's versions. The number of items let go."""
        cursor = await self._conn.execute(
            "UPDATE edition_items SET version_id = NULL WHERE edition_id = ?"
            " AND version_id IN (SELECT version_id FROM versions WHERE game_id = ?)",
            (edition_id, game_id),
        )
        await self._conn.commit()
        return cursor.rowcount

    async def link_trophy_group_to_addon(
        self, version_id: int, group_id: str, store_id: str
    ) -> bool:
        """A PSN trophy group is the store add-on that brings it: the add-on's
        DLC row takes the group, the group's own stand-in row goes. False when
        the add-on is not a DLC of that version."""
        async with self.transaction():
            cursor = await self._conn.execute(
                # The advisers' answers come lower-cased (compare_answers._norm).
                "SELECT dlc_id FROM dlcs WHERE version_id = ? AND upper(store_id) = upper(?)",
                (version_id, store_id),
            )
            row = await cursor.fetchone()
            if row is None:
                return False
            await self._conn.execute(
                "DELETE FROM dlcs WHERE version_id = ? AND trophy_group_id = ?"
                " AND store_id IS NULL",
                (version_id, group_id),
            )
            await self._conn.execute(
                "UPDATE dlcs SET trophy_group_id = ? WHERE dlc_id = ?", (group_id, row[0])
            )
        return True

    async def restore_version_hltb(self, version_id: int, hltb_id: int) -> None:
        """A refused link the advisers all say is right after all: an
        automatic link again (an operator's refusal is not touched by callers)."""
        await self._conn.execute(
            "UPDATE version_hltb SET source = 'auto', score = 0.9"
            " WHERE version_id = ? AND hltb_id = ? AND source = 'rejected'",
            (version_id, hltb_id),
        )
        await self._conn.commit()

    async def reject_dlc_hltb(self, dlc_id: int, hltb_id: int) -> None:
        """This DLC is not this HLTB entry: kept as a refusal (`rejected`), so
        the matcher never makes the link again."""
        await self._conn.execute(
            "INSERT INTO dlc_hltb (dlc_id, hltb_id, source) VALUES (?, ?, 'rejected')"
            " ON CONFLICT(dlc_id, hltb_id) DO UPDATE SET source = 'rejected'",
            (dlc_id, hltb_id),
        )
        await self._conn.commit()

    async def versions_of_hltb(self, hltb_id: int) -> list[dict[str, Any]]:
        cursor = await self._conn.execute(
            "SELECT v.*, vh.source AS link_source FROM version_hltb vh"
            " JOIN versions v ON v.version_id = vh.version_id WHERE vh.hltb_id = ?"
            " AND vh.source <> 'rejected'",
            (hltb_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def link_version_hltb(
        self, version_id: int, hltb_id: int, source: str = "auto", score: float | None = None
    ) -> None:
        """An automatic link never replaces a link already there (the
        operator's, or a refusal); the operator's own replaces whatever
        there is, a refusal too."""
        if source == "manual":
            await self._conn.execute(
                "INSERT INTO version_hltb (version_id, hltb_id, source, score)"
                " VALUES (?, ?, 'manual', NULL) ON CONFLICT(version_id, hltb_id)"
                " DO UPDATE SET source = 'manual', score = NULL",
                (version_id, hltb_id),
            )
        else:
            await self._conn.execute(
                "INSERT INTO version_hltb (version_id, hltb_id, source, score)"
                " VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING",
                (version_id, hltb_id, source, score),
            )
        await self._conn.commit()

    async def list_hltb_match(
        self, platform: str, title_id: str
    ) -> tuple[int, float | None] | None:
        """The HowLongToBeat entry an achievement list is (owner, 2026-10-14:
        one home, the links of its versions): the operator's link before an
        automatic one, then the surer match, then the lower id. None when it
        has none — not matched yet, none found, or every link refused."""
        versions = await self.versions_of_list(platform, title_id)
        if not versions:
            return None
        marks = ",".join("?" * len(versions))
        cursor = await self._conn.execute(
            "SELECT vh.hltb_id, vh.score FROM version_hltb vh"
            f" WHERE vh.version_id IN ({marks}) AND vh.source <> 'rejected'"
            " ORDER BY vh.source = 'manual' DESC, vh.score IS NULL, vh.score DESC, vh.hltb_id"
            " LIMIT 1",
            versions,
        )
        row = await cursor.fetchone()
        return (int(row["hltb_id"]), row["score"]) if row else None

    async def versions_of_list(self, platform: str, title_id: str) -> list[int]:
        """The versions an achievement list is of: those whose list it is, and
        those that carry it as a regional twin (a second list of one product,
        kept beside the first in `store_ids`). An Xbox list matches either
        generation, as everywhere."""
        where, params = platform_is(platform, "v.platform")
        values = ("xbox_modern", "xbox_360") if not params else (platform,)
        twins = " OR ".join("v.store_ids LIKE ?" for _ in values)
        cursor = await self._conn.execute(
            f"SELECT v.version_id FROM versions v WHERE ({where} AND v.title_id = ?) OR {twins}"
            " ORDER BY v.version_id",
            (*params, title_id, *(f'%"{p}:{title_id}"%' for p in values)),
        )
        return [int(row[0]) for row in await cursor.fetchall()]

    async def title_hltb_id(self, platform: str, title_id: str) -> int | None:
        match = await self.list_hltb_match(platform, title_id)
        return match[0] if match else None

    async def ensure_list_version(self, platform: str, title_id: str) -> list[int]:
        """The versions of an achievement list; every list is at least one,
        so when it has none a stand-in is made from the list itself."""
        found = await self.versions_of_list(platform, title_id)
        if found:
            return found
        record = await self.title_record(platform, title_id)
        if not record:
            return []
        from bot.services.stores import stand_in_for

        stand_in = stand_in_for(record)
        # A product that is already a version (this list is its second, as
        # a regional twin is) takes the list as an id, never as a rewrite.
        cursor = await self._conn.execute(
            "SELECT version_id FROM versions WHERE store = ? AND product_id = ? AND console = ?",
            (stand_in.store, stand_in.product_id, stand_in.console),
        )
        row = await cursor.fetchone()
        if row is not None:
            await self.add_store_ids(int(row[0]), [("list", f"{platform}:{title_id}")])
            await self._conn.commit()
            return [int(row[0])]
        version_id = await self.save_version(
            stand_in,
            platform=platform,
            title_id=title_id,
            found=("list", f"{platform}:{title_id}"),
        )
        if platform == "psn":
            await self.save_trophy_group_dlcs(version_id, title_id)
        return [version_id]

    async def record_hltb_match(
        self,
        platform: str,
        title_id: str,
        hltb_id: int | None,
        score: float | None,
        entry_name: str | None = None,
    ) -> None:
        """What one match attempt found: an automatic link on each version of
        the list (not where it was refused). A miss, or an entry refused
        everywhere, counts as a failed attempt — after the third the list
        leaves the queue (`record_fetch`)."""
        from bot.services.game_match import is_part

        subject = f"{platform}:{title_id}"
        if hltb_id is not None:
            for version_id in await self.ensure_list_version(platform, title_id):
                row = await self.version_row(version_id)
                if (
                    row is not None
                    and is_part(row["kind"], row["role"], [row["name"] or ""])
                    and not is_part(None, None, [entry_name or ""])
                ):
                    continue  # a demo, a beta, a tool: no entry of its own, unless the entry is
                await self.link_version_hltb(version_id, hltb_id, "auto", score)
            if await self.list_hltb_match(platform, title_id) is not None:
                await self.record_fetch(subject, "hltb_match", status="ok")
                return
        await self.record_fetch(subject, "hltb_match", status="error", error="no match")

    async def give_up_hltb_match(self, platform: str, title_id: str) -> None:
        """A name not worth even searching (a platform's own placeholder, or
        nothing Latin in it): not asked again for the longest step."""
        await self.record_fetch(f"{platform}:{title_id}", "hltb_match", status="not_found")

    async def steam_app_patched_since(self, appid: int, since: str) -> bool:
        cursor = await self._conn.execute(
            "SELECT 1 FROM game_patches WHERE steam_appid = ? AND published_at >= ? LIMIT 1",
            (appid, since),
        )
        return await cursor.fetchone() is not None

    # ------------------------------------------------------------ by hand (the viewer)

    async def make_fetch_due(self, subject: str, source: str) -> None:
        """Ask this source again at the next chance, whatever the schedule said."""
        await self._conn.execute(
            "UPDATE fetch_state SET next_check_at = ? WHERE subject = ? AND source = ?",
            (utcnow_iso(), subject, source),
        )
        await self._conn.commit()

    async def unlink_version_hltb(
        self, version_id: int, hltb_id: int, *, only_auto: bool = False
    ) -> None:
        """The version is not this entry: the link is kept as a refusal
        (`rejected`), so nothing makes it again. `only_auto`: only an
        automatic link (the evidence says no), never the operator's."""
        if only_auto:
            await self._conn.execute(
                "UPDATE version_hltb SET source = 'rejected', score = NULL"
                " WHERE version_id = ? AND hltb_id = ? AND source = 'auto'",
                (version_id, hltb_id),
            )
            await self._conn.commit()
            return
        await self._conn.execute(
            "INSERT INTO version_hltb (version_id, hltb_id, source, score)"
            " VALUES (?, ?, 'rejected', NULL) ON CONFLICT(version_id, hltb_id)"
            " DO UPDATE SET source = 'rejected', score = NULL",
            (version_id, hltb_id),
        )
        await self._conn.commit()

    async def set_version_title(
        self, version_id: int, platform: str | None, title_id: str | None
    ) -> None:
        """Which achievement list a version has, set by hand (or cleared)."""
        await self._conn.execute(
            "UPDATE versions SET platform = ?, title_id = ?, updated_at = ? WHERE version_id = ?",
            (platform, title_id, utcnow_iso(), version_id),
        )
        await self._conn.commit()

    async def delete_version(self, version_id: int) -> None:
        """A version that is not one (a bundle taken for a game, a wrong
        match): its DLC, store ids and HLTB links go with it."""
        async with self.transaction():
            for table in ("dlc_hltb", "dlcs", "version_hltb", "versions"):
                if table == "dlc_hltb":
                    await self._conn.execute(
                        "DELETE FROM dlc_hltb WHERE dlc_id IN"
                        " (SELECT dlc_id FROM dlcs WHERE version_id = ?)",
                        (version_id,),
                    )
                else:
                    await self._conn.execute(
                        f"DELETE FROM {table} WHERE version_id = ?",
                        (version_id,),
                    )

    async def retire_other_consoles(
        self, store: str, product_id: str, keep: list[int]
    ) -> list[int]:
        """A product's versions on consoles its store no longer makes it a
        version on (a One game's phantom "Series" version, 2026-10-12): each
        goes into the first kept one — what was decided about it (labels, a
        game's anchor), its store ids, HLTB links and edition places move
        there, as it was the same product all along — and is deleted."""
        if not keep:
            return []
        into = keep[0]
        cursor = await self._conn.execute(
            "SELECT version_id FROM versions WHERE store = ? AND product_id = ? AND stand_in = 0",
            (store, product_id),
        )
        stale = [int(r[0]) for r in await cursor.fetchall() if int(r[0]) not in keep]
        for old in stale:
            async with self.transaction():
                # A label about the old one is about the product: kept, unless
                # the kept version already has one with that other version.
                for column, other in (("version_id", "other_id"), ("other_id", "version_id")):
                    await self._conn.execute(
                        f"UPDATE match_decisions SET {column} = ?"
                        f" WHERE {column} = ? AND {other} <> ?"
                        " AND NOT EXISTS (SELECT 1 FROM match_decisions o"
                        f"  WHERE o.{column} = ? AND o.{other} = match_decisions.{other})",
                        (into, old, into, into),
                    )
                await self._conn.execute(
                    "UPDATE games SET anchor_version_id = ? WHERE anchor_version_id = ?"
                    " AND NOT EXISTS (SELECT 1 FROM games WHERE anchor_version_id = ?)",
                    (into, old, into),
                )
                await self.add_store_ids(into, await self.store_ids_of(old))
                await self._conn.execute(
                    "INSERT INTO version_hltb (version_id, hltb_id, source)"
                    " SELECT ?, hltb_id, source FROM version_hltb WHERE version_id = ?"
                    " ON CONFLICT DO NOTHING",
                    (into, old),
                )
                await self._conn.execute(
                    "UPDATE edition_items SET version_id = ? WHERE version_id = ?", (into, old)
                )
                await self.delete_version(old)
        return stale

    # ------------------------------------------------------------ editions (094)

    async def save_edition(
        self,
        store: str,
        store_id: str,
        name: str | None,
        kind: str | None,
        on_sale: bool | None = None,
        media: dict | None = None,
        scope: str | None = None,
    ) -> int:
        """An edition seen on its store now: kept, its last sighting stamped;
        its pictures (`services/edition_media`) when the answer had any.
        `scope` is what it is by its contents (`stores.classify_bundle`);
        None keeps what it was (a new one is an edition)."""
        now = utcnow_iso()
        await self._conn.execute(
            "INSERT INTO editions (store, store_id, name, kind, first_seen_at, last_seen_at,"
            " on_sale, media, scope) VALUES (?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, 'edition'))"
            " ON CONFLICT(store, store_id) DO UPDATE SET"
            "  name = COALESCE(excluded.name, editions.name),"
            "  kind = COALESCE(excluded.kind, editions.kind), last_seen_at = excluded.last_seen_at,"
            "  on_sale = COALESCE(excluded.on_sale, editions.on_sale),"
            "  media = COALESCE(excluded.media, editions.media),"
            "  scope = COALESCE(?, editions.scope)",
            (
                store,
                store_id,
                name,
                kind,
                now,
                now,
                None if on_sale is None else int(on_sale),
                json.dumps(media, ensure_ascii=False) if media else None,
                scope,
                scope,
            ),
        )
        cursor = await self._conn.execute(
            "SELECT edition_id FROM editions WHERE store = ? AND store_id = ?", (store, store_id)
        )
        edition_id = int((await cursor.fetchone())["edition_id"])
        await self._conn.commit()
        return edition_id

    async def set_edition_media(self, store: str, store_id: str, media: dict) -> bool:
        """An edition's pictures read again from a kept answer. True when it
        is one of ours."""
        cursor = await self._conn.execute(
            "UPDATE editions SET media = ? WHERE store = ? AND store_id = ?",
            (json.dumps(media, ensure_ascii=False) if media else None, store, store_id),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    async def edition_ids(self, store: str) -> set[str]:
        cursor = await self._conn.execute("SELECT store_id FROM editions WHERE store = ?", (store,))
        return {str(r[0]) for r in await cursor.fetchall()}

    async def edition_covers_to_fetch(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Editions with pictures and no cover on disk, never asked before."""
        cursor = await self._conn.execute(
            "SELECT edition_id, store, store_id, media FROM editions"
            " WHERE media IS NOT NULL AND image_path IS NULL AND image_checked_at IS NULL"
            " ORDER BY edition_id" + (f" LIMIT {int(limit)}" if limit else "")
        )
        return [dict(r) for r in await cursor.fetchall()]

    async def set_edition_cover(
        self, edition_id: int, path: str | None, digest: str | None
    ) -> None:
        """One visit's answer, stamped found or not."""
        await self._conn.execute(
            "UPDATE editions SET image_path = ?, image_hash = ?,"
            " image_checked_at = to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD\"T\"HH24:MI:SS')"
            " WHERE edition_id = ?",
            (path, digest, edition_id),
        )
        await self._conn.commit()

    async def save_edition_item(
        self,
        edition_id: int,
        store_id: str,
        name: str | None,
        item_kind: str,
        *,
        is_primary: bool = False,
        version_id: int | None = None,
        role: str | None = None,
    ) -> None:
        await self._conn.execute(
            "INSERT INTO edition_items (edition_id, store_id, name, item_kind, is_primary,"
            " version_id, role) VALUES (?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(edition_id, store_id) DO UPDATE SET"
            "  name = COALESCE(excluded.name, edition_items.name),"
            "  item_kind = excluded.item_kind, is_primary = excluded.is_primary,"
            "  version_id = COALESCE(excluded.version_id, edition_items.version_id),"
            "  role = excluded.role",
            (edition_id, store_id, name, item_kind, 1 if is_primary else 0, version_id, role),
        )
        await self._conn.commit()

    async def editions_with_items(self) -> list[dict[str, Any]]:
        """Every edition with what it holds, for the re-parse to read again:
        `{edition_id, name, scope, kind, items: [{store_id, item_kind,
        is_primary, role}]}`, items in the order kept."""
        cursor = await self._conn.execute(
            "SELECT e.edition_id, e.name, e.scope, e.kind, i.store_id, i.item_kind,"
            " i.is_primary, i.role FROM editions e"
            " JOIN edition_items i ON i.edition_id = e.edition_id"
            " ORDER BY e.edition_id, i.seq"
        )
        found: dict[int, dict[str, Any]] = {}
        for r in await cursor.fetchall():
            edition = found.setdefault(
                int(r["edition_id"]),
                {
                    "edition_id": int(r["edition_id"]),
                    "name": r["name"],
                    "scope": r["scope"],
                    "kind": r["kind"],
                    "items": [],
                },
            )
            edition["items"].append(
                {
                    "store_id": r["store_id"],
                    "item_kind": r["item_kind"],
                    "is_primary": bool(r["is_primary"]),
                    "role": r["role"],
                }
            )
        return list(found.values())

    async def set_edition_scope(
        self, edition_id: int, scope: str, kind: str | None, roles: dict[str, str | None]
    ) -> None:
        """What an edition is by its contents: its scope, its kind when it
        changes with it (None keeps the kind), each item's role."""
        async with self.transaction():
            await self._conn.execute(
                "UPDATE editions SET scope = ?, kind = COALESCE(?, kind) WHERE edition_id = ?",
                (scope, kind, edition_id),
            )
            await self._conn.executemany(
                "UPDATE edition_items SET role = ? WHERE edition_id = ? AND store_id = ?",
                [(role, edition_id, store_id) for store_id, role in roles.items()],
            )

    async def version_of_product(self, store: str, product_id: str) -> int | None:
        """One of our versions of this store product (any console)."""
        cursor = await self._conn.execute(
            "SELECT version_id FROM versions WHERE store = ? AND product_id = ?"
            " ORDER BY version_id LIMIT 1",
            (store, product_id),
        )
        row = await cursor.fetchone()
        return int(row["version_id"]) if row else None

    async def versions_of_product(self, store: str, product_id: str) -> list[dict[str, Any]]:
        cursor = await self._conn.execute(
            "SELECT * FROM versions WHERE store = ? AND product_id = ? ORDER BY version_id",
            (store, product_id),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def x360_title_ids(self) -> list[str]:
        """The 360 title ids a backward-compatible product is kept for."""
        return [s.split(":", 1)[1] for s in await self.payload_subjects("xbox_catalog", "x360:")]

    async def linked_hltb_ids(self) -> list[int]:
        cursor = await self._conn.execute(
            "SELECT DISTINCT hltb_id FROM version_hltb WHERE source <> 'rejected' ORDER BY hltb_id"
        )
        return [int(row[0]) for row in await cursor.fetchall()]

    async def version_row(self, version_id: int) -> dict | None:
        cursor = await self._conn.execute(
            "SELECT * FROM versions WHERE version_id = ?", (version_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def delete_store_versions(self, store: str, product_id: str) -> None:
        """Versions of a store product nobody here has, that turned out to be
        no game (a DLC app a search found)."""
        cursor = await self._conn.execute(
            "SELECT version_id FROM versions WHERE store = ? AND product_id = ?"
            " AND origin = 'store' AND title_id IS NULL",
            (store, product_id),
        )
        for row in await cursor.fetchall():
            await self.delete_version(int(row["version_id"]))
