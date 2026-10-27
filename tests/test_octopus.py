"""The octopus (#215; owner, 2026-10-24): one game assembled whole by a chain
with a goal — entry → anchor → its game → each version of that game expanded,
round after round while the game gains versions; another game met on the way
(a remaster, a series) is kept and never expanded."""

from __future__ import annotations

from bot.db.repo import Repo
from bot.services.admin_settings import STORE_COLLECTION_KEY
from bot.services.game_link import LinkReport
from bot.services.game_match import name_key
from bot.services.octopus import OctopusCollector, game_key, list_key, search_key
from bot.services.store_collect import CollectReport
from bot.services.stores import StoreVersion


async def _version(
    repo: Repo, store: str, product: str, console: str, name: str, platform=None, title_id=None
) -> int:
    return await repo.save_version(
        StoreVersion(store=store, product_id=product, console=console, name=name),
        platform=platform,
        title_id=title_id,
    )


class Stub:
    """The stores, as the octopus meets them: a search by "Halo Reach" finds
    its PS5 release (with a list) and a remaster; the PS5 list leads to the
    PS4 product. Records what it is asked; nothing reaches a store."""

    def __init__(self, repo: Repo) -> None:
        self.repo = repo
        self.asked: list[str] = []

    async def collect(self, platform, title_id, *, force=False, link=True):
        self.asked.append(list_key(platform, title_id))
        report = CollectReport(platform, title_id)
        if (platform, title_id) == ("psn", "NPWR1"):
            report.versions.append(await _version(self.repo, "psn", "CUSA1", "ps4", "Halo Reach"))
        return report

    async def collect_name(self, name, *, link=True):
        self.asked.append(f"name:{name}")
        report = CollectReport("name", name)
        report.versions += [
            await _version(self.repo, "psn", "PPSA1", "ps5", "Halo Reach", "psn", "NPWR1"),
            await _version(self.repo, "steam", "9", "steam", "Halo Reach Firefight", "steam", "9"),
        ]
        return report

    async def collect_steam_app(self, appid, *, found, force=False):
        self.asked.append(f"product:steam:{appid}")
        return CollectReport("steam", appid)

    async def collect_hltb(self, hltb_id):
        self.asked.append(f"hltb:{hltb_id}")
        return CollectReport("hltb", str(hltb_id)), "Halo Reach"


def _linker(calls: list[list[int]]):
    """The matcher, as these tests need it: a version named as the game is
    that game; any other name is a game of its own."""

    async def link(repo: Repo, version_ids: list[int]) -> LinkReport:
        calls.append(sorted(version_ids))
        report = LinkReport()
        rows = [await repo.version_row(v) for v in version_ids]
        homes: dict[str, int] = {}
        for row in rows:
            if row and row["game_id"]:
                card = await repo.game_card(int(row["game_id"]))
                homes.setdefault(name_key(card["name"]), int(row["game_id"]))
        for row in rows:
            if row is None:
                continue
            key = name_key(str(row["name"]))
            game = homes.get(key)
            if game is None:
                game = await repo.create_game(str(row["name"]), 2010, int(row["version_id"]))
                homes[key] = game
            await repo.write_members({int(row["version_id"]): (game, "version", None, None)})
            report.games.setdefault(game, []).append(int(row["version_id"]))
        return report

    return link


async def _halo(repo: Repo) -> tuple[int, int]:
    v = await _version(repo, "steam", "976730", "steam", "Halo Reach", "steam", "976730")
    game = await repo.create_game("Halo Reach", 2010, v)
    await repo.write_members({v: (game, "version", None, None)})
    return game, v


async def _consoles(repo: Repo, game: int) -> set[str]:
    return {
        str((await repo.version_row(v))["console"]) for v in await repo.versions_of_games([game])
    }


async def test_an_achievement_leads_to_its_game_assembled_whole(repo: Repo) -> None:
    game, _v = await _halo(repo)
    stub = Stub(repo)
    octopus = OctopusCollector(repo, stub, linker=_linker([]))  # type: ignore[arg-type]
    await octopus.enqueue("achievement:steam:976730:ACH_1")
    report = await octopus.run()
    assert len(report.games) == 1
    assembled = report.games[0]
    assert assembled.game_id == game
    # Round 1: its list and the search; round 2: the PS5 version's list,
    # which leads to PS4; round 3: PS4 has nothing more — the game is whole.
    assert (assembled.versions_before, assembled.versions_after) == (1, 3)
    assert assembled.rounds == 3
    assert await _consoles(repo, game) == {"steam", "ps5", "ps4"}
    # The other game was kept, in a game of its own, and never expanded.
    assert list_key("steam", "9") not in stub.asked
    assert stub.asked.count("name:halo reach") == 1


