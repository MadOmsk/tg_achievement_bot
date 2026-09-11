"""Anthropic API wrapper — translation of *descriptions* only: an
achievement's own (2026-09-09 user request) and, since 2026-09-12 (#2), a
game's own summary for the /hltb card. Never a name, of either kind.
A thin httpx wrapper, not the `anthropic` SDK
(CLAUDE.md: don't add a dependency unless it's clearly needed) — the same
choice already made for Steam and Xbox Live, both raw HTTP too.
"""

from __future__ import annotations

import json
import logging

import httpx

log = logging.getLogger(__name__)

API_BASE = "https://api.anthropic.com/v1"
ANTHROPIC_VERSION = "2023-06-01"
# Cheapest model that's good enough for a one/two-sentence achievement
# description — this is bulk, cache-forever, translate-once work, never a
# live per-message call (CLAUDE.md's own "no recurring paid LLM usage
# without explicit rate limits" rule for exactly this class of feature).
HAIKU_MODEL = "claude-haiku-4-5-20251001"

_CONNECT_TIMEOUT_SECONDS = 10.0
_READ_TIMEOUT_SECONDS = 30.0

_LANGUAGE_NAME = {"ru": "Russian", "en": "English"}

# A generous ceiling, not a per-item budget — one call already covers a
# whole game's worth of descriptions (batched by the caller,
# services/translate/descriptions.py), so this only needs to be large
# enough for the biggest achievement list in practice, not tuned per call.
_MAX_OUTPUT_TOKENS = 4096


class AnthropicApiError(Exception):
    """A request to the Anthropic API failed for a reason unrelated to the
    key itself (network, rate limit, malformed response, ...)."""


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


async def translate_descriptions(
    api_key: str, texts: dict[str, str], *, target_language: str
) -> dict[str, str]:
    """Translate a batch of achievement *descriptions* — never names, never
    called for those (2026-09-09 user request) — in one call, keyed by
    whatever id the caller wants back (an achievement_id in practice). Meant
    to cover one whole game's worth of descriptions per call (batched by the
    caller) rather than one call per achievement, both for cost and so a
    backfill of a large game doesn't fire dozens of requests back to back.

    Returns whatever the model actually translated, keyed the same way —
    never raises on a malformed or partial response, just logs and returns
    less than asked for (or nothing): a missing translation means that one
    achievement's description stays in whatever language it already had,
    exactly the same "degrade, don't break" shape every platform client
    here already follows for its own expected failures.
    """
    if not texts:
        return {}
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
        async with httpx.AsyncClient(timeout=_timeout()) as client:
            response = await client.post(
                f"{API_BASE}/messages",
                headers=_headers(api_key),
                json={
                    "model": HAIKU_MODEL,
                    "max_tokens": _MAX_OUTPUT_TOKENS,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
    except httpx.RequestError as exc:
        log.warning("anthropic translate request failed: %r", exc)
        return {}
    if response.status_code != 200:
        log.warning("anthropic translate request failed: HTTP %s", response.status_code)
        return {}

    try:
        content = response.json()["content"][0]["text"]
        translations = json.loads(_strip_json_fence(content))
    except (KeyError, IndexError, ValueError) as exc:
        log.warning("anthropic translate: could not parse response: %r", exc)
        return {}
    if not isinstance(translations, list):
        log.warning("anthropic translate: expected a JSON array, got %s", type(translations))
        return {}

    return dict(zip(ids, translations, strict=False))


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
    decision, 2026-09-12: no prewarm) — the result is cached in `hltb_cache`
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
        async with httpx.AsyncClient(timeout=_timeout()) as client:
            response = await client.post(
                f"{API_BASE}/messages",
                headers=_headers(api_key),
                json={
                    "model": HAIKU_MODEL,
                    "max_tokens": _MAX_OUTPUT_TOKENS,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
    except httpx.RequestError as exc:
        log.warning("anthropic game-description translate failed: %r", exc)
        return None
    if response.status_code != 200:
        log.warning("anthropic game-description translate failed: HTTP %s", response.status_code)
        return None
    try:
        translated = response.json()["content"][0]["text"].strip()
    except (KeyError, IndexError, ValueError) as exc:
        log.warning("anthropic game-description translate: could not parse response: %r", exc)
        return None
    return translated or None


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
