"""The store side of a game (#147, stage 2): parsing each store's answer, the
fetch schedule, and one collection end to end — no real network."""

from __future__ import annotations

from datetime import timedelta

import pytest

from bot.db.repo import Repo
from bot.services import store_collect
from bot.services.store_collect import StoreCollector
from bot.services.stores import psn_store, steam_store, xbox_catalog
from bot.util import utcnow

STEAM_APP = {
    "type": "game",
    "name": "The Witcher 3: Wild Hunt",
    "steam_appid": 292030,
    "is_free": False,
    "dlc": [355880, 378648],
    "short_description": "An RPG.",
    "developers": ["CD PROJEKT RED"],
    "publishers": ["CD PROJEKT RED"],
    "platforms": {"windows": True, "mac": False, "linux": False},
    "categories": [{"id": 2, "description": "Single-player"}],
    "genres": [{"id": "3", "description": "RPG"}],
    "release_date": {"coming_soon": False, "date": "18 May, 2015"},
    "header_image": "https://cdn/header.jpg",
}


def _xbox_product(**props: object) -> dict:
    return {
        "ProductId": "BR765873CQJD",
        "ProductType": "Game",
        "AlternateIds": [{"IdType": "XboxTitleId", "Value": "1799887933"}],
        "LocalizedProperties": [
            {
                "ProductTitle": "The Witcher 3: Wild Hunt",
                "DeveloperName": "CD PROJEKT RED",
                "PublisherName": "CD PROJEKT S.A.",
                "ShortDescription": "An RPG.",
                "Images": [{"ImagePurpose": "BoxArt", "Uri": "//store-images/box.png"}],
            }
        ],
        "MarketProperties": [
            {
                "OriginalReleaseDate": "2015-05-19T00:00:00.0000000Z",
                "RelatedProducts": [{"RelationshipType": "Bundle", "RelatedProductId": "EDITION1"}],
            }
        ],
        "Properties": {"XboxConsoleGenCompatible": ["ConsoleGen8", "ConsoleGen9"], **props},
        "DisplaySkuAvailabilities": [],
    }


def test_a_steam_app_reads_as_one_version() -> None:
    version = steam_store.parse_app(STEAM_APP, {"name": "Ведьмак 3", "short_description": "РПГ."})
    assert (version.store, version.product_id, version.console) == ("steam", "292030", "steam")
    assert version.name_ru == "Ведьмак 3"
    assert version.release_date == "2015-05-18"
    assert version.developer == "CD PROJEKT RED"
    assert version.dlc_ids == ["355880", "378648"]
    assert not version.live_service


def test_steam_release_dates_that_are_not_a_day_are_none() -> None:
    assert steam_store.release_day("Q1 2027") is None
    assert steam_store.release_day("Coming soon") is None
    assert steam_store.release_day("Feb 8, 2024") == "2024-02-08"


def test_a_free_game_with_purchases_is_a_live_service() -> None:
    data = {**STEAM_APP, "is_free": True, "categories": [{"id": 35}]}
    assert steam_store.parse_app(data).live_service


def test_a_smart_delivery_product_is_a_version_per_console() -> None:
    versions = xbox_catalog.parse_product(_xbox_product())
    assert [v.console for v in versions] == ["one", "series"]
    assert versions[0].store_ids == [("xbox_product", "BR765873CQJD"), ("xbox_title", "1799887933")]
    assert versions[0].media["cover"] == "https://store-images/box.png"


def test_play_anywhere_pc_is_a_platform_of_the_version_not_a_version() -> None:
    product = _xbox_product()
    product["DisplaySkuAvailabilities"] = [{"Sku": {"Properties": {"XboxXPA": True}}}]
    versions = xbox_catalog.parse_product(product)
    assert [v.console for v in versions] == ["one", "series"]
    assert all(v.also_on == ["pc"] for v in versions)


def test_a_withdrawn_products_placeholder_date_is_no_date() -> None:
    product = _xbox_product()
    product["MarketProperties"][0]["OriginalReleaseDate"] = "9998-12-30T00:00:00.0000000Z"
    assert xbox_catalog.parse_product(product)[0].release_date is None


