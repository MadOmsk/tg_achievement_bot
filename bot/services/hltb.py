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
from datetime import UTC, datetime, timedelta

import httpx
from howlongtobeatpy import HowLongToBeat

from bot.db.repo import Repo
from bot.services.translate.auth import AnthropicAuth, AnthropicNotConfiguredError
from bot.services.translate.client import translate_game_description
from bot.util import utcnow

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
    # The rest of the game's page — see `details_of_entry` for the shape. None
    # until the page has been read for it.
    details: dict | None = None
    # What the game-page matcher weighs (#131) — search results only, never
    # cached: HLTB's other names for it, "game"/"dlc"/"mod", and how many
    # people logged a completion.
    alias: str | None = None
    game_type: str | None = None
    popularity: int = 0

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


async def ensure_title_match(repo: Repo, platform: str, title_id: str) -> None:
    """This game's HLTB entry, matched once and kept forever (#131) —
    lazily, not by a walker: called once from each platform's fetcher right
    after it publishes a game's first new achievement, and again from the
    Mini App's game-details endpoint if a game still has no match when
    somebody actually opens its page (an old game nobody's played lately
    gets matched the first time anybody looks, not before).

    A no-op whenever `repo.title_hltb_match_row` says the game is not due —
    already matched, or asked (and failed) too recently — so calling this on
    every achievement and every page view costs nothing once the answer is
    known. Local import: `services.hltb_match` imports this module for
    `HltbError`/`HltbResult`, so the reverse import has to happen at call
    time, not at module load.
    """
    from bot.services.hltb_match import GameIdentity, find, usable_name

    row = await repo.title_hltb_match_row(platform, title_id)
    if row is None:
        return
    names = tuple(dict.fromkeys(n for n in (row.name_en, row.name, row.name_ru) if n))
    from bot.services.game_match import is_part

    if is_part(None, None, names):
        # A demo, a beta, a tool (owner, 2026-10-14): HLTB times the game.
        await repo.give_up_hltb_match(row.platform, title_id)
        return
    if not any(usable_name(n) for n in names):
        # A platform's own placeholder ("Unknown", "?") or a name with
        # nothing Latin in it — HLTB's English-only search has nothing to
        # go on, and asking three times a game apart would only confirm
        # that. Skips straight past the retries.
        await repo.give_up_hltb_match(row.platform, title_id)
        return
    identity = GameIdentity(
        names=names,
        platform=row.platform,
        platforms=tuple(row.platforms),
        steam_appid=int(title_id) if row.platform == "steam" and title_id.isdigit() else None,
        first_played_year=row.first_played_year,
    )
    try:
        match = await find(identity, search_candidates, steam_appids)
    except HltbError as exc:
        log.info("HLTB match unanswerable for title %s (%s)", title_id, exc)
        await repo.record_hltb_match(row.platform, title_id, None, None)
        return
    if match is None:
        await repo.record_hltb_match(row.platform, title_id, None, None)
        return
    await repo.record_hltb_match(
        row.platform, title_id, match.hltb_id, match.score, entry_name=match.name
    )
    log.info("HLTB match for %s (%s): %s (score=%.3f)", title_id, names[0], match.name, match.score)


async def search_candidates(query: str) -> list[HltbResult]:
    """Everything HLTB returns for `query`, unfiltered and unsorted — the
    game-page matcher (#131) scores candidates itself, and the library's own
    similarity cut-off drops the right entry whenever the platform's name
    and HLTB's differ by an edition or a subtitle."""
    try:
        entries = await HowLongToBeat(0.0).async_search(
            _clean_query(query), similarity_case_sensitive=False
        )
    except Exception as exc:  # the library exposes no narrower exception type
        raise HltbError(f"HLTB search failed for {query!r}: {exc}") from None
    return [_as_result(e) for e in entries or []]


async def steam_appid_of(hltb_id: int) -> int | None:
    """The Steam appid HLTB's page lists for a matched game — exact, where
    Steam's own name search only ever shows its ten most popular hits (a small
    game called "Haven" is lost among Sun Haven and Space Haven)."""
    game = await _fetch_page_game(f"https://howlongtobeat.com/game/{hltb_id}")
    if game is None:
        return None
    for key in ("profile_steam", "profile_steam_alt"):
        try:
            value = int(game.get(key) or 0)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return None


