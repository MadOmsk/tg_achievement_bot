"""services/translate/descriptions.py::bilingual_descriptions — decides
"do we already have both languages cached, and if not, can the LLM fill the
gap" (2026-09-09 user request). Never touches a platform directly; the
native ru/en pair is always supplied by the caller."""

from __future__ import annotations

from bot.db.repo import Repo
from bot.services.translate import descriptions as descriptions_module
from bot.services.translate.auth import AnthropicAuth
from bot.services.translate.descriptions import bilingual_descriptions

PLATFORM = "steam"
TITLE_ID = "570"


async def _configured_anthropic_auth(repo: Repo, cipher) -> AnthropicAuth:
    auth = AnthropicAuth(repo, cipher, env_key="fake-key")
    await auth.get_key()  # force the env seed into app_settings
    return auth


async def test_two_genuinely_different_texts_are_cached_natively_no_llm_call(
    repo: Repo, cipher, monkeypatch
) -> None:
    async def _boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("a real native translation needs no LLM call at all")

    monkeypatch.setattr(descriptions_module, "translate_descriptions", _boom)
    anthropic_auth = await _configured_anthropic_auth(repo, cipher)

    result = await bilingual_descriptions(
        repo,
        anthropic_auth,
        PLATFORM,
        TITLE_ID,
        {"WIN": ("Победи в игре", "Win the game")},
    )

    assert result == {"WIN": ("Победи в игре", "Win the game")}
    cached = await repo.get_cached_description(PLATFORM, TITLE_ID, "WIN")
    assert cached is not None
    assert cached.source == "native"


async def test_identical_texts_ask_the_llm_for_a_russian_version(
    repo: Repo, cipher, monkeypatch
) -> None:
    async def _fake_translate(api_key, texts, *, target_language):
        assert target_language == "ru"
        return {aid: f"[ru] {text}" for aid, text in texts.items()}

    monkeypatch.setattr(descriptions_module, "translate_descriptions", _fake_translate)
    anthropic_auth = await _configured_anthropic_auth(repo, cipher)

    result = await bilingual_descriptions(
        repo,
        anthropic_auth,
        PLATFORM,
        TITLE_ID,
        {"WIN": ("Win the game", "Win the game")},
    )

    assert result == {"WIN": ("[ru] Win the game", "Win the game")}
    cached = await repo.get_cached_description(PLATFORM, TITLE_ID, "WIN")
    assert cached is not None
    assert cached.source == "llm"
    assert cached.description_ru == "[ru] Win the game"


async def test_already_cached_achievement_never_touches_the_llm_or_the_input(
    repo: Repo, cipher, monkeypatch
) -> None:
    await repo.cache_description(
        PLATFORM,
        TITLE_ID,
        "WIN",
        description_ru="уже переведено",
        description_en="already translated",
        source="llm",
    )

    async def _boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("a cache hit must never call the LLM")

    monkeypatch.setattr(descriptions_module, "translate_descriptions", _boom)
    anthropic_auth = await _configured_anthropic_auth(repo, cipher)

    result = await bilingual_descriptions(
        repo,
        anthropic_auth,
        PLATFORM,
        TITLE_ID,
        # Deliberately different from what's cached — proves the cached
        # value wins, the freshly "fetched" text passed in is ignored.
        {"WIN": ("Win the game", "Win the game")},
    )

    assert result == {"WIN": ("уже переведено", "already translated")}


async def test_no_anthropic_key_leaves_text_untranslated_and_uncached(
    repo: Repo, cipher, monkeypatch
) -> None:
    async def _boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("no key configured — must never even try to call the API")

    monkeypatch.setattr(descriptions_module, "translate_descriptions", _boom)
    anthropic_auth = AnthropicAuth(repo, cipher)  # never configured

    result = await bilingual_descriptions(
        repo,
        anthropic_auth,
        PLATFORM,
        TITLE_ID,
        {"WIN": ("Win the game", "Win the game")},
    )

    assert result == {"WIN": ("Win the game", "Win the game")}
    assert await repo.get_cached_description(PLATFORM, TITLE_ID, "WIN") is None


async def test_a_partial_llm_response_leaves_the_missing_one_uncached(
    repo: Repo, cipher, monkeypatch
) -> None:
    async def _partial(api_key, texts, *, target_language):
        # Only translates the first of two — the model dropped one entry.
        first_id = next(iter(texts))
        return {first_id: "переведено"}

    monkeypatch.setattr(descriptions_module, "translate_descriptions", _partial)
    anthropic_auth = await _configured_anthropic_auth(repo, cipher)

    result = await bilingual_descriptions(
        repo,
        anthropic_auth,
        PLATFORM,
        TITLE_ID,
        {
            "A": ("Text A", "Text A"),
            "B": ("Text B", "Text B"),
        },
    )

    translated = [aid for aid, (ru, en) in result.items() if ru != en]
    untranslated = [aid for aid, (ru, en) in result.items() if ru == en]
    assert len(translated) == 1
    assert len(untranslated) == 1
    assert await repo.get_cached_description(PLATFORM, TITLE_ID, translated[0]) is not None
    assert await repo.get_cached_description(PLATFORM, TITLE_ID, untranslated[0]) is None
