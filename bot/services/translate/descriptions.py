"""Bilingual achievement description orchestration (2026-09-09 user
request) — the one place that decides "do we already have both languages
cached, and if not, can the LLM fill the gap". Platform clients only ever
supply what they themselves already fetched natively (Xbox/Steam/PSN all
now request both `ru`/`en` locales directly — see each platform's own
client for how); this module never talks to a platform, only to the shared
cache (db/repo/_descriptions.py) and, when needed, services/translate/client.py.

Names are never translated, only descriptions (explicit user instruction) —
nothing in this module ever sees an achievement's name at all.
"""

from __future__ import annotations

import logging

from bot.db.repo import Repo
from bot.services.translate.auth import AnthropicAuth, AnthropicNotConfiguredError
from bot.services.translate.client import translate_descriptions

log = logging.getLogger(__name__)

# Stored, shown, and still waiting for a translation — see schema.sql's own
# comment on `title_achievements.description_source`.
FALLBACK = "fallback"


async def bilingual_descriptions(
    repo: Repo,
    anthropic_auth: AnthropicAuth,
    platform: str,
    title_id: str,
    native: dict[str, tuple[str | None, str | None]],
) -> dict[str, tuple[str | None, str | None]]:
    """`native` maps achievement_id -> (description_ru, description_en), both
    already fetched directly from the platform in their own two locale
    requests. Returns the same shape, filled in with whichever language a
    platform's own fallback silently omitted.

    A platform's second locale request is a silent fallback, not an error
    (Steam/Xbox/PSN all just return their own default-language text again
    when no real translation exists — see each client's own comment) — the
    only signal available is "both requests came back identical". When
    that happens the shared text is treated as English (overwhelmingly the
    common case for a fallback default in practice) and the LLM is asked
    for a Russian version; nothing here ever guesses at a third language.

    Already-cached achievements are returned straight from the cache
    without ever touching the platform text passed in for them — cache
    forever, translate once, exactly like every other cache in this
    project (steam_schema_cache, hltb_cache, ...).
    """
    result: dict[str, tuple[str | None, str | None]] = {}
    needs_translation: dict[str, str] = {}

    for achievement_id, (description_ru, description_en) in native.items():
        cached = await repo.get_cached_description(platform, title_id, achievement_id)
        if cached is not None and cached.source == FALLBACK:
            # Stored untranslated last time because nothing could translate it
            # (no key, or a failed call). The text is already on screen; this
            # is the upgrade attempt, and it costs nothing when there is still
            # no key — the same fallback row is simply written again.
            needs_translation[achievement_id] = cached.description_en or description_en or ""
            continue
        if cached is not None:
            result[achievement_id] = (cached.description_ru, cached.description_en)
            continue
        if (
            description_ru is not None
            and description_en is not None
            and description_ru.strip() == description_en.strip()
        ):
            needs_translation[achievement_id] = description_en
            continue
        await repo.cache_description(
            platform,
            title_id,
            achievement_id,
            description_ru=description_ru,
            description_en=description_en,
            source="native",
        )
        result[achievement_id] = (description_ru, description_en)

    if not needs_translation:
        return result

    try:
        api_key = await anthropic_auth.require_key()
    except AnthropicNotConfiguredError:
        # No key at all. The text is still stored — untranslated, marked
        # `fallback`, `description_ru` left NULL (user request, 2026-09-13:
        # "don't silently ignore it, show the untranslated version"). It used
        # to be returned and not cached, which kept the door open for a later
        # translation but also meant every caller re-fetched the same title
        # forever and the render path had nothing to read.
        #
        # `fallback` is what keeps that door open instead: the row is offered
        # to the translator again on the next pass, and the moment a key
        # exists it becomes a real `llm` row.
        for achievement_id, text in needs_translation.items():
            await repo.cache_description(
                platform,
                title_id,
                achievement_id,
                description_ru=None,
                description_en=text,
                source=FALLBACK,
            )
            result[achievement_id] = (text, text)
        return result

    translated = await translate_descriptions(api_key, needs_translation, target_language="ru")
    for achievement_id, english_text in needs_translation.items():
        russian_text = translated.get(achievement_id)
        if russian_text is None:
            # The key exists but this one came back without a translation.
            # Same treatment as having no key: stored untranslated, marked
            # `fallback`, offered again next pass.
            log.info(
                "no translation for %s/%s/%s — stored untranslated, will retry later",
                platform,
                title_id,
                achievement_id,
            )
            await repo.cache_description(
                platform,
                title_id,
                achievement_id,
                description_ru=None,
                description_en=english_text,
                source=FALLBACK,
            )
            result[achievement_id] = (english_text, english_text)
            continue
        await repo.cache_description(
            platform,
            title_id,
            achievement_id,
            description_ru=russian_text,
            description_en=english_text,
            source="llm",
        )
        result[achievement_id] = (russian_text, english_text)

    return result
