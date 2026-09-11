"""The self-healing description backfill (2026-09-11, user request).

Xbox is the one platform whose first-time history arrives uncached — its
backfill uses the broad contract-2 call, which takes no language at all — so
the gap reopens with every new account. This job closes it a few titles at a
time, from inside the bot process, where XboxAuthService's per-user lock
actually applies.
"""

from __future__ import annotations

from bot.constants import Platform
from bot.db.repo import AchievementRow, Repo
from bot.poller.description_backfill import DescriptionBackfill
from bot.services.models import ParsedAchievement
from bot.services.xbox.client import XboxApiError

TG_ID = 1
XUID = "xuid-1"
TITLE_ID = "t1"


def _row(achievement_id: str, platform: str = Platform.XBOX_MODERN) -> AchievementRow:
    return AchievementRow(
        title_id=TITLE_ID,
        achievement_id=achievement_id,
        name="Ashes to Ashes",
        description="снимок",
        icon_url=None,
        unlocked_at="2026-09-02T10:00:00+00:00",
        gamerscore=10,
        rarity_percent=None,
        platform=platform,
    )


def _parsed(achievement_id: str, description: str | None) -> ParsedAchievement:
    return ParsedAchievement(
        achievement_id=achievement_id,
        title_id=TITLE_ID,
        title_name="Halo",
        name="Ashes to Ashes",
        description=description,
        icon_url=None,
        unlocked_at=None,
        gamerscore=10,
        rarity_percent=None,
        platform=Platform.XBOX_MODERN,
    )


class _FakeClient:
    """Answers with a different description per locale, so the result is
    recorded as a genuine platform translation rather than an LLM fill."""

    def __init__(self, by_locale: dict[str, list[ParsedAchievement]] | None = None) -> None:
        self.by_locale = by_locale or {
            "ru-RU": [_parsed("a1", "Сжечь всех врагов")],
            "en-US": [_parsed("a1", "Burn every enemy")],
        }
        self.calls: list[tuple[int, str, str]] = []

    async def title_achievements(self, tg_id, title_id, platform, *, language="en-US"):
        self.calls.append((tg_id, title_id, language))
        return self.by_locale[language]


class _DeadClient:
    async def title_achievements(self, *_args, **_kwargs):
        raise XboxApiError("token is dead")


async def _seed(repo: Repo, *achievement_ids: str) -> None:
    await repo.ensure_user(TG_ID)
    await repo.link_xbox_account(TG_ID, XUID, "Mad Omsk", None)
    await repo.insert_new_achievements(XUID, [_row(a) for a in achievement_ids], is_backfill=True)


async def test_a_tick_caches_an_uncached_title(repo: Repo) -> None:
    await _seed(repo, "a1")
    client = _FakeClient()

    await DescriptionBackfill(repo, client, object()).tick()  # type: ignore[arg-type]

    cached = await repo.get_cached_description(Platform.XBOX_MODERN, TITLE_ID, "a1")
    assert cached is not None
    assert cached.description_ru == "Сжечь всех врагов"
    assert cached.description_en == "Burn every enemy"
    assert cached.source == "native"


async def test_both_locales_are_requested(repo: Repo) -> None:
    await _seed(repo, "a1")
    client = _FakeClient()

    await DescriptionBackfill(repo, client, object()).tick()  # type: ignore[arg-type]

    assert {language for _tg, _title, language in client.calls} == {"ru-RU", "en-US"}


async def test_an_already_cached_title_is_not_fetched_again(repo: Repo) -> None:
    """The whole point of the gap query: once a title is cached, it costs
    nothing forever after."""
    await _seed(repo, "a1")
    await repo.cache_description(
        Platform.XBOX_MODERN,
        TITLE_ID,
        "a1",
        description_ru="уже есть",
        description_en="already here",
        source="native",
    )
    client = _FakeClient()

    await DescriptionBackfill(repo, client, object()).tick()  # type: ignore[arg-type]

    assert client.calls == []


async def test_a_tick_takes_only_its_own_bite(repo: Repo) -> None:
    """Pacing is the point — it must never try to drain the whole gap at
    once against someone else's API."""
    await repo.ensure_user(TG_ID)
    await repo.link_xbox_account(TG_ID, XUID, "Mad Omsk", None)
    rows = []
    for index in range(5):
        row = _row("a1")
        row.title_id = f"title-{index}"
        rows.append(row)
    await repo.insert_new_achievements(XUID, rows, is_backfill=True)

    client = _FakeClient()
    await DescriptionBackfill(repo, client, object(), titles_per_tick=2).tick()  # type: ignore[arg-type]

    # Two titles, two locales each.
    assert len(client.calls) == 4


async def test_a_title_nobody_can_answer_for_is_not_retried_forever(repo: Repo) -> None:
    """Without this the same dead title would be re-attempted every single
    minute — a hot loop against Microsoft's API, not a retry policy."""
    await _seed(repo, "a1")
    job = DescriptionBackfill(repo, _DeadClient(), object())  # type: ignore[arg-type]

    await job.tick()
    await job.tick()

    assert (Platform.XBOX_MODERN, TITLE_ID) in job._unanswerable


async def test_a_failing_title_does_not_end_the_tick(repo: Repo) -> None:
    await _seed(repo, "a1")
    job = DescriptionBackfill(repo, _DeadClient(), object())  # type: ignore[arg-type]

    await job.tick()  # must not raise

    assert await repo.get_cached_description(Platform.XBOX_MODERN, TITLE_ID, "a1") is None


async def test_nothing_to_do_is_a_cheap_no_op(repo: Repo) -> None:
    client = _FakeClient()

    await DescriptionBackfill(repo, client, object()).tick()  # type: ignore[arg-type]

    assert client.calls == []
