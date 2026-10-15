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
