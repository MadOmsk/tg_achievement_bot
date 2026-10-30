"""An HLTB page read into entries (#147): a game's page, a DLC's page, and
which of them may say what about whom — no network."""

from __future__ import annotations

from bot.db.repo import Repo
from bot.services.stores import hltb_page


def _page(game_id: int, name: str, kind: str, parent: int = 0, related=(), main=36000) -> dict:
    return {
        "game": [
            {
                "game_id": game_id,
                "game_name": name,
                "game_type": kind,
                "game_parent": parent,
                "comp_main": main,
                "comp_main_avg": main,
            }
        ],
        "relationships": [
            {"game_id": i, "game_name": n, "game_type": t, "comp_main": 7200} for i, n, t in related
        ],
    }


GAME = _page(2127, "Cyberpunk 2077", "game", related=[(113203, "Phantom Liberty", "dlc")])
DLC = _page(
    113203,
    "Cyberpunk 2077: Phantom Liberty",
    "dlc",
    parent=2127,
    related=[(2127, "Cyberpunk 2077", "game")],
    main=72000,
)


def test_a_dlc_pages_own_game_is_its_parent_not_its_child() -> None:
    entry = hltb_page.parse_page(DLC)
    assert entry is not None
    assert entry.parent_hltb_id == 2127
    assert entry.parent is not None and entry.parent.hltb_id == 2127
    assert entry.children == []
    game = hltb_page.parse_page(GAME)
    assert game is not None and [c.hltb_id for c in game.children] == [113203]
    assert game.children[0].parent_hltb_id == 2127


async def _row(repo: Repo, hltb_id: int) -> dict:
    cursor = await repo._conn.execute(
        "SELECT game_type, parent_hltb_id, comp_main, page_read_at FROM hltb_entries"
        " WHERE hltb_id = ?",
        (hltb_id,),
    )
    return dict(await cursor.fetchone())


async def test_a_games_own_times_are_never_another_pages_averages(repo: Repo) -> None:
    await repo.save_hltb_page(hltb_page.parse_page(GAME))  # type: ignore[arg-type]
    own = await _row(repo, 2127)
    await repo.save_hltb_page(hltb_page.parse_page(DLC))  # type: ignore[arg-type]
    game, dlc = await _row(repo, 2127), await _row(repo, 113203)
    assert game["comp_main"] == own["comp_main"] and game["parent_hltb_id"] is None
    assert game["game_type"] == "game"
    assert (dlc["game_type"], dlc["parent_hltb_id"]) == ("dlc", 2127)
    assert dlc["page_read_at"] is not None
    assert dlc["comp_main"] == 72000  # its own page's hours, not the game page's average


async def test_a_game_once_taken_for_its_dlcs_child_is_put_right(repo: Repo) -> None:
    """The old reading stored Cyberpunk 2077 as Phantom Liberty's child;
    reading the DLC's page again (its own page never read) undoes it."""
    await repo._conn.execute(
        "INSERT INTO hltb_entries (hltb_id, name, game_type, parent_hltb_id, checked_at)"
        " VALUES (2127, 'Cyberpunk 2077', 'game', 113203, '2026-10-01')"
    )
    await repo.save_hltb_page(hltb_page.parse_page(DLC))  # type: ignore[arg-type]
    assert (await _row(repo, 2127))["parent_hltb_id"] is None


# ------------------------------------------- the whole page, in fields (2026-10-15)

