"""Steam moved its community images off Akamai (2026-10-17): the address
is mended where it is used — the schema, a cached schema, the post."""

from __future__ import annotations

from types import SimpleNamespace


def test_steams_old_image_host_is_mended() -> None:
    # A game released lately has no icon on Akamai any more (2026-10-17):
    # "Thank You Bus Driver" went to the chat as text only.
    from bot.services import images

    old = "https://steamcdn-a.akamaihd.net/steamcommunity/public/images/apps/5067360/ddb2.jpg"
    assert images.current_url(old) == (
        "https://shared.fastly.steamstatic.com/community_assets/images/apps/5067360/ddb2.jpg"
    )
    other = "https://images-eds-ssl.xboxlive.com/image?url=x"
    assert images.current_url(other) == other


async def test_a_post_asks_telegram_for_the_steam_icon_where_it_is_now(repo, monkeypatch) -> None:
    from bot.poller.publisher import _gallery

    row = SimpleNamespace(
        icon_url="https://steamcdn-a.akamaihd.net/steamcommunity/public/images/apps/1/a.jpg",
        is_secret=False,
    )
    assert _gallery([row]) == [
        ("https://shared.fastly.steamstatic.com/community_assets/images/apps/1/a.jpg", False)
    ]


async def test_a_cached_steam_schema_hands_out_the_current_icon_host(repo) -> None:
    from bot.db.repo import SteamSchemaAchievement
    from bot.services.steam import achievements

    await repo.steam_schema_cache_result(
        "1",
        None,
        [
            SteamSchemaAchievement(
                apiname="A",
                icon="https://steamcdn-a.akamaihd.net/steamcommunity/public/images/apps/1/a.jpg",
                hidden=False,
            )
        ],
    )
    schema = await achievements._schema(repo, "key", "1")
    assert schema[0].icon.startswith("https://shared.fastly.steamstatic.com/community_assets/")
