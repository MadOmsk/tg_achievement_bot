"""The octopus (#204, #215; owner, 2026-10-16/17, 2026-10-24): whatever a
game can be reached from looked for in every store, and everything that
belongs to it pulled — its releases on every platform, their achievement
lists, DLC, editions, HowLongToBeat — so its page is whole.

**Collection only.** Nothing here decides what is one game: the versions found
are marked dirty, and the linker's stage (`game_link.link_dirty`) rebuilds
them once per batch — never inside the collection, so games do not change
under it and the result does not depend on the order. A find by name stays
provisional (#202).

**A queue on stable keys** (`octopus_queue`, migration 126): what to look for
is a key that survives a relink, never only a game id —

- `game:<id>` — a game of ours, opened into its other keys (not stamped: it
  is only a way in);
- `list:<platform>:<title_id>` — an achievement list: its own product on its
  store, the other stores by name, HLTB, DLC, editions (`StoreCollector`);
- `steam:<appid>` — a Steam app;
- `hltb:<id>` — a HowLongToBeat page: its Steam apps, then a search by its
  name;
- `name:<text>` — a name searched in every store and HLTB.

A key done is stamped in `fetch_state` (source `octopus`) and asked again only
when due, whatever game it is in by then. Each key carries its `hops` from what
was asked for; neighbours past `MAX_HOPS` are not queued, so a search does not
crawl a whole store.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from bot.db.repo import Repo
from bot.services import psn_products
from bot.services.game_link import LinkReport, link_dirty
from bot.services.game_match import name_key
from bot.services.store_collect import StoreCollector

log = logging.getLogger(__name__)
SOURCE = "octopus"
# How far from what was asked for a search may go: a game opens into its
# lists and names (1), an HLTB page into a search by its name (2).
MAX_HOPS = 2
# Names one game is searched by: its own, the Russian one, store names of its
# versions and editions, HLTB's — different ones only (#215).
NAMES_PER_GAME = 6
# Keys handled between two linker passes.
BATCH = 20


def game_key(game_id: int) -> str:
    return f"game:{game_id}"


def list_key(platform: str, title_id: str) -> str:
    return f"list:{platform}:{title_id}"


def steam_key(appid: str | int) -> str:
    return f"steam:{appid}"


def hltb_key(hltb_id: int) -> str:
    return f"hltb:{hltb_id}"


def search_key(name: str) -> str:
    """A name normalized (`name_key`): "LEGO® Batman™ 3" and "LEGO Batman 3"
    are one search, asked once."""
    return f"name:{name_key(name) or name.strip()}"


@dataclass
class OctopusReport:
    """What one run did, for the script's report."""

    done: int = 0
    skipped: int = 0
    gone: int = 0
    queued: int = 0
    found: list[int] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    linked: int = 0
    review: int = 0
    batches: int = 0

    @property
    def handled(self) -> int:
        return self.done + self.skipped + self.gone


class OctopusCollector:
    def __init__(
        self,
        repo: Repo,
        collector: StoreCollector,
        *,
        linker: Callable[[Repo], Awaitable[LinkReport | None]] = link_dirty,
    ) -> None:
        self._repo = repo
        self._collector = collector
        self._linker = linker

    async def enqueue(self, key: str, *, hops: int = 0, reason: str = "") -> bool:
        """Ask for a key; one past `MAX_HOPS` is not queued. Returns whether
        it was new."""
        if hops > MAX_HOPS:
            return False
        return await self._repo.octopus_enqueue(key, hops, reason)

    async def run(
        self,
        *,
        limit: int | None = None,
        batch: int = BATCH,
        force: bool = False,
        link: bool = True,
    ) -> OctopusReport:
        """The queue worked through, `batch` keys at a time, the linker after
        each batch; stops when nothing is due or after `limit` keys."""
        report = OctopusReport()
        while limit is None or report.handled < limit:
            size = batch if limit is None else min(batch, limit - report.handled)
            items = await self._repo.octopus_due(size)
            if not items:
                break
            for key, hops, reason in items:
                await self._one(key, hops, reason, report, force)
            report.batches += 1
            if link:
                linked = await self._linker(self._repo)
                if linked is not None:
                    report.linked += len(linked.games)
                    report.review += len(linked.review)
        return report

    async def _one(
        self, key: str, hops: int, reason: str, report: OctopusReport, force: bool
    ) -> None:
        stamped = not key.startswith("game:")
        try:
            if stamped and not force and not await self._repo.fetch_due(key, SOURCE):
                report.skipped += 1
                await self._repo.octopus_done(key)
                return
            found = await self._work(key, hops, reason, report, force)
        except Exception as exc:
            log.exception("octopus %s failed", key)
            report.failed.append(f"{key}: {exc!r}")
            await self._repo.octopus_failed(key, repr(exc))
            if stamped:
                await self._repo.record_fetch(key, SOURCE, status="error", error=repr(exc))
            return
        if found is None:
            report.gone += 1
        else:
            report.done += 1
            report.found += found
            await self._repo.mark_dirty(found)
            if stamped:
                await self._repo.record_fetch(key, SOURCE, status="ok", changed=bool(found))
        await self._repo.octopus_done(key)

    async def _work(
        self, key: str, hops: int, reason: str, report: OctopusReport, force: bool
    ) -> list[int] | None:
        """One key looked for: the versions it found, or None for a game that
        is gone (deleted by a relink, or merged into nothing)."""
        kind, _, rest = key.partition(":")
        if kind == "game":
            return await self._game(int(rest), hops, report)
        if kind == "list":
            platform, _, title_id = rest.partition(":")
            collected = await self._collector.collect(platform, title_id, force=force, link=False)
        elif kind == "steam":
            collected = await self._collector.collect_steam_app(
                rest, found=("octopus", reason or key), force=force
            )
        elif kind == "hltb":
            collected, name = await self._collector.collect_hltb(int(rest))
            if name:
                report.queued += await self.enqueue(search_key(name), hops=hops + 1, reason=key)
        elif kind == "name":
            collected = await self._collector.collect_name(rest, link=False)
        else:
            raise ValueError(f"unknown octopus key {key!r}")
        report.failed += [f"{key}: {e}" for e in collected.errors]
        return list(collected.versions)

    async def _game(self, game_id: int, hops: int, report: OctopusReport) -> list[int] | None:
        """A game opened into the keys it is reached by — its lists, its HLTB
        pages, every different name it goes by — and its PlayStation
        concepts' products read at once (they are its own)."""
        game = await self._repo.game_card(game_id)
        if game is None:
            return None
        game_id = int(game["game_id"])
        reason = game_key(game_id)
        for platform, title_id in await self._repo.octopus_lists_of_game(game_id):
            report.queued += await self.enqueue(
                list_key(platform, title_id), hops=hops + 1, reason=reason
            )
        for hltb_id in await self._repo.octopus_hltb_of_game(game_id):
            report.queued += await self.enqueue(hltb_key(hltb_id), hops=hops + 1, reason=reason)
        seen: set[str] = set()
        for name in await self._repo.octopus_names_of_game(game_id):
            normal = name_key(name)
            if not normal or normal.isdigit() or normal in seen:
                continue
            seen.add(normal)
            report.queued += await self.enqueue(search_key(normal), hops=hops + 1, reason=reason)
            if len(seen) >= NAMES_PER_GAME:
                break
        concepts = await self._repo.psn_concepts_of_game(game_id)
        if concepts:
            await psn_products.read_pages(self._repo, None, concepts=concepts)
            await psn_products.put_in_place(self._repo, None, concepts)
        return []