FULL = {
    "game": [
        {
            "game_id": 10779,
            "game_name": "Ultimate Marvel vs. Capcom 3",
            "game_alias": "UMvC3",
            "game_type": "game",
            "game_parent": 0,
            "game_image": "10779_Ultimate.jpg",
            "game_name_date": 0,
            "profile_steam": 357190,
            "profile_steam_alt": 0,
            "profile_itch": 0,
            "profile_ign": "2793dde8",
            "profile_dev": "Capcom, Eighting",
            "profile_pub": "Capcom",
            "profile_genre": "Fighting",
            "profile_platform": "PC, PlayStation 3, Xbox 360",
            "profile_summary": "  Fight.\n ",
            "release_world": "2011-11-15",
            "release_na": "2011-11-15",
            "release_eu": "2011-11-18",
            "release_jp": "0000-00-00",
            "rating_esrb": "T",
            "rating_pegi": "",
            "rating_cero": "",
            "review_score": 79,
            "comp_main": 4764,
            "comp_main_avg": 5000,
            "comp_main_med": 4700,
            "comp_main_h": 9000,
            "comp_main_l": 600,
            "comp_main_count": 40,
            "comp_plus": 43964,
            "comp_100": 348420,
            "comp_all": 19231,
            "invested_co": 144000,
            "invested_co_count": 3,
            "invested_mp": 102580,
            "comp_speed": 0,
            "comp_lvl_sp": 1,
            "comp_lvl_co": 0,
            "count_comp": 93,
            "count_backlog": 331,
            "count_playing": 3,
            "count_retired": 50,
            "added_stats": "2026-09-03 19:52:29",
        }
    ],
    "platformData": [
        {
            "platform": "PC",
            "comp_main": 8104,
            "comp_plus": 50795,
            "comp_100": 0,
            "comp_low": 630,
            "comp_high": 108240,
            "count_comp": 51,
            "count_total": 302,
        },
        {"platform": "Xbox 360", "comp_main": 5355, "count_comp": 18, "count_total": 85},
    ],
    "individuality": [
        {
            "platform": "PC, PlayStation Vita",
            "comp_main": "5946",
            "comp_plus": "32654",
            "comp_100": "241200",
            "comp_all": "20766",
            "compare": "5.0000",
            "count_comp": "113",
        }
    ],
    "relationships": [
        {
            "game_id": 111,
            "game_name": "Costume Pack",
            "game_type": "dlc",
            "comp_main": 3600,
            "comp_all_count": 7,
            "count_backlog": 2,
            "review_score": 70,
        },
        {"game_id": 222, "game_name": "UMvC3 Collection", "game_type": "compil", "comp_main": 0},
    ],
    "userReviews": {"80": "90", "70": "63", "60": None, "review_count": 274},
}


def test_the_page_is_read_into_every_field_it_gives() -> None:
    entry = hltb_page.parse_page(FULL)
    assert entry is not None
    row = entry.row
    assert (row["name"], row["alias"], row["game_type"]) == (
        "Ultimate Marvel vs. Capcom 3",
        "UMvC3",
        "game",
    )
    assert (row["image"], row["steam_appid"], row["ign_id"]) == (
        "10779_Ultimate.jpg",
        357190,
        "2793dde8",
    )
    assert row["parent_hltb_id"] is None and row["steam_alt"] is None  # 0 is no id
    assert (row["developer"], row["publisher"], row["genres"]) == (
        "Capcom, Eighting",
        "Capcom",
        "Fighting",
    )
    assert row["summary_en"] == "Fight."
    assert (row["release_world"], row["release_eu"], row["release_jp"]) == (
        "2011-11-15",
        "2011-11-18",
        None,  # "0000-00-00" is no date
    )
    assert (row["rating_esrb"], row["rating_pegi"], row["review_score"]) == ("T", None, 79)
    # Hours stay seconds; an amount of time HLTB left at 0 is none, a count is a count.
    assert (row["comp_main"], row["comp_main_med"], row["comp_main_count"]) == (4764, 4700, 40)
    assert row["comp_speed"] is None and row["comp_lvl_sp"] == 1 and row["comp_lvl_co"] == 0
    assert (row["invested_co"], row["invested_co_count"], row["invested_mp"]) == (144000, 3, 102580)
    assert (
        row["count_comp"],
        row["count_backlog"],
        row["count_playing"],
        row["count_retired"],
    ) == (
        93,
        331,
        3,
        50,
    )
    assert row["added_stats"] == "2026-09-03 19:52:29" and row["review_count"] == 274
    assert entry.release_year == 2011 and entry.image_url.endswith("/10779_Ultimate.jpg")
    assert entry.platforms == ["PC", "PlayStation 3", "Xbox 360"]


