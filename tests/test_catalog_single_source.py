"""The catalog is the one store of an achievement's names, descriptions and
rarity (#119)."""

from __future__ import annotations

from bot.db.repo import Repo, TitleAchievementRow


def _listed(achievement_id: str, **fields) -> TitleAchievementRow:
    return TitleAchievementRow(
        platform="xbox_modern",
        title_id="g",
        achievement_id=achievement_id,
        name_ru=fields.get("name_ru", "Имя"),
        name_en=fields.get("name_en", "Name"),
        description_ru=fields.get("description_ru"),
        description_en=fields.get("description_en"),
        icon_url=None,
        is_secret=False,
        rarity_percent=None,
        updated_at="2026-09-25T00:00:00+00:00",
    )


async def test_facts_a_poll_learned_are_not_the_games_list(repo: Repo) -> None:
    """A percentage or a name for every achievement a poll saw must not pass
    for the whole game: a game "complete" with its unlocks alone would never
    be asked for the rest, and would count as 100% done."""
    await repo.cache_rarity("xbox_modern", "g", {"1": 5.0, "2": 50.0})
    await repo.cache_names("xbox_modern", "g", {"1": ("Имя", "Name")})

    assert await repo.title_achievements_count("xbox_modern", "g") == 0
    assert await repo.get_title_achievements("xbox_modern", "g") == []

    # A live poll's earned-only rows are not the list either.
    await repo.upsert_title_achievements([_listed("1")])
    assert await repo.title_achievements_count("xbox_modern", "g") == 0

    await repo.upsert_title_achievements([_listed("1"), _listed("2"), _listed("3")], complete=True)

    assert await repo.title_achievements_count("xbox_modern", "g") == 3
    rows = {r.achievement_id: r for r in await repo.get_title_achievements("xbox_modern", "g")}
    assert rows["1"].rarity_percent == 5.0  # the poll's fact survives the refresh


async def test_a_refresh_never_overwrites_a_translation(repo: Repo) -> None:
    await repo.cache_description(
        "xbox_modern",
        "g",
        "1",
        description_ru="Победи",
        description_en="Win",
        source="llm",
    )
    # The platform gave the same English twice; the refresh passes it by.
    await repo.upsert_title_achievements([_listed("1", description_ru="Win", description_en="Win")])

    cached = await repo.get_cached_description("xbox_modern", "g", "1")
    assert cached is not None
    assert (cached.description_ru, cached.description_en, cached.source) == (
        "Победи",
        "Win",
        "llm",
    )


async def test_a_description_the_refresh_stored_still_goes_to_the_translator(
    repo: Repo,
) -> None:
    """Stored by the catalog refresh, never through bilingual_descriptions:
    rendered as it is, but not yet "cached" — its Russian may be the English
    given twice."""
    await repo.upsert_title_achievements([_listed("1", description_ru="Win", description_en="Win")])

    assert await repo.get_cached_description("xbox_modern", "g", "1") is None
    rendered = await repo.cached_descriptions([("xbox_modern", "g", "1")])
    assert rendered[("xbox_modern", "g", "1")].description_en == "Win"


async def test_the_english_under_ru_is_not_stored_as_russian(repo: Repo) -> None:
    """#127: a platform answering a Russian request in English is no Russian."""
    await repo.upsert_title_achievements(
        [_listed("1", description_ru="Win", description_en="Win")], complete=True
    )
    rows = await repo.get_title_achievements("xbox_modern", "g")
    assert rows[0].description_ru is None
    assert rows[0].description_en == "Win"


async def test_the_walker_translates_steam_from_stored_text(
    repo: Repo, monkeypatch, cipher
) -> None:
    """Steam/PSN (#127): the English is already stored, only the translation
    is missing — no platform request."""
    from bot.db.repo import AchievementRow
    from bot.poller.description_backfill import DescriptionBackfill
    from bot.services.translate import descriptions as descriptions_module
    from bot.services.translate.auth import AnthropicAuth

    await repo.ensure_user(7, "igor")
    await repo.link_platform_account(await repo.person_id(7), "steam", "7656", "Igor")
    await repo.insert_new_achievements_steam(
        await repo.person_id(7),
        "7656",
        [
            AchievementRow(
                title_id="550",
                achievement_id="WIN",
                name="Победа",
                description="Win the game",
                icon_url=None,
                unlocked_at=None,
                gamerscore=0,
                rarity_percent=None,
                platform="steam",
            )
        ],
        is_backfill=True,
    )

    async def _fake_translate(api_key, texts, *, target_language):
        return {aid: f"[ru] {text}" for aid, text in texts.items()}

    monkeypatch.setattr(descriptions_module, "translate_descriptions", _fake_translate)
    auth = AnthropicAuth(repo, cipher, env_key="fake-key")
    await auth.get_key()

    await DescriptionBackfill(repo, object(), auth).tick()  # type: ignore[arg-type]

    cached = await repo.get_cached_description("steam", "550", "WIN")
    assert cached is not None and cached.description_ru == "[ru] Win the game"


async def test_a_russian_side_must_read_as_russian(repo: Repo, monkeypatch, cipher) -> None:
    """Owner, 2026-09-25 (#127): not "differs from the English" but "has
    Cyrillic" — English off by a period, a placeholder or another language go
    to the translator; text with no letters needs no translation."""
    from bot.services.translate import descriptions as descriptions_module
    from bot.services.translate.auth import AnthropicAuth
    from bot.services.translate.descriptions import bilingual_descriptions

    asked: dict[str, str] = {}

    async def _fake_translate(api_key, texts, *, target_language):
        asked.update(texts)
        return {aid: f"[ru] {text}" for aid, text in texts.items()}

    monkeypatch.setattr(descriptions_module, "translate_descriptions", _fake_translate)
    auth = AnthropicAuth(repo, cipher, env_key="fake-key")
    await auth.get_key()

    result = await bilingual_descriptions(
        repo,
        auth,
        "xbox_modern",
        "g",
        {
            "period": ("Pass the first round.", "Pass the first round"),
            "placeholder": ("<Translated text>", "Collected 5 glasses"),
            "korean": ("한 번씩 물리치십시오.", "Beat each one"),
            "neutral": ("100%", "100%"),
            "real": ("Победи", "Win"),
        },
    )

    assert set(asked) == {"period", "placeholder", "korean"}
    assert result["real"] == ("Победи", "Win")
    assert result["neutral"] == ("100%", "100%")
    assert result["period"][0] == "[ru] Pass the first round"
