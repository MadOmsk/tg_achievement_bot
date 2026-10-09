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
from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING

from bot.services.game_link import GameLinker
from bot.services.hltb import ensure_title_match
from bot.services.hltb_match import core, normalize, similarity
from bot.services.steam.client import get_schema
from bot.services.steam_news import find_appid
from bot.services.stores import StoreVersion, hltb_page, psn_store, steam_store, xbox_catalog
from bot.util import utcnow

if TYPE_CHECKING:
    from bot.db.repo import Repo
    from bot.services.psn.auth import PsnAuth
    from bot.services.steam.auth import SteamAuth

log = logging.getLogger(__name__)

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

    def ensure(self, platform: str, title_id: str) -> None:
        """Collect the game in the background if anything about it is due —
        never on the path that called it. A no-op while it is running."""
        key = (str(platform), title_id)
        if key in self._running:
            return
        task = asyncio.create_task(self._collect_logged(*key))
        self._running[key] = task
        task.add_done_callback(lambda _t: self._running.pop(key, None))

    async def _collect_logged(self, platform: str, title_id: str) -> CollectReport:
        try:
            return await self.collect(platform, title_id)
        except Exception:
            log.exception("store collection failed for %s %s", platform, title_id)
            return CollectReport(platform, title_id, errors=["crashed"])

    async def collect(self, platform: str, title_id: str, *, force: bool = False) -> CollectReport:
        platform = str(platform)
        report = CollectReport(platform, title_id)
        async with self._locks.setdefault((platform, title_id), asyncio.Lock()):
            if platform == "steam":
                await self._steam(title_id, report, force)
            elif platform == "xbox_modern":
                await self._xbox(title_id, report, force)
            elif platform == "psn":
                await self._psn(title_id, report, force)
            await self._list_version(platform, title_id, report)
            await self._hltb(platform, title_id, report, force)
            await self._siblings(platform, title_id, report, force)
            if report.asked or report.versions:
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
        self, appid: str, report: CollectReport, force: bool, *, ours: bool = True
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
        version = steam_store.parse_app(data, data_ru)
        version_id = await self._repo.save_version(
            version,
            platform="steam" if ours else None,
            title_id=appid if ours else None,
            origin="played" if ours else "store",
        )
        report.versions.append(version_id)
        more = await self._steam_dlcs(version_id, version, report)
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
        games = [p for p in found if str(p.get("ProductType") or "") in ("Game", "Application")]
        if not games:
            await self._repo.record_fetch(subject, source, status="not_found")
            return
        changed = await self._repo.save_payload(subject, source, found)
        for product in games:
            versions = xbox_catalog.parse_product(product)
            ids = []
            for version in versions:
                ids.append(
                    await self._repo.save_version(
                        version, platform="xbox_modern", title_id=title_id
                    )
                )
            report.versions += ids
            if versions:
                changed |= await self._xbox_addons(
                    versions[0].product_id, versions[0].dlc_ids, ids, report
                )
        steam_appid = await self._title_steam_appid("xbox_modern", title_id)
        patched = await self._recently_patched(steam_appid)
        await self._repo.record_fetch(subject, source, status="ok", changed=changed or patched)

    async def _xbox_addons(
        self, product_id: str, related: list[str], version_ids: list[int], report: CollectReport
    ) -> bool:
        """The product's add-ons, for every console version of it (Smart
        Delivery add-ons work on both)."""
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
        for product in found:
            addon = xbox_catalog.parse_addon(product)
            if addon is None:
                continue
            for version_id in version_ids:
                await self._repo.save_dlc(version_id, addon)
            report.dlcs += 1
        return changed

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
                await self._psn_siblings(names, report)
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
        await self._steam(str(appid), report, force, ours=ours)
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

    async def _psn_siblings(self, names: list[str], report: CollectReport) -> None:
        """PSN's concepts for the name, the closest few, stored as `store`
        versions with no list (none of ours was proved for them)."""
        from bot.services.psn import client as psn

        if self._psn_auth is None or not names:
            return
        client = await self._psn_auth.get_client()
        results = await psn.store_search(client, core(names[0]))
        ours = normalize(core(names[0]))
        seen: set[str] = set()
        for item in results:
            result = item.get("result") or {}
            concept_id = str(item.get("id") or result.get("id") or "")
            name = str((result.get("defaultProduct") or {}).get("invariantName") or "")
            if (
                not concept_id
                or concept_id in seen
                or similarity(ours, normalize(core(name))) < 0.8
            ):
                continue
            seen.add(concept_id)
            title_ids = psn_store.title_ids_in_search([item])
            if not title_ids:
                continue
            concept = await psn.store_concept(client, title_ids[0])
            if concept is None:
                continue
            await self._repo.save_payload(f"psn:{concept.get('id')}", "psn_store", concept)
            for version in psn_store.parse_concept(concept):
                report.versions.append(
                    await self._repo.save_version(
                        version, platform=None, title_id=None, origin="store"
                    )
                )
            if len(seen) >= SIBLING_CONCEPTS:
                break

    async def _list_version(self, platform: str, title_id: str, report: CollectReport) -> None:
        """Every achievement list is at least one version, so it can be put
        into a game: a store product when a store found one, otherwise the
        list itself as `titles` describes it — a stand-in (`stand_in`, under
        the platform's store): a 360 game, an Xbox card the catalog no longer
        carries, a PSN list not proved.
        Once a store product is found, the stand-in goes."""
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
        version = StoreVersion(
            store=_store_of(platform),
            product_id=title_id,
            console=_console_of(platform, str(record.get("platforms") or "")),
            name=str(record.get("name") or "") or None,
            name_ru=record.get("name_ru"),  # type: ignore[arg-type]
            kind="game",
            stand_in=True,
        )
        report.versions.append(
            await self._repo.save_version(version, platform=platform, title_id=title_id)
        )

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
        lists = await psn.trophy_lists_of(client, account, candidates)  # type: ignore[arg-type]
        proved = [title_id for title_id, found in lists.items() if npwr in found]
        if not proved:
            return None
        concept = await psn.store_concept(client, proved[0])  # type: ignore[arg-type]
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
        versions = await self._repo.versions_of_title(platform, title_id)
        for version in versions:
            await self._repo.link_version_hltb(int(version["version_id"]), hltb_id)
        subject, source = f"hltb:{hltb_id}", "hltb_page"
        if not force and not await self._repo.fetch_due(subject, source):
            report.skipped.append(source)
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
        await self._repo.save_hltb_game(entry)
        await self._repo.record_fetch(subject, source, status="ok", changed=changed)

    async def _title_steam_appid(self, platform: str, title_id: str) -> int | None:
        steam = await self._repo.title_steam(platform, title_id)
        return steam.steam_appid if steam else None


def _store_of(platform: str) -> str:
    return "xbox" if platform in ("xbox_modern", "xbox_360") else platform


def _console_of(platform: str, platforms: str) -> str:
    """The console a list stands for, from the platforms `titles` keeps:
    the newest one it names, as a version is one console."""
    from bot.services.platform_format import ONE, PS4, PS5, SERIES, X360, parse_platforms

    found = parse_platforms(platforms)
    if platform == "xbox_360":
        return X360
    if platform == "steam":
        return "steam"
    if platform == "psn":
        return PS5 if PS5 in found and PS4 not in found else PS4
    if SERIES in found and ONE not in found:
        return SERIES
    if found == {"pc"}:
        return "pc"
    return ONE
