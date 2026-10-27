"""What HowLongToBeat says about a game, a version and a DLC, read through the
links (#147; owner, 2026-10-15)."""

from __future__ import annotations

from bot.db.repo import Repo
from bot.services.hltb_platforms import hltb_platform, platforms_of_group
from bot.services.stores import StoreDlc, StoreVersion, hltb_page


def _page(hltb_id: int, name: str, kind: str, main: int, platforms=(), groups=(), parent=0) -> dict:
    return {
        "game": [
            {
                "game_id": hltb_id,
                "game_name": name,
                "game_type": kind,
                "game_parent": parent,
                "comp_main": main,
                "comp_plus": main * 2,
                "comp_100": main * 3,
            }
        ],
        "platformData": [
            {"platform": p, "comp_main": m, "comp_plus": m * 2, "comp_100": m * 3, "count_comp": 5}
            for p, m in platforms
        ],
        "individuality": [
            {"platform": p, "comp_main": str(m), "comp_plus": "0", "comp_100": "0", "comp_all": "0"}
            for p, m in groups
        ],
    }


async def _entry(repo: Repo, *args, **kw) -> int:
    page = _page(*args, **kw)
    await repo.save_hltb_page(hltb_page.parse_page(page))  # type: ignore[arg-type]
    return int(page["game"][0]["game_id"])


async def _version(repo: Repo, product: str, console: str, game: int | None = None) -> int:
    version = await repo.save_version(
        StoreVersion(store="xbox", product_id=product, console=console, name="Control"),
        platform=None,
        title_id=None,
    )
    if game is not None:
        await repo._conn.execute(
            "UPDATE versions SET game_id = ?, role = 'version' WHERE version_id = ?",
            (game, version),
        )
        await repo._conn.commit()
    return version


def test_our_consoles_are_hltbs_platforms() -> None:
    assert hltb_platform("series") == "Xbox Series X/S" and hltb_platform("one") == "Xbox One"
    assert hltb_platform("360") == "Xbox 360" and hltb_platform("ps5") == "PlayStation 5"
    # A PC is a PC whoever sells it: Steam, the Microsoft Store, a store not known.
    assert hltb_platform("steam") == hltb_platform("pc") == "PC"
    assert hltb_platform("cloud") is None and hltb_platform(None) is None
    assert platforms_of_group("PC, PlayStation Vita , Xbox One") == [
        "PC",
        "PlayStation Vita",
        "Xbox One",
    ]


async def test_a_game_takes_the_hours_of_its_main_games_entry(repo: Repo) -> None:
    game = await repo.create_game("Control", 2019)
    xbox = await _version(repo, "X", "series", game)
    steam = await _version(repo, "S", "steam", game)
    dlc_entry = await _entry(repo, 20, "Control: The Foundation", "dlc", 3600, parent=10)
    main = await _entry(repo, 10, "Control", "game", 36000)
    other = await _entry(repo, 11, "Control Ultimate", "game", 40000)
    for version, entry, score in ((xbox, main, 0.9), (steam, main, 0.8), (xbox, other, 0.95)):
        await repo.link_version_hltb(version, entry, "auto", score)
    await repo.link_version_hltb(steam, dlc_entry, "auto", 0.99)

    found = await repo.game_hltb(game)

    # The surer score first would be Ultimate's; the game takes the entry two
    # versions share, and an additional content is never a game's main entry.
    assert found is not None
    assert found["entry"]["hltb_id"] == other  # 0.95 is the surest automatic link
    assert [e["hltb_id"] for e in found["others"]] == [main]
    # The operator's word outranks the score.
    await repo.link_version_hltb(steam, main, "manual")
    again = await repo.game_hltb(game)
    assert again is not None and again["entry"]["hltb_id"] == main
    assert await repo.game_hltb(game + 99) is None


async def test_a_version_takes_the_row_of_its_platform_or_the_group_that_has_it(repo: Repo) -> None:
    game = await repo.create_game("Control", 2019)
    series = await _version(repo, "X", "series", game)
    one = await _version(repo, "O", "one", game)
    ps5 = await _version(repo, "P", "ps5", game)
    cloud = await _version(repo, "C", "cloud", game)
    entry = await _entry(
        repo,
        10,
        "Control",
        "game",
        36000,
        platforms=[("Xbox Series X/S", 30000), ("PC", 40000)],
        groups=[("PlayStation 5, Xbox One", 33000)],
    )
    for v in (series, one, ps5, cloud):
        await repo.link_version_hltb(v, entry, "auto", 0.9)

    got = await repo.version_hltb_platform(series)
    assert got is not None and got["platform"] == "Xbox Series X/S"
    assert got["row"]["comp_main"] == 30000 and got["group"] is None
    # No row of its own for Xbox One or PlayStation 5: the group that names it.
    for version, name in ((one, "Xbox One"), (ps5, "PlayStation 5")):
        got = await repo.version_hltb_platform(version)
        assert got is not None and got["platform"] == name and got["row"] is None
        assert got["group"]["comp_main"] == 33000
    # The cloud has no platform: the entry alone.
    got = await repo.version_hltb_platform(cloud)
    assert got is not None and got["platform"] is None and got["row"] is None
    assert got["entry"]["hltb_id"] == entry
    unlinked = await _version(repo, "U", "one", game)
    assert await repo.version_hltb_platform(unlinked) is None


