"""The Xbox add-ons sold only on their own (owner, 2026-10-27): no edition
lists them, so the catalog's add-on search finds them — a 360 game's above
all. No real network."""

from __future__ import annotations

import pytest

from bot.db.repo import Repo
from bot.services import store_collect
from bot.services.store_collect import StoreCollector
from bot.services.stores import xbox_catalog


def _product(big_id: str, kind: str, title: str, parent: str | None = None) -> dict:
    product: dict = {
        "ProductId": big_id,
        "ProductType": kind,
        "LocalizedProperties": [{"ProductTitle": title}],
        "MarketProperties": [{"RelatedProducts": []}],
    }
    if parent:
        product["MarketProperties"][0]["RelatedProducts"] = [
            {"RelationshipType": "addOnParent", "RelatedProductId": parent}
        ]
    return product


async def _dlc_names(repo: Repo, version_id: int) -> list[str]:
    cursor = await repo._conn.execute(
        "SELECT name FROM dlcs WHERE version_id = ? ORDER BY name", (version_id,)
    )
    return [row[0] for row in await cursor.fetchall()]


async def test_a_360_games_season_pass_is_its_dlc(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Gears of War 3's Season Pass names the 360 product as its parent; an
    add-on of another game the search also suggests is not its."""
    await repo.upsert_title("1297287339", "Gears of War 3", "xbox_360")
    report = store_collect.CollectReport("xbox_360", "1297287339")
    collector = StoreCollector(repo)
    await collector._list_version("xbox_360", "1297287339", report)
    [version] = report.versions
    await repo._conn.execute(
        "UPDATE versions SET store = 'xbox', product_id = 'BPKDQSSFQ9WV', stand_in = 0,"
        " console = '360' WHERE version_id = ?",
        (version,),
    )
    asked: list[str] = []

    async def search_addons(name: str) -> list[str]:
        asked.append(name)
        return ["BP0MGTDNQP50", "OTHER"]

    async def products(ids: list[str]) -> list[dict]:
        return [
            _product("BP0MGTDNQP50", "Durable", "Gears of War 3 Season Pass", "BPKDQSSFQ9WV"),
            _product("OTHER", "Durable", "Gears of War 4 Pack", "SOMETHINGELSE"),
        ]

    monkeypatch.setattr(xbox_catalog, "search_addons", search_addons)
    monkeypatch.setattr(xbox_catalog, "products", products)
    await collector._x360_addons("1297287339", report, force=False)
    assert asked == ["Gears of War 3"]
    assert await _dlc_names(repo, version) == ["Gears of War 3 Season Pass"]
    # Asked once until due.
    asked.clear()
    await collector._x360_addons("1297287339", report, force=False)
    assert asked == []


async def test_a_stand_in_without_a_store_page_asks_nothing(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    await repo.upsert_title("1297287122", "Kameo", "xbox_360")
    report = store_collect.CollectReport("xbox_360", "1297287122")
    collector = StoreCollector(repo)
    await collector._list_version("xbox_360", "1297287122", report)

    async def search_addons(name: str) -> list[str]:
        raise AssertionError("a stand-in has no product to be the parent of an add-on")

    monkeypatch.setattr(xbox_catalog, "search_addons", search_addons)
    await collector._x360_addons("1297287122", report, force=False)
