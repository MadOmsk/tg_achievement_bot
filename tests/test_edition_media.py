"""An edition's pictures, each store's tag kept (#147)."""

from __future__ import annotations

from bot.db.repo import Repo
from bot.services import edition_media


def test_each_stores_pictures_keep_their_tags_and_name_a_cover() -> None:
    xbox = edition_media.xbox(
        {
            "LocalizedProperties": [
                {
                    "Images": [
                        {"ImagePurpose": "TitledHeroArt", "Uri": "//x/hero"},
                        {"ImagePurpose": "BoxArt", "Uri": "//x/box"},
                    ]
                }
            ]
        }
    )
    assert xbox["cover"] == "https://x/box"
    assert [i["tag"] for i in xbox["images"]] == ["TitledHeroArt", "BoxArt"]
    psn = edition_media.psn(
        {
            "media": [
                {"type": "IMAGE", "role": "MASTER", "url": "p/m"},
                {"type": "VIDEO", "url": "v"},
            ]
        }
    )
    assert psn == {"cover": "p/m", "images": [{"tag": "MASTER", "url": "p/m"}]}
    steam = edition_media.steam({"header_image": "s/h", "page_image": "s/p"})
    assert edition_media.cover_url(steam) == "s/h"
    assert [i["tag"] for i in steam["images"]] == ["header_image", "page_image"]
    assert edition_media.cover_url({}) is None


async def test_an_editions_pictures_are_kept_and_its_cover_asked_once(repo: Repo) -> None:
    edition = await repo.save_edition(
        "xbox", "B1", "Deluxe", "deluxe", media={"cover": "https://x/box"}
    )
    (row,) = await repo.edition_covers_to_fetch()
    assert row["edition_id"] == edition
    await repo.set_edition_cover(edition, None, None)
    assert await repo.edition_covers_to_fetch() == []
    # A later sighting with no pictures keeps the ones known.
    await repo.save_edition("xbox", "B1", "Deluxe", "deluxe")
    assert await repo.set_edition_media("xbox", "B1", {"cover": "https://x/new"})
