"""Game covers: the URL, the downloaded file, and the column between them.

The walker's whole job is to visit each game once and leave it alone
afterwards, so most of what is worth testing is about *not* doing work: a
game with art is never queued again, and a game nobody can find art for
goes to the back of the queue instead of returning on the next tick forever.
"""

from __future__ import annotations

from bot.constants import Platform
from bot.db.repo import AchievementRow, Repo
from bot.poller import covers as covers_poller
from bot.poller.covers import CoverRefresh
from bot.services import covers
from bot.services.steam.client import cover_url

STEAM_APPID = "440"
XBOX_TITLE = "1234567890"
PSN_TITLE = "NPWR00001_00"


class _FakeXbox:
    """Answers like titlehub's own resolve_title: a title entry with art."""

    def __init__(self, icon_url: str | None = "https://xbox.test/art.jpg") -> None:
        self.asked: list[tuple[int, str]] = []
        self._icon_url = icon_url

    async def resolve_title(self, tg_id: int, title_id: str):
        self.asked.append((tg_id, title_id))
        if self._icon_url is None:
            return None
        return type(
            "Entry",
            (),
            {
                "title_id": title_id,
                "name": "A Game",
                "platform": Platform.XBOX_MODERN,
                "icon_url": self._icon_url,
            },
        )()


def _downloads_to(monkeypatch, tmp_path, *, payload: bytes | None = b"\xff\xd8jpeg"):
    """Keep the walker off the network; still exercise the real writer."""
    saved: list[str] = []

    async def fake_download(url: str, name: str, *, root=None):
        saved.append(url)
        if payload is None:
            return None
        from bot.services import images

        return images.write(payload, name, covers.cover_dir(tmp_path))

    monkeypatch.setattr(covers_poller.covers, "download", fake_download)
    return saved


def test_steam_cover_url_is_derived_not_fetched() -> None:
    """The whole reason Steam costs nothing: no API call to learn the URL."""
    url = cover_url(STEAM_APPID)
    assert STEAM_APPID in url
    assert url.endswith("library_600x900.jpg")


def test_the_filename_keeps_platforms_apart() -> None:
    """A Steam appid and an Xbox title id are both bare numbers and can
    collide; `titles` is keyed by title_id alone, so the file is the last
    place the two can still be told apart."""
    assert covers.cover_name(Platform.STEAM, "440") != covers.cover_name(
        Platform.XBOX_MODERN, "440"
    )


async def test_a_steam_cover_is_stored_without_asking_anyone(
    repo: Repo, monkeypatch, tmp_path
) -> None:
    await repo.upsert_title(STEAM_APPID, "Team Fortress 2", Platform.STEAM)
    urls = _downloads_to(monkeypatch, tmp_path)
    client = _FakeXbox()

    await CoverRefresh(repo, client).tick()  # type: ignore[arg-type]

    assert client.asked == []  # Steam needs no token and no request
    assert urls == [cover_url(STEAM_APPID)]
    assert await repo.titles_needing_cover(10) == [], "a title with a cover is done forever"


async def test_an_xbox_cover_is_looked_up_through_an_owner(
    repo: Repo, cipher, monkeypatch, tmp_path
) -> None:
    await repo.ensure_user(7, "igor")
    await repo.save_refresh_token(7, cipher.encrypt("refresh"))
    await repo.link_xbox_account(7, "xuid-1", "Mad Omsk", None)
    await repo.upsert_title(XBOX_TITLE, "Gears of War 3", Platform.XBOX_360)
    await repo.insert_new_achievements(
        "xuid-1",
        [
            AchievementRow(
                title_id=XBOX_TITLE,
                achievement_id="a1",
                name="Level 25",
                description=None,
                icon_url=None,
                unlocked_at=None,
                gamerscore=10,
                rarity_percent=None,
                platform=Platform.XBOX_360,
                title_name="Gears of War 3",
            )
        ],
        is_backfill=False,
    )
    _downloads_to(monkeypatch, tmp_path)
    client = _FakeXbox()

    await CoverRefresh(repo, client).tick()  # type: ignore[arg-type]

    assert client.asked == [(7, XBOX_TITLE)]
    assert await repo.title_icon_url(XBOX_TITLE) == "https://xbox.test/art.jpg"


async def test_a_title_nobody_can_answer_for_goes_to_the_back_of_the_queue(
    repo: Repo, monkeypatch, tmp_path
) -> None:
    """It stays in the queue — there is still no cover — but `cover_checked_at`
    is stamped, which sorts it behind everything never looked at. Without
    that stamp the same unanswerable game would be retried every minute for
    the rest of the process's life, ahead of games that do have art."""
    await repo.upsert_title(XBOX_TITLE, "A Game Nobody Holds", Platform.XBOX_MODERN)
    _downloads_to(monkeypatch, tmp_path)
    client = _FakeXbox(icon_url=None)

    await CoverRefresh(repo, client).tick()  # type: ignore[arg-type]
    first = await repo.titles_needing_cover(10)
    await CoverRefresh(repo, client).tick()  # type: ignore[arg-type]

    assert [t.title_id for t in first] == [XBOX_TITLE]
    assert client.asked == []  # nobody holds this game, so nobody to ask through
    stamped = await repo.titles_needing_cover(10)
    assert [t.title_id for t in stamped] == [XBOX_TITLE]


async def test_a_failed_download_still_keeps_the_url(repo: Repo, monkeypatch, tmp_path) -> None:
    """A CDN having a bad minute costs the bytes, not the address: the Mini
    App can still load it directly, and the next visit retries."""
    await repo.upsert_title(STEAM_APPID, "Team Fortress 2", Platform.STEAM)
    _downloads_to(monkeypatch, tmp_path, payload=None)

    await CoverRefresh(repo, _FakeXbox()).tick()  # type: ignore[arg-type]

    assert await repo.title_icon_url(STEAM_APPID) == cover_url(STEAM_APPID)
    assert [t.title_id for t in await repo.titles_needing_cover(10)] == [STEAM_APPID]


async def test_coverage_counts_what_is_left(repo: Repo, monkeypatch, tmp_path) -> None:
    await repo.upsert_title(STEAM_APPID, "Team Fortress 2", Platform.STEAM)
    await repo.upsert_title(PSN_TITLE, "Marvel's Spider-Man", Platform.PSN)
    assert await repo.cover_coverage() == (0, 0, 2)

    _downloads_to(monkeypatch, tmp_path)
    await CoverRefresh(repo, _FakeXbox()).tick()  # type: ignore[arg-type]

    files, urls, total = await repo.cover_coverage()
    assert (files, total) == (1, 2)
    assert urls == 1
