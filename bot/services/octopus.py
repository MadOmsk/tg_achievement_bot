"""The octopus (#204, #215; owner, 2026-10-16/17, 2026-10-24): one game
assembled whole — every version of the same game (other consoles, other
stores, editions), and for each version its store data, achievement list,
DLC, editions and HowLongToBeat. A chain with a goal, not a crawl:

1. **Entry → anchor**: an achievement → its list; a list → itself; a DLC →
   its base version; a store product → itself; an HLTB page → the versions
   it is linked to (its Steam app first), else a search by its name; a name →
   a search, then one game per distinct find; a game → its anchor version.
2. **Anchor → the game** it is in (the linker makes one if none).
3. **Each version of that game expanded**: its list or product collected (own
   product, sibling products by id, HLTB, DLC, editions), and the game searched
   by every different name it goes by; then **the linker**
   (`game_link.link_and_spread`) over this game's neighbourhood. What it puts
   in *this* game is a version; another game — a remaster, a remake, a
   compilation, a series, a doubt for review — is kept, **never expanded**.
4. **Again while the game gains versions** (a PS5 product leads to the PS4
   one), `MAX_ROUNDS` at most.
5. **Done**: every version's anchor is stamped (`fetch_state`, source
   `octopus`), so another entry to the same game does not assemble it again
   until due; what is still missing is reported.

The queue (`octopus_queue`, migration 126) holds entries by a key that
survives a relink: `game:<id>`, `list:<platform>:<title_id>`,
`product:<store>:<id>`, `achievement:<platform>:<title_id>:<id>`, `dlc:<id>`,
`hltb:<id>`, `name:<text>`. A find by name stays provisional (#202).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from bot.db.repo import Repo
from bot.services import psn_products
from bot.services.game_link import LinkReport, link_and_spread
from bot.services.game_match import name_key
from bot.services.store_collect import StoreCollector

log = logging.getLogger(__name__)
SOURCE = "octopus"
# Rounds of one game's assembly: each expands the versions the last one added.
MAX_ROUNDS = 4
# Names one game is searched by in all: its own, the Russian one, store names
# of its versions and editions, HLTB's — different ones only (#215).
NAMES_PER_GAME = 6
KINDS = ("game", "list", "product", "achievement", "dlc", "hltb", "name")


def game_key(game_id: int) -> str:
    return f"game:{game_id}"


def list_key(platform: str, title_id: str) -> str:
    return f"list:{platform}:{title_id}"


def product_key(store: str, product_id: str) -> str:
    return f"product:{store}:{product_id}"


def search_key(name: str) -> str:
    """A name normalized (`name_key`): "LEGO® Batman™ 3" and "LEGO Batman 3"
    are one search, asked once."""
    return f"name:{name_key(name) or name.strip()}"


def anchor_key(version: dict) -> str:
    """What a version is reached by: its achievement list, else its product."""
    if version.get("platform") and version.get("title_id"):
        return list_key(str(version["platform"]), str(version["title_id"]))
    return product_key(str(version["store"]), str(version["product_id"]))


@dataclass
class GameReport:
    """One game's assembly."""

    entry: str
    game_id: int | None = None
    name: str | None = None
    versions_before: int = 0
    versions_after: int = 0
    rounds: int = 0
    found: list[int] = field(default_factory=list)
    stand_ins: int = 0
    hltb: int = 0
    review: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class OctopusReport:
    """What one run did, for the script's report."""

    games: list[GameReport] = field(default_factory=list)
    searched: int = 0
    skipped: int = 0
    gone: int = 0
    queued: int = 0
    failed: list[str] = field(default_factory=list)

    @property
    def handled(self) -> int:
        return len(self.games) + self.searched + self.skipped + self.gone


Linker = Callable[[Repo, list[int]], Awaitable[LinkReport]]


