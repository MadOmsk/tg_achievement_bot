"""A game put into Russian whole, whichever door it came through."""

from __future__ import annotations

import psycopg
import pytest

from bot.db.repo import Database, Repo
from bot.services import game_descriptions
from bot.services.game_descriptions import GameTranslator
from bot.services.translate import client, descriptions

STORY = "A long tale of war, brotherhood and the end of a world. " * 2


class _Auth:
    async def get_key(self) -> str:
        return "key"

    async def require_key(self) -> str:
        return "key"


async def _game_with_a_list(repo: Repo) -> int:
    cursor = await repo._conn.execute(
        "INSERT INTO games (name, created_at, updated_at) VALUES ('Game', 'x', 'x')"
        " RETURNING game_id"
    )
    game_id = int((await cursor.fetchone())[0])
    await repo._conn.execute(
        "INSERT INTO achievement_list_connectors (platform, title_id, name, updated_at)"
        " VALUES ('steam', '7', 'G', 'x')"
    )
    await repo._conn.execute(
        "INSERT INTO versions (store, product_id, console, platform, title_id, game_id, role,"
        " description_en, updated_at)"
        " VALUES ('steam', '7', 'steam', 'steam', '7', ?, 'version', ?, 'x')",
        (game_id, STORY),
    )
    rows = [("a", None, "Win."), ("b", "Победи.", "Beat."), ("c", "Win.", "Win it.")]
    for achievement_id, russian, english in rows:
        await repo._conn.execute(
            "INSERT INTO title_achievements (platform, title_id, achievement_id, description_ru,"
            " description_en, listed, updated_at) VALUES ('steam', '7', ?, ?, ?, 1, 'x')",
            (achievement_id, russian, english),
        )
    return game_id


@pytest.fixture
def _model(monkeypatch: pytest.MonkeyPatch) -> list:
    asked: list = []

    async def texts(api_key: str, wanted: dict, *, target_language: str) -> dict:
        asked.append(sorted(wanted))
        return {key: f"RU {value}" for key, value in wanted.items()}

    async def story(api_key: str, text: str, *, target_language: str) -> str:
        asked.append(text)
        return f"RU {text}"

    monkeypatch.setattr(descriptions, "translate_descriptions", texts)
    monkeypatch.setattr(game_descriptions, "translate_game_description", story)
    return asked


async def test_a_game_goes_whole_and_only_what_has_no_russian_is_paid_for(
    repo: Repo, _model: list
) -> None:
    game_id = await _game_with_a_list(repo)
    translator = GameTranslator(repo, _Auth())
    assert await translator.translate(game_id) is True
    # The Russian the catalog already had is only marked; "Win." is no Russian.
    assert sorted(map(str, _model)) == sorted(["['a', 'c']", STORY])
    cursor = await repo._conn.execute(
        "SELECT achievement_id, description_ru, description_source FROM title_achievements"
        " ORDER BY achievement_id"
    )
    assert [tuple(row) for row in await cursor.fetchall()] == [
        ("a", "RU Win.", "llm"),
        ("b", "Победи.", "native"),
        ("c", "RU Win it.", "llm"),
    ]
    _model.clear()
    assert await translator.translate(game_id) is False
    assert _model == []


async def test_a_page_is_told_what_is_on_its_way_and_starts_it(repo: Repo, _model: list) -> None:
    game_id = await _game_with_a_list(repo)
    translator = GameTranslator(repo, _Auth())
    assert (await translator.pending(game_id, "en")).achievements is False
    found = await translator.pending(game_id, "ru")
    assert found.description and found.achievements
    for task in list(translator._tasks):
        await task
    found = await translator.pending(game_id, "ru")
    assert not found.description and not found.achievements


