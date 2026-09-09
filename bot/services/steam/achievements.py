"""Steam achievements: fetch + cache, composing over services/steam/client.py
(SPEC 9, M-Steam-2b). Mirrors services/hltb.py's role in the project — a
cache-backed service layer sitting above a stateless client, the same split
hltb.py already uses, rather than either putting caching directly in
client.py or waiting until the poller layer (which is Xbox's own pattern,
services/xbox/client.py + poller/fetcher.py).

Errors from the client (SteamApiError — private profile, unreachable API,
bad key) are not caught here on purpose: this is a pure fetch, the same
"log it and skip this tick" handling XboxApiError already gets belongs to
the poller that calls this (SPEC 9, M-Steam-2c), not to this layer.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from bot.constants import Platform
from bot.db.repo import Repo, SteamSchemaAchievement
from bot.services.models import ParsedAchievement
from bot.services.steam.client import (
    RawAchievement,
    get_global_percentages,
    get_player_achievements,
    get_schema,
)
from bot.services.translate.auth import AnthropicAuth
from bot.services.translate.descriptions import bilingual_descriptions
from bot.util import parse_iso, utcnow

# "Раз в неделю" (SPEC 9, M-Steam-2b) — real unlock percentages drift slowly,
# and re-fetching more often than this buys nothing (no key-less rate limit
# to worry about either), while never re-fetching would leave old games'
# rarity permanently stale.
RARITY_CACHE_TTL_DAYS = 7


async def fetch_unlocked(
    repo: Repo, anthropic_auth: AnthropicAuth, api_key: str, steam_id: str, appid: str
) -> list[ParsedAchievement]:
    """Every currently-unlocked achievement for one Steam game. Writing to
    seen_achievements and resolving tg_id are the poller's job (SPEC 9,
    M-Steam-2c) — this only ever reads the Steam API and this module's own
    cache tables."""
    raw = await get_player_achievements(api_key, steam_id, appid)
    unlocked = [item for item in raw if item.achieved]
    if not unlocked:
        # Nothing achieved yet, or a private/stats-less profile (client.py
        # already turned Steam's own `success: false` into an empty list) —
        # either way there is nothing worth a schema/rarity lookup for.
        return []

    schema_by_id = {a.apiname: a for a in await _schema(repo, api_key, appid)}
    percentages = await _percentages(repo, appid)
    descriptions = await _bilingual_descriptions(
        repo, anthropic_auth, api_key, steam_id, appid, unlocked
    )

    result: list[ParsedAchievement] = []
    for item in unlocked:
        schema_item = schema_by_id.get(item.apiname)
        # The bot only ever renders Russian today (no language switch exists
        # yet) — the English half is only ever written to
        # achievement_description_cache, for whenever that switch does
        # (2026-09-09). Falls back to whatever this call itself fetched
        # (already Russian) if bilingual lookup found nothing to add.
        description_ru, _description_en = descriptions.get(
            item.apiname, (item.description, item.description)
        )
        result.append(
            ParsedAchievement(
                achievement_id=item.apiname,
                title_id=appid,
                title_name=None,  # presence already has it fresh (SPEC 9, M-Steam-2c)
                name=item.name,
                description=description_ru,
                icon_url=schema_item.icon if schema_item else None,
                unlocked_at=_parse_unlocktime(item.unlocktime),
                gamerscore=0,  # Steam has no gamerscore — SPEC 9, M-Steam-2e keeps it Xbox-only
                rarity_percent=percentages.get(item.apiname),
                platform=Platform.STEAM,
                is_secret=schema_item.hidden if schema_item else False,
            )
        )
    return result


async def _bilingual_descriptions(
    repo: Repo,
    anthropic_auth: AnthropicAuth,
    api_key: str,
    steam_id: str,
    appid: str,
    unlocked: list[RawAchievement],
) -> dict[str, tuple[str | None, str | None]]:
    """A second `l=english` request, only when at least one of this batch's
    achievements isn't already in achievement_description_cache — the
    common case, once someone has ever unlocked a given achievement before,
    is that every one of them already is, and the extra Steam call (and any
    LLM call behind it) is skipped entirely, forever, for that achievement.

    Achievements with no description at all (Steam allows this) are left
    out — nothing to translate.
    """
    candidates = {item.apiname: item.description for item in unlocked if item.description}
    if not candidates:
        return {}

    result: dict[str, tuple[str | None, str | None]] = {}
    uncached: dict[str, str] = {}
    for apiname, russian_text in candidates.items():
        cached = await repo.get_cached_description(Platform.STEAM, appid, apiname)
        if cached is not None:
            result[apiname] = (cached.description_ru, cached.description_en)
        else:
            uncached[apiname] = russian_text
    if not uncached:
        return result

    english = {
        item.apiname: item.description
        for item in await get_player_achievements(api_key, steam_id, appid, language="english")
        if item.apiname in uncached and item.description
    }
    native = {
        apiname: (russian_text, english.get(apiname)) for apiname, russian_text in uncached.items()
    }
    resolved = await bilingual_descriptions(repo, anthropic_auth, Platform.STEAM, appid, native)
    return {**result, **resolved}


async def _schema(repo: Repo, api_key: str, appid: str) -> list[SteamSchemaAchievement]:
    cached = await repo.steam_schema_get_cached(appid)
    if cached is not None:
        return cached[1]
    raw = await get_schema(api_key, appid)
    achievements = [
        SteamSchemaAchievement(apiname=item.apiname, icon=item.icon, hidden=item.hidden)
        for item in raw
    ]
    await repo.steam_schema_cache_result(appid, None, achievements)
    return achievements


async def _percentages(repo: Repo, appid: str) -> dict[str, float]:
    cached = await repo.steam_rarity_get_cached(appid)
    if cached is not None:
        percentages, cached_at = cached
        cached_dt = parse_iso(cached_at)
        if cached_dt is not None and utcnow() - cached_dt < timedelta(days=RARITY_CACHE_TTL_DAYS):
            return percentages

    percentages = await get_global_percentages(appid)
    await repo.steam_rarity_cache_result(appid, percentages)
    return percentages


def _parse_unlocktime(unlocktime: int) -> datetime | None:
    # 0 is Steam's own "no real date" placeholder — same class of problem as
    # Xbox's 0001-01-01/1753-01-01 (bot/services/xbox/models.py), just a
    # unix-epoch int instead of an ISO string, so parse_timestamp there
    # doesn't apply directly; same "placeholder means unknown, not a date"
    # principle, its own small converter.
    return datetime.fromtimestamp(unlocktime, tz=UTC) if unlocktime > 0 else None
