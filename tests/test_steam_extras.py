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


class _Key:
    async def get_key(self) -> str:
        return "sk-test"


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
            "Third Room",
            "Look under the stairs for the hatch and pull the rusty ring.",
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
            for aid, name in (
                ("1", "First Steps"),
                ("2", "Hidden Room"),
                ("3", "Third Room"),
                ("4", "Never Covered"),
            )
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

    async def guides_of(appid, api_key, stop_when=None):
        calls["guides"] += 1
        guide = _guide()
        if stop_when is not None and await stop_when(guide):
            return GuideSet([guide], True)
        return GuideSet([guide], complete["value"])

    monkeypatch.setattr(se, "find_appid", find_appid)
    monkeypatch.setattr(se, "fetch_patches", fetch_patches)

    async def locate_sections(api_key, lines, achievements, marks=None, sections=()):
        # The model points at the lines under "First Steps" and "Hidden Room".
        return {0: [(3, 3)], 1: [(5, 5)], 2: [(7, 7)]}

    monkeypatch.setattr(se, "guides_of", guides_of)
    monkeypatch.setattr(se, "locate_sections", locate_sections)
    calls["complete"] = complete  # type: ignore[assignment]
    return calls


async def test_a_game_is_filled_once(repo: Repo, steam_auth: SteamAuth, steam) -> None:
    await _seed(repo)
    extras = se.SteamExtras(repo, steam_auth, _Key())  # type: ignore[arg-type]

    assert await extras.fill_title("xbox", TITLE) is True
    tips = await repo.title_tips("xbox_modern", TITLE)
    assert set(tips) == {"1", "2", "3"}
    assert tips["1"][0].startswith("Walk out of the house")
    assert [p.title for p in await repo.game_patches(983970, 10)] == ["Small patch"]

    assert await extras.fill_title("xbox", TITLE) is True
    assert (steam["appid"], steam["patches"], steam["guides"]) == (1, 1, 1)