def test_an_edition_bundles_the_add_ons_and_only_durables_are_kept() -> None:
    edition = {
        "DisplaySkuAvailabilities": [
            {
                "Sku": {
                    "Properties": {
                        "BundledSkus": [
                            {"BigId": "BR765873CQJD", "IsPrimary": True},
                            {"BigId": "ADDON1", "IsPrimary": False},
                        ]
                    }
                }
            }
        ]
    }
    assert xbox_catalog.bundled([edition], "BR765873CQJD") == ["ADDON1"]
    durable = {
        "ProductId": "ADDON1",
        "ProductType": "Durable",
        "LocalizedProperties": [{"ProductTitle": "Blood and Wine"}],
    }
    coins = {
        "ProductId": "COINS",
        "ProductType": "Consumable",
        "LocalizedProperties": [{"ProductTitle": "Coins"}],
    }
    assert xbox_catalog.parse_addon(durable).name == "Blood and Wine"  # type: ignore[union-attr]
    assert xbox_catalog.parse_addon(coins) is None


def test_a_psn_concept_is_a_version_per_console() -> None:
    concept = {
        "id": "204794",
        "nameEn": "The Witcher 3",
        "publisherName": "CD PROJEKT RED S.A.",
        "releaseDate": {"date": "2022-12-14T05:00:00Z"},
        "titleIds": ["CUSA00527_00", "CUSA05574_00", "PPSA03972_00"],
        "categorizedProducts": [{"topCategory": "ADD_ON", "ids": ["UP4497-CUSA00527_00-DLCBOB"]}],
    }
    versions = psn_store.parse_concept(concept)
    assert [v.console for v in versions] == ["ps4", "ps5"]
    assert ("psn_title", "CUSA05574_00") in versions[0].store_ids
    assert versions[1].store_ids == [("psn_concept", "204794"), ("psn_title", "PPSA03972_00")]
    assert versions[0].release_date == "2022-12-14"


def test_search_results_name_their_title_ids() -> None:
    results = [{"result": {"defaultProduct": {"id": "UP4497-PPSA03972_00-00000000000GOTY7"}}}]
    assert psn_store.title_ids_in_search(results) == ["PPSA03972_00"]


async def test_an_answer_that_does_not_change_is_trusted_longer(repo: Repo) -> None:
    for expected in (7, 14, 30, 90, 90):
        await repo.record_fetch("steam:1", "steam_store", status="ok")
        cursor = await repo._conn.execute("SELECT interval_days FROM fetch_state")
        assert (await cursor.fetchone())["interval_days"] == expected
    await repo.record_fetch("steam:1", "steam_store", status="ok", changed=True)
    cursor = await repo._conn.execute("SELECT interval_days, next_check_at FROM fetch_state")
    row = await cursor.fetchone()
    assert row["interval_days"] == 7
    assert not await repo.fetch_due("steam:1", "steam_store")


async def test_three_failures_give_a_source_up_for_a_month(repo: Repo) -> None:
    for _ in range(3):
        await repo.record_fetch("xbox_title:1", "xbox_catalog", status="error", error="boom")
    cursor = await repo._conn.execute("SELECT status, next_check_at FROM fetch_state")
    row = await cursor.fetchone()
    assert row["status"] == "gave_up"
    assert row["next_check_at"] > (utcnow() + timedelta(days=29)).isoformat(timespec="seconds")


async def test_a_payload_says_whether_it_changed(repo: Repo) -> None:
    assert not await repo.save_payload(
        "steam:1", "steam_store", {"a": 1}
    )  # first: nothing to compare
    assert not await repo.save_payload("steam:1", "steam_store", {"a": 1})
    assert await repo.save_payload("steam:1", "steam_store", {"a": 2})
    assert await repo.payload("steam:1", "steam_store") == {"a": 2}


