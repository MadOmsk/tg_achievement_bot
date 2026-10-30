"""The store side of a game (#147, stage 2): parsing each store's answer, the
fetch schedule, and one collection end to end — no real network."""

from __future__ import annotations

from datetime import timedelta

import pytest

from bot.db.repo import Repo
from bot.services import store_collect
from bot.services.store_collect import CollectReport, StoreCollector
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


def test_xbox_cross_gen_set_is_kept_apart_from_the_product_group() -> None:
    """2026-10-11: a cross-gen set is one game; a product group can be a
    series (FF7 Remake and Rebirth share one) — one field lost the other."""
    [one, _series] = xbox_catalog.parse_product(
        _xbox_product(ProductGroupId="GROUP", XboxCrossGenSetId="SET")
    )
    assert (one.store_group, one.cross_gen_set) == ("GROUP", "SET")


def test_bundles_and_collections_are_named_so() -> None:
    from bot.services.stores import edition_kind

    assert edition_kind("Cyberpunk 2077 & Phantom Liberty Bundle") == "bundle"
    assert edition_kind("BioShock: The Collection") == "collection"


async def test_a_second_list_never_takes_the_first_ones_place(repo) -> None:
    """A regional twin (another NPWR of the same PSN product) used to
    overwrite the version's list; it is kept beside it instead."""
    from bot.services.stores import StoreVersion

    version = StoreVersion(store="psn", product_id="204794", console="ps4", name="Game")
    first = await repo.save_version(version, platform="psn", title_id="NPWR00001_00")
    again = await repo.save_version(version, platform="psn", title_id="NPWR00002_00")

    assert first == again
    row = await repo.version_row(first)
    assert (row["platform"], row["title_id"]) == ("psn", "NPWR00001_00")
    lists = sorted(sid for kind, sid in await repo.store_ids_of(first) if kind == "list")
    assert lists == ["psn:NPWR00001_00", "psn:NPWR00002_00"]


def test_a_steam_apps_own_type_is_its_kind() -> None:
    """A launcher of one mode of another app (type "advertising") keeps that
    type, so the matcher reads it as a mode of its game (2026-10-12)."""
    data = {**STEAM_APP, "type": "advertising", "name": "Call of Duty: Black Ops II - Zombies"}
    assert steam_store.parse_app(data).kind == "advertising"


# ------------------------------------------------------------ data fixes (2026-10-12)


def test_a_one_game_on_series_by_backward_compatibility_is_a_one_version() -> None:
    """879 "Series versions" were One games the store calls only compatible
    with Series; made for Series is what it calls optimized."""
    bc = _xbox_product(XboxConsoleGenOptimized=["ConsoleGen8"])
    [one] = xbox_catalog.parse_product(bc)
    assert (one.console, one.also_on) == ("one", ["series"])
    both = _xbox_product(XboxConsoleGenOptimized=["ConsoleGen8", "ConsoleGen9"])
    assert [v.console for v in xbox_catalog.parse_product(both)] == ["one", "series"]
    series = _xbox_product(
        XboxConsoleGenCompatible=["ConsoleGen9"], XboxConsoleGenOptimized=["ConsoleGen9"]
    )
    assert [v.console for v in xbox_catalog.parse_product(series)] == ["series"]


def test_xbox_trailers_are_the_playable_streams() -> None:
    product = _xbox_product()
    product["LocalizedProperties"][0]["Videos"] = [
        {"Caption": "Old", "Uri": "http://xbox-mbr.xboxlive.com/a.ism/manifest"}
    ]
    product["LocalizedProperties"][0]["CMSVideos"] = [
        {
            "Caption": "Trailer",
            "HLS": "https://cdn/a.m3u8",
            "DASH": "https://cdn/a.mpd",
            "PreviewImage": {"Uri": "//store-images/p.png"},
        }
    ]
    [video] = xbox_catalog.parse_product(product)[0].media["videos"]  # type: ignore[misc]
    assert video == {
        "name": "Trailer",
        "url": "https://cdn/a.m3u8",
        "hls": "https://cdn/a.m3u8",
        "dash": "https://cdn/a.mpd",
        "poster": "https://store-images/p.png",
    }
    del product["LocalizedProperties"][0]["CMSVideos"]
    assert "videos" not in xbox_catalog.parse_product(product)[0].media


def _addon(big_id: str, parent: str) -> dict:
    return {
        "ProductId": big_id,
        "ProductType": "Durable",
        "LocalizedProperties": [{"ProductTitle": f"Add-on {big_id}"}],
        "MarketProperties": [
            {"RelatedProducts": [{"RelationshipType": "addOnParent", "RelatedProductId": parent}]}
        ],
    }