async def test_a_game_is_read_again_until_a_guide_fills_half_of_it(
    repo: Repo, steam_auth: SteamAuth, steam, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed(repo)
    steam["complete"]["value"] = False  # Steam holds the other guides back
    pointed = {"value": {}}

    async def locate(api_key, lines, achievements, marks=None):
        return pointed["value"]

    monkeypatch.setattr(se, "locate_sections", locate)
    extras = se.SteamExtras(repo, steam_auth, _Key())  # type: ignore[arg-type]

    # No guide read so far is of use: the game is asked again later.
    assert await extras.fill_title("xbox", TITLE) is False
    assert await repo.title_tips("xbox_modern", TITLE) == {}
    assert await extras.tips_due("xbox", TITLE)

    # A guide that fills half the achievements ends the reading; the rest are not wanted.
    # (A guide the model found nothing in is remembered; forget it, as a changed
    # guide would, and the next look is the one that finds the tips.)
    await repo._conn.execute("DELETE FROM title_guide_reads")
    await repo._conn.commit()
    pointed["value"] = {0: [(3, 3)], 1: [(5, 5)]}
    extras = se.SteamExtras(repo, steam_auth, _Key())  # type: ignore[arg-type]
    assert await extras.fill_title("xbox", TITLE) is True
    assert set(await repo.title_tips("xbox_modern", TITLE)) == {"1", "2"}
    assert not await extras.tips_due("xbox", TITLE)


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
    extras = se.SteamExtras(repo, steam_auth, _Key())  # type: ignore[arg-type]
    for _ in range(3):
        await extras.fill_title("xbox", TITLE)
        # The next attempt waits an hour; pretend it has passed.
        await repo._conn.execute("UPDATE titles SET steam_appid_checked_at = NULL")
    await extras.fill_title("xbox", TITLE)
    assert looked == 3
    assert not await extras.tips_due("xbox", TITLE)


async def test_a_steam_game_is_its_own_app(repo: Repo, steam_auth: SteamAuth, steam) -> None:
    await _seed(repo, platform="steam", title_id="553850")
    extras = se.SteamExtras(repo, steam_auth, _Key())  # type: ignore[arg-type]
    assert await extras.appid("steam", "553850") == 553850
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
    extras = se.SteamExtras(repo, steam_auth, _Key())  # type: ignore[arg-type]
    extras.ensure_title("xbox", TITLE)
    extras.ensure_title("xbox", TITLE)  # already running: not started twice
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
        # Xbox games whose Steam app is known: a game is its platform and
        # its id (089), so the rows and the game are both Xbox ones.
        await repo.upsert_title(str(appid), f"Game {appid}", "xbox_modern")
        await repo.record_steam_appid("xbox_modern", str(appid), appid)
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


async def test_a_read_that_finds_nothing_keeps_the_tips_already_stored(
    repo: Repo, steam_auth: SteamAuth, steam
) -> None:
    await _seed(repo)
    extras = se.SteamExtras(repo, steam_auth, _Key())  # type: ignore[arg-type]
    await extras.fill_title("xbox", TITLE)
    assert set(await repo.title_tips("xbox_modern", TITLE)) == {"1", "2", "3"}

    await repo.replace_title_tips("xbox_modern", TITLE, {}, complete=True)

    assert set(await repo.title_tips("xbox_modern", TITLE)) == {"1", "2", "3"}


async def test_a_visit_never_rereads_old_tips_but_the_schedule_does(
    repo: Repo, steam_auth: SteamAuth, steam
) -> None:
    await _seed(repo)
    extras = se.SteamExtras(repo, steam_auth, _Key())  # type: ignore[arg-type]
    assert await extras.fill_title("xbox", TITLE) is True
    reads = steam["guides"]

    await repo._conn.execute(
        "UPDATE titles SET tips_checked_at = '2020-01-01T00:00:00' WHERE title_id = ?", (TITLE,)
    )
    await repo._conn.commit()
    assert not await extras.tips_due("xbox", TITLE)
    assert await extras.fill_title("xbox", TITLE) is True
    assert steam["guides"] == reads

    await extras.refresh_tips("xbox", TITLE)
    assert steam["guides"] == reads + 1


async def test_a_section_the_model_points_at_is_copied_from_the_guide(
    repo: Repo, steam_auth: SteamAuth, steam, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed(repo)
    asked = {"n": 0}

    async def locate(api_key, lines, achievements, marks=None, sections=()):
        asked["n"] += 1
        assert [a[0] for a in achievements] == [
            "First Steps",
            "Hidden Room",
            "Third Room",
            "Never Covered",
        ]
        # The name lines are told to the model as marks.
        assert marks == {2: 1, 4: 2, 6: 3}
        # "Never Covered" is found by the model though no line of the guide names it;
        # its section is two pieces with a line left out between them.
        return {3: [(8, 8), (10, 11)]}

    monkeypatch.setattr(se, "locate_sections", locate)
    extras = se.SteamExtras(repo, steam_auth, _Key())  # type: ignore[arg-type]
    assert await extras.fill_title("xbox", TITLE) is True

    tips = await repo.title_tips("xbox_modern", TITLE)
    assert (
        tips["4"][0] == "Another\nMore\nFiller text to pass the ten-line minimum of a usable guide."
    )
    assert set(tips) == {"4"}
    await extras.refresh_tips("xbox", TITLE)
    assert asked["n"] == 1


async def test_without_an_anthropic_key_nothing_is_read_or_stamped(
    repo: Repo, steam_auth: SteamAuth, steam
) -> None:
    await _seed(repo)
    extras = se.SteamExtras(repo, steam_auth)
    assert await extras.fill_title("xbox", TITLE) is True
    assert await repo.title_tips("xbox_modern", TITLE) == {}
    assert steam["guides"] == 0
    assert await extras.tips_due("xbox", TITLE)


async def test_a_model_that_finds_nothing_leaves_no_tips(
    repo: Repo, steam_auth: SteamAuth, steam, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed(repo)

    async def locate(api_key, lines, achievements, marks=None, sections=()):
        return {}

    monkeypatch.setattr(se, "locate_sections", locate)
    extras = se.SteamExtras(repo, steam_auth, _Key())  # type: ignore[arg-type]
    await extras.fill_title("xbox", TITLE)
    assert await repo.title_tips("xbox_modern", TITLE) == {}


async def test_a_model_that_cannot_be_asked_leaves_the_game_unread(
    repo: Repo, steam_auth: SteamAuth, steam, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed(repo)

    async def locate(api_key, lines, achievements, marks=None, sections=()):
        return None

    monkeypatch.setattr(se, "locate_sections", locate)
    extras = se.SteamExtras(repo, steam_auth, _Key())  # type: ignore[arg-type]
    assert await extras.fill_title("xbox", TITLE) is False
    assert await extras.tips_due("xbox", TITLE)


async def test_a_platinum_is_never_a_candidate_for_a_tip(repo: Repo) -> None:
    await repo.upsert_title("NPWR1_00", "A Game", "psn")
    await repo.upsert_title_achievements(
        [
            TitleAchievementRow(
                platform="psn",
                title_id="NPWR1_00",
                achievement_id=aid,
                name_en=name,
                trophy_type=tier,
            )
            for aid, name, tier in (("0", "A Game", "platinum"), ("1", "Do it", "bronze"))
        ],
        complete=True,
    )
    names = await repo.title_achievement_names("psn", "NPWR1_00")
    assert [row.achievement_id for row in names] == ["1"]


async def test_a_guide_that_gave_nothing_is_not_asked_again_until_something_changes(
    repo: Repo, steam_auth: SteamAuth, steam, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed(repo)
    asked = {"n": 0}

    async def locate(api_key, lines, achievements, marks=None):
        asked["n"] += 1
        return {}

    monkeypatch.setattr(se, "locate_sections", locate)
    await se.SteamExtras(repo, steam_auth, _Key()).fill_title("xbox", TITLE)  # type: ignore[arg-type]
    await se.SteamExtras(repo, steam_auth, _Key()).refresh_tips("xbox", TITLE)  # type: ignore[arg-type]
    assert asked["n"] == 1

    # A new achievement in the game's list changes the question.
    await repo.upsert_title_achievements(
        [
            TitleAchievementRow(
                platform="xbox_modern",
                title_id=TITLE,
                achievement_id="5",
                name_en="Fresh One",
                description_en="Do it",
            )
        ],
        complete=True,
    )
    await se.SteamExtras(repo, steam_auth, _Key()).refresh_tips("xbox", TITLE)  # type: ignore[arg-type]
    assert asked["n"] == 2


async def test_an_unchanged_guide_gives_back_its_tips_without_the_model(
    repo: Repo, steam_auth: SteamAuth, steam, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed(repo)
    asked = {"n": 0}

    async def locate(api_key, lines, achievements, marks=None):
        asked["n"] += 1
        return {0: [(3, 3)], 1: [(5, 5)], 2: [(7, 7)]}

    monkeypatch.setattr(se, "locate_sections", locate)
    await se.SteamExtras(repo, steam_auth, _Key()).fill_title("xbox", TITLE)  # type: ignore[arg-type]
    first = await repo.title_tips("xbox_modern", TITLE)
    assert asked["n"] == 1 and len(first) == 3

    # A month on, by a bot that has restarted: nothing changed, nothing is asked.
    await se.SteamExtras(repo, steam_auth, _Key()).refresh_tips("xbox", TITLE)  # type: ignore[arg-type]
    assert asked["n"] == 1
    assert await repo.title_tips("xbox_modern", TITLE) == first


async def test_a_guide_whose_tips_lost_to_a_later_one_is_never_asked_again(
    repo: Repo, steam_auth: SteamAuth, steam, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed(repo)
    first = _guide()
    second = make_guide("g2", "Second", list(first.lines))
    asked: list[str] = []

    async def guides_of(appid, api_key, stop_when=None):
        read = []
        for guide in (first, second):
            read.append(guide)
            if stop_when is not None and await stop_when(guide):
                return GuideSet(read, True)
        return GuideSet(read, True)

    async def locate(api_key, lines, achievements, marks=None):
        asked.append("g")
        # The first guide covers one achievement, the second fills half the list.
        return {0: [(3, 3)]} if len(asked) == 1 else {0: [(3, 3)], 1: [(5, 5)], 2: [(7, 7)]}

    monkeypatch.setattr(se, "guides_of", guides_of)
    monkeypatch.setattr(se, "locate_sections", locate)
    await se.SteamExtras(repo, steam_auth, _Key()).fill_title("xbox", TITLE)  # type: ignore[arg-type]
    assert len(asked) == 2
    assert {source for _, source in (await _sources(repo)).items()} == {"g2"}

    # Nothing changed: both answers are stored, neither guide is bought again.
    await se.SteamExtras(repo, steam_auth, _Key()).refresh_tips("xbox", TITLE)  # type: ignore[arg-type]
    assert len(asked) == 2


async def _sources(repo: Repo) -> dict[str, str]:
    cursor = await repo._conn.execute(
        "SELECT achievement_id, tip_source FROM title_achievements"
        " WHERE title_id = ? AND tip_source IS NOT NULL",
        (TITLE,),
    )
    return {row["achievement_id"]: row["tip_source"] for row in await cursor.fetchall()}


async def test_a_translation_filled_in_later_does_not_buy_the_guide_again(
    repo: Repo, steam_auth: SteamAuth, steam, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed(repo)
    asked = {"n": 0}

    async def locate(api_key, lines, achievements, marks=None):
        asked["n"] += 1
        return {0: [(3, 3)], 1: [(5, 5)], 2: [(7, 7)]}

    monkeypatch.setattr(se, "locate_sections", locate)
    await se.SteamExtras(repo, steam_auth, _Key()).fill_title("xbox", TITLE)  # type: ignore[arg-type]
    # The translator fills a Russian side the prompt never shows (it shows English).
    await repo._conn.execute(
        "UPDATE title_achievements SET description_ru = 'Сделай это' WHERE title_id = ?",
        (TITLE,),
    )
    await repo._conn.commit()
    await se.SteamExtras(repo, steam_auth, _Key()).refresh_tips("xbox", TITLE)  # type: ignore[arg-type]
    assert asked["n"] == 1
