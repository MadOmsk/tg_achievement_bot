"""HowLongToBeat lookups (SPEC 6.6): search and resolve, cached forever.

No official API exists; the third-party howlongtobeatpy package reverse-
engineers HLTB's own search endpoint and tracks its (regularly changing)
obfuscation for us. Hidden behind this module so a break there, or a future
library swap, never touches handlers or the database schema beyond this file.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

import httpx
from howlongtobeatpy import HowLongToBeat

from bot.db.repo import HltbCacheRow, Repo
from bot.services.translate.auth import AnthropicAuth, AnthropicNotConfiguredError
from bot.services.translate.client import translate_game_description

log = logging.getLogger(__name__)

DEFAULT_MAX_RESULTS = 20
_PAGE_REQUEST_TIMEOUT = 10.0
# howlongtobeatpy itself only ever fetches by *searching*, never the game's
# own page — neither genre nor description lives in that response (verified
# live: the search JSON that backs both `search()` and `resolve()`'s
# `async_search_from_id` has profile_platform/profile_dev but no
# profile_genre and no profile_summary at all). The game page carries both,
# embedded as JSON in a `__NEXT_DATA__` script tag (Next.js server-rendered
# props, not scraped-out-of-prose HTML) — confirmed live against several
# different games. A plain UA string was enough; HLTB does not appear to
# gate this particular page on anything fancier.
_PAGE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}
_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)

# Xbox's own title names carry trademark clutter and separator punctuation
# HLTB's search doesn't expect — e.g. a chat-recent-games shortcut hands over
# "HELLDIVERS™ 2" verbatim (SPEC 6.6). Stripped to spaces, not deleted
# outright, so "Halo: Reach" still searches as two words, not "HaloReach".
_SEARCH_NOISE = re.compile(r"[™©®℠:,]")

# A zero-result search retries once, silently, with just the first word that
# isn't one of these (SPEC 6.6) — "Dishonored Definitive Edition PC" finds
# nothing on HLTB, "Dishonored" alone does. Only articles/prepositions/
# pronouns/platform names are skipped when picking that word — an edition
# qualifier like "definitive" is never checked at all, since the first real
# word found is kept and everything after it is simply dropped.
_STOPWORDS = {
    # articles
    "a",
    "an",
    "the",
    # prepositions
    "of",
    "on",
    "in",
    "at",
    "to",
    "for",
    "with",
    "from",
    "by",
    # pronouns
    "this",
    "that",
    "these",
    "those",
    "it",
    "its",
    "his",
    "her",
    "their",
    # platform names — noise in a title search, not part of the title
    "pc",
    "xbox",
    "playstation",
    "ps",
    "ps1",
    "ps2",
    "ps3",
    "ps4",
    "ps5",
    "switch",
    "steam",
    "windows",
}


class HltbError(Exception):
    """Expected failure — HLTB unreachable, or its layout changed underneath
    the library. Same "log and tell the user, never crash" treatment as an
    XboxApiError (SPEC 1.5)."""


@dataclass(slots=True)
class HltbResult:
    hltb_id: int
    name: str
    release_year: int | None
    main_hours: float | None
    extra_hours: float | None
    completionist_hours: float | None
    platforms: list[str]
    game_url: str | None
    image_url: str | None
    genre: str | None
    description_en: str | None = None
    description_ru: str | None = None

    def description(self, locale: str) -> str | None:
        """The summary in the asked-for locale, falling back to whichever
        side exists — an untranslated English description still says more
        than no description at all (#2)."""
        if locale == "ru":
            return self.description_ru or self.description_en
        return self.description_en or self.description_ru


async def search(query: str, limit: int = DEFAULT_MAX_RESULTS) -> list[HltbResult]:
    """Up to `limit` candidates, best match first — nobody types an exact
    HLTB title, so the caller always needs to let a person pick (SPEC 6.6).
    `limit` is admin-configurable (`hltb_results_limit`, 6.4) — the caller
    reads the setting, this stays a plain parameter with a sane default."""
    cleaned = _clean_query(query)
    results = await _search_raw(cleaned, limit)
    if results:
        return results

    fallback = _pick_fallback_word(cleaned)
    if fallback is None:
        return results  # nothing sensible left to retry with — a real "not found"

    try:
        return await _search_raw(fallback, limit)
    except HltbError:
        # The retry failing must not turn what would have been a plain
        # "nothing found" into a hard error the caller didn't have before.
        return results


async def _search_raw(cleaned_query: str, limit: int) -> list[HltbResult]:
    try:
        # similarity_case_sensitive=False: found live — Xbox's own title
        # names are often ALL CAPS ("HELLDIVERS 2"), and the library's
        # default case-sensitive similarity check threw out the correct
        # match entirely (0 results) rather than just ranking it lower.
        entries = await HowLongToBeat().async_search(cleaned_query, similarity_case_sensitive=False)
    except Exception as exc:  # the library exposes no narrower exception type
        raise HltbError(f"HLTB search failed for {cleaned_query!r}: {exc}") from None
    entries = sorted(entries or [], key=lambda e: e.similarity, reverse=True)
    return [_as_result(e) for e in entries[:limit]]


def _pick_fallback_word(cleaned_query: str) -> str | None:
    """The already-cleaned query's first word that isn't a stopword — or
    None if there's nothing worth retrying with (a single-word query would
    just repeat the same search; an all-stopword query has no good word at
    all)."""
    words = cleaned_query.split()
    if len(words) < 2:
        return None
    for word in words:
        if word.lower() not in _STOPWORDS:
            return word
    return None


async def resolve(
    repo: Repo, hltb_id: int, *, anthropic_auth: AnthropicAuth | None = None
) -> HltbResult:
    """Cached forever once a person actually picks a result — a completion
    time does not meaningfully change day to day, and HLTB's search is the
    fragile part here, not this number (SPEC 6.6).

    `anthropic_auth`, when given, also lets a freshly-fetched (or an
    older, description-less) entry pick up its Russian summary (#2) — one
    Haiku call per game, ever, the first time somebody looks it up.
    """
    cached = await repo.hltb_get_cached(hltb_id)
    if cached is not None:
        return await _top_up_translation(repo, _from_cache_row(cached), anthropic_auth)

    try:
        entry = await HowLongToBeat().async_search_from_id(hltb_id)
    except Exception as exc:
        raise HltbError(f"HLTB lookup failed for id={hltb_id}: {exc}") from None
    if entry is None:
        raise HltbError(f"HLTB has no entry for id={hltb_id}")

    result = _as_result(entry)
    if result.game_url:
        # Only for the one game someone actually picked, not every candidate
        # in a 20-result search list — genre and description are both
        # nice-to-haves, one extra request per newly-cached game is fine,
        # one per search is not. Both come out of the same single fetch.
        result.genre, result.description_en = await _fetch_page_details(result.game_url)
    result.description_ru = await _translate(result.description_en, anthropic_auth)
    await _cache(repo, result)
    return result


async def _top_up_translation(
    repo: Repo, result: HltbResult, anthropic_auth: AnthropicAuth | None
) -> HltbResult:
    """Self-healing for a row cached before descriptions existed at all, or
    cached while no Anthropic key was configured (#2): the English side is
    already there, the Russian one is filled in on the next lookup rather
    than being stuck missing forever behind a cache that never expires.

    Deliberately does NOT re-fetch the HLTB page for a row whose English
    side is missing too — that is either a game HLTB has no summary for
    (most of them: verified live, obscure entries return an empty
    profile_summary) or a row from before migration 035, and re-fetching
    every such card forever to find out is not worth one extra request per
    lookup. `scripts/backfill_hltb_descriptions.py` is the one-off that
    covers those.
    """
    if result.description_ru or not result.description_en:
        return result
    translated = await _translate(result.description_en, anthropic_auth)
    if translated is None:
        return result
    result.description_ru = translated
    await _cache(repo, result)
    return result


async def _translate(text: str | None, anthropic_auth: AnthropicAuth | None) -> str | None:
    """None whenever a translation can't be had — no text, no key, or the
    call itself failing. The caller stores that None and tries again on the
    next lookup, exactly like a platform description the LLM couldn't reach
    (services/translate/descriptions.py's own "left untranslated, will retry
    later")."""
    if not text or anthropic_auth is None:
        return None
    try:
        api_key = await anthropic_auth.require_key()
    except AnthropicNotConfiguredError:
        return None
    return await translate_game_description(api_key, text, target_language="ru")


async def _cache(repo: Repo, result: HltbResult) -> None:
    await repo.hltb_cache_result(
        HltbCacheRow(
            hltb_id=result.hltb_id,
            name=result.name,
            release_year=result.release_year,
            main_hours=result.main_hours,
            extra_hours=result.extra_hours,
            completionist_hours=result.completionist_hours,
            platforms=result.platforms,
            game_url=result.game_url,
            image_url=result.image_url,
            genre=result.genre,
            description_en=result.description_en,
            description_ru=result.description_ru,
        )
    )


async def _fetch_page_details(game_url: str) -> tuple[str | None, str | None]:
    """(genre, description), both best-effort — a failure here must not cost
    the rest of the card (SPEC 1.5's "expected failure, never crash"), so
    every error just means "no genre and no description this time", logged
    and swallowed, never raised as HltbError."""
    try:
        async with httpx.AsyncClient(timeout=_PAGE_REQUEST_TIMEOUT) as client:
            response = await client.get(game_url, headers=_PAGE_HEADERS)
        response.raise_for_status()
        return _extract_details(response.text)
    except Exception as exc:
        log.info("could not fetch HLTB page details from %s: %s", game_url, exc)
        return None, None


def _extract_details(html_page: str) -> tuple[str | None, str | None]:
    """Genre and description both live in the game page's own `__NEXT_DATA__`
    — Next.js' server-rendered props, real structured JSON rather than text
    scraped out of prose HTML (still someone else's undocumented internal
    shape, same fragility class as the search JSON `search()`/`resolve()`
    already depend on via howlongtobeatpy). Verified live against several
    different games — same path every time:
    props.pageProps.game.data.game[0], `profile_genre` and `profile_summary`.

    The description is deliberately read from here rather than from the
    rendered HTML: the paragraph is also in the markup, but only behind a
    CSS-module class name carrying a build hash that changes on every HLTB
    frontend deploy.
    """
    match = _NEXT_DATA_RE.search(html_page)
    if not match:
        return None, None
    data = json.loads(match.group(1))
    games = data["props"]["pageProps"]["game"]["data"]["game"]
    if not games:
        return None, None
    genre = games[0].get("profile_genre") or None
    # HLTB returns an empty string, not a missing key, for an entry it has
    # no summary for — common for obscure games (verified live). Internal
    # line breaks are collapsed: some summaries are several short paragraphs
    # (Onimusha's is three), and the card shows this collapsed to about three
    # lines, where a blank line costs a third of what is visible.
    summary = " ".join((games[0].get("profile_summary") or "").split()) or None
    return genre, summary


def _as_result(entry: object) -> HltbResult:
    return HltbResult(
        hltb_id=entry.game_id,  # type: ignore[attr-defined]
        name=entry.game_name,  # type: ignore[attr-defined]
        release_year=entry.release_world,  # type: ignore[attr-defined]
        main_hours=_clean(entry.main_story),  # type: ignore[attr-defined]
        extra_hours=_clean(entry.main_extra),  # type: ignore[attr-defined]
        completionist_hours=_clean(entry.completionist),  # type: ignore[attr-defined]
        platforms=list(entry.profile_platforms or []),  # type: ignore[attr-defined]
        game_url=entry.game_web_link or None,  # type: ignore[attr-defined]
        image_url=entry.game_image_url or None,  # type: ignore[attr-defined]
        # Neither genre nor description is in the search JSON at all — both
        # are filled in by resolve(), from the game's own page.
        genre=None,
    )


def _from_cache_row(row: HltbCacheRow) -> HltbResult:
    return HltbResult(
        hltb_id=row.hltb_id,
        name=row.name,
        release_year=row.release_year,
        main_hours=row.main_hours,
        extra_hours=row.extra_hours,
        completionist_hours=row.completionist_hours,
        platforms=row.platforms,
        game_url=row.game_url,
        image_url=row.image_url,
        genre=row.genre,
        description_en=row.description_en,
        description_ru=row.description_ru,
    )


def _clean(hours: float | None) -> float | None:
    # Some entries (co-op/PvP-only games) report 0 or omit a style entirely —
    # "0 hours" would read as an error, not as "no data".
    return hours if hours and hours > 0 else None


def _clean_query(text: str) -> str:
    return " ".join(_SEARCH_NOISE.sub(" ", text).split())
