"""The store side of a game (#147, migration 090): versions, their store ids
and DLC, the new HLTB entries, each source's last answer and when to ask it
again."""

from __future__ import annotations

import hashlib
import json
import zlib
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from bot.util import utcnow, utcnow_iso

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

    async def save_payload(self, subject: str, source: str, payload: Any) -> bool:
        """Keep a source's answer (compressed, the latest only). True when it
        differs from the one kept — the signal that the game changed."""
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
            (subject, source, utcnow_iso(), digest, zlib.compress(text.encode("utf-8"), 9)),
        )
        await self._conn.commit()
        return row is not None

    async def payload(self, subject: str, source: str) -> Any | None:
        cursor = await self._conn.execute(
            "SELECT payload FROM source_payloads WHERE subject = ? AND source = ?",
            (subject, source),
        )
        row = await cursor.fetchone()
        return json.loads(zlib.decompress(row["payload"]).decode("utf-8")) if row else None

    # ------------------------------------------------------------ versions

    async def save_version(
        self,
        version: StoreVersion,
        *,
        platform: str | None,
        title_id: str | None,
        origin: str = "played",
    ) -> int:
        """Store a version as its store describes it, and every id that names
        it; its achievement list is kept once known, never blanked."""
        now = utcnow_iso()
        await self._conn.execute(
            "INSERT INTO versions (store, product_id, console, platform, title_id, name, name_ru,"
            "  kind, developer, publisher, release_date, genres, also_on, store_group,"
            "  description_en, description_ru, media, live_service, origin, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(store, product_id, console) DO UPDATE SET"
            "  platform = COALESCE(excluded.platform, versions.platform),"
            "  title_id = COALESCE(excluded.title_id, versions.title_id),"
            "  name = COALESCE(excluded.name, versions.name),"
            "  name_ru = COALESCE(excluded.name_ru, versions.name_ru),"
            "  kind = COALESCE(excluded.kind, versions.kind),"
            "  developer = COALESCE(excluded.developer, versions.developer),"
            "  publisher = COALESCE(excluded.publisher, versions.publisher),"
            "  release_date = COALESCE(excluded.release_date, versions.release_date),"
            "  genres = excluded.genres, also_on = excluded.also_on,"
            "  store_group = COALESCE(excluded.store_group, versions.store_group),"
            "  description_en = COALESCE(excluded.description_en, versions.description_en),"
            "  description_ru = COALESCE(excluded.description_ru, versions.description_ru),"
            "  media = excluded.media, live_service = excluded.live_service,"
            # A version somebody here plays stays `played` once it is.
            "  origin = CASE WHEN versions.origin = 'played' THEN 'played'"
            "   ELSE excluded.origin END,"
            "  updated_at = excluded.updated_at",
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
                version.description_ru,
                json.dumps(version.media, ensure_ascii=False),
                1 if version.live_service else 0,
                origin,
                now,
            ),
        )
        cursor = await self._conn.execute(
            "SELECT version_id FROM versions WHERE store = ? AND product_id = ? AND console = ?",
            (version.store, version.product_id, version.console),
        )
        version_id = int((await cursor.fetchone())["version_id"])
        for kind, store_id in version.store_ids:
            await self._conn.execute(
                "INSERT OR IGNORE INTO version_store_ids (store, store_id, version_id, source)"
                " VALUES (?, ?, ?, 'catalog')",
                (kind, store_id, version_id),
            )
        await self._conn.commit()
        return version_id

    async def versions_of_title(self, platform: str, title_id: str) -> list[dict[str, Any]]:
        cursor = await self._conn.execute(
            "SELECT * FROM versions WHERE platform = ? AND title_id = ? ORDER BY console",
            (platform, title_id),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def store_ids_of_title(self, platform: str, title_id: str, store: str) -> list[str]:
        """The ids of one kind (`psn_title`, …) its versions are known by."""
        cursor = await self._conn.execute(
            "SELECT DISTINCT i.store_id FROM version_store_ids i"
            " JOIN versions v ON v.version_id = i.version_id"
            " WHERE v.platform = ? AND v.title_id = ? AND i.store = ?",
            (platform, title_id, store),
        )
        return [str(row[0]) for row in await cursor.fetchall()]

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
            "  image_url, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(version_id, store_id) WHERE store_id IS NOT NULL DO UPDATE SET"
            "  name = COALESCE(excluded.name, dlcs.name),"
            "  kind = COALESCE(excluded.kind, dlcs.kind),"
            "  release_date = COALESCE(excluded.release_date, dlcs.release_date),"
            "  description_en = COALESCE(excluded.description_en, dlcs.description_en),"
            "  image_url = COALESCE(excluded.image_url, dlcs.image_url),"
            "  updated_at = excluded.updated_at",
            (
                version_id,
                dlc.store_id,
                dlc.name,
                dlc.kind,
                dlc.release_date,
                dlc.description_en,
                dlc.image_url,
                utcnow_iso(),
            ),
        )
        await self._conn.commit()

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

    async def save_hltb_game(self, entry: HltbEntry) -> None:
        """The entry and, without a page of their own, its DLC rows."""
        for item in (entry, *entry.children):
            await self._conn.execute(
                "INSERT INTO hltb_games (hltb_id, name, game_type, parent_hltb_id, steam_appid,"
                "  developer, publisher, release_year, platforms, times, platform_times, details,"
                "  summary_en, image_url, checked_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(hltb_id) DO UPDATE SET name = excluded.name,"
                "  game_type = excluded.game_type,"
                "  parent_hltb_id = COALESCE(excluded.parent_hltb_id, hltb_games.parent_hltb_id),"
                "  steam_appid = COALESCE(excluded.steam_appid, hltb_games.steam_appid),"
                "  developer = COALESCE(excluded.developer, hltb_games.developer),"
                "  publisher = COALESCE(excluded.publisher, hltb_games.publisher),"
                "  release_year = COALESCE(excluded.release_year, hltb_games.release_year),"
                "  platforms = COALESCE(excluded.platforms, hltb_games.platforms),"
                "  times = excluded.times,"
                "  platform_times = COALESCE(excluded.platform_times, hltb_games.platform_times),"
                "  details = COALESCE(excluded.details, hltb_games.details),"
                "  summary_en = COALESCE(excluded.summary_en, hltb_games.summary_en),"
                "  image_url = COALESCE(excluded.image_url, hltb_games.image_url),"
                "  checked_at = excluded.checked_at",
                (
                    item.hltb_id,
                    item.name,
                    item.game_type,
                    item.parent_hltb_id,
                    item.steam_appid,
                    item.developer,
                    item.publisher,
                    item.release_year,
                    json.dumps(item.platforms) if item.platforms else None,
                    json.dumps(item.times),
                    json.dumps(item.platform_times) if item.platform_times else None,
                    json.dumps(item.details, ensure_ascii=False) if item.details else None,
                    item.summary_en,
                    item.image_url,
                    utcnow_iso(),
                ),
            )
        # The Russian summary already paid for in the legacy store is kept.
        await self._conn.execute(
            "UPDATE hltb_games SET summary_ru = (SELECT description_ru FROM hltb_cache c"
            "  WHERE c.hltb_id = hltb_games.hltb_id)"
            " WHERE hltb_id = ? AND summary_ru IS NULL",
            (entry.hltb_id,),
        )
        await self._conn.commit()

    async def link_version_hltb(self, version_id: int, hltb_id: int, source: str = "auto") -> None:
        await self._conn.execute(
            "INSERT OR IGNORE INTO version_hltb (version_id, hltb_id, source) VALUES (?, ?, ?)",
            (version_id, hltb_id, source),
        )
        await self._conn.commit()

    async def title_hltb_id(self, platform: str, title_id: str) -> int | None:
        cursor = await self._conn.execute(
            "SELECT hltb_id FROM titles WHERE platform = ? AND title_id = ?", (platform, title_id)
        )
        row = await cursor.fetchone()
        return int(row["hltb_id"]) if row and row["hltb_id"] else None

    async def steam_app_patched_since(self, appid: int, since: str) -> bool:
        cursor = await self._conn.execute(
            "SELECT 1 FROM game_patches WHERE steam_appid = ? AND published_at >= ? LIMIT 1",
            (appid, since),
        )
        return await cursor.fetchone() is not None
