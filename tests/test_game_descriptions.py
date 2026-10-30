"""A game's description translated like an achievement's (#230)."""

from __future__ import annotations

import asyncio

import pytest

from bot.db.repo import Repo
from bot.db.repo._stores import native_ru
from bot.services import game_descriptions, game_page
from bot.services.stores import StoreVersion

ENGLISH = "A long tale of war, brotherhood and the end of a world. " * 2
RUSSIAN = "Долгая история войны, братства и конца целого мира. " * 2


def _version(**kwargs) -> dict:
    return {"version_id": 1, "description_en": ENGLISH, "description_ru": None} | kwargs


def test_a_store_russian_is_trusted_only_when_it_is_russian() -> None:
    assert native_ru(RUSSIAN, ENGLISH) == RUSSIAN
    assert native_ru(ENGLISH, ENGLISH) is None  # the English handed back
    assert native_ru("A different English text", ENGLISH) is None
    assert native_ru(None, ENGLISH) is None


def test_the_reader_gets_a_translation_only_of_the_english_it_was_made_of() -> None:
    llm = _version(
        description_ru=RUSSIAN,
        description_source="llm",
        description_ru_of=game_page.text_hash(ENGLISH),
    )
    assert game_page.description_of([llm], None, "ru")["lang"] == "ru"
    stale = llm | {"description_en": ENGLISH + " Now with a sequel."}
    assert game_page.description_of([stale], None, "ru")["lang"] == "en"
    legacy = _version(description_ru=ENGLISH)  # before 138: English as Russian
    assert game_page.description_of([legacy], None, "ru")["lang"] == "en"


def test_what_is_translated() -> None:
    assert game_page.to_translate([_version()], None) == ("version", 1, ENGLISH)
    native = _version(description_ru=RUSSIAN, description_source="native")
    assert game_page.to_translate([native], None) is None
    hltb = {"hltb_id": 7, "summary_en": ENGLISH + " More.", "summary_ru": None}
    assert game_page.to_translate([], hltb) == ("hltb", 7, ENGLISH + " More.")
    assert game_page.to_translate([_version(description_en=None)], None) is None


class _Auth:
    async def require_key(self) -> str:
        return "key"


@pytest.mark.asyncio
async def test_a_version_is_translated_once_and_a_store_russian_wins(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    async def translate(api_key: str, text: str, *, target_language: str) -> str:
        calls.append(text)
        return RUSSIAN

    monkeypatch.setattr(game_descriptions, "translate_game_description", translate)
    await repo.save_version(
        StoreVersion(store="xbox", product_id="P1", console="one", description_en=ENGLISH),
        platform=None,
        title_id=None,
    )
    rows = await repo.versions_of_product("xbox", "P1")
    version_id = int(rows[0]["version_id"])
    versions = [_version(version_id=version_id)]

    game_descriptions.translate_later(repo, _Auth(), versions, None)
    game_descriptions.translate_later(repo, _Auth(), versions, None)  # already running
    await asyncio.gather(*game_descriptions._TASKS)
    assert calls == [ENGLISH]
    cursor = await repo._conn.execute(
        "SELECT description_ru, description_source, description_ru_of FROM versions"
        " WHERE version_id = ?",
        (version_id,),
    )
    assert tuple(await cursor.fetchone()) == (RUSSIAN, "llm", game_page.text_hash(ENGLISH))

    # A store answering the Russian request in English keeps our translation;
    # the store's own Russian replaces it.
    await repo.save_version(
        StoreVersion(
            store="xbox", product_id="P1", console="one",
            description_en=ENGLISH, description_ru=ENGLISH,
        ),
        platform=None,
        title_id=None,
    )  # fmt: skip
    cursor = await repo._conn.execute(
        "SELECT description_source FROM versions WHERE version_id = ?", (version_id,)
    )
    assert (await cursor.fetchone())[0] == "llm"
    own = "Своё описание магазина, на русском языке, довольно длинное."
    await repo.save_version(
        StoreVersion(
            store="xbox", product_id="P1", console="one",
            description_en=ENGLISH, description_ru=own,
        ),
        platform=None,
        title_id=None,
    )  # fmt: skip
    cursor = await repo._conn.execute(
        "SELECT description_ru, description_source, description_ru_of FROM versions"
        " WHERE version_id = ?",
        (version_id,),
    )
    assert tuple(await cursor.fetchone()) == (own, "native", None)


@pytest.mark.asyncio
async def test_no_key_leaves_it_english(repo: Repo) -> None:
    game_descriptions.translate_later(repo, None, [_version()], None)
    assert not game_descriptions._TASKS


@pytest.mark.asyncio
async def test_a_page_hears_a_translation_is_on_its_way(monkeypatch: pytest.MonkeyPatch) -> None:
    """The page says the text is coming, so the app asks again (#230)."""
    started = asyncio.Event()

    async def translate(*_: object) -> None:
        started.set()

    monkeypatch.setattr(game_descriptions, "_translate", translate)
    assert game_descriptions.translate_later(None, _Auth(), [_version()], None)  # type: ignore[arg-type]
    native = _version(description_ru=RUSSIAN, description_source="native")
    assert not game_descriptions.translate_later(None, _Auth(), [native], None)  # type: ignore[arg-type]
    await asyncio.gather(*game_descriptions._TASKS)
    assert started.is_set()


class _GameRepo:
    async def game_of_list(self, platform: str, title_id: str) -> int | None:
        return 5 if (platform, title_id) == ("steam", "10") else None

    async def game_hltb(self, game_id: int) -> None:
        return None

    async def game_page_versions(self, game_id: int) -> list[dict]:
        return [_version(version_id=9)]


@pytest.mark.asyncio
async def test_a_collected_list_has_its_game_translated_at_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A collection that brought the English hands it to the translator then,
    not on the next visit (`StoreCollector.on_collected`)."""
    from bot.services import store_collect

    done: list[tuple[str, int, str]] = []

    async def translate(repo, auth, kind: str, key: int, english: str) -> None:
        done.append((kind, key, english))

    async def on() -> bool:
        return True

    async def collect(self, platform: str, title_id: str, **_: object):
        return store_collect.CollectReport(platform, title_id)

    class _Queue:
        async def octopus_enqueue(self, *_: object) -> None:
            return None

    monkeypatch.setattr(game_descriptions, "_translate", translate)
    monkeypatch.setattr(store_collect, "collection_on", lambda _repo: on())
    monkeypatch.setattr(store_collect.StoreCollector, "collect", collect)
    collector = store_collect.StoreCollector(_Queue())  # type: ignore[arg-type]

    async def collected(platform: str, title_id: str) -> None:
        await game_descriptions.translate_game(_GameRepo(), _Auth(), platform, title_id)  # type: ignore[arg-type]

    collector.on_collected = collected
    collector.ensure("steam", "10", reason="page")
    assert collector.running("steam", "10")
    await asyncio.gather(*collector._running.values())
    await asyncio.gather(*game_descriptions._TASKS)
    assert done == [("version", 9, ENGLISH)]
    assert not collector.running("steam", "10")
