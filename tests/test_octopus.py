"""The octopus (#215): a queue on stable keys, any way into a game, a hop
budget, and linking as a stage of its own after each batch."""

from __future__ import annotations

from bot.db.repo import Repo
from bot.services import octopus as octo
from bot.services.octopus import OctopusCollector, game_key, list_key, search_key
from bot.services.store_collect import CollectReport
from bot.services.stores import StoreVersion


class Stub:
    """The collector, recording what it is asked; nothing reaches a store."""

    def __init__(self, repo: Repo) -> None:
        self.repo = repo
        self.asked: list[str] = []

    async def collect(self, platform, title_id, *, force=False, link=True):
        self.asked.append(list_key(platform, title_id))
        return CollectReport(platform, title_id)

    async def collect_name(self, name, *, link=True):
        self.asked.append(f"name:{name}")
        report = CollectReport("name", name)
        report.versions.append(
            await self.repo.save_version(
                StoreVersion(store="psn", product_id=f"p-{name}", console="ps5", name=name),
                platform=None,
                title_id=None,
            )
        )
        return report

    async def collect_steam_app(self, appid, *, found, force=False):
        self.asked.append(f"steam:{appid}")
        return CollectReport("steam", appid)

    async def collect_hltb(self, hltb_id):
        self.asked.append(f"hltb:{hltb_id}")
        return CollectReport("hltb", str(hltb_id)), "Halo Reach"


async def _game_with_list(repo: Repo, name: str, title_id: str) -> int:
    v = await repo.save_version(
        StoreVersion(store="steam", product_id=title_id, console="steam", name=f"{name}®"),
        platform="steam",
        title_id=title_id,
    )
    game = await repo.create_game(name, 2010, v)
    await repo.write_members({v: (game, "version", None, None)})
    return game


async def _linker_counting(calls: list[int]):
    async def linker(repo: Repo):
        calls.append(len(await repo.take_dirty()))
        return None

    return linker


async def test_a_game_opens_into_its_lists_and_its_names(repo: Repo) -> None:
    game = await _game_with_list(repo, "Halo Reach", "976730")
    stub = Stub(repo)
    calls: list[int] = []
    octopus = OctopusCollector(repo, stub, linker=await _linker_counting(calls))  # type: ignore[arg-type]
    await octopus.enqueue(game_key(game))
    report = await octopus.run()
    # Its list, and one search for "Halo Reach" and "Halo Reach®" alike.
    assert stub.asked == [list_key("steam", "976730"), search_key("Halo Reach")]
    assert report.done == 3 and report.found
    # The game opened first (nothing to link), then its keys: the version
    # the search found, linked once.
    assert calls == [0, 1]


async def test_a_key_done_is_not_asked_again_whatever_game_it_is_in(repo: Repo) -> None:
    """Stable keys (#215): a relink may give the game another id; its list
    was looked for and is not due."""
    game = await _game_with_list(repo, "Halo Reach", "976730")
    stub = Stub(repo)
    octopus = OctopusCollector(repo, stub, linker=await _linker_counting([]))  # type: ignore[arg-type]
    await octopus.enqueue(game_key(game))
    await octopus.run()
    moved = await repo.create_game("Halo Reach", 2010)
    version = (await repo.versions_of_games([game]))[0]
    await repo.write_members({version: (moved, "version", None, None)})
    stub.asked.clear()
    await octopus.enqueue(game_key(moved))
    report = await octopus.run()
    assert stub.asked == []
    assert report.skipped == 2


async def test_a_game_gone_mid_run_is_no_error(repo: Repo) -> None:
    octopus = OctopusCollector(repo, Stub(repo), linker=await _linker_counting([]))  # type: ignore[arg-type]
    await octopus.enqueue(game_key(999))
    report = await octopus.run()
    assert report.gone == 1 and not report.failed
    assert await repo.octopus_waiting() == 0


async def test_the_search_stops_at_its_hop_budget(repo: Repo) -> None:
    """An HLTB page opens a search by its name — one hop more; past
    `MAX_HOPS` nothing is queued."""
    octopus = OctopusCollector(repo, Stub(repo), linker=await _linker_counting([]))  # type: ignore[arg-type]
    assert await octopus.enqueue("hltb:7", hops=octo.MAX_HOPS)
    report = await octopus.run()
    assert report.queued == 0
    assert not await octopus.enqueue("hltb:8", hops=octo.MAX_HOPS + 1)
    await octopus.enqueue("hltb:9", hops=0)
    report = await octopus.run()
    assert report.queued == 1  # the search by its name, one hop on


async def test_the_linker_runs_once_a_batch_never_inside_it(repo: Repo) -> None:
    stub = Stub(repo)
    calls: list[int] = []
    octopus = OctopusCollector(repo, stub, linker=await _linker_counting(calls))  # type: ignore[arg-type]
    for name in ("Alpha", "Beta", "Gamma", "Delta"):
        await octopus.enqueue(search_key(name))
    report = await octopus.run(batch=2)
    assert report.batches == 2
    assert calls == [2, 2]
