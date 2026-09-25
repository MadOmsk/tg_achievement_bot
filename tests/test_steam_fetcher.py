"""poller/steam_fetcher.py: dedup, publish, and backfill isolation (SPEC 9,
M-Steam-2c/2d) — the Steam counterpart of test_poller.py's Fetcher tests.
fetch_unlocked()/get_owned_games() are faked at the module boundary, same
as the rest of this project's poller tests fake the Xbox client."""

from __future__ import annotations

from bot.db.repo import AchievementRow, Repo
from bot.poller import steam_fetcher as steam_fetcher_module
from bot.poller.steam_fetcher import SteamFetcher
from bot.services.models import ParsedAchievement
from bot.services.steam.client import OwnedGame, SteamApiError, SteamPresence

TG_ID = 42
STEAM_ID = "76561197960287930"


def parsed(
    achievement_id: str, appid: str = "550", title_name: str | None = None
) -> ParsedAchievement:
    return ParsedAchievement(
        achievement_id=achievement_id,
        title_id=appid,
        title_name=title_name,
        name=f"Achievement {achievement_id}",
        description=None,
        icon_url=None,
        unlocked_at=None,
        gamerscore=0,
        rarity_percent=42.0,
        platform="steam",
    )


class FakePublisher:
    def __init__(self) -> None:
        self.published: list[list[AchievementRow]] = []

    async def publish(
        self, tg_id, xuid, gamertag, achievements, title_name=None, *, window_hours=None
    ) -> None:
        self.published.append(list(achievements))


async def _linked_user(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "igor")
    await repo.link_platform_account(TG_ID, "steam", STEAM_ID, "Mad Omsk")


async def test_poll_title_publishes_only_new_achievements(
    repo: Repo, steam_auth, monkeypatch
) -> None:
    await _linked_user(repo)
    by_appid = {"550": [parsed("a1"), parsed("a2")]}

    async def fake_fetch_unlocked(
        repo_, anthropic_auth_, api_key, steam_id, appid, *, title_name=None
    ):
        return by_appid.get(appid, [])

    monkeypatch.setattr(steam_fetcher_module, "fetch_unlocked", fake_fetch_unlocked)
    publisher = FakePublisher()
    fetcher = SteamFetcher(repo, steam_auth, publisher, anthropic_auth=object())  # type: ignore[arg-type]

    assert await fetcher.poll_title(TG_ID, STEAM_ID, "Mad Omsk", "550", "L4D2") == 2
    # Same answer a tick later: nothing new, nothing published.
    assert await fetcher.poll_title(TG_ID, STEAM_ID, "Mad Omsk", "550", "L4D2") == 0
    assert len(publisher.published) == 1

    by_appid["550"].append(parsed("a3"))
    assert await fetcher.poll_title(TG_ID, STEAM_ID, "Mad Omsk", "550", "L4D2") == 1
    assert [a.achievement_id for a in publisher.published[1]] == ["a3"]


async def test_refresh_user_polls_the_current_game(repo: Repo, steam_auth, monkeypatch) -> None:
    """The admin panel's own "🔄 Обновить Steam" (2026-09-05 follow-up) —
    never existed before, unlike Xbox's Fetcher.refresh_user()."""
    await _linked_user(repo)

    async def fake_batch(api_key, steam_ids):
        assert steam_ids == [STEAM_ID]
        return {
            STEAM_ID: SteamPresence(
                steam_id=STEAM_ID,
                persona_name="Mad Omsk",
                persona_state=1,
                gameid="550",
                game_name="Left 4 Dead 2",
            )
        }

    async def fake_fetch_unlocked(
        repo_, anthropic_auth_, api_key, steam_id, appid, *, title_name=None
    ):
        return [parsed("a1", appid)]

    monkeypatch.setattr(steam_fetcher_module, "get_presence_batch", fake_batch)
    monkeypatch.setattr(steam_fetcher_module, "fetch_unlocked", fake_fetch_unlocked)
    fetcher = SteamFetcher(repo, steam_auth, FakePublisher(), anthropic_auth=object())  # type: ignore[arg-type]

    summary = await fetcher.refresh_user(TG_ID, STEAM_ID, "Mad Omsk", "ru")

    assert "Left 4 Dead 2" in summary
    assert "1" in summary
    presence = await repo.steam_presence_of(STEAM_ID)
    assert presence is not None and presence.gameid == "550"


