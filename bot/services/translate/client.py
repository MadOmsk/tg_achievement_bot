"""Anthropic API wrapper — translation of achievement descriptions only
(2026-09-09 user request). A thin httpx wrapper, not the `anthropic` SDK
(CLAUDE.md: don't add a dependency unless it's clearly needed) — the same
choice already made for Steam and Xbox Live, both raw HTTP too.
"""

from __future__ import annotations

import httpx

API_BASE = "https://api.anthropic.com/v1"
ANTHROPIC_VERSION = "2023-06-01"
# Cheapest model that's good enough for a one/two-sentence achievement
# description — this is bulk, cache-forever, translate-once work, never a
# live per-message call (CLAUDE.md's own "no recurring paid LLM usage
# without explicit rate limits" rule for exactly this class of feature).
HAIKU_MODEL = "claude-haiku-4-5-20251001"

_CONNECT_TIMEOUT_SECONDS = 10.0
_READ_TIMEOUT_SECONDS = 30.0


class AnthropicApiError(Exception):
    """A request to the Anthropic API failed for a reason unrelated to the
    key itself (network, rate limit, malformed response, ...)."""


def _headers(api_key: str) -> dict[str, str]:
    return {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }


async def check_alive(api_key: str) -> bool:
    """A free liveness probe (SPEC-equivalent to Steam's check_alive) — lists
    models rather than sending an actual completion, so verifying a key
    costs nothing. 401/403 means the key itself is bad; anything else
    (network blip, 5xx) is not evidence the key is dead, same "don't punish
    a transient failure" reasoning check_health call sites already rely on
    for Steam/PSN.
    """
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=_CONNECT_TIMEOUT_SECONDS, read=_READ_TIMEOUT_SECONDS)
        ) as client:
            response = await client.get(f"{API_BASE}/models", headers=_headers(api_key))
    except httpx.RequestError:
        return True  # can't reach Anthropic right now — not the key's fault
    if response.status_code in (401, 403):
        return False
    return True