async def test_an_editions_add_on_of_another_game_is_not_this_games(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A collection of several games bundles each one's add-ons: only those
    naming this game as their parent are its DLC; one stored before goes."""
    game = _xbox_product(XboxConsoleGenOptimized=["ConsoleGen8", "ConsoleGen9"])
    edition = {
        "ProductId": "EDITION1",
        "ProductType": "Game",
        "DisplaySkuAvailabilities": [
            {
                "Sku": {
                    "Properties": {
                        "BundledSkus": [
                            {"BigId": "BR765873CQJD", "IsPrimary": True},
                            {"BigId": "MINE", "IsPrimary": False},
                            {"BigId": "THEIRS", "IsPrimary": False},
                        ]
                    }
                }
            }
        ],
    }
    catalog = {
        "EDITION1": edition,
        "MINE": _addon("MINE", "BR765873CQJD"),
        "THEIRS": _addon("THEIRS", "OTHERGAME"),
    }

    async def products_for_title(title_id: str) -> list[dict]:
        return [game]

    async def products(big_ids: list[str]) -> list[dict]:
        return [catalog[i] for i in big_ids if i in catalog]

    monkeypatch.setattr(store_collect.xbox_catalog, "products_for_title", products_for_title)
    monkeypatch.setattr(store_collect.xbox_catalog, "products", products)
    monkeypatch.setattr(StoreCollector, "_siblings", _nothing)
    await repo.upsert_title("1799887933", "The Witcher 3", "xbox_modern")
    # An earlier collection put the other game's add-on here.
    [one, _series] = xbox_catalog.parse_product(game)
    earlier = await repo.save_version(one, platform="xbox_modern", title_id="1799887933")
    await repo.save_dlc(earlier, xbox_catalog.parse_addon(catalog["THEIRS"]))  # type: ignore[arg-type]

    await StoreCollector(repo).collect("xbox_modern", "1799887933")
    cursor = await repo._conn.execute("SELECT DISTINCT store_id FROM dlcs ORDER BY store_id")
    assert [r[0] for r in await cursor.fetchall()] == ["MINE"]


async def _nothing(*_args: object, **_kw: object) -> None:
    return None


async def test_a_phantom_series_version_goes_into_the_one_version(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stored before the fix as One and Series, a One game now reads as One
    only: the Series row goes, what was decided about it kept on the One."""
    old = _xbox_product()  # compatible with both, no "optimized": two versions
    [one_v, series_v] = xbox_catalog.parse_product(old)
    one = await repo.save_version(one_v, platform="xbox_modern", title_id="1799887933")
    series = await repo.save_version(series_v, platform="xbox_modern", title_id="1799887933")
    other = await repo.save_version(
        steam_store.parse_app(STEAM_APP), platform=None, title_id=None, origin="store"
    )
    await repo.save_decision(series, other, "same", features=None, model=None, decided_by="t")
    fixed = _xbox_product(XboxConsoleGenOptimized=["ConsoleGen8"])

    async def products_for_title(title_id: str) -> list[dict]:
        return [fixed]

    monkeypatch.setattr(store_collect.xbox_catalog, "products_for_title", products_for_title)

    async def no_products(ids) -> list[dict]:
        # The editions' bundled add-ons: none here (the test is about versions).
        return []

    monkeypatch.setattr(store_collect.xbox_catalog, "products", no_products)
    monkeypatch.setattr(StoreCollector, "_siblings", _nothing)
    await repo.upsert_title("1799887933", "The Witcher 3", "xbox_modern")
    report = await StoreCollector(repo).collect("xbox_modern", "1799887933")
    assert report.versions[:1] == [one]
    assert await repo.version_row(series) is None
    cursor = await repo._conn.execute("SELECT version_id, other_id FROM match_decisions")
    assert [tuple(r) for r in await cursor.fetchall()] == [(one, other)]


def test_a_psn_concepts_background_is_its_layer_art() -> None:
    concept = {
        "id": "1",
        "titleIds": ["CUSA00001_00"],
        "media": {
            "images": [
                {"type": "BACKGROUND_LAYER_ART", "url": "https://img/bg.png"},
                {"type": "MASTER", "url": "https://img/cover.png"},
            ],
            "videos": [
                {"url": "https://v/a.mp4", "hlsUrl": "https://v/a.m3u8", "posters": ["https://p"]}
            ],
        },
    }
    [version] = psn_store.parse_concept(concept)
    assert version.media["background"] == "https://img/bg.png"
    assert version.media["videos"] == [
        {"url": "https://v/a.mp4", "hls": "https://v/a.m3u8", "poster": "https://p"}
    ]


async def test_a_steam_store_name_waits_under_the_storefront_limiter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """2026-10-12: the localization walker asked the storefront outside the
    stores' limiter; it reads through `steam_store.app_details` now."""
    from bot.services.steam import client as steam_client

    asked: list[tuple[str, str]] = []

    async def app_details(appid: str, language: str = "english") -> dict | None:
        asked.append((appid, language))
        return {"name": "Ведьмак 3"}

    monkeypatch.setattr(steam_client.steam_store, "app_details", app_details)
    assert await steam_client.store_name("292030", "russian") == "Ведьмак 3"
    assert asked == [("292030", "russian")]


def test_a_steam_post_keeps_its_full_text() -> None:
    from bot.services import steam_news

    long_text = "word " * 2000
    assert steam_news.shorten(long_text) == long_text


async def test_a_price_change_is_not_a_change_of_the_game(repo: Repo) -> None:
    """Prices are dropped before an answer is kept (owner, 2026-10-12): a
    sale must not set the source's schedule back to a week."""

    def steam(price: int) -> dict:
        return {
            **STEAM_APP,
            "price_overview": {"currency": "USD", "final": price, "discount_percent": 10},
            "package_groups": [
                {
                    "save_text": "Save 10%",
                    "subs": [
                        {
                            "packageid": 1,
                            "option_text": f"Game - ${price / 100}",
                            "price_in_cents_with_discount": price,
                            "percent_savings": 10,
                        }
                    ],
                }
            ],
        }

    first = steam_store.without_prices(steam(3999))
    assert first is not None and "price_overview" not in first
    assert first["package_groups"][0]["subs"] == [{"packageid": 1}]
    assert await repo.save_payload("steam:1", "steam_store", first) is False
    assert (
        await repo.save_payload("steam:1", "steam_store", steam_store.without_prices(steam(1999)))
        is False
    )

    def xbox(price: float) -> list[dict]:
        product = _xbox_product()
        product["DisplaySkuAvailabilities"] = [
            {
                "Availabilities": [
                    {
                        "Actions": ["Purchase"],
                        "OrderManagementData": {"Price": {"ListPrice": price}},
                    }
                ],
                "HistoricalBestAvailabilities": [{"OrderManagementData": {"Price": {}}}],
            }
        ]
        return [product]

    assert xbox_catalog.without_prices(xbox(59.99)) == xbox_catalog.without_prices(xbox(19.99))
    [kept] = xbox_catalog.without_prices(xbox(59.99))
    assert kept["DisplaySkuAvailabilities"] == [
        {"Availabilities": [{"Actions": ["Purchase"], "OrderManagementData": {}}]}
    ]

    def psn(price: int) -> dict:
        return {
            "id": "1",
            "defaultProduct": {
                "firstPrice": {"price": price},
                "offers": {"skuRelevancy": []},
                "skus": [{"id": "S", "price": price, "displayPrice": f"${price}"}],
            },
        }

    assert psn_store.without_prices(psn(1999)) == {
        "id": "1",
        "defaultProduct": {"skus": [{"id": "S"}]},
    }


# ------------------------------------------------------------ availability (2026-10-12)


def _sku(*, trial: bool, actions: list[str], end: str = "9998-12-30T00:00:00Z") -> dict:
    return {
        "Sku": {"Properties": {"IsTrial": trial}},
        "Availabilities": [
            {
                "Actions": actions,
                "Conditions": {"StartDate": "2015-01-01T00:00:00Z", "EndDate": end},
            }
        ],
    }


def test_a_delisted_xbox_game_with_a_free_trial_is_off_sale() -> None:
    """The Crew: the trial SKU still offers "Purchase", the game's do not."""
    crew = {
        "DisplaySkuAvailabilities": [
            _sku(trial=True, actions=["Details", "Fulfill", "Purchase"]),
            _sku(trial=False, actions=["License", "Details"]),
        ]
    }
    assert not xbox_catalog.sold(crew)
    sold = {"DisplaySkuAvailabilities": [_sku(trial=False, actions=["Purchase"])]}
    assert xbox_catalog.sold(sold)
    ended = {
        "DisplaySkuAvailabilities": [
            _sku(trial=False, actions=["Purchase"], end="2020-01-01T00:00:00Z")
        ]
    }
    assert not xbox_catalog.sold(ended)


def test_psn_availability_is_a_full_game_sku_or_a_free_game() -> None:
    def concept(*skus: dict) -> dict:
        return {"defaultProduct": {"skus": list(skus)}}

    full = {"entitlements": [{"featureType": "FULL_GAME"}]}
    free = {"entitlements": [{"featureType": "TRIAL", "applicationType": "FREEMIUM_APP"}]}
    trial = {"entitlements": [{"featureType": "PLAY_FIRST_TRIAL"}], "fullPlayTimeTrial": 3600}
    assert psn_store.available(concept(full))
    assert psn_store.available(concept(free))
    assert psn_store.available(concept({"type": "PREORDER", "entitlements": []}))
    assert not psn_store.available(concept(trial))
    assert not psn_store.available({"categorizedProducts": [{"topCategory": "THEME"}]})


def test_a_steam_dlc_says_whether_it_is_sold() -> None:
    dlc = {"type": "dlc", "name": "Blood and Wine", "steam_appid": 378648, "is_free": False}
    assert steam_store.parse_dlc(dlc).on_sale is False
    sold = {**dlc, "package_groups": [{"subs": [{"packageid": 1}]}]}
    assert steam_store.parse_dlc(sold).on_sale is True


# ------------------------------------------------------------ Xbox 360 store pages (2026-10-12)


def _fission(big_id: str, hex_id: str, *, sells: bool, kind: str = "Game") -> dict:
    return {
        "ProductId": big_id,
        "ProductType": kind,
        "Properties": {"ProductGroupName": f"[Fission] Kameo ({hex_id})"},
        "LocalizedProperties": [{"ProductTitle": "Kameo", "PublisherName": "Xbox Game Studios"}],
        "DisplaySkuAvailabilities": [
            {
                "Sku": {"Properties": {"IsTrial": False}},
                "Availabilities": [{"Actions": ["Purchase"] if sells else ["License"]}],
            }
        ],
    }


def test_only_the_exact_fission_mark_names_a_360_game() -> None:
    assert xbox_catalog.fission_title_id(_fission("A", "4D5307D2", sells=True)) == "1297287122"
    assert (
        xbox_catalog.fission_title_id(_fission("A", "4D5307D2", sells=True, kind="Durable")) is None
    )
    loose = _fission("A", "4D5307D2", sells=True)
    loose["Properties"]["ProductGroupName"] = "Kameo 4D5307D2 pictures"
    assert xbox_catalog.fission_title_id(loose) is None


async def test_a_360_list_takes_its_compatible_product_as_its_store_page(repo: Repo) -> None:
    await repo.upsert_title("1297287122", "Kameo", "xbox_360")
    report = store_collect.CollectReport("xbox_360", "1297287122")
    collector = StoreCollector(repo)
    await collector._list_version("xbox_360", "1297287122", report)
    [stand_in] = report.versions
    # Seen in passing, in an edition's contents: the content twin and the seller.
    await collector._remember_x360(
        [
            _fission("BPVP56VRVLZ7", "4D5307D2", sells=False),
            _fission("BV83SM3191S5", "4D5307D2", sells=True),
        ]
    )
    row = await repo.version_row(stand_in)
    assert row is not None
    assert (row["store"], row["product_id"], row["console"], row["stand_in"]) == (
        "xbox",
        "BV83SM3191S5",
        "360",
        0,
    )
    assert row["release_date"] is None  # the product's day is its comeback's


async def test_a_titlehub_product_counts_only_when_its_mark_names_the_game(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bot.services.xbox.client import entry_from_json

    await repo.upsert_title("1297287122", "Kameo", "xbox_360")
    catalog = {
        "BV83SM3191S5": _fission("BV83SM3191S5", "4D5307D2", sells=True),
        "OTHER": _fission("OTHER", "58410955", sells=True),
    }

    async def products(big_ids: list[str]) -> list[dict]:
        return [catalog[i] for i in big_ids if i in catalog]

    monkeypatch.setattr(store_collect.xbox_catalog, "products", products)
    entry = entry_from_json(
        {
            "titleId": "1297287122",
            "name": "Kameo",
            "devices": ["Xbox360"],
            "productId": "OTHER",
            "detail": {"developerName": "Rare", "publisherName": "Microsoft"},
        }
    )
    collector = StoreCollector(repo)
    await collector.remember_title(entry)
    assert await repo.versions_of_title("xbox_360", "1297287122") == []
    # The stand-in takes titlehub's studio.
    report = store_collect.CollectReport("xbox_360", "1297287122")
    await collector._list_version("xbox_360", "1297287122", report)
    assert (await repo.version_row(report.versions[0]))["developer"] == "Rare"  # type: ignore[index]
    entry.product_ids = ["BV83SM3191S5"]
    await repo.make_fetch_due("x360:1297287122", "titlehub_product")
    await collector.remember_title(entry)
    [version] = await repo.versions_of_title("xbox_360", "1297287122")
    assert version["product_id"] == "BV83SM3191S5"


async def test_the_kept_answers_are_read_again_with_no_request(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`scripts/reparse_store_payloads.py`: what an old parser wrote (a
    phantom Series version, an answer with prices) is written again from the
    kept answer, and nothing asks a store."""

    async def no_request(*_a: object, **_kw: object) -> None:
        raise AssertionError("a store was asked")

    for name in ("products_for_title", "products", "search"):
        monkeypatch.setattr(store_collect.xbox_catalog, name, no_request)
    monkeypatch.setattr(store_collect.steam_store, "app_details", no_request)
    monkeypatch.setattr(store_collect.hltb_page, "fetch_page", no_request)

    await repo.upsert_title("1799887933", "The Witcher 3", "xbox_modern")
    old = _xbox_product()
    [one_v, series_v] = xbox_catalog.parse_product(old)
    await repo.save_version(one_v, platform="xbox_modern", title_id="1799887933")
    series = await repo.save_version(series_v, platform="xbox_modern", title_id="1799887933")
    kept = _xbox_product(XboxConsoleGenOptimized=["ConsoleGen8"])
    kept["DisplaySkuAvailabilities"] = [
        {
            "Availabilities": [
                {"Actions": ["Purchase"], "OrderManagementData": {"Price": {"ListPrice": 9}}}
            ]
        }
    ]
    await repo.save_payload("xbox_title:1799887933", "xbox_catalog", [kept])

    done = await StoreCollector(repo).reparse_stored()
    assert done["xbox versions"] == 1
    assert await repo.version_row(series) is None
    [again] = await repo.payload("xbox_title:1799887933", "xbox_catalog")
    assert (
        "Price"
        not in again["DisplaySkuAvailabilities"][0]["Availabilities"][0]["OrderManagementData"]
    )


def _bundle(product_id: str, *items: tuple[str, bool]) -> dict:
    return {
        "ProductId": product_id,
        "ProductType": "Game",
        "DisplaySkuAvailabilities": [
            {
                "Sku": {
                    "Properties": {"BundledSkus": [{"BigId": b, "IsPrimary": p} for b, p in items]}
                }
            }
        ],
    }


def test_a_bundle_is_read_from_what_it_holds() -> None:
    from bot.services.stores import classify_bundle

    # Monster Hunter Rise + Sunbreak: one game, no primary flag — an edition.
    assert classify_bundle("Monster Hunter Rise + Sunbreak", [("game", False), ("dlc", False)]) == (
        "edition",
        "complete",
        ["main", None],
    )
    # FIFA 16 Super Deluxe: FIFA primary, PvZ thrown in.
    assert classify_bundle(
        "FIFA 16 Super Deluxe Edition", [("dlc", False), ("game", False), ("game", True)]
    ) == ("edition", "deluxe", [None, "bonus", "main"])
    # The PopCap Bundle flags Garden Warfare primary, holds Peggle 2: its name
    # says it is a set.
    assert classify_bundle("PopCap Bundle", [("game", False), ("game", True)]) == (
        "bundle",
        "bundle",
        ["part", "part"],
    )
    # Several equal games.
    assert classify_bundle("EA Pack", [("game", False), ("game", False)]) == (
        "bundle",
        "bundle",
        ["part", "part"],
    )
    # Add-ons and currency only.
    assert classify_bundle("Season Pass", [("dlc", False), ("consumable", False)]) == (
        "addon_pack",
        "addon_pack",
        [None, None],
    )


async def test_xbox_bundles_are_kept_for_what_they_are(repo: Repo) -> None:
    """Owner, 2026-10-24: FIFA 16 Super Deluxe was listed among Plants vs.
    Zombies Garden Warfare's editions. Every game an item stands for keeps its
    version; its role says what it is to the bundle."""
    from bot.services.stores import StoreVersion

    async def game(product: str, name: str) -> int:
        return await repo.save_version(
            StoreVersion(store="xbox", product_id=product, console="one", name=name),
            platform=None,
            title_id=None,
        )

    fifa, pvz = await game("FIFA16", "FIFA 16"), await game("PVZGW", "PvZ Garden Warfare")
    items = [
        {"ProductId": "FIFA16", "ProductType": "Game"},
        {"ProductId": "PVZGW", "ProductType": "Game"},
        {"ProductId": "KO", "ProductType": "Durable"},
    ]
    editions = [
        _bundle("SUPERDELUXE", ("FIFA16", True), ("PVZGW", False), ("KO", False)),
        _bundle("EAPACK", ("FIFA16", False), ("PVZGW", False)),
        _bundle("PACK", ("KO", False)),
    ]
    await StoreCollector(repo)._xbox_editions(editions, items, CollectReport("x", "1"))
    cursor = await repo._conn.execute(
        "SELECT e.store_id, e.scope, i.store_id, i.version_id, i.role FROM edition_items i"
        " JOIN editions e ON e.edition_id = i.edition_id ORDER BY 1, 3"
    )
    assert [tuple(r) for r in await cursor.fetchall()] == [
        ("EAPACK", "bundle", "FIFA16", fifa, "part"),
        ("EAPACK", "bundle", "PVZGW", pvz, "part"),
        ("PACK", "addon_pack", "KO", None, None),
        ("SUPERDELUXE", "edition", "FIFA16", fifa, "main"),
        ("SUPERDELUXE", "edition", "KO", None, None),
        ("SUPERDELUXE", "edition", "PVZGW", pvz, "bonus"),
    ]


async def test_kept_editions_are_read_again_and_a_kind_set_by_hand_stays(repo: Repo) -> None:
    from bot.services.store_collect import classify_editions

    one = await repo.save_edition("xbox", "MHR", "Monster Hunter Rise + Sunbreak", "bundle")
    await repo.save_edition_item(one, "RISE", "Monster Hunter Rise", "game")
    await repo.save_edition_item(one, "SUNBREAK", "Sunbreak", "dlc")
    chosen = await repo.save_edition("xbox", "GOTY", "A Game: GOTY", "complete")
    await repo.save_edition_item(chosen, "G", "A Game", "game", is_primary=True)
    counts = await classify_editions(repo)
    assert counts == {"edition": 2}
    cursor = await repo._conn.execute(
        "SELECT e.store_id, e.scope, e.kind, i.role FROM editions e"
        " JOIN edition_items i ON i.edition_id = e.edition_id AND i.item_kind = 'game' ORDER BY 1"
    )
    assert [tuple(r) for r in await cursor.fetchall()] == [
        ("GOTY", "edition", "complete", "main"),  # the advisers' kind kept
        ("MHR", "edition", "complete", "main"),  # "bundle" was wrong: the game complete
    ]


async def test_saving_an_edition_again_keeps_what_it_was_read_to_be(repo: Repo) -> None:
    """The re-parse saves editions again in later steps (Xbox add-ons): a
    save that does not say its scope keeps the one read from its contents."""
    edition = await repo.save_edition("xbox", "B", "A Bundle", "bundle", scope="bundle")
    await repo.save_edition("xbox", "B", "A Bundle", None)
    cursor = await repo._conn.execute("SELECT scope FROM editions WHERE edition_id = ?", (edition,))
    assert (await cursor.fetchone())[0] == "bundle"


async def test_a_stored_xbox_answer_is_judged_on_sale_as_of_when_it_was_given(repo: Repo) -> None:
    """Each price period is an availability with its own end: a re-parse
    read later must not find every period over (2026-10-26)."""
    product = _xbox_product(XboxConsoleGenOptimized=["ConsoleGen8"])
    product["DisplaySkuAvailabilities"] = [
        _sku(trial=False, actions=["Purchase"], end="2026-10-15T09:59:59Z")
    ]
    assert xbox_catalog.sold(product, "2026-10-12T18:00:00+00:00")
    assert not xbox_catalog.sold(product, "2026-10-26T00:00:00+00:00")

    await repo.save_payload(
        "xbox_title:1799887933", "xbox_catalog", [product], fetched_at="2026-10-12T18:00:00+00:00"
    )
    await StoreCollector(repo).reparse_stored()
    [version] = await repo.versions_of_product("xbox", str(product["ProductId"]))
    assert version["on_sale"] == 1
    # The re-parse keeps when the answer was given.
    assert (
        await repo.payload_fetched_at("xbox_title:1799887933", "xbox_catalog")
        == "2026-10-12T18:00:00+00:00"
    )
