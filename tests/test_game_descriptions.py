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
    async def get_key(self) -> str:
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
    game_id = await _in_a_game(repo, version_id)

    translator = game_descriptions.GameTranslator(repo, _Auth())
    translator.later([game_id])
    translator.later([game_id])  # already running
    await asyncio.gather(*translator._tasks)
    assert await translator.translate(game_id) is False  # Russian now: nothing to ask
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
    translator = game_descriptions.GameTranslator(repo, None)
    translator.later([1])
    assert not translator._tasks
    assert await translator.translate(1) is False


async def _in_a_game(repo: Repo, version_id: int) -> int:
    cursor = await repo._conn.execute(
        "INSERT INTO games (name, anchor_version_id, created_at, updated_at)"
        " VALUES ('Game', ?, '2026-10-30', '2026-10-30') RETURNING game_id",
        (version_id,),
    )
    game_id = int((await cursor.fetchone())[0])
    await repo._conn.execute(
        "UPDATE versions SET game_id = ? WHERE version_id = ?", (game_id, version_id)
    )
    await repo._conn.commit()
    return game_id
