"""PlayStation store product pages: what is kept, where it goes (#147)."""

from __future__ import annotations

import json

from bot.db.repo import Repo
from bot.services import psn_products
from bot.services.stores import StoreVersion
from bot.services.stores import psn_product as page


def _page(product_id: str, name: str) -> str:
    info = {
        "cache": {
            f"Product:{product_id}": {
                "id": product_id,
                "name": name,
                "storeDisplayClassification": "OTHER",
                "releaseDate": "2024-11-26T16:00:00Z",
                "publisherName": "Frozen District",
                "localizedGenres": [{"value": "Simulation"}],
                "platforms": ["PS4"],
                "concept": {"__ref": "Concept:42"},
                "price": {"value": "$19.99"},
                "descriptions": [{"type": "LONG", "value": "Ten <br/>quests"}],
            }
        }
    }
    cta = {"cache": {"GameCTA:x": {"local": {"priceOrText": "$19.99"}}}}
    props = {
        "productId": product_id,
        "locale": "en-us",
        "batarangs": {
            "info": {"text": '<script type="application/json">' + json.dumps(info) + "</script>"},
            "cta": {"text": '<script type="application/json">' + json.dumps(cta) + "</script>"},
        },
    }
    data = {"props": {"pageProps": props}}
    ld = {"@type": "Product", "name": name, "category": "Add-on"}
    return (
        f'<script id="__NEXT_DATA__" type="application/json">'
        # As a real page escapes a script tag inside its JSON strings.
        f"{json.dumps(data).replace('</', '<' + chr(92) + '/')}</script>"
        f'<script type="application/ld+json">{json.dumps(ld)}</script>'
    )


def test_a_product_page_is_kept_without_prices_and_read_into_a_product() -> None:
    payload = page.extract(_page("UP1-CUSA1_00-ADDON", "Dine Out"))
    assert payload is not None
    assert "cta" not in payload["sections"] and "19.99" not in json.dumps(payload)
    product = page.parse_product(payload)
    assert (product.name, product.category, product.concept_id) == ("Dine Out", "Add-on", "42")
    assert (product.release_date, product.publisher, product.genres) == (
        "2024-11-26",
        "Frozen District",
        ["Simulation"],
    )
    assert product.description == "Ten \nquests" and product.platforms == ["PS4"]
    assert page.extract("<html>nothing</html>") is None


async def test_an_add_on_is_a_dlc_of_the_version_of_its_console(repo: Repo) -> None:
    ps4 = await repo.save_version(
        StoreVersion(
            store="psn", product_id="1", console="ps4", name="G", store_ids=[("psn_concept", "42")]
        ),
        platform=None,
        title_id=None,
        origin="played",
    )
    await repo.save_version(
        StoreVersion(
            store="psn", product_id="2", console="ps5", name="G", store_ids=[("psn_concept", "42")]
        ),
        platform=None,
        title_id=None,
        origin="played",
    )
    await repo.save_payload(
        "psn:42",
        "psn_store",
        {"categorizedProducts": [{"topCategory": "ADD_ON", "ids": ["UP1-CUSA1_00-ADDON"]}]},
    )
    await repo.save_payload(
        "psn_product:UP1-CUSA1_00-ADDON",
        "psn_product",
        page.extract(_page("UP1-CUSA1_00-ADDON", "Dine Out")),
    )
    report = await psn_products.put_in_place(repo, "played")
    assert report.dlcs == 1
    cursor = await repo._conn.execute("SELECT version_id, name, store_id FROM dlcs")
    assert [tuple(r) for r in await cursor.fetchall()] == [(ps4, "Dine Out", "UP1-CUSA1_00-ADDON")]


async def test_a_concept_of_many_add_ons_is_kept_as_a_list(repo: Repo, monkeypatch) -> None:
    """DEAD OR ALIVE 5 Last Round has a thousand add-ons, two seconds a page
    (owner, 2026-10-24): past `DLC_PAGES_MAX` only the game's pages are read,
    each add-on is a DLC by its id, and one page is read when wanted."""
    ps4 = await repo.save_version(
        StoreVersion(
            store="psn", product_id="1", console="ps4", name="G", store_ids=[("psn_concept", "42")]
        ),
        platform=None,
        title_id=None,
        origin="played",
    )
    many = [f"UP1-CUSA1_00-ADDON{i:03}" for i in range(psn_products.DLC_PAGES_MAX + 1)]
    await repo.save_payload(
        "psn:42",
        "psn_store",
        {
            "categorizedProducts": [
                {"topCategory": "GAME", "ids": ["UP1-CUSA1_00-GAME"]},
                {"topCategory": "ADD_ON", "ids": many},
            ]
        },
    )
    asked: list[str] = []

    async def fetch(product_id: str):
        asked.append(product_id)
        return page.extract(_page(product_id, f"Page of {product_id}"))

    monkeypatch.setattr(psn_products.page, "fetch_product", fetch)
    report = await psn_products.read_pages(repo, None)
    assert asked == ["UP1-CUSA1_00-GAME"]
    assert report.listed_only == len(many)

    placed = await psn_products.put_in_place(repo, None, {"42"})
    assert placed.dlcs == len(many) and placed.editions == 1
    cursor = await repo._conn.execute(
        "SELECT COUNT(*), COUNT(name) FROM dlcs WHERE version_id = ?", (ps4,)
    )
    assert tuple(await cursor.fetchone()) == (len(many), 0)

    # Wanted: one page read, the DLC named.
    assert await psn_products.read_one(repo, many[7])
    cursor = await repo._conn.execute("SELECT name FROM dlcs WHERE store_id = ?", (many[7],))
    assert (await cursor.fetchone())[0] == f"Page of {many[7]}"


async def test_put_in_place_keeps_to_the_concepts_it_is_given(repo: Repo) -> None:
    for concept, product in (("42", "1"), ("43", "2")):
        await repo.save_version(
            StoreVersion(
                store="psn",
                product_id=product,
                console="ps4",
                name="G",
                store_ids=[("psn_concept", concept)],
            ),
            platform=None,
            title_id=None,
            origin="played",
        )
        addon = f"UP1-CUSA{product}_00-ADDON"
        await repo.save_payload(
            f"psn:{concept}",
            "psn_store",
            {"categorizedProducts": [{"topCategory": "ADD_ON", "ids": [addon]}]},
        )
        await repo.save_payload(
            f"psn_product:{addon}", "psn_product", page.extract(_page(addon, f"DLC {concept}"))
        )
    report = await psn_products.put_in_place(repo, None, {"42"})
    assert report.dlcs == 1
