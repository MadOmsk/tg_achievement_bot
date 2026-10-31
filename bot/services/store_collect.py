"""Collecting what the stores and HLTB say about one game (#147, stage 2).

A game here is one achievement list (`titles`); collecting it stores its
versions (a store product on one console), their DLC, its HLTB entry and the
raw answers. Asked when a game's first new achievement is published and when
its page is opened — and then nothing goes out unless the answer is due
(`fetch_state`): many people in one game cost what one does. A source's
answer is trusted 7 → 14 → 30 → 90 days while it does not change; a change,
or a Steam patch in the last 30 days, sets it back to 7, so a live-service
game keeps being asked about.

Network calls stay outside any transaction; each write is its own.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from bot.services import edition_media
from bot.services.admin_settings import STORE_COLLECTION_DEFAULT, STORE_COLLECTION_KEY
from bot.services.game_link import GameLinker
from bot.services.game_match import is_part, name_key
from bot.services.hltb import ensure_title_match
from bot.services.hltb_match import (
    core,
    entry_fits_version,
    is_episode,
    match_dlc_entries,
    similarity,
)
from bot.services.steam.client import get_schema
from bot.services.steam_news import find_appid
from bot.services.stores import (
    StoreVersion,
    classify_bundle,
    edition_kind,
    hltb_page,
    psn_store,
    stand_in_for,
    steam_store,
    xbox_catalog,
)
from bot.util import utcnow

if TYPE_CHECKING:
    from bot.db.repo import Repo
    from bot.services.psn.auth import PsnAuth
    from bot.services.steam.auth import SteamAuth


async def collection_on(repo: Repo) -> bool:
    """The super-admin's switch for asking the stores at all (/admin →
    Прочее, `STORE_COLLECTION_KEY`), read on every run: off, nothing is
    collected and the octopus rests. The operator's own tools ignore it."""
    return bool(await repo.get_int_setting(STORE_COLLECTION_KEY, int(STORE_COLLECTION_DEFAULT)))


log = logging.getLogger(__name__)

# How close a store search's hit must be to the name asked for to be stored
# (the matcher decides what it is): this alike, or the one name opening the
# other ("The Last of Us" → "The Last of Us Part I").
NAME_SEARCH_FLOOR = 0.8
# HLTB entries read for one name (a game, its remaster, its remake…).
HLTB_PER_NAME = 4
# Editions (Steam packages) read per game.
EDITIONS_PER_GAME = 8
# PSN concepts looked at for one game's name: the closest few.
SIBLING_CONCEPTS = 2
# Steam DLC named in one pass; a game with more is finished in the passes after.
DLC_NAMES_PER_PASS = 50
RECENT_PATCH_DAYS = 30


@dataclass(slots=True)
class CollectReport:
    """What one collection did, for the log and `scripts/collect_game.py`."""

    platform: str
    title_id: str
    asked: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    versions: list[int] = field(default_factory=list)
    dlcs: int = 0
    hltb_id: int | None = None
    games: list[int] = field(default_factory=list)
    review: int = 0
    errors: list[str] = field(default_factory=list)


