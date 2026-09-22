"""Full game achievement catalog service — `title_achievements` (Issue #99, #80).

Manages the complete catalog of achievements for games across Xbox, PlayStation,
and Steam, ensuring data freshness with a 24-hour debounce, deduplicating requests,
and reconciling DLC / new achievements.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from bot.constants import Platform
from bot.db.repo import Repo, TitleAchievementRow, TitleAchievementWithUnlock
from bot.services.psn.auth import PsnAuth
from bot.services.psn.client import (
    EarnedTrophy,
    PsnApiError,
    PsnPrivateProfileError,
    PsnTitleUnavailableError,
    TrophyTitle,
    trophies_for_title,
    trophy_groups_for_title,
)
from bot.services.steam.auth import SteamAuth
from bot.services.steam.client import (
    SteamApiError,
    get_global_percentages,
    get_schema,
    store_name,
)
from bot.services.translate.auth import AnthropicAuth
from bot.services.translate.descriptions import bilingual_descriptions
from bot.services.xbox.client import XboxApiError, XboxClient
from bot.util import parse_iso, utcnow, utcnow_iso

log = logging.getLogger(__name__)

DEFAULT_DEBOUNCE_HOURS = 24


class TitleCatalogService:
    def __init__(
        self,
        repo: Repo,
        *,
        xbox_client: XboxClient | None = None,
        psn_auth: PsnAuth | None = None,
        steam_auth: SteamAuth | None = None,
        anthropic_auth: AnthropicAuth | None = None,
    ) -> None:
        self._repo = repo
        self._xbox_client = xbox_client
        self._psn_auth = psn_auth
        self._steam_auth = steam_auth
        self._anthropic_auth = anthropic_auth

    async def ensure_title_achievements_fresh(
        self,
        platform: Platform | str,
        title_id: str,
        *,
        tg_id: int | None = None,
        force: bool = False,
        debounce_hours: int = DEFAULT_DEBOUNCE_HOURS,
    ) -> list[TitleAchievementRow]:
        """Ensure the game's achievement catalog in `title_achievements` is up to date.

        - If last verified within `debounce_hours` (default 24h) and achievements exist,
          returns cached data without touching external APIs.
        - If >= debounce_hours or force=True:
          Compares stored count against platform API count. If equal, stamps checked_at
          and returns cached achievements (0 LLM tokens, minimal API calls).
          If unequal (new game or DLC dropped): fetches missing achievements and translations,
          updates catalog, and stamps checked_at.
        """
        plat = platform.value if isinstance(platform, Platform) else platform

        if not force:
            checked_at_str = await self._repo.title_achievements_checked_at(title_id)
            if checked_at_str:
                checked_at = parse_iso(checked_at_str)
                if checked_at and (utcnow() - checked_at) < timedelta(hours=debounce_hours):
                    stored = await self._repo.get_title_achievements(plat, title_id)
                    if stored:
                        return stored

        # Refresh according to platform
        try:
            if plat == Platform.STEAM.value:
                return await self._refresh_steam(title_id, force=force)
            elif plat == Platform.PSN.value:
                return await self._refresh_psn(title_id, force=force, tg_id=tg_id)
            elif plat in (Platform.XBOX_MODERN.value, Platform.XBOX_360.value):
                return await self._refresh_xbox(
                    plat,
                    title_id,
                    force=force,
                    tg_id=tg_id,
                )
        except Exception:
            log.warning("failed to refresh title catalog for %s/%s", plat, title_id, exc_info=True)

        return await self._repo.get_title_achievements(plat, title_id)

    async def get_title_checklist_for_user(
        self,
        platform: Platform | str,
        title_id: str,
        tg_id: int | None,
        *,
        force: bool = False,
        debounce_hours: int = DEFAULT_DEBOUNCE_HOURS,
    ) -> list[TitleAchievementWithUnlock]:
        """Fetch full achievement checklist with unlock state for a specific Telegram user."""
        plat = platform.value if isinstance(platform, Platform) else platform

        await self.ensure_title_achievements_fresh(
            plat, title_id, tg_id=tg_id, force=force, debounce_hours=debounce_hours
        )

        xuid: str | None = None
        if tg_id:
            is_xbox = plat in (Platform.XBOX_MODERN.value, Platform.XBOX_360.value)
            account_plat = "xbox" if is_xbox else plat
            link = await self._repo.get_platform_link(tg_id, account_plat)
            if link:
                xuid = link.external_id

        return await self._repo.get_title_achievements_with_user_unlocks(plat, title_id, xuid=xuid)

    # ------------------------------------------------------------------ Steam

    async def _refresh_steam(self, appid: str, *, force: bool = False) -> list[TitleAchievementRow]:
        if not self._steam_auth:
            return await self._repo.get_title_achievements(Platform.STEAM.value, appid)

        try:
            api_key = await self._steam_auth.require_key()
        except SteamApiError:
            return await self._repo.get_title_achievements(Platform.STEAM.value, appid)

        schema_ru = await get_schema(api_key, appid, language="russian")
        api_total = len(schema_ru)

        stored_count = await self._repo.title_achievements_count(Platform.STEAM.value, appid)
        if not force and stored_count > 0 and stored_count == api_total:
            await self._repo.set_title_achievements_checked_at(appid)
            return await self._repo.get_title_achievements(Platform.STEAM.value, appid)

        # Count mismatch or empty: update catalog
        schema_en = await get_schema(api_key, appid, language="english")
        en_by_id = {item.apiname: item for item in schema_en}
        percentages = await get_global_percentages(appid)
        await self._repo.cache_rarity(Platform.STEAM, appid, percentages)

        # Store localized title name if missing
        if not await self._repo.has_localized_title(appid):
            await self._repo.set_title_names(
                appid, await store_name(appid, "russian"), await store_name(appid, "english")
            )

        now = utcnow_iso()
        rows: list[TitleAchievementRow] = []

        to_translate: dict[str, tuple[str | None, str | None]] = {}
        for item in schema_ru:
            en_item = en_by_id.get(item.apiname)
            name_ru = item.display_name or item.apiname
            name_en = en_item.display_name if en_item else item.apiname
            desc_ru = item.description
            desc_en = en_item.description if en_item else None

            # If Russian description matches English or is missing, prepare for translation
            if desc_en and (not desc_ru or desc_ru == desc_en):
                to_translate[item.apiname] = (desc_ru or desc_en, desc_en)

            rows.append(
                TitleAchievementRow(
                    platform=Platform.STEAM.value,
                    title_id=appid,
                    achievement_id=item.apiname,
                    name_ru=name_ru,
                    name_en=name_en,
                    description_ru=desc_ru,
                    description_en=desc_en,
                    icon_url=item.icon,
                    is_secret=item.hidden,
                    rarity_percent=percentages.get(item.apiname),
                    updated_at=now,
                )
            )

        if to_translate and self._anthropic_auth:
            try:
                resolved = await bilingual_descriptions(
                    self._repo,
                    self._anthropic_auth,
                    Platform.STEAM,
                    appid,
                    to_translate,
                )
                for r in rows:
                    if r.achievement_id in resolved:
                        r.description_ru = resolved[r.achievement_id][0]
            except Exception:
                log.info("steam translation failed for appid %s", appid, exc_info=True)

        await self._repo.upsert_title_achievements(rows)
        await self._repo.upsert_title(
            appid,
            appid,
            Platform.STEAM,
            achievements_total=api_total,
        )
        await self._repo.set_title_achievements_checked_at(appid)
        return rows

    # -------------------------------------------------------------------- PSN

    async def _refresh_psn(
        self, np_communication_id: str, *, force: bool = False, tg_id: int | None = None
    ) -> list[TitleAchievementRow]:
        if not self._psn_auth:
            return await self._repo.get_title_achievements(Platform.PSN.value, np_communication_id)

        try:
            client = await self._psn_auth.client()
            translation_client = await self._psn_auth.get_translation_client()
        except Exception:
            return await self._repo.get_title_achievements(Platform.PSN.value, np_communication_id)

        # Determine account_id to query
        account_id: str | None = None
        if tg_id:
            link = await self._repo.active_link_of(tg_id, "psn")
            if link:
                account_id = link.external_id

        if not account_id:
            # Fall back to any active PSN link
            cursor = await self._repo._conn.execute(
                "SELECT external_id FROM account_links "
                "WHERE platform = 'psn' AND is_active = 1 LIMIT 1"
            )
            row = await cursor.fetchone()
            if row:
                account_id = row["external_id"]

        if not account_id:
            return await self._repo.get_title_achievements(Platform.PSN.value, np_communication_id)

        dummy_title = TrophyTitle(
            np_communication_id=np_communication_id,
            title_name="?",
            title_platform=[],
        )

        # Structure / Groups fetch (Issue #80 fix: updates title_groups)
        structure = await trophy_groups_for_title(
            client, account_id, dummy_title, translation_client=translation_client
        )
        api_total = sum(g.total for g in structure.groups) if structure.groups else 0

        stored_count = await self._repo.title_achievements_count(
            Platform.PSN.value, np_communication_id
        )
        if not force and stored_count > 0 and stored_count == api_total:
            await self._repo.set_title_achievements_checked_at(np_communication_id)
            return await self._repo.get_title_achievements(Platform.PSN.value, np_communication_id)

        if structure.groups:
            await self._repo.save_title_groups(
                np_communication_id,
                [(g.group_id, g.name, g.total, g.name_ru, g.name_en) for g in structure.groups],
            )
        if structure.title_name_ru or structure.title_name_en:
            await self._repo.set_title_names(
                np_communication_id, structure.title_name_ru, structure.title_name_en
            )

        # Fetch all trophies (locked and unlocked)
        try:
            trophies_en = await trophies_for_title(
                client, account_id, dummy_title, earned_only=False
            )
        except (PsnPrivateProfileError, PsnTitleUnavailableError, PsnApiError):
            return await self._repo.get_title_achievements(Platform.PSN.value, np_communication_id)

        trophies_ru: list[EarnedTrophy] = []
        if translation_client:
            try:
                trophies_ru = await trophies_for_title(
                    translation_client, account_id, dummy_title, earned_only=False
                )
            except Exception:
                trophies_ru = []

        ru_by_id = {t.trophy_id: t for t in trophies_ru}
        now = utcnow_iso()
        rows: list[TitleAchievementRow] = []
        to_translate: dict[str, tuple[str | None, str | None]] = {}

        for t in trophies_en:
            ru_t = ru_by_id.get(t.trophy_id)
            name_ru = ru_t.trophy_name if ru_t else t.trophy_name
            name_en = t.trophy_name
            desc_ru = ru_t.trophy_detail if ru_t else None
            desc_en = t.trophy_detail

            if desc_en and (not desc_ru or desc_ru == desc_en):
                to_translate[str(t.trophy_id)] = (desc_ru or desc_en, desc_en)

            t_type = (
                t.trophy_type.value if hasattr(t.trophy_type, "value") else str(t.trophy_type or "")
            )
            rows.append(
                TitleAchievementRow(
                    platform=Platform.PSN.value,
                    title_id=np_communication_id,
                    achievement_id=str(t.trophy_id),
                    name_ru=name_ru,
                    name_en=name_en,
                    description_ru=desc_ru,
                    description_en=desc_en,
                    icon_url=t.trophy_icon_url,
                    is_secret=t.trophy_hidden,
                    trophy_type=t_type,
                    trophy_group_id=t.trophy_group_id,
                    rarity_percent=t.trophy_earn_rate,
                    updated_at=now,
                )
            )

        if to_translate and self._anthropic_auth:
            try:
                resolved = await bilingual_descriptions(
                    self._repo,
                    self._anthropic_auth,
                    Platform.PSN,
                    np_communication_id,
                    to_translate,
                )
                for r in rows:
                    if r.achievement_id in resolved:
                        r.description_ru = resolved[r.achievement_id][0]
            except Exception:
                log.info("psn translation failed for title %s", np_communication_id, exc_info=True)

        await self._repo.upsert_title_achievements(rows)
        await self._repo.upsert_title(
            np_communication_id,
            dummy_title.title_name,
            Platform.PSN,
            achievements_total=len(rows) or api_total,
        )
        await self._repo.set_title_achievements_checked_at(np_communication_id)
        return rows

    # ------------------------------------------------------------------- Xbox

    async def _refresh_xbox(
        self,
        platform_str: str,
        title_id: str,
        *,
        force: bool = False,
        tg_id: int | None = None,
    ) -> list[TitleAchievementRow]:
        if not self._xbox_client:
            return await self._repo.get_title_achievements(platform_str, title_id)

        target_tg_id = tg_id
        if not target_tg_id:
            cursor = await self._repo._conn.execute(
                "SELECT al.tg_id FROM account_links al "
                "JOIN tokens tok ON tok.tg_id = al.tg_id AND tok.status = 'active' "
                "WHERE al.platform = 'xbox' AND al.is_active = 1 LIMIT 1"
            )
            row = await cursor.fetchone()
            if row:
                target_tg_id = int(row["tg_id"])

        if not target_tg_id:
            return await self._repo.get_title_achievements(platform_str, title_id)

        platform_enum = (
            Platform.XBOX_360 if platform_str == Platform.XBOX_360.value else Platform.XBOX_MODERN
        )

        try:
            achievements_en, api_total = await self._xbox_client.title_achievements_with_total(
                target_tg_id,
                title_id,
                platform_enum,
                language="en-US",
                earned_only=False,
            )
        except XboxApiError:
            return await self._repo.get_title_achievements(platform_str, title_id)

        stored_count = await self._repo.title_achievements_count(platform_str, title_id)
        if not force and stored_count > 0 and stored_count == api_total:
            await self._repo.set_title_achievements_checked_at(title_id)
            return await self._repo.get_title_achievements(platform_str, title_id)

        # Mismatch or new: fetch ru-RU
        try:
            achievements_ru = await self._xbox_client.title_achievements(
                target_tg_id,
                title_id,
                platform_enum,
                language="ru-RU",
                earned_only=False,
            )
        except XboxApiError:
            achievements_ru = []

        ru_by_id = {item.achievement_id: item for item in achievements_ru}
        now = utcnow_iso()
        rows: list[TitleAchievementRow] = []
        to_translate: dict[str, tuple[str | None, str | None]] = {}

        for item in achievements_en:
            ru_item = ru_by_id.get(item.achievement_id)
            name_ru = ru_item.name if ru_item else item.name
            name_en = item.name
            desc_ru = ru_item.description if ru_item else None
            desc_en = item.description

            if desc_en and (not desc_ru or desc_ru == desc_en):
                to_translate[item.achievement_id] = (desc_ru or desc_en, desc_en)

            rows.append(
                TitleAchievementRow(
                    platform=platform_str,
                    title_id=title_id,
                    achievement_id=item.achievement_id,
                    name_ru=name_ru,
                    name_en=name_en,
                    description_ru=desc_ru,
                    description_en=desc_en,
                    icon_url=item.icon_url,
                    is_secret=item.is_secret,
                    gamerscore=item.gamerscore,
                    rarity_percent=item.rarity_percent,
                    updated_at=now,
                )
            )

        if to_translate and self._anthropic_auth:
            try:
                resolved = await bilingual_descriptions(
                    self._repo,
                    self._anthropic_auth,
                    platform_enum,
                    title_id,
                    to_translate,
                )
                for r in rows:
                    if r.achievement_id in resolved:
                        r.description_ru = resolved[r.achievement_id][0]
            except Exception:
                log.info("xbox translation failed for title %s", title_id, exc_info=True)

        await self._repo.upsert_title_achievements(rows)
        await self._repo.upsert_title(
            title_id,
            achievements_en[0].title_name or title_id if achievements_en else title_id,
            platform_enum,
            achievements_total=len(rows) or api_total,
        )
        await self._repo.set_title_achievements_checked_at(title_id)
        return rows