async def test_refresh_user_reports_offline_with_no_game(
    repo: Repo, steam_auth, monkeypatch
) -> None:
    await _linked_user(repo)

    async def fake_batch(api_key, steam_ids):
        return {
            STEAM_ID: SteamPresence(
                steam_id=STEAM_ID,
                persona_name="Mad Omsk",
                persona_state=0,
                gameid=None,
                game_name=None,
            )
        }

    monkeypatch.setattr(steam_fetcher_module, "get_presence_batch", fake_batch)
    fetcher = SteamFetcher(repo, steam_auth, FakePublisher(), anthropic_auth=object())  # type: ignore[arg-type]

    summary = await fetcher.refresh_user(TG_ID, STEAM_ID, "Mad Omsk", "ru")

    assert "не в сети" in summary


async def test_refresh_user_handles_a_missing_profile(repo: Repo, steam_auth, monkeypatch) -> None:
    await _linked_user(repo)

    async def fake_batch(api_key, steam_ids):
        return {}  # Steam simply omits a deleted/hidden profile

    monkeypatch.setattr(steam_fetcher_module, "get_presence_batch", fake_batch)
    fetcher = SteamFetcher(repo, steam_auth, FakePublisher(), anthropic_auth=object())  # type: ignore[arg-type]

    summary = await fetcher.refresh_user(TG_ID, STEAM_ID, "Mad Omsk", "ru")

    assert "не" in summary.lower()


async def test_backfill_publishes_nothing(repo: Repo, steam_auth, monkeypatch) -> None:
    """The whole point of SPEC 5.6/9's backfill: the first link must be silent."""
    await _linked_user(repo)

    async def fake_get_owned_games(api_key, steam_id):
        return [OwnedGame(appid="550", name="L4D2", playtime_forever=100)]

    async def fake_fetch_unlocked(
        repo_, anthropic_auth_, api_key, steam_id, appid, *, title_name=None
    ):
        return [parsed("a1", appid), parsed("a2", appid)]

    monkeypatch.setattr(steam_fetcher_module, "get_owned_games", fake_get_owned_games)
    monkeypatch.setattr(steam_fetcher_module, "fetch_unlocked", fake_fetch_unlocked)
    publisher = FakePublisher()
    fetcher = SteamFetcher(repo, steam_auth, publisher, anthropic_auth=object())  # type: ignore[arg-type]

    stored = await fetcher.backfill(TG_ID, STEAM_ID)

    assert stored == 2
    assert publisher.published == []


async def test_backfill_caches_each_games_name(repo: Repo, steam_auth, monkeypatch) -> None:
    """#70: every Steam game stored by backfill used to render as "без
    названия" forever. `fetch_unlocked` hardcoded `title_name=None` on the
    assumption presence had supplied it — but backfill never touches
    presence, and it is holding the name the whole time, right there on the
    `OwnedGame` it is walking.

    Checked through `titles` rather than through a games list: a backfill
    row with no unlock date is deliberately outside every window, so the
    name has to be verified where it actually lands.
    """
    await _linked_user(repo)

    async def fake_get_owned_games(api_key, steam_id):
        return [OwnedGame(appid="550", name="Left 4 Dead 2", playtime_forever=100)]

    async def fake_fetch_unlocked(
        repo_, anthropic_auth_, api_key, steam_id, appid, *, title_name=None
    ):
        return [parsed("a1", appid, title_name)]

    monkeypatch.setattr(steam_fetcher_module, "get_owned_games", fake_get_owned_games)
    monkeypatch.setattr(steam_fetcher_module, "fetch_unlocked", fake_fetch_unlocked)
    fetcher = SteamFetcher(repo, steam_auth, FakePublisher(), anthropic_auth=object())  # type: ignore[arg-type]

    await fetcher.backfill(TG_ID, STEAM_ID)

    assert await repo.title_name("550") == "Left 4 Dead 2"