class StoreCollector:
    def __init__(
        self, repo: Repo, psn_auth: PsnAuth | None = None, steam_auth: SteamAuth | None = None
    ) -> None:
        self._repo = repo
        self._psn_auth = psn_auth
        self._steam_auth = steam_auth
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}
        self._running: dict[tuple[str, str], asyncio.Task[CollectReport]] = {}
        self._background: set[asyncio.Task[None]] = set()
        # Told the games a collection put a list in, so their descriptions
        # are translated (`GameTranslator.later`); the bot sets it, scripts not.
        self.on_games: Callable[[list[int]], None] | None = None
        # The game's translator, for the Mini App's pages (the same object).
        self.translator: Any = None

    def ensure(self, platform: str, title_id: str, *, reason: str = "published") -> None:
        """Collect the game in the background if anything about it is due —
        never on the path that called it — and put it in the octopus's queue,
        which assembles the whole game later (#215). A no-op while it is
        running."""
        key = (str(platform), title_id)
        if key in self._running:
            return
        task = asyncio.create_task(self._collect_logged(*key, reason=reason))
        self._running[key] = task
        task.add_done_callback(lambda _t: self._running.pop(key, None))

    async def _collect_logged(
        self, platform: str, title_id: str, *, reason: str = "published"
    ) -> CollectReport:
        try:
            if not await collection_on(self._repo):
                return CollectReport(platform, title_id)
            # The octopus's key for a list (`octopus.list_key`); a key in the
            # queue already stays as it is.
            await self._repo.octopus_enqueue(f"list:{platform}:{title_id}", reason)
            report = await self.collect(platform, title_id)
            if self.on_games is not None and report.games:
                self.on_games(report.games)
            return report
        except Exception:
            log.exception("store collection failed for %s %s", platform, title_id)
            return CollectReport(platform, title_id, errors=["crashed"])

    async def collect(
        self, platform: str, title_id: str, *, force: bool = False, link: bool = True
    ) -> CollectReport:
        platform = str(platform)
        report = CollectReport(platform, title_id)
        async with self._locks.setdefault((platform, title_id), asyncio.Lock()):
            if platform == "steam":
                await self._steam(title_id, report, force)
            elif platform == "xbox_modern":
                await self._xbox(title_id, report, force)
            elif platform == "psn":
                await self._psn(title_id, report, force)
            elif platform == "xbox_360":
                await self.x360_by_name(title_id, force=force)
                await self._x360_addons(title_id, report, force)
            await self._list_version(platform, title_id, report)
            # Before HLTB: looking for the other stores finds the HLTB entry,
            # which the HLTB step then links to every version of this list.
            await self._siblings(platform, title_id, report, force)
            await self._hltb(platform, title_id, report, force)
            if link and (report.asked or report.versions):
                # What it is now known to be, put into games (stage 3).
                linked = await GameLinker(self._repo).link_title(platform, title_id)
                report.games = sorted(linked.games)
                report.review = len(linked.review)
        if report.asked:
            log.info(
                "store collection %s %s: asked %s, versions %s, dlc %s, hltb %s%s",
                platform,
                title_id,
                ",".join(report.asked),
                report.versions,
                report.dlcs,
                report.hltb_id,
                f", errors {report.errors}" if report.errors else "",
            )
        return report

    # ------------------------------------------------------------ Steam

    async def _steam(
        self,
        appid: str,
        report: CollectReport,
        force: bool,
        *,
        ours: bool = True,
        found: tuple[str, str] | None = None,
    ) -> None:
        """A Steam app: ours (a list somebody here has) or found for another
        platform's game (`ours=False`: stored with no list, as `store`)."""
        subject, source = f"steam:{appid}", "steam_store"
        if not force and not await self._repo.fetch_due(subject, source):
            report.skipped.append(source)
            return
        report.asked.append(source)
        try:
            data = await steam_store.app_details(appid)
            data_ru = await steam_store.app_details(appid, "russian") if data else None
        except Exception as exc:
            report.errors.append(f"{source}: {exc!r}")
            await self._repo.record_fetch(subject, source, status="error", error=repr(exc))
            return
        if data is None:
            await self._repo.record_fetch(subject, source, status="not_found")
            return
        changed = await self._repo.save_payload(subject, source, data)
        if not ours and str(data.get("type") or "game") not in ("game", "demo"):
            # A DLC, a soundtrack or a tool the search found: not a version of
            # anything (it reaches its game as the game's DLC).
            await self._repo.delete_store_versions("steam", appid)
            await self._repo.record_fetch(subject, source, status="ok", changed=changed)
            return
        version = steam_store.parse_app(data, data_ru)
        # The poster and head of now, which `appdetails` does not give: best effort.
        try:
            art = (await steam_store.library_art([appid])).get(str(appid), {})
        except Exception as exc:
            art = {}
            log.info("steam library art of %s not read: %r", appid, exc)
        version.media.update(art)
        version_id = await self._repo.save_version(
            version,
            platform="steam" if ours else None,
            title_id=appid if ours else None,
            origin="played" if ours else "store",
            found=("played", f"steam:{appid}") if ours else found,
        )
        report.versions.append(version_id)
        more = await self._steam_dlcs(version_id, version, report)
        await self._steam_editions(appid, version_id, data, report)
        patched = await self._recently_patched(int(appid))
        await self._repo.record_fetch(
            subject, source, status="ok", changed=changed or patched, soon=more
        )

    async def _steam_dlcs(
        self, version_id: int, version: StoreVersion, report: CollectReport
    ) -> bool:
        """Name the app's DLC not named yet, a pass's worth; True when some
        are left for the next pass."""
        named = await self._repo.dlc_ids_named(version_id)
        missing = [dlc_id for dlc_id in version.dlc_ids if dlc_id not in named]
        for dlc_id in missing[:DLC_NAMES_PER_PASS]:
            try:
                data = await steam_store.app_details(dlc_id)
            except Exception as exc:
                report.errors.append(f"steam dlc {dlc_id}: {exc!r}")
                return True
            if data is None:
                continue
            await self._repo.save_dlc(version_id, steam_store.parse_dlc(data))
            report.dlcs += 1
        return len(missing) > DLC_NAMES_PER_PASS

    async def _steam_editions(
        self, appid: str, version_id: int, data: dict, report: CollectReport
    ) -> None:
        """The packages the app is sold as: its editions (Skyrim: Special,
        Anniversary), with what each holds."""
        sold = set(steam_store.sold_package_ids(data))
        for package_id in steam_store.package_ids(data)[:EDITIONS_PER_GAME]:
            try:
                package = await steam_store.package(package_id)
            except Exception as exc:
                report.errors.append(f"steam package {package_id}: {exc!r}")
                return
            if package is None:
                continue
            await self._repo.save_payload(f"steam_package:{package_id}", "steam_package", package)
            name = str(package.get("name") or "") or None
            edition_id = await self._repo.save_edition(
                "steam",
                package_id,
                name,
                edition_kind(name),
                package_id in sold,
                media=edition_media.steam(package),
            )
            for app in package.get("apps") or []:
                app_id = str(app.get("id") or "")
                if not app_id:
                    continue
                is_game = app_id == appid
                await self._repo.save_edition_item(
                    edition_id,
                    app_id,
                    app.get("name"),
                    "game" if is_game else "dlc",
                    is_primary=is_game,
                    version_id=version_id if is_game else None,
                    role="main" if is_game else None,
                )

    async def _recently_patched(self, appid: int | None) -> bool:
        if appid is None:
            return False
        since = (utcnow() - timedelta(days=RECENT_PATCH_DAYS)).isoformat(timespec="seconds")
        return await self._repo.steam_app_patched_since(appid, since)

    # ------------------------------------------------------------ Xbox

    async def _xbox(self, title_id: str, report: CollectReport, force: bool) -> None:
        subject, source = f"xbox_title:{title_id}", "xbox_catalog"
        if not force and not await self._repo.fetch_due(subject, source):
            report.skipped.append(source)
            return
        report.asked.append(source)
        try:
            found = await xbox_catalog.products_for_title(title_id)
        except Exception as exc:
            report.errors.append(f"{source}: {exc!r}")
            await self._repo.record_fetch(subject, source, status="error", error=repr(exc))
            return
        games = [
            p
            for p in found
            if str(p.get("ProductType") or "") in ("Game", "Application")
            and not xbox_catalog.bundle_items(p)
        ]
        if not games:
            await self._repo.record_fetch(subject, source, status="not_found")
            return
        changed = await self._repo.save_payload(subject, source, found)
        await self._remember_x360(found)
        # Every product carrying this title id is this game's: an add-on
        # naming any of them as its own is the game's (a cross-gen game's).
        owners = {str(p.get("ProductId")) for p in found if p.get("ProductId")}
        all_ids: list[int] = []
        for product in games:
            versions = xbox_catalog.parse_product(product)
            ids = await self._save_xbox_versions(
                versions, "xbox_modern", title_id, "played", ("played", f"xbox_modern:{title_id}")
            )
            report.versions += ids
            all_ids += ids
            if versions:
                changed |= await self._xbox_addons(
                    versions[0].product_id, versions[0].dlc_ids, ids, report, owners
                )
        changed |= await self._xbox_addons_alone(
            owners, [xbox_catalog.title_of(p) for p in games], all_ids, report, force
        )
        steam_appid = await self._title_steam_appid("xbox_modern", title_id)
        patched = await self._recently_patched(steam_appid)
        await self._repo.record_fetch(subject, source, status="ok", changed=changed or patched)

    async def _save_xbox_versions(
        self,
        versions: list[StoreVersion],
        platform: str | None,
        title_id: str | None,
        origin: str,
        found: tuple[str, str],
    ) -> list[int]:
        """A product's versions, one per console it is made for; a version
        stored before on a console it is not made for (a One game's phantom
        "Series" version) goes into the kept one."""
        ids = [
            await self._repo.save_version(
                v, platform=platform, title_id=title_id, origin=origin, found=found
            )
            for v in versions
        ]
        if versions:
            await self._repo.retire_other_consoles("xbox", versions[0].product_id, ids)
        return ids

    async def _xbox_addons(
        self,
        product_id: str,
        related: list[str],
        version_ids: list[int],
        report: CollectReport,
        owners: set[str] | None = None,
    ) -> bool:
        """The product's add-ons, for every console version of it (Smart
        Delivery add-ons work on both) — those that name this game as their
        own (`owners`: its products), not the other games' an edition of
        several bundles."""
        if not related or not version_ids:
            return False
        try:
            editions = await xbox_catalog.products(related)
            addon_ids = xbox_catalog.bundled(editions, product_id)
            found = await xbox_catalog.products(addon_ids) if addon_ids else []
        except Exception as exc:
            report.errors.append(f"xbox add-ons: {exc!r}")
            return False
        changed = await self._repo.save_payload(
            f"xbox_addons:{product_id}", "xbox_catalog", {"editions": editions, "addons": found}
        )
        await self._remember_x360(editions + found)
        await self._xbox_editions(editions, found, report)
        mine = (owners or set()) | {product_id}
        foreign = [
            str(p.get("ProductId"))
            for p in found
            if p.get("ProductId") and not xbox_catalog.belongs_to(p, mine)
        ]
        for version_id in version_ids:
            # Another game's add-on an earlier collection put here goes.
            await self._repo.delete_dlcs(version_id, foreign)
        for product in found:
            addon = xbox_catalog.parse_addon(product)
            if addon is None or not xbox_catalog.belongs_to(product, mine):
                continue
            for version_id in version_ids:
                await self._repo.save_dlc(version_id, addon)
            report.dlcs += 1
        return changed

    async def _xbox_addons_alone(
        self,
        owners: set[str],
        names: list[str | None],
        version_ids: list[int],
        report: CollectReport,
        force: bool,
    ) -> bool:
        """The add-ons sold only on their own (owner, 2026-10-27): no edition
        lists them, so the catalog's add-ons for the game's names are read,
        and those naming one of `owners` (the game's products) as their
        parent are kept. Two names at most, when due (`fetch_state`)."""
        searched = list(dict.fromkeys(n for n in map(_store_name, names) if n))[:2]
        if not owners or not searched or not version_ids:
            return False
        subject, source = f"xbox_addons_alone:{min(owners)}", "xbox_addon_search"
        if not force and not await self._repo.fetch_due(subject, source):
            report.skipped.append(source)
            return False
        report.asked.append(source)
        try:
            ids: list[str] = []
            for name in searched:
                ids += [i for i in await xbox_catalog.search_addons(name) if i not in ids]
            found = await xbox_catalog.products(ids) if ids else []
        except Exception as exc:
            report.errors.append(f"{source}: {exc!r}")
            await self._repo.record_fetch(subject, source, status="error", error=repr(exc))
            return False
        mine = [p for p in found if xbox_catalog.belongs_to(p, owners)]
        changed = await self._repo.save_payload(subject, source, mine)
        for product in mine:
            addon = xbox_catalog.parse_addon(product)
            if addon is None:
                continue
            for version_id in version_ids:
                await self._repo.save_dlc(version_id, addon)
            report.dlcs += 1
        await self._repo.record_fetch(
            subject, source, status="ok" if mine else "not_found", changed=changed
        )
        return changed

    async def xbox_product_addons(self, version: dict, *, force: bool = False) -> CollectReport:
        """An Xbox store product with no achievement list of ours (the
        octopus's find by name): its add-ons sold on their own."""
        product_id = str(version["product_id"])
        report = CollectReport("xbox", product_id)
        ids = [int(v["version_id"]) for v in await self._repo.versions_of_product(
            "xbox", product_id)]  # fmt: skip
        await self._xbox_addons_alone(
            {product_id}, [version.get("name")], ids or [int(version["version_id"])], report, force
        )
        return report

    async def _x360_addons(self, title_id: str, report: CollectReport, force: bool) -> None:
        """A 360 game's add-ons: it has no editions, so only those sold on
        their own exist, under its backward-compatible product."""
        versions = [
            v
            for v in await self._repo.versions_of_title("xbox_360", title_id)
            if v["store"] == "xbox" and not v["stand_in"]
        ]
        if not versions:
            return
        record = await self._repo.title_record("xbox_360", title_id) or {}
        await self._xbox_addons_alone(
            {str(v["product_id"]) for v in versions},
            [versions[0]["name"], record.get("name"), record.get("name_en")],
            [int(v["version_id"]) for v in versions],
            report,
            force,
        )

    async def _xbox_editions(
        self, editions: list[dict], items: list[dict], report: CollectReport
    ) -> None:
        """Bundles as editions (owner, 2026-10-10): a pack of a game and its
        add-ons (the E-Day Premium Edition), kept with what it holds. A
        bundle with no game of its own is a bundle of games."""
        by_id = {str(p.get("ProductId")): p for p in items}
        missing = [
            big_id
            for edition in editions
            for big_id, _primary in xbox_catalog.bundle_items(edition)
            if big_id not in by_id
        ]
        if missing:
            try:
                fetched = await xbox_catalog.products(list(dict.fromkeys(missing)))
                for product in fetched:
                    by_id[str(product.get("ProductId"))] = product
                await self._remember_x360(fetched)
            except Exception as exc:
                report.errors.append(f"xbox edition items: {exc!r}")
        for edition in editions:
            contents = xbox_catalog.bundle_items(edition)
            if not contents:
                continue
            name = xbox_catalog.title_of(edition)
            kinds = [
                {"Game": "game", "Durable": "dlc", "Consumable": "consumable"}.get(
                    str(by_id.get(big_id, {}).get("ProductType") or ""), "other"
                )
                for big_id, _primary in contents
            ]
            # What it is, read from what it holds (owner, 2026-10-24): one game
            # is its edition, a game thrown in is a bonus, several equal games
            # a bundle, no game a pack of add-ons.
            scope, kind, roles = classify_bundle(
                name, [(k, p) for k, (_id, p) in zip(kinds, contents, strict=True)]
            )
            edition_id = await self._repo.save_edition(
                "xbox",
                str(edition.get("ProductId")),
                name,
                kind,
                xbox_catalog.sold(edition),
                media=edition_media.xbox(edition),
                scope=scope,
            )
            for (big_id, is_primary), item_kind, role in zip(contents, kinds, roles, strict=True):
                item = by_id.get(big_id, {})
                version_id = (
                    await self._repo.version_of_product("xbox", big_id)
                    if item_kind == "game"
                    else None
                )
                await self._repo.save_edition_item(
                    edition_id,
                    big_id,
                    xbox_catalog.title_of(item) if item else None,
                    item_kind,
                    is_primary=is_primary,
                    version_id=version_id,
                    role=role,
                )

    # ------------------------------------------------------------ by name (#147)

    async def collect_name(self, name: str, *, link: bool = True) -> CollectReport:
        """A game by its name, on every store, nobody here needing to have it
        (owner, 2026-10-10: seeding the matcher with games of many editions).
        What each store's search finds close to the name is stored (versions
        as `store`, editions, DLC) and then matched."""
        report = CollectReport("name", name)
        ours = name_key(name)
        report.asked.append("search")
        try:
            await self._xbox_by_name(name, ours, report)
        except Exception as exc:
            report.errors.append(f"xbox search: {exc!r}")
        try:
            for item in await steam_store.search(name):
                hit = name_key(str(item.get("name") or ""))
                if item.get("type") != "app" or not _close(ours, hit):
                    continue
                appid = str(item["id"])
                held = await self._repo.title_record("steam", appid) is not None
                await self._steam(appid, report, True, ours=held, found=("search", f"name:{name}"))
                await self._steam_schema(appid)
        except Exception as exc:
            report.errors.append(f"steam search: {exc!r}")
        try:
            await self._psn_siblings([name], report, ("search", f"name:{name}"))
        except Exception as exc:
            report.errors.append(f"psn search: {exc!r}")
        try:
            await self._hltb_by_name(name, ours, report)
        except Exception as exc:
            report.errors.append(f"hltb search: {exc!r}")
        if link and report.versions:
            linked = await GameLinker(self._repo).link_versions(sorted(set(report.versions)))
            report.games = sorted(linked.games)
            report.review = len(linked.review)
        return report

    async def collect_steam_app(
        self, appid: str, *, found: tuple[str, str], force: bool = False
    ) -> CollectReport:
        """One Steam app as an entry of its own (#215): its version, DLC,
        editions and schema; a list of ours if somebody here has it."""
        report = CollectReport("steam", appid)
        held = await self._repo.title_record("steam", appid) is not None
        await self._steam(appid, report, force, ours=held, found=found)
        await self._steam_schema(appid)
        return report

    async def collect_hltb(self, hltb_id: int) -> tuple[CollectReport, str | None]:
        """One HowLongToBeat page as an entry of its own (#215): the page read
        and kept, the Steam apps it names, its links checked. Returns the
        report and the entry's name (for a search by it)."""
        report = CollectReport("hltb", str(hltb_id))
        data = await hltb_page.fetch_page(hltb_id)
        entry = hltb_page.parse_page(data) if data else None
        if entry is None:
            report.errors.append("hltb page unreadable")
            return report, None
        await self._repo.save_payload(f"hltb:{entry.hltb_id}", "hltb_page", data)
        await self._repo.save_hltb_page(entry)
        await self._from_hltb(entry, report)
        await link_hltb_entry(self._repo, entry.hltb_id)
        report.hltb_id = entry.hltb_id
        return report, entry.name

    async def _hltb_by_name(self, name: str, ours: str, report: CollectReport) -> None:
        """HLTB's entries close to the name, each page read and kept; one is
        linked to a Steam version only when its page names that very app."""
        from bot.services.hltb import search_candidates

        steam_versions = {}
        for version_id in set(report.versions):
            row = await self._repo.version_row(version_id)
            if row and row["store"] == "steam":
                steam_versions[str(row["product_id"])] = version_id
        read = 0
        for result in (await search_candidates(name))[: HLTB_PER_NAME * 3]:
            if not _close(ours, name_key(result.name)):
                continue
            data = await hltb_page.fetch_page(result.hltb_id)
            entry = hltb_page.parse_page(data) if data else None
            if entry is None:
                continue
            await self._repo.save_payload(f"hltb:{entry.hltb_id}", "hltb_page", data)
            await self._repo.save_hltb_page(entry)
            await self._from_hltb(entry, report)
            if entry.steam_appid and str(entry.steam_appid) in steam_versions:
                await self._repo.link_version_hltb(
                    steam_versions[str(entry.steam_appid)], entry.hltb_id
                )
            report.hltb_id = report.hltb_id or entry.hltb_id
            read += 1
            if read >= HLTB_PER_NAME:
                break

    async def _from_hltb(self, entry: hltb_page.HltbEntry, report: CollectReport) -> None:
        """What an HLTB entry tells beyond itself (owner, 2026-10-10: a game
        off sale is still everybody's who has it). Its Steam apps — the main
        and the other one its page names — are read even when Steam no
        longer lists them (Skyrim 2011). The consoles HLTB names are not made
        versions (2026-10-11: HLTB is matched by name, and a version nobody
        sells is no version): the game page shows them as HLTB's platforms."""
        for appid in dict.fromkeys(a for a in (entry.steam_appid, entry.steam_alt) if a):
            if await self._repo.version_of_product("steam", str(appid)) is None:
                held = await self._repo.title_record("steam", str(appid)) is not None
                await self._steam(
                    str(appid), report, False, ours=held, found=("hltb", f"hltb:{entry.hltb_id}")
                )
                await self._steam_schema(str(appid))

    async def _xbox_by_name(self, name: str, ours: str, report: CollectReport) -> None:
        hits = [
            p
            for p in await xbox_catalog.search(name)
            if p.get("Type") == "Game" and _close(ours, name_key(str(p.get("Title") or "")))
        ]
        if not hits:
            return
        products = await xbox_catalog.products([str(p["ProductId"]) for p in hits])
        await self._remember_x360(products)
        editions = [p for p in products if xbox_catalog.bundle_items(p)]
        title_ids_of = {
            str(p.get("ProductId")): {
                str(a.get("Value"))
                for a in p.get("AlternateIds") or []
                if a.get("IdType") == "XboxTitleId"
            }
            for p in products
        }
        for product in products:
            if xbox_catalog.bundle_items(product):
                continue
            title_ids = [
                str(a.get("Value"))
                for a in product.get("AlternateIds") or []
                if a.get("IdType") == "XboxTitleId"
            ]
            held = None
            for title_id in title_ids:
                if await self._repo.title_record("xbox_modern", title_id) is not None:
                    held = title_id
                    break
            versions = xbox_catalog.parse_product(product)
            ids = await self._save_xbox_versions(
                versions,
                "xbox_modern" if held else None,
                held,
                "played" if held else "store",
                ("played", f"xbox_modern:{held}") if held else ("search", f"name:{name}"),
            )
            report.versions += ids
            if versions:
                own = set(title_ids)
                owners = {pid for pid, tids in title_ids_of.items() if tids & own}
                await self._xbox_addons(
                    versions[0].product_id, versions[0].dlc_ids, ids, report, owners
                )
                await self._xbox_addons_alone(
                    owners | {versions[0].product_id},
                    [xbox_catalog.title_of(product)],
                    ids,
                    report,
                    False,
                )
        await self._xbox_editions(editions, [], report)

    # ------------------------------------------------------------ other stores (stage 4)

    async def _siblings(
        self, platform: str, title_id: str, report: CollectReport, force: bool
    ) -> None:
        """The game's versions on the stores nobody here has it on (#147,
        stage 4): Steam's app (the one its HLTB page names, else a careful
        name search — `steam_news.find_appid`), PSN's concepts by name. Only
        found and stored here; whether they are this game is the matcher's."""
        subject, source = f"siblings:{platform}:{title_id}", "siblings"
        if not force and not await self._repo.fetch_due(subject, source):
            report.skipped.append(source)
            return
        record = await self._repo.title_record(platform, title_id)
        if not record:
            return
        names = [str(n) for n in (record.get("name_en"), record.get("name")) if n]
        report.asked.append(source)
        try:
            if platform != "steam":
                await self._steam_sibling(platform, title_id, names, report, force)
            if platform != "psn":
                await self._psn_siblings(names, report, ("sibling", f"{platform}:{title_id}"))
        except Exception as exc:
            report.errors.append(f"{source}: {exc!r}")
            await self._repo.record_fetch(subject, source, status="error", error=repr(exc))
            return
        await self._repo.record_fetch(subject, source, status="ok")

    async def _steam_sibling(
        self, platform: str, title_id: str, names: list[str], report: CollectReport, force: bool
    ) -> None:
        steam = await self._repo.title_steam(platform, title_id)
        appid = steam.steam_appid if steam else None
        if appid is None:
            # The HLTB entry first: its page names the Steam app exactly, where
            # a name search may find several and rightly answer none.
            await ensure_title_match(self._repo, platform, title_id)
            hltb_id = await self._repo.title_hltb_id(platform, title_id)
            appid = await find_appid(names, hltb_id)
        if appid is None:
            return
        ours = await self._repo.title_record("steam", str(appid)) is not None
        await self._steam(
            str(appid), report, force, ours=ours, found=("sibling", f"{platform}:{title_id}")
        )
        await self._steam_schema(str(appid))

    async def _steam_schema(self, appid: str) -> None:
        """The app's achievement names (English), kept for the matcher: one
        list's names are the same on every platform."""
        subject, source = f"steam_schema:{appid}", "steam_schema"
        if self._steam_auth is None or not await self._repo.fetch_due(subject, source):
            return
        api_key = await self._steam_auth.get_key()
        if not api_key:
            return
        try:
            schema = await get_schema(api_key, appid, language="english")
        except Exception as exc:
            await self._repo.record_fetch(subject, source, status="error", error=repr(exc))
            return
        names = [item.display_name for item in schema if item.display_name]
        changed = await self._repo.save_payload(subject, source, names)
        await self._repo.record_fetch(subject, source, status="ok", changed=changed)

    async def _psn_siblings(
        self, names: list[str], report: CollectReport, found: tuple[str, str]
    ) -> None:
        """PSN's concepts for the name, the closest few, stored as `store`
        versions with no list (none of ours was proved for them)."""
        from bot.services.psn import client as psn

        if self._psn_auth is None or not names:
            return
        client = await self._psn_auth.get_client()
        results = await psn.store_search(client, core(names[0]))
        ours = name_key(names[0])
        seen: set[str] = set()
        # The search's close hits first, then the ids the game's own page on
        # playstation.com names (the search misses GTA V and Fallout 4).
        title_ids: list[str] = []
        for item in results:
            result = item.get("result") or {}
            concept_id = str(item.get("id") or result.get("id") or "")
            name = str((result.get("defaultProduct") or {}).get("invariantName") or "")
            if not concept_id or similarity(ours, name_key(name)) < 0.8:
                continue
            title_ids += psn_store.title_ids_in_search([item])[:1]
        try:
            title_ids += await psn_store.game_page_title_ids(core(names[0]))
        except Exception as exc:
            log.info("playstation.com page for %r: %r", names[0], exc)
        for title_id in dict.fromkeys(title_ids):
            concept = psn_store.without_prices(await psn.store_concept(client, title_id))
            if concept is None or str(concept.get("id")) in seen:
                continue
            if not _close(ours, name_key(str(concept.get("nameEn") or concept.get("name") or ""))):
                # A page names its game's other games too (a bundle, a sequel).
                continue
            seen.add(str(concept.get("id")))
            await self._repo.save_payload(f"psn:{concept.get('id')}", "psn_store", concept)
            for version in psn_store.parse_concept(concept):
                report.versions.append(
                    await self._repo.save_version(
                        version, platform=None, title_id=None, origin="store", found=found
                    )
                )
            if len(seen) >= SIBLING_CONCEPTS:
                break

    # ------------------------------------------------------------ the stored answers again

    async def reparse_stored(self) -> dict[str, int]:
        """Every kept answer read again through today's parsers, and written as
        a collection would write it — **no request** (owner, 2026-10-12;
        `scripts/reparse_store_payloads.py`): versions, their consoles and
        availability, Xbox add-ons (only their own game's), what each edition is by
        what it holds (`classify_editions`), the 360 store
        pages, HLTB entries and their links. The answers themselves are kept
        again without prices. What only a request brings (a Steam DLC's or
        package's own answer, the Russian appdetails) is left as it is."""
        done: dict[str, int] = {}

        def count(key: str) -> None:
            done[key] = done.get(key, 0) + 1

        repo = self._repo
        for subject in await repo.payload_subjects("steam_store", "steam:"):
            data = steam_store.without_prices(await repo.payload(subject, "steam_store"))
            if not data:
                continue
            await repo.save_payload(subject, "steam_store", data)
            appid = subject.split(":", 1)[1]
            ours = await repo.title_record("steam", appid) is not None
            if not ours and str(data.get("type") or "game") not in ("game", "demo"):
                await repo.delete_store_versions("steam", appid)
                continue
            await repo.save_version(
                steam_store.parse_app(data),
                platform="steam" if ours else None,
                title_id=appid if ours else None,
                origin="played" if ours else "store",
            )
            count("steam versions")
        addons_done: set[str] = set()
        for subject in await repo.payload_subjects("xbox_catalog", "xbox_title:"):
            found = xbox_catalog.without_prices(await repo.payload(subject, "xbox_catalog") or [])
            answered = await repo.payload_fetched_at(subject, "xbox_catalog")
            await repo.save_payload(subject, "xbox_catalog", found, fetched_at=answered)
            await self._remember_x360(found)
            title_id = subject.split(":", 1)[1]
            owners = {str(p.get("ProductId")) for p in found if p.get("ProductId")}
            for product in found:
                if str(product.get("ProductType") or "") not in (
                    "Game",
                    "Application",
                ) or xbox_catalog.bundle_items(product):
                    continue
                versions = xbox_catalog.parse_product(product, answered)
                ids = await self._save_xbox_versions(
                    versions,
                    "xbox_modern",
                    title_id,
                    "played",
                    ("played", f"xbox_modern:{title_id}"),
                )
                count("xbox versions")
                if versions:
                    addons_done.add(versions[0].product_id)
                    await self._reparse_xbox_addons(versions[0].product_id, ids, owners)
        for subject in await repo.payload_subjects("xbox_catalog", "xbox_addons:"):
            # Add-ons of products found by name (no title payload of their own).
            product_id = subject.split(":", 1)[1]
            if product_id in addons_done:
                continue
            cursor_ids = [
                int(v["version_id"])
                for v in await repo.versions_of_product("xbox", product_id)
                if v["console"] != "360"
            ]
            if cursor_ids:
                await self._reparse_xbox_addons(product_id, cursor_ids, None)
        for subject in await repo.payload_subjects("psn_store", "psn:"):
            concept = psn_store.without_prices(await repo.payload(subject, "psn_store"))
            if not concept:
                continue
            await repo.save_payload(subject, "psn_store", concept)
            for version in psn_store.parse_concept(concept):
                # Which list a PSN version has was proved when it was collected
                # (asking Sony): kept as it is (`save_version` never blanks it).
                await repo.save_version(version, platform=None, title_id=None, origin="store")
                count("psn versions")
        hltb_ids: list[int] = []
        for subject in await repo.payload_subjects("hltb_page", "hltb:"):
            data = await repo.payload(subject, "hltb_page")
            entry = hltb_page.parse_page(data) if data else None
            if entry is None:
                continue
            await repo.save_hltb_page(entry)
            hltb_ids.append(entry.hltb_id)
            count("hltb pages")
        for title_id in await repo.x360_title_ids():
            await link_x360_product(repo, title_id)
        for hltb_id in await repo.linked_hltb_ids():
            await link_hltb_entry(repo, hltb_id)
            count("hltb links checked")
        # Last, after every step that saves an edition again: what each kept
        # edition is, read from what it holds (owner, 2026-10-24).
        for scope, n in (await classify_editions(repo)).items():
            done[f"editions: {scope}"] = n
        return done

    async def _reparse_xbox_addons(
        self, product_id: str, version_ids: list[int], owners: set[str] | None
    ) -> None:
        """A product's kept add-ons answer, as `_xbox_addons` writes it."""
        subject = f"xbox_addons:{product_id}"
        kept = await self._repo.payload(subject, "xbox_catalog")
        if not isinstance(kept, dict):
            return
        answered = await self._repo.payload_fetched_at(subject, "xbox_catalog")
        editions = xbox_catalog.without_prices(kept.get("editions") or [])
        found = xbox_catalog.without_prices(kept.get("addons") or [])
        await self._repo.save_payload(
            subject, "xbox_catalog", {"editions": editions, "addons": found}, fetched_at=answered
        )
        await self._remember_x360(editions + found)
        mine = (owners or set()) | {product_id}
        foreign = [
            str(p.get("ProductId"))
            for p in found
            if p.get("ProductId") and not xbox_catalog.belongs_to(p, mine)
        ]
        for version_id in version_ids:
            await self._repo.delete_dlcs(version_id, foreign)
        for product in found:
            addon = xbox_catalog.parse_addon(product, answered)
            if addon is None or not xbox_catalog.belongs_to(product, mine):
                continue
            for version_id in version_ids:
                await self._repo.save_dlc(version_id, addon)
        for edition in editions:
            if xbox_catalog.bundle_items(edition):
                name = xbox_catalog.title_of(edition)
                await self._repo.save_edition(
                    "xbox",
                    str(edition.get("ProductId")),
                    name,
                    None,
                    xbox_catalog.sold(edition, answered),
                )

    # ------------------------------------------------------------ Xbox 360 (owner, 2026-10-12)

    async def _remember_x360(self, products: list[dict]) -> None:
        """A 360 game's backward-compatible product seen in passing (an
        edition's, a bundle's) is kept under its 360 title id
        (`x360:<title id>`), and the 360 list, when somebody here has it,
        takes it as its store page. The product's own `[Fission] … (hex)`
        mark is the proof: a search by name (`x360_by_name`) only finds the
        candidates."""
        by_title: dict[str, list[dict]] = {}
        for product in products:
            if (title_id := xbox_catalog.fission_title_id(product)) is not None:
                by_title.setdefault(title_id, []).append(product)
        for title_id, found in by_title.items():
            subject = f"x360:{title_id}"
            kept = {
                str(p.get("ProductId")): p
                for p in await self._repo.payload(subject, "xbox_catalog") or []
            }
            kept.update({str(p.get("ProductId")): p for p in found})
            await self._repo.save_payload(subject, "xbox_catalog", [kept[k] for k in sorted(kept)])
            await link_x360_product(self._repo, title_id)

    async def x360_by_name(self, title_id: str, *, force: bool = False) -> bool:
        """A 360 list's store page looked for by the list's names (owner,
        2026-10-15: 451 of 458 360 lists had none — the catalog's lookup by
        title id knows no 360 game, and a page was only found in passing). The
        catalog's games for each name are read and kept when their
        `[Fission]` mark names a 360 list (`_remember_x360`), this one or
        another; a game never made backward compatible has none. True when the
        list has its page now."""
        subject, source = f"x360:{title_id}", "x360_search"
        if not force and not await self._repo.fetch_due(subject, source):
            return False
        record = await self._repo.title_record("xbox_360", title_id)
        if not record:
            return False
        names = []
        for raw in (record.get("name"), record.get("name_en")):
            name = re.sub(r"[®™©]", "", str(raw or "")).strip()
            if name and name != title_id and name != "?" and name not in names:
                names.append(name)
        try:
            for name in names:
                hits = [p for p in await xbox_catalog.search(name) if p.get("Type") == "Game"]
                if hits:
                    await self._remember_x360(
                        await xbox_catalog.products([str(p["ProductId"]) for p in hits])
                    )
        except Exception as exc:
            await self._repo.record_fetch(subject, source, status="error", error=repr(exc))
            return False
        found = await link_x360_product(self._repo, title_id)
        await self._repo.record_fetch(subject, source, status="ok" if found else "not_found")
        return found is not None

    async def remember_title(self, entry: object) -> None:
        """What a titlehub answer said about a game (`XboxClient.resolve_title`),
        kept as an answer (`titlehub:<title id>`): a stand-in takes its studio,
        publisher, day and genres from it. For a 360 game, the Store products
        it names (`productId`, the product of its `modernTitleId`) are read
        from the catalog — public, no login — and one becomes its store page
        only when its own `[Fission]` mark names this very 360 title id.
        Derived from the documentation: to be checked live on two or three
        games (Kameo, Banjo-Tooie, one never made compatible)."""
        from dataclasses import asdict

        data = asdict(entry)  # type: ignore[call-overload]
        title_id = str(data.get("title_id") or "")
        if not title_id:
            return
        await self._repo.save_payload(f"titlehub:{title_id}", "titlehub", data)
        if str(data.get("platform")) != "xbox_360":
            return
        subject, source = f"x360:{title_id}", "titlehub_product"
        if not await self._repo.fetch_due(subject, source):
            return
        try:
            products = await xbox_catalog.products(list(data.get("product_ids") or []))
            if data.get("modern_title_id"):
                products += await xbox_catalog.products_for_title(str(data["modern_title_id"]))
        except Exception as exc:
            await self._repo.record_fetch(subject, source, status="error", error=repr(exc))
            return
        await self._remember_x360(products)
        proved = any(xbox_catalog.fission_title_id(p) == title_id for p in products)
        await self._repo.record_fetch(subject, source, status="ok" if proved else "not_found")

    def remember_title_soon(self, entry: object) -> None:
        """`remember_title` in the background, never on the caller's path."""
        task = asyncio.create_task(self._remember_logged(entry))
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def _remember_logged(self, entry: object) -> None:
        try:
            if not await collection_on(self._repo):
                return
            await self.remember_title(entry)
        except Exception:
            log.exception("keeping a titlehub answer failed")

    async def _list_version(self, platform: str, title_id: str, report: CollectReport) -> None:
        """Every achievement list is at least one version, so it can be put
        into a game: a store product when a store found one, otherwise the
        list itself as `titles` describes it — a stand-in (`stand_in`, under
        the platform's store): a 360 game, an Xbox card the catalog no longer
        carries, a PSN list not proved.
        Once a store product is found, the stand-in goes. A stand-in takes
        what titlehub said of the game (its studio, publisher, day, genres)."""
        if platform == "xbox_360":
            await link_x360_product(self._repo, title_id)
        versions = await self._repo.versions_of_title(platform, title_id)
        real = [v for v in versions if not v["stand_in"]]
        stand_ins = [v for v in versions if v["stand_in"]]
        if real:
            for version in stand_ins:
                await self._repo.delete_version(int(version["version_id"]))
            return
        record = await self._repo.title_record(platform, title_id)
        if not record:
            return
        version = stand_in_for(record)
        said = await self._repo.payload(f"titlehub:{title_id}", "titlehub")
        if isinstance(said, dict):
            version.developer = said.get("developer")
            version.publisher = said.get("publisher")
            version.release_date = said.get("release_date")
            version.genres = list(said.get("genres") or [])
        version_id = await self._repo.save_version(
            version, platform=platform, title_id=title_id, found=("list", f"{platform}:{title_id}")
        )
        report.versions.append(version_id)
        if platform == "psn":
            report.dlcs += await self._repo.save_trophy_group_dlcs(version_id, title_id)

    # ------------------------------------------------------------ PSN

    async def _psn(self, npwr: str, report: CollectReport, force: bool) -> None:
        subject, source = f"psn_list:{npwr}", "psn_store"
        if self._psn_auth is None:
            return
        if not force and not await self._repo.fetch_due(subject, source):
            report.skipped.append(source)
            return
        report.asked.append(source)
        try:
            client = await self._psn_auth.get_client()
            concept = await self._psn_concept(client, npwr)
        except Exception as exc:
            report.errors.append(f"{source}: {exc!r}")
            await self._repo.record_fetch(subject, source, status="error", error=repr(exc))
            return
        if concept is None:
            await self._repo.record_fetch(subject, source, status="not_found")
            return
        concept, ours = concept
        changed = await self._repo.save_payload(f"psn:{concept.get('id')}", source, concept)
        for version in psn_store.parse_concept(concept):
            mine = any(kind == "psn_title" and sid in ours for kind, sid in version.store_ids)
            version_id = await self._repo.save_version(
                version,
                platform="psn" if mine else None,
                title_id=npwr if mine else None,
                origin="played" if mine else "store",
                found=("played", f"psn:{npwr}") if mine else ("sibling", f"psn:{npwr}"),
            )
            report.versions.append(version_id)
            if mine:
                report.dlcs += await self._repo.save_trophy_group_dlcs(version_id, npwr)
        await self._repo.record_fetch(subject, source, status="ok", changed=changed)

    async def _psn_concept(self, client: object, npwr: str) -> tuple[dict, set[str]] | None:
        """The store concept of our trophy list and the title ids Sony says
        have it — or None when nothing could be proved. Ids already proved
        are tried first; otherwise the store is searched by the game's name."""
        from bot.services.psn import client as psn

        account = await self._repo.psn_holder_of(npwr)
        if account is None:
            return None
        candidates = await self._repo.store_ids_of_title("psn", npwr, "psn_title")
        if not candidates:
            record = await self._repo.title_record("psn", npwr) or {}
            name = str(record.get("name_en") or record.get("name") or "")
            if not name:
                return None
            results = await psn.store_search(client, name)  # type: ignore[arg-type]
            candidates = psn_store.title_ids_in_search(results)
            try:
                candidates += [
                    t
                    for t in await psn_store.game_page_title_ids(core(name))
                    if t not in candidates
                ]
            except Exception as exc:
                log.info("playstation.com page for %r: %r", name, exc)
        lists = await psn.trophy_lists_of(client, account, candidates)  # type: ignore[arg-type]
        proved = [title_id for title_id, found in lists.items() if npwr in found]
        if not proved:
            return None
        concept = psn_store.without_prices(
            await psn.store_concept(client, proved[0])  # type: ignore[arg-type]
        )
        if concept is None:
            return None
        # Every id of the concept Sony also ties to our list (a regional twin).
        others = [t for t in psn_store.concept_title_ids(concept) if t not in proved]
        if others:
            more = await psn.trophy_lists_of(client, account, others)  # type: ignore[arg-type]
            proved += [title_id for title_id, found in more.items() if npwr in found]
        return concept, set(proved)

    # ------------------------------------------------------------ HLTB

    async def _hltb(self, platform: str, title_id: str, report: CollectReport, force: bool) -> None:
        hltb_id = await self._repo.title_hltb_id(platform, title_id)
        if hltb_id is None:
            return
        report.hltb_id = hltb_id
        # The list's other versions (a console's, made since) are the same
        # entry too, unless one was told it is not.
        entry = await self._repo.hltb_game_row(hltb_id)
        entry_part = bool(entry) and is_part(None, None, [str(entry["name"] or "")])
        for version_id in await self._repo.versions_of_list(platform, title_id):
            row = await self._repo.version_row(version_id)
            if row is not None and (
                entry_part or not is_part(row["kind"], row["role"], [row["name"] or ""])
            ):
                await self._repo.link_version_hltb(version_id, hltb_id)
        subject, source = f"hltb:{hltb_id}", "hltb_page"
        if not force and not await self._repo.fetch_due(subject, source):
            report.skipped.append(source)
            await self.check_hltb_links(hltb_id)
            return
        report.asked.append(source)
        try:
            data = await hltb_page.fetch_page(hltb_id)
        except Exception as exc:
            report.errors.append(f"{source}: {exc!r}")
            await self._repo.record_fetch(subject, source, status="error", error=repr(exc))
            return
        entry = hltb_page.parse_page(data) if data else None
        if entry is None:
            await self._repo.record_fetch(subject, source, status="not_found")
            return
        changed = await self._repo.save_payload(subject, source, data)
        await self._repo.save_hltb_page(entry)
        await self._from_hltb(entry, report)
        await self.check_hltb_links(hltb_id)
        await self._repo.record_fetch(subject, source, status="ok", changed=changed)

    async def check_hltb_links(self, hltb_id: int) -> None:
        """An HLTB entry's links, checked against what is stored (owner,
        2026-10-12), no request: a version keeps its automatic link only
        while the evidence agrees (`hltb_match.entry_fits_version`), and the
        entry's DLC are put on our DLC of those versions — only there
        (`match_dlc_entries`). Also run by `scripts/reparse_store_payloads.py`."""
        await link_hltb_entry(self._repo, hltb_id)

    async def _title_steam_appid(self, platform: str, title_id: str) -> int | None:
        steam = await self._repo.title_steam(platform, title_id)
        return steam.steam_appid if steam else None


