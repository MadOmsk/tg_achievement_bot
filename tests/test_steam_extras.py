"""A game's Steam side in the database: its app, its tips, its patches — filled
once like the HLTB entry, refreshed in the background for patches only."""

from __future__ import annotations

import asyncio

import pytest

from bot.db.repo import AchievementRow, Repo, TitleAchievementRow
from bot.poller.patch_refresh import PatchRefresh
from bot.services import steam_extras as se
from bot.services.steam.auth import SteamAuth
from bot.services.steam_guides import Guide, GuideSet, make_guide
from bot.services.steam_news import Patch
from bot.util import utcnow

TITLE = "1924130173"


def _guide() -> Guide:
    return make_guide(
        "g1",
        "Guide",
        [
            "Intro line one",
            "Intro line two",
            "First Steps",
            "Walk out of the house and talk to the old man by the well, then follow him.",
            "Hidden Room",
            "Behind the bookcase on the second floor; push it twice to open the passage.",
            "Another",
            "Line",
            "More",
            "Filler text to pass the ten-line minimum of a usable guide.",
        ],
    )


async def _seed(repo: Repo, *, platform: str = "xbox_modern", title_id: str = TITLE) -> None:
    await repo.upsert_title(title_id, "Haven", platform)
    await repo.upsert_title_achievements(
        [
            TitleAchievementRow(
                platform=platform,
                title_id=title_id,
                achievement_id=aid,
                name_en=name,
                description_en="Do the thing",
            )
            for aid, name in (("1", "First Steps"), ("2", "Hidden Room"), ("3", "Never Covered"))
        ],
        complete=True,
    )