async def test_another_entry_to_the_same_game_does_not_assemble_it_again(repo: Repo) -> None:
    game, _v = await _halo(repo)
    stub = Stub(repo)
    octopus = OctopusCollector(repo, stub, linker=_linker([]))  # type: ignore[arg-type]
    await octopus.enqueue(game_key(game))
    await octopus.run()
    stub.asked.clear()
    # The PS5 list leads to the same game, assembled a moment ago: not due.
    await octopus.enqueue(list_key("psn", "NPWR1"))
    report = await octopus.run()
    assert report.skipped == 1 and not report.games


async def test_an_entry_that_leads_nowhere_is_no_error(repo: Repo) -> None:
    octopus = OctopusCollector(repo, Stub(repo), linker=_linker([]))  # type: ignore[arg-type]
    await octopus.enqueue(game_key(999))
    await octopus.enqueue("dlc:12345")
    report = await octopus.run()
    assert report.gone == 2 and not report.failed
    assert await repo.octopus_waiting() == 0


async def test_a_name_is_one_entry_per_game_it_finds(repo: Repo) -> None:
    """ "Halo Reach" finds the game and another one: each becomes an entry of
    its own, assembled by itself."""
    octopus = OctopusCollector(repo, Stub(repo), linker=_linker([]))  # type: ignore[arg-type]
    await octopus.enqueue(search_key("Halo Reach"))
    report = await octopus.run(limit=1)
    assert report.queued == 2
    assert await repo.octopus_waiting() == 2


async def test_an_hltb_page_leads_to_the_versions_it_is_linked_to(repo: Repo) -> None:
    game, v = await _halo(repo)
    await repo._conn.execute(
        "INSERT INTO hltb_entries (hltb_id, name, checked_at) VALUES (7, 'Halo: Reach', 'now')"
    )
    await repo._conn.execute(
        "INSERT INTO version_hltb (version_id, hltb_id, source) VALUES (?, 7, 'test')", (v,)
    )
    stub = Stub(repo)
    octopus = OctopusCollector(repo, stub, linker=_linker([]))  # type: ignore[arg-type]
    await octopus.enqueue("hltb:7")
    report = await octopus.run()
    assert stub.asked[0] == "hltb:7"
    assert len(report.games) == 1 and report.games[0].game_id == game
    assert report.games[0].hltb >= 1


def test_a_pasted_link_is_read_into_a_key() -> None:
    from bot.services.octopus import entry_key

    assert entry_key("https://store.steampowered.com/app/976730/Halo/") == "product:steam:976730"
    assert entry_key("https://howlongtobeat.com/game/10270") == "hltb:10270"
    assert (
        entry_key("https://store.playstation.com/ru-ru/concept/10000176") == "product:psn:10000176"
    )
    assert (
        entry_key("https://store.playstation.com/en-us/product/EP1018-PPSA22946_00-HARRYPOTTER17")
        == "storeid:psn_title:PPSA22946_00"
    )
    assert (
        entry_key("https://www.xbox.com/en-US/games/store/halo/9nblggh4r315/0001")
        == "storeid:xbox_product:9NBLGGH4R315"
    )
    assert entry_key("list:psn:NPWR1") == "list:psn:NPWR1"
    assert entry_key("Halo Reach") == search_key("Halo Reach")
    assert entry_key("https://example.com/whatever") is None


async def test_a_store_id_leads_to_its_version(repo: Repo) -> None:
    game, v = await _halo(repo)
    await repo.add_store_ids(v, [("xbox_product", "9NBLGGH4R315")])
    octopus = OctopusCollector(repo, Stub(repo), linker=_linker([]))  # type: ignore[arg-type]
    await octopus.enqueue("storeid:xbox_product:9nblggh4r315")
    report = await octopus.run(limit=1)
    assert len(report.games) == 1 and report.games[0].game_id == game


