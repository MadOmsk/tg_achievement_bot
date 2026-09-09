"""services/psn/achievements.py::_bilingual_descriptions — PSN's own dual-
locale fetch (2026-09-09, #48), the third and last platform wired to
services/translate. Unlike Xbox/Steam (one client, a per-request language
parameter), PSN needs a *second* PSNAWP instance entirely (see
services/psn/auth.py::PsnAuth.get_translation_client) — these fakes key off
object identity of the client passed to `trophies_for_title` to tell the
primary and translation requests apart, the same way FakeClient.calls
tracks the `language=` argument in test_fetcher_bilingual.py."""

from __future__ import annotations

from dataclasses import dataclass

from bot.db.repo import Repo
from bot.services.crypto import TokenCipher
from bot.services.psn import achievements as psn_achievements_module
from bot.services.psn.achievements import sync_account
from bot.services.psn.client import EarnedTrophy
from bot.services.translate import descriptions as descriptions_module
from bot.services.translate.auth import AnthropicAuth

TG_ID = 42
ACCOUNT_ID = "acc-1"
PRIMARY_CLIENT = object()
TRANSLATION_CLIENT = object()


@dataclass
class _FakeTitle:
    np_communication_id: str
    title_name: str
    progress: int = 10


def _trophy(trophy_id: int, detail: str | None) -> EarnedTrophy:
    return EarnedTrophy(
        trophy_id=trophy_id,
        title_name="Some Game",
        title_icon_url=None,
        trophy_name=f"Trophy {trophy_id}",
        trophy_detail=detail,
        trophy_icon_url=None,
        trophy_type=None,  # type: ignore[arg-type]
        trophy_hidden=False,
        trophy_rarity=None,
        trophy_earn_rate=None,
        earned_date_time="2026-09-09T10:00:00+00:00",
    )


def _install_fakes(monkeypatch, titles, by_client: dict[object, dict[str, list[EarnedTrophy]]]):
    async def fake_titles(client, account_id, limit=None):
        return titles

    async def fake_trophies(client, account_id, title):
        return list(by_client.get(client, {}).get(title.np_communication_id, []))

    monkeypatch.setattr(psn_achievements_module, "trophy_titles_for_account", fake_titles)
    monkeypatch.setattr(psn_achievements_module, "trophies_for_title", fake_trophies)


async def _linked(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "igor")
    await repo.link_platform_account(TG_ID, "psn", ACCOUNT_ID, "Gamer")


async def _run(repo: Repo, anthropic_auth: AnthropicAuth, translation_client: object | None):
    return await sync_account(
        repo,
        PRIMARY_CLIENT,  # type: ignore[arg-type]
        TG_ID,
        ACCOUNT_ID,
        is_backfill=False,
        anthropic_auth=anthropic_auth,
        translation_client=translation_client,  # type: ignore[arg-type]
    )


async def _stored_description(repo: Repo, trophy_id: str) -> str | None:
    cursor = await repo._conn.execute(
        "SELECT description FROM seen_achievements WHERE xuid = ? AND achievement_id = ?",
        (ACCOUNT_ID, trophy_id),
    )
    row = await cursor.fetchone()
    return row["description"] if row else None


async def test_no_translation_client_leaves_the_english_text_untouched(
    repo: Repo, cipher: TokenCipher, monkeypatch
) -> None:
    await _linked(repo)
    title = _FakeTitle("NPWR00001_00", "Some Game")
    _install_fakes(
        monkeypatch,
        [title],
        {PRIMARY_CLIENT: {"NPWR00001_00": [_trophy(1, "Win the game")]}},
    )
    anthropic_auth = AnthropicAuth(repo, cipher, env_key="fake-key")
    await anthropic_auth.get_key()

    outcome = await _run(repo, anthropic_auth, translation_client=None)

    assert outcome.new_rows[0].description == "Win the game"
    assert await repo.get_cached_description("psn", "NPWR00001_00", "1") is None


async def test_genuine_native_translation_is_cached_with_no_llm_call(
    repo: Repo, cipher: TokenCipher, monkeypatch
) -> None:
    await _linked(repo)
    title = _FakeTitle("NPWR00001_00", "Some Game")
    _install_fakes(
        monkeypatch,
        [title],
        {
            PRIMARY_CLIENT: {"NPWR00001_00": [_trophy(1, "Win the game")]},
            TRANSLATION_CLIENT: {"NPWR00001_00": [_trophy(1, "Победи в игре")]},
        },
    )
    anthropic_auth = AnthropicAuth(repo, cipher, env_key="fake-key")
    await anthropic_auth.get_key()

    async def _boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("a real native translation needs no LLM call at all")

    monkeypatch.setattr(descriptions_module, "translate_descriptions", _boom)

    outcome = await _run(repo, anthropic_auth, translation_client=TRANSLATION_CLIENT)

    assert outcome.new_rows[0].description == "Победи в игре"
    cached = await repo.get_cached_description("psn", "NPWR00001_00", "1")
    assert cached is not None
    assert cached.source == "native"
    assert await _stored_description(repo, "1") == "Победи в игре"


