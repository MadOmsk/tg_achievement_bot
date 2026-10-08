"""Video guides from YouTube: what a video names, how it is matched to our
achievements, how a channel is read, and that the key never leaks."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import replace
from datetime import timedelta
from urllib.parse import urlencode

import httpx
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from bot.config import Settings
from bot.db.repo import GuideVideoRow, Repo, TitleAchievementRow
from bot.poller import guide_videos as poller
from bot.services.crypto import TokenCipher
from bot.services.youtube import client as youtube
from bot.services.youtube.auth import YouTubeAuth
from bot.services.youtube.guides import Mark, game_keys, marks_of, title_key
from bot.services.youtube.videos import achievement_videos
from bot.util import utcnow
from bot.web.mini_api import cors_middleware, setup_mini_api

CHANNEL = "UCFXmIUDNofRpYSG7lku0i_Q"
TITLE = "1234567"


# ------------------------------------------------------------ what a video names


def test_a_title_for_one_achievement_names_it() -> None:
    marks = marks_of(
        "House Flipper Remastered - Alpha Male 🏆 Trophy/Achievement Guide - Sell a house", ""
    )
    assert marks == [Mark("alpha male", 0)]


def test_a_timeline_marks_achievements_parts_and_bare_names() -> None:
    description = "\n".join(
        [
            "TIMELINE:",
            "00:00 – Collectible 1/2 – COG Tags of Sergeant Aman Landry",
            "02:42 – ACHIEVEMENT – Chainsaw Go Brrrrrrrrr",
            "06:09 – TROPHY – I Am Heavy Weapons Guy – PART 1",
            "1:08:17 – TROPHY – I Am Heavy Weapons Guy – PART 2",
            "00:07 – Bountilogical Studies PhD (Missable)",
            "Not a line of the timeline",
        ]
    )
    marks = marks_of("Gears of War: E-Day - Act 3-3 - All Collectibles & Achievements", description)
    assert Mark("chainsaw go brrrrrrrrr", 162) in marks
    assert Mark("1 am heavy weapons guy", 369, 1) in marks
    assert Mark("1 am heavy weapons guy", 4097, 2) in marks
    assert Mark("bountilogical studies phd", 7) in marks
    assert len(marks) == 5


def test_a_game_is_the_first_parts_of_a_title() -> None:
    assert title_key("Gears of War: E-Day - Act 4-2: Technical Difficulties") == (
        "gears of war e day | act 4 2 technical difficulties"
    )
    # A game's edition tail is cut as well, for videos named without it.
    assert "a plague tale innocence" in game_keys("A Plague Tale: Innocence - Windows 10")


# ------------------------------------------------------------ matching


async def _game(repo: Repo, name: str = "Gears of War: E-Day") -> None:
    await repo.upsert_title(TITLE, name, "xbox_modern")
    await repo.upsert_title_achievements(
        [
            TitleAchievementRow(
                platform="xbox_modern", title_id=TITLE, achievement_id=aid, name_en=label
            )
            for aid, label in (("1", "Okay, Boomer."), ("2", "Chainsaw Go Brrrrrrrrr"))
        ],
        complete=True,
    )


def _video(video_id: str, title: str, description: str) -> GuideVideoRow:
    return GuideVideoRow(
        video_id=video_id,
        channel_id=CHANNEL,
        title=title,
        title_key=title_key(title),
        published_at="2026-10-01T10:00:00Z",
        marks=tuple((m.label, m.start_seconds, m.part) for m in marks_of(title, description)),
    )


async def test_an_achievement_finds_its_moment_in_its_own_games_videos(repo: Repo) -> None:
    await _game(repo)
    await repo.save_guide_videos(
        [
            _video(
                "v1",
                "Gears of War: E-Day - Act 2-2: Hold the Line - All Collectibles & Achievements",
                "04:32 – ACHIEVEMENT – Okay, Boomer\n16:34 – ACHIEVEMENT – Explosive Indigestion",
            ),
            # Another game whose name starts the same: never this one's.
            _video("v2", "Gears of War: E-Day 2 - Act 1", "01:00 – ACHIEVEMENT – Okay, Boomer"),
        ]
    )

    found = await achievement_videos(repo, "xbox_modern", TITLE)

    assert list(found) == ["1"]
    (video,) = found["1"]
    assert (video.video_id, video.start_seconds, video.channel) == ("v1", 272, "TrophyTom")


async def test_a_description_edited_later_replaces_the_marks(repo: Repo) -> None:
    await _game(repo)
    await repo.save_guide_videos([_video("v1", "Gears of War: E-Day - Act 3", "00:00 – Intro")])
    assert await achievement_videos(repo, "xbox_modern", TITLE) == {}

    await repo.save_guide_videos(
        [
            _video(
                "v1", "Gears of War: E-Day - Act 3", "02:42 – ACHIEVEMENT – Chainsaw Go Brrrrrrrrr"
            )
        ]
    )
    assert list(await achievement_videos(repo, "xbox_modern", TITLE)) == ["2"]


# ------------------------------------------------------------ reading a channel


class _Key:
    def __init__(self, key: str | None = "k") -> None:
        self.key = key

    async def get_key(self) -> str | None:
        return self.key


def _page(n: int) -> list[youtube.Video]:
    return [youtube.Video(f"v{n}", f"Game - Part {n}", "00:10 – Win", None)]


async def test_a_channel_is_read_through_once_then_only_its_newest_page(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    pages = {None: (_page(1), "t2"), "t2": (_page(2), "t3"), "t3": (_page(3), None)}
    asked: list[str | None] = []

    async def uploads_playlist(key, channel_id):
        return "UU1"

    async def playlist_page(key, playlist_id, page_token=None):
        asked.append(page_token)
        return pages[page_token]

    monkeypatch.setattr(poller.youtube, "uploads_playlist", uploads_playlist)
    monkeypatch.setattr(poller.youtube, "playlist_page", playlist_page)
    job = poller.GuideVideos(repo, _Key(), channels={CHANNEL: "TrophyTom"}, pages_per_tick=2)

    await job.tick()
    assert asked == [None, "t2"]
    await job.tick()
    assert asked == [None, "t2", "t3"]
    assert (await repo.guide_channel(CHANNEL)).backfill_done

    # Read through: the newest page only, and only once it has gone stale.
    await job.tick()
    assert asked == [None, "t2", "t3"]
    state = await repo.guide_channel(CHANNEL)
    stale = (utcnow() - timedelta(hours=poller.REFRESH_HOURS + 1)).isoformat(timespec="seconds")
    await repo.save_guide_channel(replace(state, checked_at=stale))
    await job.tick()
    assert asked == [None, "t2", "t3", None]

    # A week on, the whole history again: a timeline added to an old video.
    state = await repo.guide_channel(CHANNEL)
    week_ago = (utcnow() - timedelta(days=poller.REREAD_DAYS)).isoformat(timespec="seconds")
    await repo.save_guide_channel(replace(state, read_through_at=week_ago))
    await job.tick()  # starts the pass over
    await job.tick()
    await job.tick()
    assert asked == [None, "t2", "t3", None, None, "t2", "t3"]
    assert (await repo.guide_channel(CHANNEL)).read_through_at > week_ago


async def test_a_refusal_rests_the_channel_for_an_hour(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    async def refused(key, channel_id):
        calls.append(channel_id)
        raise youtube.YouTubeError("channels: HTTP 403 quotaExceeded")

    monkeypatch.setattr(poller.youtube, "uploads_playlist", refused)
    job = poller.GuideVideos(repo, _Key(), channels={CHANNEL: "TrophyTom"})
    await job.tick()
    await job.tick()
    assert calls == [CHANNEL]


async def test_no_key_reads_nothing(repo: Repo, monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom(*args, **kwargs):
        raise AssertionError("no key, no request")

    monkeypatch.setattr(poller.youtube, "uploads_playlist", boom)
    await poller.GuideVideos(repo, _Key(None), channels={CHANNEL: "TrophyTom"}).tick()


# ------------------------------------------------------------ the key


async def test_a_failed_call_never_carries_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "AIzaSECRET"
    real = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["key"] == secret
        return httpx.Response(403, json={"error": {"errors": [{"reason": "forbidden"}]}})

    monkeypatch.setattr(
        youtube.httpx,
        "AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(handler), **kw),
    )
    with pytest.raises(youtube.YouTubeError) as caught:
        await youtube.playlist_page(secret, "UU1")
    assert secret not in str(caught.value)
    assert not await youtube.check_alive(secret)


async def test_the_env_key_seeds_once_and_a_clear_keeps_it_out(
    repo: Repo, cipher: TokenCipher
) -> None:
    auth = YouTubeAuth(repo, cipher, env_key="from-env")
    assert await auth.get_key() == "from-env"
    await auth.clear(admin_id=1)
    assert await auth.get_key() is None
    assert await YouTubeAuth(repo, cipher, env_key="from-env").get_key() is not None


# ------------------------------------------------------------ the endpoint


def _init_data(bot_token: str, user_id: int) -> str:
    user = json.dumps({"id": user_id, "first_name": "T", "username": "t"}, separators=(",", ":"))
    pairs = {"auth_date": str(int(time.time())), "user": user}
    check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(pairs)


class _Extras:
    async def tips_due(self, platform: str, title_id: str) -> bool:
        return False


async def test_the_guides_answer_carries_the_videos(repo: Repo, settings: Settings) -> None:
    await repo.ensure_user(42, "me")
    await _game(repo)
    await repo.save_guide_videos(
        [
            _video(
                "v1", "Gears of War: E-Day - Act 3", "02:42 – ACHIEVEMENT – Chainsaw Go Brrrrrrrrr"
            )
        ]
    )
    app = web.Application(middlewares=[cors_middleware()])
    setup_mini_api(app, settings, repo, steam_extras=_Extras())
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        resp = await client.get(
            f"/api/mini/games/xbox_modern/{TITLE}/guides",
            headers={"X-Telegram-Init-Data": _init_data(settings.bot_token.get_secret_value(), 42)},
        )
        body = await resp.json()
    finally:
        await client.close()
    assert body["videos"]["2"] == [
        {
            "id": "v1",
            "title": "Gears of War: E-Day - Act 3",
            "channel": "TrophyTom",
            "start": 162,
            "part": 0,
            "url": "https://www.youtube.com/watch?v=v1&t=162s",
        }
    ]


async def test_a_game_with_guide_videos_gets_its_whole_guide(repo: Repo) -> None:
    from bot.services.youtube.videos import game_guide

    await _game(repo)
    assert await game_guide(repo, "xbox_modern", TITLE) is None

    await repo.save_guide_videos(
        [
            _video("v1", "Gears of War: E-Day - Act 3", ""),
            _video("v2", "Gears of War: E-Day - Okay 🏆 Trophy Guide", ""),
        ]
    )
    guide = await game_guide(repo, "xbox_modern", TITLE)
    # No whole-game video: the channel's videos of the game.
    assert guide is not None and guide.video_id is None
    assert guide.url.endswith("/search?query=Gears+of+War%3A+E-Day")
    assert guide.count == 2

    await repo.save_guide_videos(
        [_video("v3", "Gears of War: E-Day - All Achievements - Full Game Walkthrough", "")]
    )
    guide = await game_guide(repo, "xbox_modern", TITLE)
    assert guide is not None and guide.video_id == "v3"