async def classify_editions(repo: Repo) -> dict[str, int]:
    """Every kept edition's scope and its items' roles read again from what it
    holds (`stores.classify_bundle`). A kind set by the advisers or by hand is
    kept while it stays an edition; one that was a bundle's (`bundle`, or
    none) becomes its name's. Returns how many of each scope."""
    counts: dict[str, int] = {}
    for edition in await repo.editions_with_items():
        items = edition["items"]
        scope, kind, roles = classify_bundle(
            edition["name"], [(i["item_kind"], i["is_primary"]) for i in items]
        )
        counts[scope] = counts.get(scope, 0) + 1
        keep_kind = scope == "edition" and edition["kind"] not in (None, "bundle", "addon_pack")
        changed_roles = {
            i["store_id"]: role for i, role in zip(items, roles, strict=True) if i["role"] != role
        }
        if scope == edition["scope"] and keep_kind and not changed_roles:
            continue
        await repo.set_edition_scope(
            edition["edition_id"], scope, None if keep_kind else kind, changed_roles
        )
    return counts


def _close(ours: str, hit: str) -> bool:
    if similarity(ours, hit) >= NAME_SEARCH_FLOOR:
        return True
    a, b = ours.split(), hit.split()
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return len(short) >= 2 and long_[: len(short)] == short