def test_the_platform_rows_groups_and_scores_are_read() -> None:
    entry = hltb_page.parse_page(FULL)
    assert entry is not None
    pc = next(r for r in entry.platform_rows if r["platform"] == "PC")
    assert (pc["comp_main"], pc["comp_100"], pc["comp_low"], pc["count_total"]) == (
        8104,
        None,
        630,
        302,
    )
    assert [r["platform"] for r in entry.platform_rows] == ["PC", "Xbox 360"]
    (group,) = entry.groups
    assert group["platforms"] == "PC, PlayStation Vita"
    assert (group["comp_main"], group["compare"], group["count_comp"]) == (5946, 5.0, 113)
    assert entry.reviews == {80: 90, 70: 63}


def test_only_additional_content_is_the_pages_child() -> None:
    entry = hltb_page.parse_page(FULL)
    assert entry is not None
    assert [(c.hltb_id, c.parent_hltb_id) for c in entry.children] == [(111, 10779)]
    assert [(c.hltb_id, c.parent_hltb_id) for c in entry.others] == [(222, None)]
    assert (
        entry.children[0].row["comp_all_count"] == 7 and entry.children[0].row["count_backlog"] == 2
    )


async def test_the_whole_page_is_saved_and_a_second_reading_replaces_it(repo: Repo) -> None:
    await repo.save_hltb_page(hltb_page.parse_page(FULL))  # type: ignore[arg-type]
    cursor = await repo._conn.execute(
        "SELECT release_year, image_url, comp_main, count_backlog, review_count FROM hltb_entries"
        " WHERE hltb_id = 10779"
    )
    assert tuple(await cursor.fetchone()) == (
        2011,
        "https://howlongtobeat.com/games/10779_Ultimate.jpg",
        4764,
        331,
        274,
    )
    for table, expected in (
        ("hltb_platform_times", 2),
        ("hltb_platform_groups", 1),
        ("hltb_entry_platforms", 3),
        ("hltb_review_scores", 2),
        ("hltb_related", 1),
    ):
        cursor = await repo._conn.execute(f"SELECT COUNT(*) FROM {table}")
        assert (await cursor.fetchone())[0] == expected, table
    # The entry the page names carries what its row says, and no page of its own.
    cursor = await repo._conn.execute(
        "SELECT game_type, parent_hltb_id, comp_main, count_backlog, page_read_at"
        " FROM hltb_entries WHERE hltb_id = 111"
    )
    assert tuple(await cursor.fetchone()) == ("dlc", 10779, 3600, 2, None)

    changed = dict(FULL, platformData=[FULL["platformData"][0]])
    await repo.save_hltb_page(hltb_page.parse_page(changed))  # type: ignore[arg-type]
    cursor = await repo._conn.execute("SELECT COUNT(*) FROM hltb_platform_times")
    assert (await cursor.fetchone())[0] == 1


def test_the_parser_and_the_table_name_the_same_columns() -> None:
    import re

    from bot.db.repo._database import GAMES_SCHEMA_PATH

    ddl = GAMES_SCHEMA_PATH.read_text(encoding="utf-8")
    block = ddl[ddl.index("CREATE TABLE hltb_entries (") :]
    block = block[: block.index(");")]
    columns = set(re.findall(r"^\s+(\w+) (?:BIGINT|TEXT|DOUBLE PRECISION)", block, re.MULTILINE))
    assert {column for _page, column, _kind in hltb_page.ENTRY_FIELDS} <= columns
    assert {
        "hltb_id",
        "review_count",
        "summary_ru",
        "summary_ru_of",
        "checked_at",
        "page_read_at",
    } <= columns