async def test_a_dlc_takes_its_entry_and_the_row_of_its_versions_platform(repo: Repo) -> None:
    game = await repo.create_game("Control", 2019)
    version = await _version(repo, "P", "ps4", game)
    await repo.save_dlc(version, StoreDlc(store_id="D1", name="The Foundation"))
    cursor = await repo._conn.execute("SELECT dlc_id FROM dlcs WHERE version_id = ?", (version,))
    dlc = int((await cursor.fetchone())[0])
    entry = await _entry(
        repo,
        20,
        "Control: The Foundation",
        "dlc",
        3600,
        platforms=[("PlayStation 4", 3000)],
        parent=10,
    )

    assert await repo.dlc_hltb_platform(dlc) is None
    await repo.link_dlc_hltb(dlc, entry)

    got = await repo.dlc_hltb_platform(dlc)
    assert got is not None and got["entry"]["comp_main"] == 3600  # the DLC's own hours
    assert got["platform"] == "PlayStation 4" and got["row"]["comp_main"] == 3000
    await repo.reject_dlc_hltb(dlc, entry)
    assert await repo.dlc_hltb_platform(dlc) is None


def test_the_repo_and_the_matcher_agree_on_what_is_additional_content() -> None:
    from bot.db.repo._hltb_read import _ADDITIONAL
    from bot.services.hltb_match import NOT_A_GAME

    assert {t.strip("' ") for t in _ADDITIONAL.strip("()").split(",")} == set(NOT_A_GAME)


async def test_the_full_poll_reads_the_pages_something_of_ours_reaches(
    repo: Repo, monkeypatch
) -> None:
    from scripts.poll_hltb import poll

    game = await repo.create_game("Control", 2019)
    version = await _version(repo, "X", "series", game)
    main = await _entry(repo, 10, "Control", "game", 36000)
    await repo.link_version_hltb(version, main, "auto", 0.9)
    # Its DLC entries are known from the game's page only (no page read), one is
    # ours; an entry nothing of ours reaches is left alone.
    page = _page(10, "Control", "game", 36000)
    page["relationships"] = [
        {"game_id": 21, "game_name": "The Foundation", "game_type": "dlc", "comp_main": 3600},
        {"game_id": 22, "game_name": "AWE", "game_type": "dlc", "comp_main": 7200},
    ]
    await repo.save_hltb_page(hltb_page.parse_page(page))  # type: ignore[arg-type]
    await repo._conn.execute(
        "INSERT INTO hltb_entries (hltb_id, name, game_type, checked_at)"
        " VALUES (99, 'Elsewhere', 'dlc', 'x')"
    )
    await repo._conn.commit()

    assert await repo.hltb_pages_to_read() == [21, 22]  # additional content of a game we have
    assert await repo.hltb_pages_to_read(limit=1) == [21]

    pages = {
        21: _page(21, "Control: The Foundation", "dlc", 3600, platforms=[("PC", 3000)], parent=10),
        22: None,  # HLTB has no such page
    }

    async def fake_fetch(hltb_id: int):
        if hltb_id == 22:
            return None
        return pages[hltb_id]

    monkeypatch.setattr(hltb_page, "fetch_page", fake_fetch)
    done = await poll(repo, [21, 22], stop_after=3)

    assert done == {"read": 1, "gone": 1, "failed": 0}
    assert await repo.hltb_pages_to_read() == []  # the page that is not there is not asked again
    cursor = await repo._conn.execute("SELECT COUNT(*) FROM hltb_platform_times WHERE hltb_id = 21")
    assert (await cursor.fetchone())[0] == 1


async def test_the_poll_stops_when_the_site_keeps_refusing(repo: Repo, monkeypatch) -> None:
    from scripts.poll_hltb import poll

    async def refuse(hltb_id: int):
        raise RuntimeError("429")

    monkeypatch.setattr(hltb_page, "fetch_page", refuse)
    done = await poll(repo, [1, 2, 3, 4, 5], stop_after=2)
    assert done == {"read": 0, "gone": 0, "failed": 2}