async def link_hltb_entry(repo: Repo, hltb_id: int) -> None:
    """See `StoreCollector.check_hltb_links`."""
    from bot.services.game_match import candidate_year

    entry = await repo.hltb_game_row(hltb_id)
    if entry is None:
        return
    # Both Steam apps its page names (a game's re-release has another id:
    # Skyrim's 2011 app beside Special Edition's), read from the kept page.
    appids = {int(a) for a in (entry.get("steam_appid"),) if a}
    page = await repo.payload(f"hltb:{hltb_id}", "hltb_page")
    parsed = hltb_page.parse_page(page) if page else None
    if parsed is not None and parsed.hltb_id == hltb_id:
        appids |= {a for a in (parsed.steam_appid, parsed.steam_alt) if a}
    names = [str(entry["name"])]
    for version in await repo.versions_of_hltb(hltb_id):
        fits = entry_fits_version(
            game_type=entry.get("game_type"),
            steam_appids=appids,
            entry_year=entry.get("release_year"),
            version_store=str(version["store"]),
            version_product=str(version["product_id"]),
            version_kind=version.get("kind"),
            version_year=candidate_year(version),
            version_episode=is_episode(version.get("name"), version.get("name_ru")),
        )
        # A demo has no entry — unless the entry is the demo's own (HowLongToBeat
        # times a few: Resident Evil 2's "1-Shot Demo", an open beta).
        part = is_part(
            version.get("kind"),
            version.get("role"),
            [str(n) for n in (version.get("name"), version.get("name_ru")) if n],
        ) and not is_part(None, None, [str(entry["name"])])
        if not fits or part:
            await repo.unlink_version_hltb(int(version["version_id"]), hltb_id, only_auto=True)
        elif version.get("name"):
            names.append(str(version["name"]))
    dlcs = await repo.dlcs_under_hltb(hltb_id)
    if not dlcs:
        return
    children = [
        (int(c["hltb_id"]), str(c["name"] or ""), c.get("steam_appid"))
        for c in await repo.hltb_children(hltb_id)
        if (c.get("game_type") or "dlc") in ("dlc", "expansion")
    ]
    links = match_dlc_entries(
        children,
        [(int(d["dlc_id"]), str(d["store"]), d["store_id"], d["name"]) for d in dlcs],
        names,
    )
    await repo.replace_dlc_hltb([int(d["dlc_id"]) for d in dlcs], links)