async def test_a_bundle_series_and_account_spread_into_what_they_hold(repo: Repo) -> None:
    game, v = await _halo(repo)
    other = await _version(repo, "steam", "620", "steam", "Portal 2", "steam", "620")
    edition = await repo.save_edition("steam", "sub:1", "Two games", "bundle", scope="bundle")
    await repo.save_edition_item(edition, "620", "Portal 2", "game", version_id=other, role="part")
    await repo.save_edition_item(edition, "976730", "Halo", "game", version_id=v, role="part")
    series = await repo.create_series("Halo")
    await repo.set_series_member(game, series, True)
    await repo._conn.execute(
        "INSERT INTO accounts (platform, external_id, first_seen_at, updated_at)"
        " VALUES ('steam', '765', 'now', 'now')"
    )
    await repo._conn.execute(
        "INSERT INTO seen_achievements (xuid, title_id, achievement_id, name, platform,"
        " created_at) VALUES ('765', '620', 'A', 'a', 'steam', 'now')"
    )
    octopus = OctopusCollector(repo, Stub(repo), linker=_linker([]))  # type: ignore[arg-type]
    assert await octopus._held("edition", str(edition)) == [
        list_key("steam", "976730"),
        list_key("steam", "620"),
    ]
    assert await octopus._held("series", str(series)) == [game_key(game), search_key("Halo")]
    assert await octopus._held("account", "steam:765") == [list_key("steam", "620")]
    # Run, a spreading entry is handled by queueing what it holds.
    await octopus.enqueue(f"series:{series}")
    report = await octopus.run(limit=1)
    assert report.spread == 1 and report.queued == 2 and not report.games


async def test_the_bots_worker_takes_its_share_and_zero_is_off(repo: Repo) -> None:
    from bot.poller.octopus import PER_TICK_KEY, OctopusWorker

    await _halo(repo)
    octopus = OctopusCollector(repo, Stub(repo), linker=_linker([]))  # type: ignore[arg-type]
    for n in range(3):
        await octopus.enqueue(game_key(999 + n))
    # Store collection is off by default: the worker rests.
    await repo.set_app_setting(PER_TICK_KEY, "2")
    await OctopusWorker(repo, octopus).tick()
    assert await repo.octopus_waiting() == 3
    await repo.set_app_setting(STORE_COLLECTION_KEY, "1")
    await repo.set_app_setting(PER_TICK_KEY, "0")
    await OctopusWorker(repo, octopus).tick()
    assert await repo.octopus_waiting() == 3
    await repo.set_app_setting(PER_TICK_KEY, "2")
    await OctopusWorker(repo, octopus).tick()
    assert await repo.octopus_waiting() == 1


async def test_a_list_collected_for_the_bot_is_queued_for_the_octopus(repo: Repo) -> None:
    from bot.services.store_collect import StoreCollector

    collector = StoreCollector(repo)

    async def collect(platform, title_id, *, force=False, link=True):
        return CollectReport(platform, title_id)

    collector.collect = collect  # type: ignore[method-assign]
    await collector._collect_logged("psn", "NPWR1", reason="page")
    assert await repo.octopus_due(5) == []  # store collection off by default
    await repo.set_app_setting(STORE_COLLECTION_KEY, "1")
    await collector._collect_logged("psn", "NPWR1", reason="page")
    assert await repo.octopus_due(5) == [(list_key("psn", "NPWR1"), "page")]


async def test_the_admin_home_tells_how_the_octopus_is_getting_on(repo: Repo) -> None:
    from bot.poller import octopus as worker
    from bot.poller.octopus import OctopusWorker
    from bot.services.admin_status import octopus_status

    game, _v = await _halo(repo)
    octopus = OctopusCollector(repo, Stub(repo), linker=_linker([]))  # type: ignore[arg-type]
    await octopus.enqueue(game_key(game))
    for n in range(2):
        await octopus.enqueue(game_key(999 + n))
    status = await octopus_status(repo)
    assert (status.on, status.queue, status.retrying) == (False, 3, 0)

    await repo.set_app_setting(STORE_COLLECTION_KEY, "1")
    before = (await octopus_status(repo)).hour
    await OctopusWorker(repo, octopus).tick()
    status = await octopus_status(repo)
    assert status.on and status.queue == 2
    assert status.hour == before + 1
    assert worker.last_game is not None and status.last_name == worker.last_game.name
