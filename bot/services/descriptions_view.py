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


def _for_locale(cached: CachedDescription, locale: str) -> str | None:
    text = cached.description_en if locale == "en" else cached.description_ru
    # An empty string is as useless as a missing one, and both platforms and
    # the LLM can produce either.
    return text if text and text.strip() else None


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
    cached = await repo.cached_descriptions(
        [(row.platform, row.title_id, row.achievement_id) for row in rows]
    )
    if not cached:
        return rows

    localized = []
    for row in rows:
        entry = cached.get((row.platform, row.title_id, row.achievement_id))
        text = _for_locale(entry, locale) if entry is not None else None
        localized.append(replace(row, description=text) if text is not None else row)
    return localized