async def test_what_failed_rests_and_no_page_blurs_it(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    game_id = await _game_with_a_list(repo)
    calls: list[str] = []

    async def nothing(*args: object, **kwargs: object) -> dict:
        calls.append("texts")
        return {}

    async def no_story(*args: object, **kwargs: object) -> None:
        calls.append("story")

    monkeypatch.setattr(descriptions, "translate_descriptions", nothing)
    monkeypatch.setattr(game_descriptions, "translate_game_description", no_story)
    translator = GameTranslator(repo, _Auth())
    await translator.translate(game_id)
    assert sorted(calls) == ["story", "texts"]
    assert await translator.is_due(game_id) is False
    found = await translator.pending(game_id, "ru")
    assert not found.description and not found.achievements
    assert await translator.translate(game_id) is False
    assert len(calls) == 2


def test_a_batch_is_bounded_by_its_text_too() -> None:
    chunks = client._chunks({"a": "x" * 7000, "b": "x" * 2000, "c": "y"})
    assert [sorted(chunk) for chunk in chunks] == [["a"], ["b", "c"]]
    many = client._chunks({str(i): "x" for i in range(client._BATCH_SIZE + 1)})
    assert [len(chunk) for chunk in many] == [client._BATCH_SIZE, 1]


async def test_a_reply_cut_off_goes_again_in_halves(monkeypatch: pytest.MonkeyPatch) -> None:
    sizes: list[int] = []

    class _Response:
        status_code = 200

        def __init__(self, count: int) -> None:
            self._count = count

        def json(self) -> dict:
            if self._count > 1:
                return {"stop_reason": "max_tokens", "content": []}
            return {"stop_reason": "end_turn", "content": [{"type": "text", "text": '["ru"]'}]}

    class _Client:
        def __init__(self, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, url: str, **kwargs: dict) -> _Response:
            prompt = kwargs["json"]["messages"][0]["content"]
            count = int(prompt.split("ONLY a JSON array of ")[1].split()[0])
            sizes.append(count)
            return _Response(count)

    monkeypatch.setattr(client.httpx, "AsyncClient", _Client)
    done = await client.translate_descriptions("k", {"a": "x", "b": "y"}, target_language="ru")
    assert sizes == [2, 1, 1]
    assert done == {"a": "ru", "b": "ru"}


async def test_the_queue_is_off_until_switched_on(repo: Repo, _model: list) -> None:
    from bot.poller import translations
    from bot.services.guide_translations import GuideTranslator
    from bot.services.news_translations import NewsTranslator

    await _game_with_a_list(repo)
    walker = translations.Translations(
        repo,
        NewsTranslator(repo, _Auth()),
        GuideTranslator(repo, _Auth()),
        GameTranslator(repo, _Auth()),
    )
    await walker.tick()
    assert _model == []
    await repo.set_app_setting(translations.QUEUE_KEY, "1")
    await walker.tick()
    assert _model != []


async def test_an_answer_that_cannot_be_used_costs_only_the_odd_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sizes: list[int] = []

    class _Response:
        status_code = 200

        def __init__(self, count: int, text: str) -> None:
            self._count, self._text = count, text

        def json(self) -> dict:
            if "odd" in self._text:
                answer = "not json"
            else:
                answer = '["ru"]' if self._count == 1 else '["ru", "ru"]'
            return {"stop_reason": "end_turn", "content": [{"type": "text", "text": answer}]}

    class _Client:
        def __init__(self, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, url: str, **kwargs: dict) -> _Response:
            prompt = kwargs["json"]["messages"][0]["content"]
            count = int(prompt.split("ONLY a JSON array of ")[1].split()[0])
            sizes.append(count)
            return _Response(count, prompt)

    monkeypatch.setattr(client.httpx, "AsyncClient", _Client)
    done = await client.translate_descriptions("k", {"a": "x", "b": "odd"}, target_language="ru")
    assert done == {"a": "ru"}
    assert sizes == [2, 1, 1]


async def test_a_game_that_keeps_failing_rests_longer(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    translator = GameTranslator(repo, _Auth())
    now = game_descriptions.time.monotonic()
    translator._rest(1)
    first = translator._failed[1] - now
    translator._rest(1)
    assert translator._failed[1] - now > first + 3000
    for _ in range(10):
        translator._rest(1)
    assert translator._failed[1] - now <= game_descriptions.LONGEST_REST_SECONDS + 5


async def test_only_what_waits_for_the_model_is_blurred(repo: Repo) -> None:
    await _game_with_a_list(repo)
    translator = GameTranslator(repo, _Auth())
    assert await translator.rows_on_their_way("steam", "7") == {"a", "c"}


async def test_the_catalog_link_lock_is_one_at_a_time(repo: Repo, database: Database) -> None:
    with psycopg.connect(database._dsn, autocommit=True) as other:
        taken = "SELECT pg_try_advisory_lock(234001)"
        async with repo.catalog_link_lock():
            assert other.execute(taken).fetchone()[0] is False
        assert other.execute(taken).fetchone()[0] is True
        other.execute("SELECT pg_advisory_unlock(234001)")