def _store_name(name: object) -> str:
    """A name to ask a store's search with: no ®™©, never an id."""
    text = re.sub(r"[®™©]", "", str(name or "")).strip()
    return "" if not text or text.isdigit() or text == "?" else text


async def link_x360_product(repo: Repo, title_id: str) -> int | None:
    """The 360 list's store page, from the backward-compatible product kept
    under its title id (`x360:<title id>`, proved by its `[Fission]` mark):
    the selling one (a `Purchase` ever offered), not its content twin. The
    list's stand-in becomes that product, as the 360 version — its id and
    labels kept (`save_version`). None when there is none, or nobody here has
    the list. No request."""
    products = await repo.payload(f"x360:{title_id}", "xbox_catalog") or []
    answered = await repo.payload_fetched_at(f"x360:{title_id}", "xbox_catalog")
    selling = [
        p
        for p in products
        if xbox_catalog.fission_title_id(p) == title_id and xbox_catalog.offers_purchase(p)
    ]
    if not selling or await repo.title_record("xbox_360", title_id) is None:
        return None
    # Two selling products would be a mystery: the one sold now, else the first.
    product = sorted(
        selling, key=lambda p: (not xbox_catalog.sold(p, answered), str(p.get("ProductId")))
    )[0]
    return await repo.save_version(
        xbox_catalog.parse_x360(product, answered), platform="xbox_360", title_id=title_id
    )