async def steam_appids(result: HltbResult) -> set[int] | None:
    """The Steam appids HLTB's page lists for this entry (`profile_steam`,
    `profile_steam_alt`): an empty set when it lists none, None when the
    page could not be read."""
    if not result.game_url:
        return None
    game = await _fetch_page_game(result.game_url)
    if game is None:
        return None
    ids = set()
    for key in ("profile_steam", "profile_steam_alt"):
        try:
            value = int(game.get(key) or 0)
        except (TypeError, ValueError):
            continue
        if value > 0:
            ids.add(value)
    return ids


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
    """An entry from the mirror (`hltb_entries`), its page read when it never
    was and again when stale (`is_stale`): a new game's times fill in over its
    first weeks — Gears of War: E-Day was cached on its release week with
    multiplayer hours only and never asked again. A failed re-read keeps what
    is stored.

    `anthropic_auth`, when given, also gives an entry its Russian summary (#2) —
    one Haiku call per summary, ever, the first time somebody looks it up; the
    same English text keeps its translation.
    """
    from bot.services.stores import hltb_page

    row = await repo.hltb_entry(hltb_id)
    if row is None or row["page_read_at"] is None or is_stale(row):
        try:
            data = await hltb_page.fetch_page(hltb_id)
        except Exception as exc:
            if row is not None:
                log.info("HLTB re-read for id=%s failed, keeping the stored one: %r", hltb_id, exc)
                return await _with_translation(repo, row, anthropic_auth)
            raise HltbError(f"HLTB lookup failed for id={hltb_id}: {exc}") from None
        entry = hltb_page.parse_page(data) if data else None
        if entry is None:
            if row is not None:
                return await _with_translation(repo, row, anthropic_auth)
            raise HltbError(f"HLTB has no entry for id={hltb_id}")
        subject = f"hltb:{hltb_id}"
        changed = await repo.save_payload(subject, "hltb_page", data)
        await repo.save_hltb_page(entry)
        await repo.record_fetch(subject, "hltb_page", status="ok", changed=changed)
        row = await repo.hltb_entry(hltb_id)
        if row is None:
            raise HltbError(f"HLTB entry id={hltb_id} could not be stored")
    return await _with_translation(repo, row, anthropic_auth)


# How long a stored HLTB entry is trusted: a game of this year or last, or one
# HLTB has no main story time for yet, is still being timed by its players.
FRESH_GAME_DAYS = 3
SETTLED_GAME_DAYS = 90


def is_stale(row: dict) -> bool:
    """Whether an entry's page is due to be read again (its own page only: an
    entry known from another page's row has none, and is read at once)."""
    read = row.get("page_read_at")
    if not read:
        return True
    try:
        at = datetime.fromisoformat(read)
    except ValueError:
        return True
    if at.tzinfo is None:
        at = at.replace(tzinfo=UTC)
    young = not row.get("comp_main") or (
        row.get("release_year") is not None and row["release_year"] >= utcnow().year - 1
    )
    days = FRESH_GAME_DAYS if young else SETTLED_GAME_DAYS
    return utcnow() - at > timedelta(days=days)


async def _with_translation(
    repo: Repo, row: dict, anthropic_auth: AnthropicAuth | None
) -> HltbResult:
    """The entry as a result, with its Russian summary: the one already paid
    for when it is of this very English text; else one Haiku call, kept. No
    summary, no key or a failing call leave it English, to be tried again on
    the next lookup."""
    from bot.services.stores.hltb_page import summary_hash

    result = result_from_entry(row)
    english = row.get("summary_en")
    if not english or result.description_ru:
        return result
    translated = await _translate(english, anthropic_auth)
    if translated is None:
        return result
    await repo.set_hltb_summary_ru(row["hltb_id"], translated, summary_hash(english))
    result.description_ru = translated
    return result


async def _translate(text: str | None, anthropic_auth: AnthropicAuth | None) -> str | None:
    """None whenever a translation can't be had — no text, no key, or the
    call itself failing. The caller tries again on the next lookup, exactly
    like a platform description the LLM couldn't reach
    (services/translate/descriptions.py's own "left untranslated, will retry
    later")."""
    if not text or anthropic_auth is None:
        return None
    try:
        api_key = await anthropic_auth.require_key()
    except AnthropicNotConfiguredError:
        return None
    return await translate_game_description(api_key, text, target_language="ru")


async def _fetch_page_game(game_url: str) -> dict | None:
    """The game's record from its HLTB page, or None — logged, never raised:
    a failure here must not cost the rest of the card (SPEC 1.5's "expected
    failure, never crash")."""
    try:
        async with httpx.AsyncClient(timeout=_PAGE_REQUEST_TIMEOUT) as client:
            response = await client.get(game_url, headers=_PAGE_HEADERS)
        response.raise_for_status()
        return _page_game(response.text)
    except Exception as exc:
        log.info("could not fetch HLTB page %s: %s", game_url, exc)
        return None


def _page_game(html_page: str) -> dict | None:
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
        return None
    data = json.loads(match.group(1))
    games = data["props"]["pageProps"]["game"]["data"]["game"]
    return games[0] if games else None


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
        alias=entry.game_alias or None,  # type: ignore[attr-defined]
        game_type=entry.game_type or None,  # type: ignore[attr-defined]
        popularity=_popularity(entry),
    )


