"""A game is its platform and its id (#147, migration 090): the id spaces of
Steam and Xbox overlap, and an Xbox game found to be the other generation
moves with its achievements instead of splitting."""

from __future__ import annotations

from bot.constants import Platform
from bot.db.repo import Repo


async def test_a_steam_and_an_xbox_game_with_one_id_are_two_games(repo: Repo) -> None:
    await repo.upsert_title("2154930", "Some Steam Game", Platform.STEAM)
    await repo.upsert_title("2154930", "Modern Warfare Remastered", Platform.XBOX_MODERN)

    assert await repo.title_name(Platform.STEAM, "2154930") == "Some Steam Game"
    assert await repo.title_name("xbox", "2154930") == "Modern Warfare Remastered"
    names = await repo.title_names([(Platform.STEAM, "2154930"), (Platform.XBOX_MODERN, "2154930")])
    assert set(names) == {(Platform.STEAM, "2154930"), (Platform.XBOX_MODERN, "2154930")}


async def test_a_game_found_to_be_360_moves_and_keeps_what_was_learned(repo: Repo) -> None:
    await repo.upsert_title("360", "Fable II", Platform.XBOX_MODERN, icon_url="https://art")
    await repo.record_hltb_match(Platform.XBOX_MODERN, "360", 42, 0.9)

    await repo.update_title_platform("360", Platform.XBOX_360)

    cursor = await repo._conn.execute(
        "SELECT platform, icon_url, platforms FROM achievement_list_connectors WHERE title_id = "
        "'360'"
    )
    rows = [tuple(row) for row in await cursor.fetchall()]
    assert rows == [("xbox_360", "https://art", '["Xbox360"]')]
    # Its HLTB entry is a link of its version, which went with it; so did the
    # time it was last asked about.
    assert await repo.list_hltb_match("xbox_360", "360") == (42, 0.9)
    # (an Xbox id is one game: either generation finds it)
    assert await repo.list_hltb_match("xbox_modern", "360") == (42, 0.9)
    cursor = await repo._conn.execute("SELECT subject FROM fetch_state WHERE source = 'hltb_match'")
    assert [r[0] for r in await cursor.fetchall()] == ["xbox_360:360"]


async def test_a_move_onto_an_existing_row_fills_its_gaps(repo: Repo) -> None:
    await repo.upsert_title("360", "Fable II", Platform.XBOX_360)
    await repo._conn.execute(
        "INSERT INTO achievement_list_connectors (platform, title_id, name, icon_url, updated_at)"
        " VALUES ('xbox_modern', '360', 'Fable II', 'https://art', '')"
    )
    await repo._conn.commit()

    await repo.update_title_platform("360", Platform.XBOX_360)

    cursor = await repo._conn.execute(
        "SELECT platform, icon_url FROM achievement_list_connectors WHERE title_id = '360'"
    )
    assert [tuple(row) for row in await cursor.fetchall()] == [("xbox_360", "https://art")]


async def test_a_move_takes_the_versions_of_its_list_with_it(repo: Repo) -> None:
    from bot.services.stores import StoreVersion

    await repo.upsert_title("360", "Fable II", Platform.XBOX_MODERN)
    version = await repo.save_version(
        StoreVersion(store="xbox", product_id="P1", console="one", name="Fable II"),
        platform="xbox_modern",
        title_id="360",
    )

    await repo.update_title_platform("360", Platform.XBOX_360)

    cursor = await repo._conn.execute(
        "SELECT platform, title_id FROM versions WHERE version_id = ?", (version,)
    )
    assert tuple(await cursor.fetchone()) == ("xbox_360", "360")
    assert [i for i in await repo.store_ids_of(version) if i[0] == "list"] == [
        ("list", "xbox_360:360")
    ]


async def test_a_360_game_named_through_the_modern_contract_stays_360(repo: Repo) -> None:
    await repo.upsert_title("360", "Fable II", Platform.XBOX_360)

    await repo.upsert_title("360", "Fable II", Platform.XBOX_MODERN, achievements_total=50)

    cursor = await repo._conn.execute(
        "SELECT platform, achievements_total FROM achievement_list_connectors WHERE title_id = "
        "'360'"
    )
    assert [tuple(row) for row in await cursor.fetchall()] == [("xbox_360", 50)]
