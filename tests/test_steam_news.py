"""Patch notes from Steam's announcements: what is a patch, and how it reads."""

from __future__ import annotations

from bot.services import steam_news as n


def _item(title: str, *, feed: str = "steam_community_announcements", tags=None) -> dict:
    return {
        "gid": title,
        "title": title,
        "date": 1790000000,
        "feedname": feed,
        "tags": tags,
        "contents": "[p]Fixed a crash.[/p][list][*]One[*]Two[/list][img]x[/img]",
    }


def test_the_developers_posts_are_kept_patches_marked() -> None:
    payload = {
        "appnews": {
            "newsitems": [
                _item("Update 11.10.0"),
                _item("See what's new in the Remastered!", tags=["patchnotes"]),
                _item("Behind the scenes"),
                _item("Cairn's demo update - live now!"),
                _item("Patch 3 is out", feed="PC Gamer"),
                _item("The Sinister Pack drops 9.18"),
            ]
        }
    }
    posts = n.parse_patches(payload)
    # Other sites' articles go; every post of the developer's stays, marked.
    assert {p.title for p in posts if p.kind == "patch"} == {
        "Update 11.10.0",
        "See what's new in the Remastered!",
    }
    assert {p.title for p in posts if p.kind == "news"} == {
        "Behind the scenes",
        "Cairn's demo update - live now!",
        "The Sinister Pack drops 9.18",
    }


def test_a_patch_carries_its_steam_id_and_plain_text() -> None:
    (patch,) = n.parse_patches({"appnews": {"newsitems": [_item("Hotfix 1.0.1")]}})
    assert patch.gid == "Hotfix 1.0.1"
    assert patch.text == "Fixed a crash.\n\n- One\n- Two"


def test_links_survive_as_label_and_address() -> None:
    text = n.plain_text("Read [url=https://example.com/notes]the notes[/url].")
    assert text == "Read [the notes](https://example.com/notes)."


def test_a_long_post_is_not_cut_inside_a_link() -> None:
    cut = n.shorten("word " * 5 + "[label](https://very.long/url/that/gets/cut", 40)
    assert "](" not in cut
    assert cut.endswith("…")


def test_a_games_extras_in_the_store_are_not_the_game() -> None:
    items = [
        {"id": 2765950, "type": "app", "name": "HELLDIVERS 2 - Armor Set"},
        {"id": 553850, "type": "app", "name": "HELLDIVERS 2"},
    ]
    assert n.pick_appid(items, ["HELLDIVERS™ 2"]) == 553850
    assert n.pick_appid([items[0]], ["HELLDIVERS™ 2"]) is None


def test_a_video_in_a_post_becomes_its_youtube_link() -> None:
    text = n.plain_text('[p]Hi[/p][previewyoutube="F23N860w9Og;full"][/previewyoutube][p]Bye[/p]')
    assert "https://www.youtube.com/watch?v=F23N860w9Og" in text.split("\n")


def test_a_table_in_a_post_becomes_rows_of_cells() -> None:
    text = n.plain_text(
        "[p]Intro[/p][table][tr][th]Name[/th][th]Value[/th][/tr]"
        "[tr][td]HP[/td][td]100[/td][/tr][/table][p]After[/p]"
    )
    assert "Name \u00a6 Value\nHP \u00a6 100" in text


def test_a_post_keeps_its_first_picture() -> None:
    assert n.first_image("[p]Hi[/p][img]{STEAM_CLAN_IMAGE}/42/a.png[/img][img]b[/img]") == (
        "https://clan.akamai.steamstatic.com/images/42/a.png"
    )
    assert n.first_image("[img]http://old.example/x.png[/img]") is None
    assert n.first_image("no pictures") is None
    # What Steam writes now.
    assert n.first_image('[p][/p][img src="{STEAM_CLAN_IMAGE}/6126332/abc.jpg"][/img]') == (
        "https://clan.akamai.steamstatic.com/images/6126332/abc.jpg"
    )


def test_a_posts_pictures_stay_as_lines_of_their_own() -> None:
    text = n.plain_text(
        '[p]Before[/p][img src="{STEAM_CLAN_IMAGE}/1/a.jpg"][/img][p]After[/p][img]x[/img]'
    )
    assert text == "Before\n\nhttps://clan.akamai.steamstatic.com/images/1/a.jpg\nAfter"


def test_a_picture_wrapped_in_a_link_stays_a_picture() -> None:
    text = n.plain_text(
        "[url=https://store.steampowered.com/publisher/2K/]"
        "[img]https://clan.fastly.steamstatic.com/images/1/a.jpg[/img][/url]As the leaves turn"
    )
    assert text == "https://clan.fastly.steamstatic.com/images/1/a.jpg\nAs the leaves turn"


def test_a_post_keeps_its_time_not_only_its_day() -> None:
    posts = n.parse_patches({"appnews": {"newsitems": [_item("Update 1.0")]}})
    assert posts[0].date == "2026-09-21T14:13:20Z"