class OctopusCollector:
    def __init__(
        self, repo: Repo, collector: StoreCollector, *, linker: Linker = link_and_spread
    ) -> None:
        self._repo = repo
        self._collector = collector
        self._linker = linker

    async def enqueue(self, key: str, *, reason: str = "") -> bool:
        """Ask for an entry; returns whether it was new."""
        if key.partition(":")[0] not in KINDS:
            raise ValueError(f"unknown octopus entry {key!r}")
        return await self._repo.octopus_enqueue(key, reason)

    async def run(self, *, limit: int | None = None, force: bool = False) -> OctopusReport:
        """The queue worked through, an entry at a time, until nothing is due
        or `limit` entries were handled."""
        report = OctopusReport()
        while limit is None or report.handled < limit:
            items = await self._repo.octopus_due(1)
            if not items:
                break
            key, reason = items[0]
            try:
                await self._entry(key, reason, report, force)
            except Exception as exc:
                log.exception("octopus %s failed", key)
                report.failed.append(f"{key}: {exc!r}")
                await self._repo.octopus_failed(key, repr(exc))
                continue
            await self._repo.octopus_done(key)
        return report

    # ------------------------------------------------------- entry → anchor

    async def _entry(self, key: str, reason: str, report: OctopusReport, force: bool) -> None:
        kind, _, rest = key.partition(":")
        if kind == "name":
            # A name may be several games: each one found is an entry of its own.
            report.searched += 1
            collected = await self._collector.collect_name(rest, link=False)
            report.failed += [f"{key}: {e}" for e in collected.errors]
            if collected.versions:
                linked = await self._linker(self._repo, sorted(set(collected.versions)))
                for game in sorted(linked.games):
                    report.queued += await self.enqueue(game_key(game), reason=key)
            return
        anchor = await self._anchor(kind, rest, key, report, force)
        if anchor is None:
            report.gone += 1
            return
        row = await self._repo.version_row(anchor)
        if row is None:
            report.gone += 1
            return
        if not force and not await self._repo.fetch_due(anchor_key(row), SOURCE):
            report.skipped += 1
            return
        report.games.append(await self.assemble(anchor, entry=key, force=force))

    async def _anchor(
        self, kind: str, rest: str, key: str, report: OctopusReport, force: bool
    ) -> int | None:
        """The version an entry leads to, collected first where it is a
        store's; None when it leads nowhere (a game gone, nothing known)."""
        if kind == "game":
            game = await self._repo.game_card(int(rest))
            return await self._repo.anchor_of(int(game["game_id"])) if game else None
        if kind == "achievement":
            platform, title_id, _id = rest.split(":", 2)
            kind, rest = "list", f"{platform}:{title_id}"
        if kind == "list":
            platform, _, title_id = rest.partition(":")
            collected = await self._collector.collect(platform, title_id, force=force, link=False)
            report.failed += [f"{key}: {e}" for e in collected.errors]
            found = await self._repo.versions_of_list(platform, title_id)
            return found[0] if found else None
        if kind == "product":
            store, _, product_id = rest.partition(":")
            if store == "steam":
                collected = await self._collector.collect_steam_app(
                    product_id, found=("octopus", key), force=force
                )
                report.failed += [f"{key}: {e}" for e in collected.errors]
            found = await self._repo.versions_of_store_product(store, product_id)
            return found[0] if found else None
        if kind == "dlc":
            return await self._repo.version_of_dlc(int(rest))
        if kind == "hltb":
            collected, name = await self._collector.collect_hltb(int(rest))
            report.failed += [f"{key}: {e}" for e in collected.errors]
            linked = [int(r["version_id"]) for r in await self._repo.versions_of_hltb(int(rest))]
            found = linked or collected.versions
            if found:
                return found[0]
            if name:
                report.queued += await self.enqueue(search_key(name), reason=key)
            return None
        raise ValueError(f"unknown octopus entry {key!r}")

    # --------------------------------------------------------- the assembly

    async def assemble(self, anchor: int, *, entry: str = "", force: bool = False) -> GameReport:
        """One game whole, from the version it is anchored on: its versions
        expanded round after round while it gains versions."""
        report = GameReport(entry or f"version:{anchor}")
        game = await self._game_of(anchor)
        report.versions_before = len(await self._repo.versions_of_games([game]))
        expanded: set[int] = set()
        searched: set[str] = set()
        for _round in range(MAX_ROUNDS):
            members = await self._repo.versions_of_games([game])
            new = [v for v in members if v not in expanded]
            if not new:
                break
            report.rounds += 1
            found: list[int] = []
            for version in new:
                found += await self._expand(version, report, force)
            expanded |= set(new)
            found += await self._search(game, searched, report)
            concepts = await self._repo.psn_concepts_of_game(game)
            if concepts:
                await psn_products.read_pages(self._repo, None, concepts=concepts)
                await psn_products.put_in_place(self._repo, None, concepts)
            report.found += found
            linked = await self._linker(self._repo, sorted(set(members) | set(found)))
            report.review += len(linked.review)
            game = await self._game_of(anchor)
        card = await self._repo.game_card(game)
        report.game_id = game
        report.name = card["name"] if card else None
        after = await self._repo.versions_of_games([game])
        report.versions_after = len(after)
        for version in after:
            row = await self._repo.version_row(version)
            if row is not None:
                await self._repo.record_fetch(
                    anchor_key(row), SOURCE, status="ok", changed=bool(report.found)
                )
        gaps = await self._repo.octopus_gaps(game)
        report.stand_ins, report.hltb = gaps["stand_ins"], gaps["hltb"]
        return report

    async def _game_of(self, anchor: int) -> int:
        game = await self._repo.game_of_version(anchor)
        if game is None:
            # A version in no game yet: the linker makes it one.
            await self._linker(self._repo, [anchor])
            game = await self._repo.game_of_version(anchor)
        if game is None:
            raise RuntimeError(f"version {anchor} is in no game after linking")
        return game

    async def _expand(self, version: int, report: GameReport, force: bool) -> list[int]:
        """One version of the game collected: its list (own product, siblings
        by id, HLTB, DLC, editions), or for a store product its own page."""
        row = await self._repo.version_row(version)
        if row is None:
            return []
        if row["platform"] and row["title_id"]:
            collected = await self._collector.collect(
                str(row["platform"]), str(row["title_id"]), force=force, link=False
            )
        elif row["store"] == "steam":
            collected = await self._collector.collect_steam_app(
                str(row["product_id"]), found=("octopus", report.entry), force=force
            )
        else:
            return []
        report.errors += collected.errors
        return list(collected.versions)

    async def _search(self, game: int, searched: set[str], report: GameReport) -> list[int]:
        """The game searched by every different name it goes by now, each once
        per assembly, `NAMES_PER_GAME` in all."""
        found: list[int] = []
        for name in await self._repo.octopus_names_of_game(game):
            normal = name_key(name)
            if not normal or normal.isdigit() or normal in searched:
                continue
            if len(searched) >= NAMES_PER_GAME:
                break
            searched.add(normal)
            collected = await self._collector.collect_name(normal, link=False)
            report.errors += collected.errors
            found += collected.versions
        return found
