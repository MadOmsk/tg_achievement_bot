"""poller/fetcher.py::Fetcher._bilingual_descriptions — Xbox's counterpart
of services/steam/achievements.py's own version (2026-09-09 user request).
Only reachable via poll_title/catch_up, the two paths that actually publish
what they fetch; backfill's own x360 pass deliberately never calls this."""

from __future__ import annotations

from bot.db.repo import Repo
from bot.poller.fetcher import Fetcher
from bot.services.crypto import TokenCipher
from bot.services.translate import descriptions as descriptions_module
from bot.services.translate.auth import AnthropicAuth
from bot.services.xbox.models import ParsedAchievement

TG_ID = 42
XUID = "2533274829605736"


def _achievement(achievement_id: str, description: str | None) -> ParsedAchievement:
    return ParsedAchievement(
        achievement_id=achievement_id,
        title_id="1",
        title_name="Game",
        name=f"Achievement {achievement_id}",
        description=description,
        icon_url=None,
        unlocked_at=None,
        gamerscore=10,
        rarity_percent=42.0,
        platform="xbox_modern",
    )


class FakeClient:
    def __init__(self, by_language: dict[str, list[ParsedAchievement]]) -> None:
        self.by_language = by_language
        self.calls: list[str] = []

    async def title_achievements(self, tg_id, title_id, platform, *, language: str = "en-US"):
        self.calls.append(language)
        return self.by_language.get(language, [])


class FakePublisher:
    async def publish(self, *args: object, **kwargs: object) -> None:
        pass


async def _connected_user(repo: Repo, cipher: TokenCipher) -> None:
    await repo.ensure_user(TG_ID, "igor")
    await repo.save_refresh_token(TG_ID, cipher.encrypt("refresh"))
    await repo.link_xbox_account(TG_ID, XUID, "Mad Omsk", None)


async def _stored_description(repo: Repo, achievement_id: str) -> str | None:
    cursor = await repo._conn.execute(
        "SELECT description FROM seen_achievements WHERE xuid = ? AND achievement_id = ?",
        (XUID, achievement_id),
    )
    row = await cursor.fetchone()
    return row["description"] if row else None


async def test_genuine_native_translation_is_cached_with_no_llm_call(
    repo: Repo, cipher: TokenCipher, monkeypatch
) -> None:
    await _connected_user(repo, cipher)
    client = FakeClient(
        {
            "en-US": [_achievement("A1", "Win the game")],
            "ru-RU": [_achievement("A1", "Победи в игре")],
        }
    )
    anthropic_auth = AnthropicAuth(repo, cipher, env_key="fake-key")
    await anthropic_auth.get_key()

    async def _boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("a real native translation needs no LLM call at all")

    monkeypatch.setattr(descriptions_module, "translate_descriptions", _boom)
    fetcher = Fetcher(repo, client, FakePublisher(), anthropic_auth=anthropic_auth)

    assert await fetcher.poll_title(TG_ID, XUID, "Mad Omsk", "1", "xbox_modern", "Game") == 1

    cached = await repo.get_cached_description("xbox_modern", "1", "A1")
    assert cached is not None
    assert cached.source == "native"
    assert await _stored_description(repo, "A1") == "Победи в игре"


async def test_identical_locales_ask_the_llm_for_a_russian_version(
    repo: Repo, cipher: TokenCipher, monkeypatch
) -> None:
    await _connected_user(repo, cipher)
    client = FakeClient(
        {
            "en-US": [_achievement("A1", "Win the game")],
            "ru-RU": [_achievement("A1", "Win the game")],  # Xbox's own fallback, not a translation
        }
    )

    async def _fake_translate(api_key, texts, *, target_language):
        assert target_language == "ru"
        return {aid: f"[ru] {text}" for aid, text in texts.items()}

    monkeypatch.setattr(descriptions_module, "translate_descriptions", _fake_translate)
    anthropic_auth = AnthropicAuth(repo, cipher, env_key="fake-key")
    await anthropic_auth.get_key()
    fetcher = Fetcher(repo, client, FakePublisher(), anthropic_auth=anthropic_auth)

    assert await fetcher.poll_title(TG_ID, XUID, "Mad Omsk", "1", "xbox_modern", "Game") == 1

    cached = await repo.get_cached_description("xbox_modern", "1", "A1")
    assert cached is not None
    assert cached.source == "llm"
    assert await _stored_description(repo, "A1") == "[ru] Win the game"


async def test_second_poll_never_refetches_the_russian_locale(
    repo: Repo, cipher: TokenCipher, monkeypatch
) -> None:
    """Once achievement_description_cache has an entry, a later poll of the
    same title (a still-in-progress game, more achievements incoming) must
    not pay for the ru-RU request again for one it already resolved."""
    await _connected_user(repo, cipher)
    client = FakeClient(
        {
            "en-US": [_achievement("A1", "Win the game"), _achievement("A2", "Find 10 coins")],
            "ru-RU": [_achievement("A1", "Победи в игре"), _achievement("A2", "Find 10 coins")],
        }
    )
    anthropic_auth = AnthropicAuth(repo, cipher, env_key="fake-key")
    await anthropic_auth.get_key()

    async def _fake_translate(api_key, texts, *, target_language):
        return {aid: f"[ru] {text}" for aid, text in texts.items()}

    monkeypatch.setattr(descriptions_module, "translate_descriptions", _fake_translate)
    fetcher = Fetcher(repo, client, FakePublisher(), anthropic_auth=anthropic_auth)

    await fetcher.poll_title(TG_ID, XUID, "Mad Omsk", "1", "xbox_modern", "Game")
    assert client.calls.count("ru-RU") == 1

    # A3 arrives later in the same game — A1/A2 are already cached, only A3
    # (not present here at all) would ever need a fresh lookup; since it
    # isn't in this response either, no new ru-RU call should fire.
    await fetcher.poll_title(TG_ID, XUID, "Mad Omsk", "1", "xbox_modern", "Game")
    assert client.calls.count("ru-RU") == 1


async def test_no_anthropic_key_leaves_description_in_english_and_uncached(
    repo: Repo, cipher: TokenCipher, monkeypatch
) -> None:
    await _connected_user(repo, cipher)
    client = FakeClient(
        {
            "en-US": [_achievement("A1", "Win the game")],
            "ru-RU": [_achievement("A1", "Win the game")],
        }
    )

    async def _boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("no key configured - must never even try to call the API")

    monkeypatch.setattr(descriptions_module, "translate_descriptions", _boom)
    anthropic_auth = AnthropicAuth(repo, cipher)  # never configured
    fetcher = Fetcher(repo, client, FakePublisher(), anthropic_auth=anthropic_auth)

    assert await fetcher.poll_title(TG_ID, XUID, "Mad Omsk", "1", "xbox_modern", "Game") == 1

    assert await repo.get_cached_description("xbox_modern", "1", "A1") is None
    assert await _stored_description(repo, "A1") == "Win the game"
