"""Anthropic API wrapper — translation of *descriptions* only: an
achievement's own (2026-09-09 user request) and, since 2026-09-12 (#2), a
game's own summary for the /hltb card. Never a name, of either kind.
A thin httpx wrapper, not the `anthropic` SDK
(CLAUDE.md: don't add a dependency unless it's clearly needed) — the same
choice already made for Steam and Xbox Live, both raw HTTP too.
"""

from __future__ import annotations

import asyncio
import json
import logging

import httpx

from bot.services import api_usage

log = logging.getLogger(__name__)

API_BASE = "https://api.anthropic.com/v1"
ANTHROPIC_VERSION = "2023-06-01"
# Cheapest model that's good enough for a one/two-sentence achievement
# description — this is bulk, cache-forever, translate-once work, never a
# live per-message call (CLAUDE.md's own "no recurring paid LLM usage
# without explicit rate limits" rule for exactly this class of feature).
HAIKU_MODEL = "claude-haiku-5-5"
# Haiku 5.5 thinks unless told otherwise, and its thinking is paid for:
# translating needs little, so it thinks at the lowest effort (owner,
# 2026-10-30: moved from Haiku 4.5, a tenth of the price).
_EFFORT = {"effort": "low"}

_CONNECT_TIMEOUT_SECONDS = 10.0
_READ_TIMEOUT_SECONDS = 30.0

_LANGUAGE_NAME = {"ru": "Russian", "en": "English"}

# The reply ceiling for one call. A whole game used to go in one call, and
# the biggest one waiting on production (a Steam game with 1075 untranslated
# descriptions, ~20k output tokens) could never fit: the reply was cut off,
# failed to parse, and was paid for again on every retry. Calls now carry
# at most `_BATCH_SIZE` descriptions (~19 output tokens each on real data,
# 2026-10-01; Haiku 5.5 counts the same text as ~30% more, and its thinking
# shares the ceiling), so a reply stays well under this.
_MAX_OUTPUT_TOKENS = 8192
_BATCH_SIZE = 40
# ...and at most this much text: forty long descriptions are not forty short
# ones. A reply cut off anyway is split and asked again, never asked whole.
_BATCH_CHARS = 8000
# A game's list goes out in several calls at once: it is what makes a page open
# quickly, and costs what one after another would.
_BATCH_CALLS_AT_ONCE = 4


class AnthropicApiError(Exception):
    """A request to the Anthropic API failed for a reason unrelated to the
    key itself (network, rate limit, malformed response, ...)."""


#: What this process has spent, for a script that measures a batch.
spent_tokens = {"input": 0, "output": 0}


def _note(response: httpx.Response) -> None:
    """One request to the model, with the tokens its answer says it spent,
    for the super-admin's home (`services/api_usage.py`)."""
    spent = 0
    if response.status_code == 200:
        try:
            usage = response.json().get("usage") or {}
            spent_tokens["input"] += int(usage.get("input_tokens") or 0)
            spent_tokens["output"] += int(usage.get("output_tokens") or 0)
            spent = int(usage.get("input_tokens") or 0) + int(usage.get("output_tokens") or 0)
        except (ValueError, AttributeError, TypeError):
            spent = 0
    api_usage.record(api_usage.ANTHROPIC, tokens=spent)


def _text_of(payload: dict) -> str:
    """The answer's text: a reply may open with thinking blocks, so the text
    is found by its type, never by its place."""
    for block in payload["content"]:
        if block.get("type") == "text":
            return block["text"]
    raise KeyError("text")


def _headers(api_key: str) -> dict[str, str]:
    return {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }


def _timeout() -> httpx.Timeout:
    # httpx.Timeout raises unless either a default or all four of
    # connect/read/write/pool are given explicitly — found live
    # (2026-09-09): check_alive() below only ever set two of them, so every
    # single call raised ValueError before a request was even attempted.
    return httpx.Timeout(
        connect=_CONNECT_TIMEOUT_SECONDS,
        read=_READ_TIMEOUT_SECONDS,
        write=_CONNECT_TIMEOUT_SECONDS,
        pool=_CONNECT_TIMEOUT_SECONDS,
    )