async def test_identical_locales_ask_the_llm_for_a_russian_version(
    repo: Repo, cipher: TokenCipher, monkeypatch
) -> None:
    await _linked(repo)
    title = _FakeTitle("NPWR00001_00", "Some Game")
    _install_fakes(
        monkeypatch,
        [title],
        {
            PRIMARY_CLIENT: {"NPWR00001_00": [_trophy(1, "Win the game")]},
            # PSN's own fallback when it has no real translation — the
            # second request just echoes the same English text back.
            TRANSLATION_CLIENT: {"NPWR00001_00": [_trophy(1, "Win the game")]},
        },
    )
    anthropic_auth = AnthropicAuth(repo, cipher, env_key="fake-key")
    await anthropic_auth.get_key()

    async def _fake_translate(api_key, texts, *, target_language):
        assert target_language == "ru"
        return {tid: f"[ru] {text}" for tid, text in texts.items()}

    monkeypatch.setattr(descriptions_module, "translate_descriptions", _fake_translate)

    outcome = await _run(repo, anthropic_auth, translation_client=TRANSLATION_CLIENT)

    assert outcome.new_rows[0].description == "[ru] Win the game"
    cached = await repo.get_cached_description("psn", "NPWR00001_00", "1")
    assert cached is not None
    assert cached.source == "llm"


async def test_translation_client_failure_keeps_the_english_text_and_does_not_raise(
    repo: Repo, cipher: TokenCipher, monkeypatch
) -> None:
    """A dead/rate-limited second client must degrade gracefully — never
    raised as PsnApiError, never mistaken for the *primary* client (and so
    the shared NPSSO) being dead."""
    await _linked(repo)
    title = _FakeTitle("NPWR00001_00", "Some Game")

    async def fake_titles(client, account_id, limit=None):
        return [title]

    async def fake_trophies(client, account_id, title):
        if client is PRIMARY_CLIENT:
            return [_trophy(1, "Win the game")]
        raise RuntimeError("second client is having a bad day")

    monkeypatch.setattr(psn_achievements_module, "trophy_titles_for_account", fake_titles)
    monkeypatch.setattr(psn_achievements_module, "trophies_for_title", fake_trophies)
    anthropic_auth = AnthropicAuth(repo, cipher, env_key="fake-key")
    await anthropic_auth.get_key()

    outcome = await _run(repo, anthropic_auth, translation_client=TRANSLATION_CLIENT)

    assert outcome.new_rows[0].description == "Win the game"
    assert await repo.get_cached_description("psn", "NPWR00001_00", "1") is None


async def test_second_sync_never_refetches_an_already_cached_trophy(
    repo: Repo, cipher: TokenCipher, monkeypatch
) -> None:
    await _linked(repo)
    title = _FakeTitle("NPWR00001_00", "Some Game", progress=10)
    calls: list[object] = []

    async def fake_titles(client, account_id, limit=None):
        return [title]

    async def fake_trophies(client, account_id, title):
        calls.append(client)
        if client is PRIMARY_CLIENT:
            return [_trophy(1, "Win the game")]
        return [_trophy(1, "Победи в игре")]

    monkeypatch.setattr(psn_achievements_module, "trophy_titles_for_account", fake_titles)
    monkeypatch.setattr(psn_achievements_module, "trophies_for_title", fake_trophies)
    anthropic_auth = AnthropicAuth(repo, cipher, env_key="fake-key")
    await anthropic_auth.get_key()

    await _run(repo, anthropic_auth, translation_client=TRANSLATION_CLIENT)
    assert calls.count(TRANSLATION_CLIENT) == 1

    # Same game, flat progress this time — trophies_for_title (and so the
    # bilingual fetch) is never even called again, cache or not.
    await _run(repo, anthropic_auth, translation_client=TRANSLATION_CLIENT)
    assert calls.count(TRANSLATION_CLIENT) == 1


async def test_no_anthropic_key_leaves_description_in_english_and_uncached(
    repo: Repo, cipher: TokenCipher, monkeypatch
) -> None:
    await _linked(repo)
    title = _FakeTitle("NPWR00001_00", "Some Game")
    _install_fakes(
        monkeypatch,
        [title],
        {
            PRIMARY_CLIENT: {"NPWR00001_00": [_trophy(1, "Win the game")]},
            TRANSLATION_CLIENT: {"NPWR00001_00": [_trophy(1, "Win the game")]},
        },
    )

    async def _boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("no key configured — must never even try to call the API")

    monkeypatch.setattr(descriptions_module, "translate_descriptions", _boom)
    anthropic_auth = AnthropicAuth(repo, cipher)  # never configured

    outcome = await _run(repo, anthropic_auth, translation_client=TRANSLATION_CLIENT)

    assert outcome.new_rows[0].description == "Win the game"
    assert await repo.get_cached_description("psn", "NPWR00001_00", "1") is None


async def test_trophies_with_no_detail_text_are_left_alone(
    repo: Repo, cipher: TokenCipher, monkeypatch
) -> None:
    await _linked(repo)
    title = _FakeTitle("NPWR00001_00", "Some Game")
    calls: list[object] = []

    async def fake_titles(client, account_id, limit=None):
        return [title]

    async def fake_trophies(client, account_id, title):
        calls.append(client)
        return [_trophy(1, None)]

    monkeypatch.setattr(psn_achievements_module, "trophy_titles_for_account", fake_titles)
    monkeypatch.setattr(psn_achievements_module, "trophies_for_title", fake_trophies)
    anthropic_auth = AnthropicAuth(repo, cipher, env_key="fake-key")
    await anthropic_auth.get_key()

    outcome = await _run(repo, anthropic_auth, translation_client=TRANSLATION_CLIENT)

    assert outcome.new_rows[0].description is None
    # No detail text at all for this trophy — nothing to translate, so the
    # second client is never even asked.
    assert TRANSLATION_CLIENT not in calls