async def test_a_steam_game_is_collected_once_until_it_is_due(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[tuple[str, str]] = []

    async def app_details(appid: str, language: str = "english") -> dict | None:
        asked.append((appid, language))
        if appid == "292030":
            return STEAM_APP
        return {"type": "dlc", "name": f"DLC {appid}", "steam_appid": int(appid)}

    monkeypatch.setattr(store_collect.steam_store, "app_details", app_details)
    await repo.upsert_title("292030", "The Witcher 3", "steam")

    report = await StoreCollector(repo).collect("steam", "292030")
    # Its own store, then the other stores' versions (none here: no PSN client).
    assert report.asked == ["steam_store", "siblings"]
    assert report.dlcs == 2
    versions = await repo.versions_of_title("steam", "292030")
    assert [v["name"] for v in versions] == ["The Witcher 3: Wild Hunt"]
    cursor = await repo._conn.execute("SELECT name FROM dlcs ORDER BY name")
    assert [row["name"] for row in await cursor.fetchall()] == ["DLC 355880", "DLC 378648"]

    asked.clear()
    again = await StoreCollector(repo).collect("steam", "292030")
    assert asked == [] and again.skipped == ["steam_store", "siblings"]


async def test_dlc_past_a_pass_are_named_in_the_next(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(store_collect, "DLC_NAMES_PER_PASS", 1)

    async def app_details(appid: str, language: str = "english") -> dict | None:
        return (
            STEAM_APP
            if appid == "292030"
            else {"type": "dlc", "name": appid, "steam_appid": int(appid)}
        )

    monkeypatch.setattr(store_collect.steam_store, "app_details", app_details)
    first = await StoreCollector(repo).collect("steam", "292030")
    assert first.dlcs == 1
    # More is left: the next pass is due within the hour, not in a week.
    cursor = await repo._conn.execute("SELECT next_check_at FROM fetch_state")
    assert (await cursor.fetchone())["next_check_at"] < (utcnow() + timedelta(hours=2)).isoformat(
        timespec="seconds"
    )
    second = await StoreCollector(repo).collect("steam", "292030", force=True)
    assert second.dlcs == 1


def test_an_editions_kind_is_read_from_its_name() -> None:
    from bot.services.stores import edition_kind

    assert edition_kind("Gears of War: E-Day Premium Edition Pre-Order") == "preorder"
    assert edition_kind("Gears of War: E-Day Premium Edition") == "premium"
    assert edition_kind("The Elder Scrolls V: Skyrim Anniversary Edition") == "anniversary"
    assert edition_kind("Gears of War: E-Day") == "standard"


def test_a_bundle_is_an_edition_with_its_contents() -> None:
    bundle = {
        "ProductId": "9PHPXPZ0JQ4T",
        "DisplaySkuAvailabilities": [
            {
                "Sku": {
                    "Properties": {
                        "BundledSkus": [
                            {"BigId": "9N4PT8HGCDHQ", "IsPrimary": True},
                            {"BigId": "9MT5FQC6WQ7M", "IsPrimary": False},
                        ]
                    }
                }
            }
        ],
    }
    assert xbox_catalog.bundle_items(bundle) == [("9N4PT8HGCDHQ", True), ("9MT5FQC6WQ7M", False)]
    assert xbox_catalog.bundle_items({"ProductId": "X"}) == []


def test_a_steam_apps_packages_are_its_editions() -> None:
    data = {
        "package_groups": [
            {"subs": [{"packageid": 110687}, {"packageid": 626153}]},
        ]
    }
    assert steam_store.package_ids(data) == ["110687", "626153"]


def test_a_product_off_sale_offers_no_purchase() -> None:
    on = {"DisplaySkuAvailabilities": [{"Availabilities": [{"Actions": ["Browse", "Purchase"]}]}]}
    off = {"DisplaySkuAvailabilities": [{"Availabilities": [{"Actions": ["Browse", "License"]}]}]}
    assert xbox_catalog.sold(on) and not xbox_catalog.sold(off)


def test_a_steam_apps_packages_off_sale_are_its_editions_too() -> None:
    data = {"package_groups": [{"subs": [{"packageid": 110687}]}], "packages": [110687, 12248]}
    assert steam_store.sold_package_ids(data) == ["110687"]
    assert steam_store.package_ids(data) == ["110687", "12248"]
    version = steam_store.parse_app({**STEAM_APP, "package_groups": [], "is_free": False})
    assert version.on_sale is False