async def check_alive(api_key: str) -> bool:
    """A free liveness probe (SPEC-equivalent to Steam's check_alive) — lists
    models rather than sending an actual completion, so verifying a key
    costs nothing. 401/403 means the key itself is bad; anything else
    (network blip, 5xx) is not evidence the key is dead, same "don't punish
    a transient failure" reasoning check_health call sites already rely on
    for Steam/PSN.
    """
    try:
        async with httpx.AsyncClient(timeout=_timeout()) as client:
            response = await client.get(f"{API_BASE}/models", headers=_headers(api_key))
    except httpx.RequestError:
        return True  # can't reach Anthropic right now — not the key's fault
    if response.status_code in (401, 403):
        return False
    return True


async def ask_model(
    api_key: str, prompt: str, *, max_tokens: int = _MAX_OUTPUT_TOKENS, what: str = "request"
) -> str | None:
    """One question to Haiku, answered in plain text; None when it could not be
    asked or answered (logged as `what`). No temperature: Haiku 5.5 refuses
    any but its default."""
    try:
        async with httpx.AsyncClient(timeout=_long_timeout()) as client:
            response = await client.post(
                f"{API_BASE}/messages",
                headers=_headers(api_key),
                json={
                    "model": HAIKU_MODEL,
                    "max_tokens": max_tokens,
                    "output_config": _EFFORT,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
    except httpx.RequestError as exc:
        log.warning("anthropic %s failed: %r", what, exc)
        return None
    _note(response)
    if response.status_code != 200:
        log.warning("anthropic %s failed: HTTP %s", what, response.status_code)
        return None
    try:
        return _text_of(response.json())
    except (KeyError, IndexError, ValueError) as exc:
        log.warning("anthropic %s: could not parse response: %r", what, exc)
        return None


def _long_timeout() -> httpx.Timeout:
    # A whole guide in, a game's worth of text out: minutes are fine here.
    return httpx.Timeout(connect=10.0, read=180.0, write=20.0, pool=10.0)


async def translate_descriptions(
    api_key: str, texts: dict[str, str], *, target_language: str
) -> dict[str, str]:
    """Translate a batch of achievement *descriptions* — never names, never
    called for those (2026-09-09 user request) — in one call, keyed by
    whatever id the caller wants back (an achievement_id in practice). The
    caller hands over one whole game; it goes out in calls of at most
    `_BATCH_SIZE` descriptions and `_BATCH_CHARS` characters — not one call per
    achievement (cost), not one per game (a big game's reply did not fit, see
    `_MAX_OUTPUT_TOKENS`) —, a few at once.

    Returns whatever the model actually translated, keyed the same way —
    never raises on a malformed or partial response, just logs and returns
    less than asked for (or nothing): a missing translation means that one
    achievement's description stays in whatever language it already had,
    exactly the same "degrade, don't break" shape every platform client
    here already follows for its own expected failures.
    """
    if not texts:
        return {}
    slots = asyncio.Semaphore(_BATCH_CALLS_AT_ONCE)

    async def one(chunk: dict[str, str]) -> dict[str, str]:
        async with slots:
            return await _translate_batch(api_key, chunk, target_language=target_language)

    # A chunk that fails loses only its own descriptions.
    done = await asyncio.gather(*(one(chunk) for chunk in _chunks(texts)))
    return {key: value for part in done for key, value in part.items()}


def _chunks(texts: dict[str, str]) -> list[dict[str, str]]:
    chunks: list[dict[str, str]] = []
    current: dict[str, str] = {}
    size = 0
    for key, text in texts.items():
        if current and (len(current) >= _BATCH_SIZE or size + len(text) > _BATCH_CHARS):
            chunks.append(current)
            current, size = {}, 0
        current[key] = text
        size += len(text)
    if current:
        chunks.append(current)
    return chunks


async def _translate_batch(
    api_key: str, texts: dict[str, str], *, target_language: str
) -> dict[str, str]:
    """One call, all or nothing; a reply that cannot be used goes again in two
    halves, since asking the same again would only be paid for again."""
    language = _LANGUAGE_NAME[target_language]
    # Numbered plain-text lines, not JSON-in-JSON — asking the model to echo
    # arbitrary ids back verbatim as JSON keys risks it "fixing" or
    # re-escaping one, which would silently drop that entry on our own
    # parse below. A local index avoids that: we already know which
    # achievement_id maps to which line, since we built the prompt.
    ids = list(texts.keys())
    numbered = "\n".join(f"{i + 1}. {texts[key]}" for i, key in enumerate(ids))
    prompt = (
        f"Translate each of the following video game achievement descriptions "
        f"into {language}. Keep the same tone and length, do not add "
        f"commentary. Reply with ONLY a JSON array of {len(ids)} strings, "
        f"the translations in the same order, nothing else.\n\n{numbered}"
    )
    try:
        async with httpx.AsyncClient(timeout=_long_timeout()) as client:
            response = await client.post(
                f"{API_BASE}/messages",
                headers=_headers(api_key),
                json={
                    "model": HAIKU_MODEL,
                    "max_tokens": _MAX_OUTPUT_TOKENS,
                    "output_config": _EFFORT,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
    except httpx.RequestError as exc:
        log.warning("anthropic translate request failed: %r", exc)
        return {}
    _note(response)
    if response.status_code != 200:
        log.warning("anthropic translate request failed: HTTP %s", response.status_code)
        return {}

    try:
        payload = response.json()
        if payload.get("stop_reason") == "max_tokens":
            log.warning("anthropic translate: reply cut off at %s tokens", _MAX_OUTPUT_TOKENS)
            return await _in_halves(api_key, texts, target_language)
        content = _text_of(payload)
        translations = json.loads(_strip_json_fence(content))
    except (KeyError, IndexError, ValueError, AttributeError) as exc:
        log.warning("anthropic translate: could not parse response: %r", exc)
        return await _in_halves(api_key, texts, target_language)
    if not isinstance(translations, list):
        log.warning("anthropic translate: expected a JSON array, got %s", type(translations))
        return await _in_halves(api_key, texts, target_language)
    # A reply with a line missing or added cannot be matched back to ids:
    # every description after the gap would get its neighbour's text. None
    # is better than a wrong one.
    if len(translations) != len(ids):
        log.warning(
            "anthropic translate: asked for %s translations, got %s", len(ids), len(translations)
        )
        return await _in_halves(api_key, texts, target_language)
    return dict(zip(ids, translations, strict=True))


async def _in_halves(api_key: str, texts: dict[str, str], target_language: str) -> dict[str, str]:
    """An answer that could not be used, asked again in two halves: one odd
    description then costs only itself, not all its neighbours every time."""
    ids = list(texts)
    if len(ids) == 1:
        return {}
    half = len(ids) // 2
    return {
        **await _translate_batch(
            api_key, {key: texts[key] for key in ids[:half]}, target_language=target_language
        ),
        **await _translate_batch(
            api_key, {key: texts[key] for key in ids[half:]}, target_language=target_language
        ),
    }


async def translate_game_description(
    api_key: str, text: str, *, target_language: str
) -> str | None:
    """One game's own summary, for the /hltb card (#2). A separate call from
    translate_descriptions() above rather than a one-item batch, because the
    prompts genuinely differ: that one carries a whole game's achievement
    list and must answer with a JSON array to keep ids aligned, this one is
    a single paragraph and can just answer with the text — one less thing to
    mis-parse for no benefit.

    Called lazily, once per game, the first time somebody looks it up (user
    decision, 2026-09-12: no prewarm) — the result is kept in `hltb_entries.summary_ru`
    forever, beside the English original.

    Returns None on any failure, never raises: the card then simply shows
    HLTB's own English text, and the next lookup of that game tries again.
    """
    stripped = text.strip()
    if not stripped:
        return None
    language = _LANGUAGE_NAME[target_language]
    prompt = (
        f"Translate this video game description into {language}. Keep the same "
        f"tone and length, do not add commentary, do not translate the game's "
        f"own title or any character names. Reply with ONLY the translation, "
        f"nothing else.\n\n{stripped}"
    )
    try:
        async with httpx.AsyncClient(timeout=_long_timeout()) as client:
            response = await client.post(
                f"{API_BASE}/messages",
                headers=_headers(api_key),
                json={
                    "model": HAIKU_MODEL,
                    "max_tokens": _MAX_OUTPUT_TOKENS,
                    "output_config": _EFFORT,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
    except httpx.RequestError as exc:
        log.warning("anthropic game-description translate failed: %r", exc)
        return None
    _note(response)
    if response.status_code != 200:
        log.warning("anthropic game-description translate failed: HTTP %s", response.status_code)
        return None
    try:
        translated = _text_of(response.json()).strip()
    except (KeyError, IndexError, ValueError) as exc:
        log.warning("anthropic game-description translate: could not parse response: %r", exc)
        return None
    return translated or None


async def translate_news(api_key: str, title: str, text: str) -> tuple[str, str] | None:
    """A Steam post of a game's developer in Russian, `(title, text)` (owner,
    2026-10-30): its picture and video lines and its links kept as they are,
    the names of the game's maps, weapons, modes and items left in English,
    as players know them. A long post goes in parts of whole lines
    (`NEWS_PART_CHARS`), each its own call, and is put back together; the
    title rides with the first. None when any part fails, never raises: the
    post then stays English and is tried again later."""
    parts = _news_parts(text.strip())
    answer = await _news_part(api_key, f"{title.strip()}\n{parts[0]}", first=True)
    if answer is None:
        return None
    head, _, body = answer.partition("\n")
    if not head.strip() or (parts[0] and not body.strip()):
        return None
    head = _without_original(head, title)
    done = [body.strip()]
    for part in parts[1:]:
        translated = await _news_part(api_key, part, first=False)
        if not translated:
            return None
        done.append(translated)
    # The parts were cut between paragraphs: an empty line puts them back.
    return head.strip(), "\n\n".join(done)


def _without_original(head: str, title: str) -> str:
    """A translated title that still opens with the original title and a dash
    ("Original — перевод") is the translation alone: the model sometimes
    echoes what it was given."""
    original = title.strip()
    translated = head.strip()
    if original and translated.lower().startswith(original.lower()):
        rest = translated[len(original) :].lstrip(" \t—–-:|")
        if rest:
            return rest
    return translated


# A part of a long post sent in one call: its translation, thinking included,
# fits `_NEWS_MAX_OUTPUT_TOKENS` with room to spare.
NEWS_PART_CHARS = 12000


def _news_parts(text: str) -> list[str]:
    """The post cut into parts of about `NEWS_PART_CHARS`: at an empty line
    (between paragraphs) where one is, else at the end of a line — never
    inside one, so no sentence is cut in two."""
    parts: list[str] = []
    current: list[str] = []
    size = 0
    for line in text.split("\n"):
        if current and size + len(line) + 1 > NEWS_PART_CHARS:
            # Back to the last empty line, so a paragraph stays whole.
            cut = max((i for i, kept in enumerate(current) if not kept.strip()), default=0)
            if cut == 0:
                cut = len(current)
            parts.append("\n".join(current[:cut]).strip("\n"))
            current = current[cut:]
            size = sum(len(kept) + 1 for kept in current)
        current.append(line)
        size += len(line) + 1
    parts.append("\n".join(current).strip("\n"))
    return [part for part in parts if part] or [""]


_NEWS_RULES = (
    "Write natural Russian, the way a Russian video game news site would, never"
    " word for word. In a title, a post's kind becomes the usual Russian word:"
    " Update and Live Update — обновление, Patch — патч, Patch Notes — список"
    " изменений, Hotfix — хотфикс, Dev Update or Developer Update — новости"
    " разработки; dates and numbers in Russian order (October 14 Patch Notes —"
    " список изменений от 14 октября). Keep every link, every picture or video"
    " address and every line break exactly as they are; translate only the words"
    " people read. Do not translate the game's title or the names of maps, modes,"
    " weapons, gadgets, classes, characters, cosmetic items, seasons or in-game"
    " events — keep them in English; only such a name itself, every word around it"
    " is translated. Keep version numbers and figures. The title is Russian only:"
    " never repeat the original title beside its translation."
)


async def _news_part(api_key: str, text: str, *, first: bool) -> str | None:
    if first:
        prompt = (
            "Translate this video game news post from Steam into Russian. The first"
            f" line is its title.\n{_NEWS_RULES} Reply with ONLY the translation, the"
            f" title on the first line, nothing else.\n\n{text}"
        )
    else:
        prompt = (
            "Translate this part of a video game news post from Steam into Russian."
            f"\n{_NEWS_RULES} Reply with ONLY the translation, nothing else.\n\n{text}"
        )
    try:
        async with httpx.AsyncClient(timeout=_news_timeout()) as client:
            response = await client.post(
                f"{API_BASE}/messages",
                headers=_headers(api_key),
                json={
                    "model": HAIKU_MODEL,
                    "max_tokens": _NEWS_MAX_OUTPUT_TOKENS,
                    "output_config": _EFFORT,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
    except httpx.RequestError as exc:
        log.warning("anthropic news translate failed: %r", exc)
        return None
    _note(response)
    if response.status_code != 200:
        log.warning("anthropic news translate failed: HTTP %s", response.status_code)
        return None
    try:
        payload = response.json()
        if payload.get("stop_reason") != "end_turn":
            log.warning("anthropic news translate stopped: %s", payload.get("stop_reason"))
            return None
        return _text_of(payload).strip()
    except (KeyError, IndexError, ValueError, AttributeError) as exc:
        log.warning("anthropic news translate: could not parse response: %r", exc)
        return None


_NEWS_MAX_OUTPUT_TOKENS = 32000


def _news_timeout() -> httpx.Timeout:
    return httpx.Timeout(connect=10.0, read=300.0, write=20.0, pool=10.0)


async def translate_guides(
    api_key: str, tips: list[tuple[str, str, str]], *, target_language: str
) -> list[str] | None:
    """How to get each achievement, from the Steam community's guides, in the
    other language (owner, 2026-10-30): `(name, description, tip)` each, the
    name and description only as context. One call for the lot — the caller
    sends one game's tips a few at a time, so the terms stay the same across
    them. Lines that are only a link, a picture or a video, and `[label](url)`
    links, are kept as they are. None on any failure, never raises."""
    language = _LANGUAGE_NAME[target_language]
    items = json.dumps(
        [{"achievement": name, "description": about, "tip": tip} for name, about, tip in tips],
        ensure_ascii=False,
    )
    prompt = (
        f"Each item below is a tip from a Steam community guide on how to get a video"
        f" game achievement. Translate each tip into {language}; the achievement's name"
        f" and description are there only as context. Keep every line break, every line"
        f" that is only a link, a picture or a video address, and every [label](url)"
        f" link's address exactly as they are (translate a label). Do not translate the"
        f" names of items, places, characters, enemies or weapons — keep them as written."
        f" Reply with ONLY a JSON array of {len(tips)} strings, the translated tips in"
        f" the same order, nothing else.\n\n{items}"
    )
    try:
        async with httpx.AsyncClient(timeout=_news_timeout()) as client:
            response = await client.post(
                f"{API_BASE}/messages",
                headers=_headers(api_key),
                json={
                    "model": HAIKU_MODEL,
                    "max_tokens": _NEWS_MAX_OUTPUT_TOKENS,
                    "output_config": _EFFORT,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
    except httpx.RequestError as exc:
        log.warning("anthropic tips translate failed: %r", exc)
        return None
    _note(response)
    if response.status_code != 200:
        log.warning("anthropic tips translate failed: HTTP %s", response.status_code)
        return None
    try:
        payload = response.json()
        if payload.get("stop_reason") != "end_turn":
            log.warning("anthropic tips translate stopped: %s", payload.get("stop_reason"))
            return None
        translated = json.loads(_strip_json_fence(_text_of(payload)))
    except (KeyError, IndexError, ValueError, AttributeError) as exc:
        log.warning("anthropic tips translate: could not parse response: %r", exc)
        return None
    if (
        not isinstance(translated, list)
        or len(translated) != len(tips)
        or not all(isinstance(t, str) and t.strip() for t in translated)
    ):
        log.warning("anthropic tips translate: asked for %s tips, got another answer", len(tips))
        return None
    return [t.strip() for t in translated]


def _strip_json_fence(text: str) -> str:
    """Haiku sometimes wraps its JSON in a markdown code fence
    (```json ... ```) despite being asked for "ONLY" the array — found live
    (2026-09-09) parsing a real response. Strips one if present; the text
    is returned unchanged otherwise, so a genuinely bare array still parses
    exactly as before this existed."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.removeprefix("```json").removeprefix("```")
        stripped = stripped.removesuffix("```")
        stripped = stripped.strip()
    return stripped
