"""The octopus search (#204; owner, 2026-10-16/17): one game looked for in
every store, and everything that belongs to it pulled — its releases on every
platform, their achievement lists, DLC, editions, HowLongToBeat — so its page
is whole. The steps are the protocol of #204, in its order; each is a piece
the collectors already have (`StoreCollector`, `psn_products`, the HLTB
matcher), here run together for one game. Each piece keeps its raw answers
and its `fetch_state`, so a game asked again costs only what is due.

Nothing here decides what is the same game: the versions found go to the
matcher (`GameLinker`), and a find by name stays provisional (#202).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from bot.db.repo import Repo
from bot.services import psn_products
from bot.services.game_link import GameLinker, spread_hltb
from bot.services.hltb import ensure_title_match
from bot.services.store_collect import StoreCollector

log = logging.getLogger(__name__)
SOURCE = "octopus"


@dataclass
class OctopusReport:
    game_id: int
    name: str | None = None
    versions_before: int = 0
    versions_after: int = 0
    lists: int = 0
    found: list[int] = field(default_factory=list)
    psn_pages: int = 0
    hltb_spread: int = 0
    games_after: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class OctopusCollector:
    def __init__(self, repo: Repo, collector: StoreCollector) -> None:
        self._repo = repo
        self._collector = collector

    async def game(self, game_id: int, *, force: bool = False, link: bool = True) -> OctopusReport:
        """Steps 1–10 of #204 for one game; 11 (advisers with web search) and
        12 (the checks) are run over the whole database by the sweep."""
        report = OctopusReport(game_id)
        game = await self._repo.game_card(game_id)
        if game is None:
            report.errors.append("no such game")
            return report
        report.name = game["name"]
        versions = await self._repo.versions_of_games([game_id])
        report.versions_before = len(versions)
        rows = [await self._repo.version_row(v) for v in versions]

        # 1–4, 6–9 for every achievement list the game has: its own product on
        # its store, the other stores by name, HLTB, its whole list, DLC and
        # editions (`StoreCollector.collect`, only what is due).
        lists = {(r["platform"], r["title_id"]) for r in rows if r and r["title_id"]}
        report.lists = len(lists)
        for platform, title_id in sorted(lists):
            try:
                found = await self._collector.collect(platform, title_id, force=force, link=False)
                report.found += found.versions
                report.errors += found.errors
            except Exception as exc:
                report.errors.append(f"collect {platform}:{title_id}: {exc!r}")

        # 3 again, by the game's own name on every store: the releases no list
        # of ours leads to (a PC port, the other generation's product).
        names = [n for n in (game["name"], game.get("name_ru")) if n and not str(n).isdigit()]
        for name in names[:1]:
            try:
                found = await self._collector.collect_name(name, link=False)
                report.found += found.versions
                report.errors += found.errors
            except Exception as exc:
                report.errors.append(f"name {name!r}: {exc!r}")

        # 7–8 for PlayStation: every product the game's concepts sell.
        concepts = await self._repo.psn_concepts_of_game(game_id)
        if concepts:
            try:
                pages = await psn_products.read_pages(self._repo, None, concepts=concepts)
                await psn_products.put_in_place(self._repo, None, concepts)
                report.psn_pages = pages.read
            except Exception as exc:
                report.errors.append(f"psn products: {exc!r}")

        # 5: an HLTB entry asked for every list still without one.
        for platform, title_id in sorted(lists):
            try:
                await ensure_title_match(self._repo, platform, title_id)
            except Exception as exc:
                report.errors.append(f"hltb {platform}:{title_id}: {exc!r}")

        # 10: the game rebuilt with what was found, its HLTB entry spread.
        everything = sorted(set(versions) | set(report.found))
        if link and everything:
            linked = await GameLinker(self._repo).link_versions(everything)
            report.games_after = sorted(linked.games)
        report.hltb_spread = await spread_hltb(self._repo, report.games_after or [game_id])
        # The game's own size now: the game its first release is in.
        now = await self._repo.version_row(versions[0]) if versions else None
        home = int(now["game_id"]) if now and now["game_id"] else game_id
        report.versions_after = len(await self._repo.versions_of_games([home]))
        await self._repo.record_fetch(
            f"game:{game_id}", SOURCE, status="error" if report.errors else "ok"
        )
        return report