async def test_poll_title_caches_the_games_name(repo: Repo, steam_auth, monkeypatch) -> None:
    """The other half of #70 — `poll_title` took `game_name` as a parameter
    all along and only ever forwarded it to the publisher, after the row had
    already been stored without it."""
    await _linked_user(repo)

    async def fake_fetch_unlocked(
        repo_, anthropic_auth_, api_key, steam_id, appid, *, title_name=None
    ):
        return [parsed("a1", appid, title_name)]

    monkeypatch.setattr(steam_fetcher_module, "fetch_unlocked", fake_fetch_unlocked)
    fetcher = SteamFetcher(repo, steam_auth, FakePublisher(), anthropic_auth=object())  # type: ignore[arg-type]

    await fetcher.poll_title(TG_ID, STEAM_ID, "Mad Omsk", "550", "Left 4 Dead 2")

    assert await repo.title_name("550") == "Left 4 Dead 2"


async def test_backfill_isolates_a_failing_game(repo: Repo, steam_auth, monkeypatch) -> None:
    """One game's SteamApiError must not sink the whole backfill (SPEC 9,
    M-Steam-2d) — same "one bad game doesn't ruin the rest" isolation
    Xbox's own backfill doesn't need (it has no per-game loop at all)."""
    await _linked_user(repo)

    async def fake_get_owned_games(api_key, steam_id):
        return [
            OwnedGame(appid="1", name="Broken Game", playtime_forever=10),
            OwnedGame(appid="2", name="Fine Game", playtime_forever=20),
        ]

    async def fake_fetch_unlocked(
        repo_, anthropic_auth_, api_key, steam_id, appid, *, title_name=None
    ):
        if appid == "1":
            raise SteamApiError("boom")
        return [parsed("a1", appid)]

    monkeypatch.setattr(steam_fetcher_module, "get_owned_games", fake_get_owned_games)
    monkeypatch.setattr(steam_fetcher_module, "fetch_unlocked", fake_fetch_unlocked)
    publisher = FakePublisher()
    fetcher = SteamFetcher(repo, steam_auth, publisher, anthropic_auth=object())  # type: ignore[arg-type]

    stored = await fetcher.backfill(TG_ID, STEAM_ID)

    assert stored == 1  # only the fine game's achievement made it in


async def test_library_gaps_are_filled_once_and_silently(
    repo: Repo, steam_auth, monkeypatch
) -> None:
    """Free-to-play games were left out of the library until #120: what is
    stored for them is history — only games with nothing stored are asked
    about, nothing is published, and it runs once per database."""
    await _linked_user(repo)
    await repo.insert_new_achievements_steam(
        TG_ID, STEAM_ID, [_row_for("550", "a1")], is_backfill=True
    )
    asked: list[str] = []

    async def fake_get_owned_games(api_key, steam_id):
        return [
            OwnedGame(appid="550", name="L4D2", playtime_forever=100),
            OwnedGame(appid="1085660", name="Destiny 2", playtime_forever=900),
            OwnedGame(appid="4000", name="Garry's Mod", playtime_forever=50, has_stats=False),
        ]

    async def fake_fetch_unlocked(
        repo_, anthropic_auth_, api_key, steam_id, appid, *, title_name=None
    ):
        asked.append(appid)
        return [parsed("d1", appid), parsed("d2", appid)]

    monkeypatch.setattr(steam_fetcher_module, "get_owned_games", fake_get_owned_games)
    monkeypatch.setattr(steam_fetcher_module, "fetch_unlocked", fake_fetch_unlocked)
    publisher = FakePublisher()
    fetcher = SteamFetcher(repo, steam_auth, publisher, anthropic_auth=object())  # type: ignore[arg-type]

    await fetcher.fill_library_gaps_once([(TG_ID, STEAM_ID)])
    await fetcher.fill_library_gaps_once([(TG_ID, STEAM_ID)])

    # L4D2 already had rows, Garry's Mod has no achievements at all, and
    # the second call is a no-op.
    assert asked == ["1085660"]
    assert publisher.published == []
    assert await repo.steam_titles_with_achievements(STEAM_ID) == {"550", "1085660"}


def _row_for(appid: str, achievement_id: str) -> AchievementRow:
    return AchievementRow(
        title_id=appid,
        achievement_id=achievement_id,
        name="A",
        description=None,
        icon_url=None,
        unlocked_at=None,
        gamerscore=0,
        rarity_percent=None,
        platform="steam",
    )