@pytest.fixture
def steam(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    calls = {"appid": 0, "patches": 0, "guides": 0}
    complete = {"value": True}

    async def find_appid(names, hltb_id):
        calls["appid"] += 1
        return 983970

    async def fetch_patches(appid):
        calls["patches"] += 1
        return [Patch(gid="p1", title="Small patch", date="2022-03-08", text="Fixes.")]

    async def guides_of(appid, api_key):
        calls["guides"] += 1
        return GuideSet([_guide()], complete["value"])

    monkeypatch.setattr(se, "find_appid", find_appid)
    monkeypatch.setattr(se, "fetch_patches", fetch_patches)
    monkeypatch.setattr(se, "guides_of", guides_of)
    calls["complete"] = complete  # type: ignore[assignment]
    return calls


async def test_a_game_is_filled_once(repo: Repo, steam_auth: SteamAuth, steam) -> None:
    await _seed(repo)
    extras = se.SteamExtras(repo, steam_auth)

    assert await extras.fill_title(TITLE) is True
    tips = await repo.title_tips("xbox_modern", TITLE)
    assert set(tips) == {"1", "2"}
    assert tips["1"][0].startswith("Walk out of the house")
    assert [p.title for p in await repo.game_patches(983970, 10)] == ["Small patch"]

    assert await extras.fill_title(TITLE) is True
    assert (steam["appid"], steam["patches"], steam["guides"]) == (1, 1, 1)


async def test_a_partial_read_keeps_its_tips_and_is_asked_again(
    repo: Repo, steam_auth: SteamAuth, steam
) -> None:
    await _seed(repo)
    steam["complete"]["value"] = False
    extras = se.SteamExtras(repo, steam_auth)

    assert await extras.fill_title(TITLE) is False
    assert set(await repo.title_tips("xbox_modern", TITLE)) == {"1", "2"}
    assert await extras.tips_due(TITLE)

    steam["complete"]["value"] = True
    assert await extras.fill_title(TITLE) is True
    assert not await extras.tips_due(TITLE)


async def test_a_game_with_no_steam_page_is_given_up_on(
    repo: Repo, steam_auth: SteamAuth, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed(repo)
    looked = 0

    async def find_appid(names, hltb_id):
        nonlocal looked
        looked += 1
        return None

    monkeypatch.setattr(se, "find_appid", find_appid)
    extras = se.SteamExtras(repo, steam_auth)
    for _ in range(3):
        await extras.fill_title(TITLE)
        # The next attempt waits an hour; pretend it has passed.
        await repo._conn.execute("UPDATE titles SET steam_appid_checked_at = NULL")
    await extras.fill_title(TITLE)
    assert looked == 3
    assert not await extras.tips_due(TITLE)


async def test_a_steam_game_is_its_own_app(repo: Repo, steam_auth: SteamAuth, steam) -> None:
    await _seed(repo, platform="steam", title_id="553850")
    extras = se.SteamExtras(repo, steam_auth)
    assert await extras.appid("553850") == 553850
    assert steam["appid"] == 0


async def test_ensure_title_does_not_wait_for_the_fill(
    repo: Repo, steam_auth: SteamAuth, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed(repo)
    started = asyncio.Event()
    release = asyncio.Event()

    async def find_appid(names, hltb_id):
        started.set()
        await release.wait()
        return None

    monkeypatch.setattr(se, "find_appid", find_appid)
    extras = se.SteamExtras(repo, steam_auth)
    extras.ensure_title(TITLE)
    extras.ensure_title(TITLE)  # already running: not started twice
    await asyncio.wait_for(started.wait(), 1)
    assert len(extras._running) == 1
    release.set()
    await asyncio.wait_for(asyncio.gather(*extras._running.values()), 1)


async def test_patches_of_played_games_are_refreshed_a_few_at_a_time(
    repo: Repo, steam_auth: SteamAuth, monkeypatch: pytest.MonkeyPatch
) -> None:
    read: list[int] = []

    async def fetch_patches(appid):
        read.append(appid)
        if appid == 2:
            raise RuntimeError("boom")
        return []

    monkeypatch.setattr(se, "fetch_patches", fetch_patches)
    now = utcnow().isoformat(timespec="seconds")
    for appid in (1, 2, 3, 4):
        await repo.upsert_title(str(appid), f"Game {appid}", "steam")
        await repo.insert_new_achievements(
            "x1",
            [
                AchievementRow(
                    title_id=str(appid),
                    achievement_id="a",
                    name="A",
                    description=None,
                    icon_url=None,
                    unlocked_at=now,
                    gamerscore=0,
                    rarity_percent=None,
                    # The account a row belongs to is an Xbox one here; the
                    # title itself is a Steam game, which is what counts.
                    platform="xbox_modern",
                )
            ],
            is_backfill=False,
        )
    await repo.upsert_title("5", "Nobody plays it", "steam")

    refresh = PatchRefresh(repo, se.SteamExtras(repo, steam_auth), apps_per_tick=3)
    await refresh.tick()
    assert len(read) == 3
    await refresh.tick()
    # The three read (the failed one included, it is retried) plus the fourth.
    assert 4 in read and 5 not in read


async def test_migration_069_adds_the_steam_side_to_an_existing_database(tmp_path) -> None:
    import aiosqlite

    from bot.db.repo import MIGRATIONS_DIR

    sql = (MIGRATIONS_DIR / "069_steam_guides_patches.sql").read_text(encoding="utf-8")
    async with aiosqlite.connect(tmp_path / "m069.db") as conn:
        await conn.executescript(
            """
            CREATE TABLE titles (title_id TEXT PRIMARY KEY, name TEXT);
            CREATE TABLE title_achievements (
                platform TEXT, title_id TEXT, achievement_id TEXT, name_en TEXT);
            INSERT INTO titles VALUES ('t', 'Game');
            INSERT INTO title_achievements VALUES ('steam', 't', 'a', 'A');
            """
        )
        await conn.executescript(sql)
        title = await (
            await conn.execute("SELECT steam_appid, steam_appid_attempts FROM titles")
        ).fetchone()
        tip = await (await conn.execute("SELECT tip_en, tip_ru FROM title_achievements")).fetchone()
        tables = {
            r[0]
            for r in await (
                await conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            ).fetchall()
        }
    assert tuple(title) == (None, 0)
    assert tuple(tip) == (None, None)
    assert {"steam_apps", "game_patches"} <= tables
