"""Pick the right language for an achievement's description at render time
(#48).

`seen_achievements.description` is a snapshot: whatever language the platform
client happened to store when that person unlocked the achievement (always
Russian, historically). The bilingual cache
(`achievement_description_cache`) is the real source — it holds both sides,
is shared across everyone who ever unlocks the same achievement, and is
filled in by all three platform clients.

So the stored column stops being the thing rendered and becomes the
fallback, for the two cases the cache cannot answer: a row unlocked before
the cache existed, and an achievement whose translation genuinely never
arrived (no Anthropic key, or the platform gave one language only).

Names are never touched here — only descriptions (CLAUDE.md).
"""

from __future__ import annotations

from dataclasses import replace

from bot.db.repo import AchievementRow, CachedDescription, Repo


def _usable(text: str | None) -> str | None:
    """An empty string is as useless as a missing one, and both platforms and
    the LLM can produce either."""
    return text if text and text.strip() else None


def _for_locale(cached: CachedDescription, locale: str) -> str | None:
    """The asked-for language, or the other one untranslated.

    Falling back across languages is deliberate (user request, 2026-09-13):
    a `fallback` row has only the platform's own language, and showing that
    beats showing nothing. The reader sees untranslated text, which is what
    the platform itself would have shown them.
    """
    wanted, other = (
        (cached.description_en, cached.description_ru)
        if locale == "en"
        else (cached.description_ru, cached.description_en)
    )
    return _usable(wanted) or _usable(other)


async def localize_descriptions(
    repo: Repo, rows: list[AchievementRow], locale: str
) -> list[AchievementRow]:
    """Return `rows` with each description swapped for the cached one in
    `locale`, where there is one. Rows are copied, never mutated: the same
    list is rendered again for the next chat, which may be in another
    language."""
    if not rows:
        return rows
    # The default locale is what the stored column already holds for every
    # row written before this existed, but not necessarily what it holds for
    # a row whose platform only ever returned English — so the lookup runs
    # for every locale, not just the non-default ones.
    keys = [(row.platform, row.title_id, row.achievement_id) for row in rows]
    cached = await repo.cached_descriptions(keys)
    # The name is the platform's own in both languages, cached beside the
    # description and swapped the same way (#61). Stored names were whatever
    # language that platform's main call happens to use — English for Xbox and
    # PSN, Russian for Steam — so a chat saw one platform in its own language
    # and the others in the platform's, whatever the chat had chosen.
    names = await repo.cached_names(keys)
    # The game's own name, for the one platform that localizes it (#61).
    titles = await repo.title_names([row.title_id for row in rows])
    if not cached and not names and not titles:
        return rows

    localized = []
    for row in rows:
        key = (row.platform, row.title_id, row.achievement_id)
        entry = cached.get(key)
        text = _for_locale(entry, locale) if entry is not None else None
        name_pair = names.get(key)
        name = _name_for_locale(name_pair, locale) if name_pair is not None else None
        title_pair = titles.get(row.title_id)
        title = _name_for_locale(title_pair, locale) if title_pair is not None else None
        changes = {}
        if text is not None:
            changes["description"] = text
        if name is not None:
            changes["name"] = name
        if title is not None:
            changes["title_name"] = title
        localized.append(replace(row, **changes) if changes else row)
    return localized


def _name_for_locale(pair: tuple[str | None, str | None], locale: str) -> str | None:
    """The asked-for language, or the other one — same order as descriptions.

    A name is never translated (CLAUDE.md): both sides here are the
    platform's own strings, and where a platform has no name in one language
    the other stands rather than the line going blank.
    """
    name_ru, name_en = pair
    wanted, other = (name_en, name_ru) if locale == "en" else (name_ru, name_en)
    return _usable(wanted) or _usable(other)