async def link_steam_apps_to_hltb(repo: Repo) -> dict[str, int]:
    """A Steam version is the HLTB entry whose page names its app (owner,
    2026-10-15): the surest evidence there is, and the lazy match never ran for
    a Steam list nobody published in since. The same checks a stored link
    passes (`entry_fits_version`, the demo rule); a game-type entry before a
    DLC's, the page's main app before its second one. Links nothing that
    already has a link, a refusal included."""
    from bot.services.game_match import candidate_year

    found: dict[int, list[dict]] = {}
    for row in await repo.steam_versions_with_hltb_by_app():
        found.setdefault(int(row["version_id"]), []).append(row)
    linked = skipped = 0
    for version_id, rows in found.items():
        chosen = None
        for row in rows:
            fits = entry_fits_version(
                game_type=row.get("game_type"),
                steam_appids={int(row["product_id"])},
                entry_year=row.get("release_year"),
                version_store="steam",
                version_product=str(row["product_id"]),
                version_kind=row.get("kind"),
                version_year=candidate_year(row),
                version_episode=is_episode(row.get("name"), row.get("name_ru")),
            )
            part = is_part(
                row.get("kind"),
                row.get("role"),
                [str(n) for n in (row.get("name"), row.get("name_ru")) if n],
            ) and not is_part(None, None, [str(row["entry_name"])])
            if fits and not part:
                chosen = row
                break
        if chosen is None:
            skipped += 1
            continue
        await repo.link_version_hltb(version_id, int(chosen["hltb_id"]), score=1.0)
        linked += 1
    return {"versions with a candidate": len(found), "linked": linked, "none fits": skipped}