def _popularity(entry: object) -> int:
    raw = getattr(entry, "json_content", None) or {}
    try:
        return int(raw.get("count_comp") or 0)
    except (TypeError, ValueError, AttributeError):
        return 0


async def overlay_mirror(repo: Repo, results: list[HltbResult]) -> list[HltbResult]:
    """Search JSON has no description/genre — if the mirror already has this
    entry's page, reuse it so the Mini App isn't empty then jumps."""
    out: list[HltbResult] = []
    for item in results:
        row = await repo.hltb_entry(item.hltb_id)
        out.append(result_from_entry(row) if row is not None and row["page_read_at"] else item)
    return out


def result_from_entry(row: dict) -> HltbResult:
    """An entry of the mirror as the result the cards and the Mini App take.
    Its translation counts only while it is of the English summary there now."""
    from bot.services.stores.hltb_page import hours, summary_hash

    english = row.get("summary_en")
    translated = row.get("summary_ru")
    if translated and row.get("summary_ru_of") not in (None, summary_hash(english)):
        translated = None
    return HltbResult(
        hltb_id=row["hltb_id"],
        name=row["name"],
        release_year=row.get("release_year"),
        main_hours=hours(row.get("comp_main")),
        extra_hours=hours(row.get("comp_plus")),
        completionist_hours=hours(row.get("comp_100")),
        platforms=list(row.get("platforms") or []),
        game_url=f"https://howlongtobeat.com/game/{row['hltb_id']}",
        image_url=row.get("image_url"),
        genre=row.get("genres"),
        description_en=english,
        description_ru=translated,
        details=details_of_entry(row),
        alias=row.get("alias"),
        game_type=row.get("game_type"),
    )


# HLTB's own time buckets and the keys a payload names them by. Each has an
# average (`<prefix>`), a median (`_med`), and the fastest and slowest
# submissions (`_l`, `_h`), all in seconds.
_TIME_BUCKETS = (
    ("main", "comp_main"),
    ("extra", "comp_plus"),
    ("completionist", "comp_100"),
    ("all", "comp_all"),
    ("coop", "invested_co"),
    ("multi", "invested_mp"),
)


def details_of_entry(row: dict) -> dict:
    """What the Mini App shows beyond the hours — rating, studio, other names,
    release dates, play modes, the spread of each time bucket and the speedrun
    records — read from the entry's columns when asked, kept nowhere. HLTB's
    counts of its own users stay in the mirror and are not sent (the Mini
    App's decision, 2026-09-29). Hours come out as hours, to a tenth; what
    HLTB left empty or zero is dropped."""
    from bot.services.stores.hltb_page import hours

    modes = [
        mode
        for mode, key in (
            ("single", "comp_lvl_sp"),
            ("coop", "comp_lvl_co"),
            ("multi", "comp_lvl_mp"),
        )
        if row.get(key)
    ]
    times: dict[str, dict[str, float]] = {}
    for name, prefix in _TIME_BUCKETS:
        # Co-op/multiplayer hours only count when the game is played that
        # way — Hollow Knight has three stray "co-op" submissions.
        if name in ("coop", "multi") and name not in modes:
            continue
        bucket = {
            label: value
            for label, suffix in (
                ("average", ""),
                ("median", "_med"),
                ("fastest", "_l"),
                ("slowest", "_h"),
            )
            if (value := hours(row.get(prefix + suffix))) is not None
        }
        if bucket:
            times[name] = bucket
    speedrun = {
        name: record
        for name, prefix in (("any", "comp_speed"), ("full", "comp_speed100"))
        if (
            record := {
                label: value
                for label, suffix in (("best", "_min"), ("median", "_med"))
                if (value := hours(row.get(prefix + suffix))) is not None
            }
        )
    }
    releases = {
        region: row[f"release_{region}"]
        for region in ("world", "na", "eu", "jp")
        if row.get(f"release_{region}")
    }
    details = {
        "review_score": row.get("review_score") or None,
        "developer": row.get("developer"),
        "publisher": row.get("publisher"),
        "alias": row.get("alias"),
        "releases": releases,
        "modes": modes,
        "times": times,
        "speedrun": speedrun,
    }
    return {key: value for key, value in details.items() if value}


def _clean(hours: float | None) -> float | None:
    # Some entries (co-op/PvP-only games) report 0 or omit a style entirely —
    # "0 hours" would read as an error, not as "no data".
    return hours if hours and hours > 0 else None


def _clean_query(text: str) -> str:
    return " ".join(_SEARCH_NOISE.sub(" ", text).split())
