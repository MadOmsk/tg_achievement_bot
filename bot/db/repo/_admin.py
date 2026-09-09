"""/admin's own auto-refresh bookkeeping, the user/chat lists and settings
behind it, and the shared titles/HLTB caches that happen to live in this
same historical section — one mixin of bot.db.repo.Repo (2026-09-09 split;
see this package's own __init__.py). Behavior is unchanged from before the
split.
"""

from __future__ import annotations

import json
from typing import Any

from bot.db.repo._models import AdminPanelRefreshRow, AdminUserRow, ChatTarget, HltbCacheRow
from bot.util import utcnow_iso


class _AdminRepo:
    # ----------------------------------------------- admin panel auto-refresh

    async def get_admin_panel_refresh(self, admin_id: int) -> AdminPanelRefreshRow | None:
        cursor = await self._conn.execute(
            "SELECT admin_id, message_id, created_at, last_updated_at "
            "FROM admin_panel_refresh WHERE admin_id = ?",
            (admin_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return AdminPanelRefreshRow(
            admin_id=row["admin_id"],
            message_id=row["message_id"],
            created_at=row["created_at"],
            last_updated_at=row["last_updated_at"],
        )

    async def start_admin_panel_refresh(self, admin_id: int, message_id: int) -> None:
        """A fresh /admin supersedes whatever was auto-refreshing for this
        admin before (Follow-up 2026-09-06, poller/admin_refresh.py) — the
        caller deletes the old *message* itself (get_admin_panel_refresh
        above gives it the id to delete); this just points the one row at
        the new one, same reset-both-timestamps shape as
        start_online_auto_refresh."""
        now = utcnow_iso()
        await self._conn.execute(
            "INSERT INTO admin_panel_refresh (admin_id, message_id, created_at, last_updated_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(admin_id) DO UPDATE SET"
            " message_id = excluded.message_id, created_at = excluded.created_at,"
            " last_updated_at = excluded.last_updated_at",
            (admin_id, message_id, now, now),
        )
        await self._conn.commit()

    async def touch_admin_panel_refresh(self, admin_id: int) -> None:
        await self._conn.execute(
            "UPDATE admin_panel_refresh SET last_updated_at = ? WHERE admin_id = ?",
            (utcnow_iso(), admin_id),
        )
        await self._conn.commit()

    async def delete_admin_panel_refresh(self, admin_id: int) -> None:
        await self._conn.execute("DELETE FROM admin_panel_refresh WHERE admin_id = ?", (admin_id,))
        await self._conn.commit()

    async def all_admin_panel_refreshes(self) -> list[AdminPanelRefreshRow]:
        cursor = await self._conn.execute(
            "SELECT admin_id, message_id, created_at, last_updated_at FROM admin_panel_refresh"
        )
        return [
            AdminPanelRefreshRow(
                admin_id=row["admin_id"],
                message_id=row["message_id"],
                created_at=row["created_at"],
                last_updated_at=row["last_updated_at"],
            )
            for row in await cursor.fetchall()
        ]

    # ----------------------------------------------------------------- admin

    async def admin_users(self) -> list[AdminUserRow]:
        """Every connected person, Xbox or Steam or PSN or any mix
        (2026-09-05 follow-up, extended for M-PSN-1) — used to be
        `WHERE u.xuid IS NOT NULL`, which hid every Steam-only person from
        the admin panel entirely."""
        cursor = await self._conn.execute(
            "SELECT u.tg_id, u.gamertag, u.username, u.xuid, u.gamerscore, u.is_excluded,"
            "       u.last_online_at, t.status, t.last_refresh_at,"
            "       ps.external_id AS steam_id, ps.display_name AS steam_name,"
            "       pp.external_id AS psn_account_id, pp.display_name AS psn_online_id "
            "FROM users u "
            "LEFT JOIN tokens t ON t.tg_id = u.tg_id "
            "LEFT JOIN platform_links ps ON ps.tg_id = u.tg_id AND ps.platform = 'steam' "
            "LEFT JOIN platform_links pp ON pp.tg_id = u.tg_id AND pp.platform = 'psn' "
            "WHERE u.xuid IS NOT NULL OR ps.external_id IS NOT NULL OR pp.external_id IS NOT NULL "
            "ORDER BY u.is_excluded, u.last_online_at DESC"
        )
        return [
            AdminUserRow(
                tg_id=row["tg_id"],
                gamertag=row["gamertag"],
                username=row["username"],
                xuid=row["xuid"],
                gamerscore=row["gamerscore"],
                is_excluded=bool(row["is_excluded"]),
                last_online_at=row["last_online_at"],
                token_status=row["status"],
                last_refresh_at=row["last_refresh_at"],
                steam_id=row["steam_id"],
                steam_name=row["steam_name"],
                psn_account_id=row["psn_account_id"],
                psn_online_id=row["psn_online_id"],
            )
            for row in await cursor.fetchall()
        ]

    async def set_excluded(self, tg_id: int, excluded: bool, by: int | None) -> None:
        """Exclusion is never silent: the person sees it in his panel (SPEC 6.4)."""
        await self._conn.execute(
            "UPDATE users SET is_excluded = ?, excluded_by = ?, excluded_at = ?, updated_at = ? "
            "WHERE tg_id = ?",
            (
                1 if excluded else 0,
                by if excluded else None,
                utcnow_iso() if excluded else None,
                utcnow_iso(),
                tg_id,
            ),
        )
        await self._conn.commit()

    async def admin_chats(self) -> list[ChatTarget]:
        cursor = await self._conn.execute(
            "SELECT c.chat_id, c.title, c.is_active, s.min_gamerscore,"
            "       s.daily_summary, s.muted_title_ids, s.rare_threshold_percent,"
            "       s.daily_summary_time, s.tz_offset_min, s.flood_limit, s.flood_window_minutes,"
            "       (SELECT COUNT(*) FROM subscriptions WHERE chat_id = c.chat_id) AS subs "
            "FROM chats c JOIN chat_settings s ON s.chat_id = c.chat_id "
            "ORDER BY c.is_active DESC, c.title"
        )
        return [
            ChatTarget(
                chat_id=row["chat_id"],
                title=row["title"],
                min_gamerscore=row["min_gamerscore"],
                muted_title_ids=json.loads(row["muted_title_ids"] or "[]"),
                rare_threshold_percent=row["rare_threshold_percent"],
                daily_summary_time=row["daily_summary_time"],
                tz_offset_min=row["tz_offset_min"],
                flood_limit=row["flood_limit"],
                flood_window_minutes=row["flood_window_minutes"],
                is_active=bool(row["is_active"]),
                daily_summary=bool(row["daily_summary"]),
                subscribers=int(row["subs"]),
            )
            for row in await cursor.fetchall()
        ]

    async def update_chat_settings(self, chat_id: int, **fields: Any) -> None:
        allowed = {
            "min_gamerscore",
            "daily_summary",
            "rare_threshold_percent",
            "daily_summary_time",
            "tz_offset_min",
            "flood_limit",
            "flood_window_minutes",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unknown chat_settings fields: {sorted(unknown)}")
        if not fields:
            return
        assignments = ", ".join(f"{name} = ?" for name in fields)
        await self._conn.execute(
            f"UPDATE chat_settings SET {assignments} WHERE chat_id = ?",
            (*fields.values(), chat_id),
        )
        await self._conn.commit()

    async def set_chat_active(self, chat_id: int, active: bool) -> None:
        await self._conn.execute(
            "UPDATE chats SET is_active = ? WHERE chat_id = ?", (1 if active else 0, chat_id)
        )
        await self._conn.commit()

    async def upsert_title(
        self, title_id: str, name: str, platform: str | None, icon_url: str | None = None
    ) -> None:
        # icon_url only overwrites when this call actually has one —
        # ensure_title_name() (fetcher.py) upserts just the name/platform on
        # every new title it resolves, and must not blank out an icon_url a
        # separate ensure_title_icon() call already cached here.
        await self._conn.execute(
            "INSERT INTO titles (title_id, name, platform, icon_url, updated_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(title_id) DO UPDATE SET name = excluded.name,"
            " platform = excluded.platform, updated_at = excluded.updated_at,"
            " icon_url = COALESCE(excluded.icon_url, titles.icon_url)",
            (title_id, name, platform, icon_url, utcnow_iso()),
        )
        await self._conn.commit()

    async def title_name(self, title_id: str) -> str | None:
        cursor = await self._conn.execute("SELECT name FROM titles WHERE title_id = ?", (title_id,))
        row = await cursor.fetchone()
        return row["name"] if row else None

    async def title_icon_url(self, title_id: str) -> str | None:
        cursor = await self._conn.execute(
            "SELECT icon_url FROM titles WHERE title_id = ?", (title_id,)
        )
        row = await cursor.fetchone()
        return row["icon_url"] if row else None

    async def hltb_all_ids(self) -> list[int]:
        """For the one-off platforms backfill (scripts/backfill_hltb_platforms.py)
        — every id already cached, so it can be re-resolved with the field
        that didn't exist when it was first cached."""
        cursor = await self._conn.execute("SELECT hltb_id FROM hltb_cache")
        return [row[0] for row in await cursor.fetchall()]

    async def hltb_get_cached(self, hltb_id: int) -> HltbCacheRow | None:
        cursor = await self._conn.execute(
            "SELECT hltb_id, name, release_year, main_hours, extra_hours,"
            " completionist_hours, platforms, game_url, image_url, genre "
            "FROM hltb_cache WHERE hltb_id = ?",
            (hltb_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return HltbCacheRow(
            hltb_id=row["hltb_id"],
            name=row["name"],
            release_year=row["release_year"],
            main_hours=row["main_hours"],
            extra_hours=row["extra_hours"],
            completionist_hours=row["completionist_hours"],
            platforms=json.loads(row["platforms"] or "[]"),
            game_url=row["game_url"],
            image_url=row["image_url"],
            genre=row["genre"],
        )

    async def hltb_cache_result(self, entry: HltbCacheRow) -> None:
        """Cached forever (SPEC 6.6) — only called once someone actually
        picks a search result, never for the rest of the candidate list."""
        await self._conn.execute(
            "INSERT OR REPLACE INTO hltb_cache "
            "(hltb_id, name, release_year, main_hours, extra_hours, completionist_hours,"
            " platforms, game_url, image_url, genre, cached_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entry.hltb_id,
                entry.name,
                entry.release_year,
                entry.main_hours,
                entry.extra_hours,
                entry.completionist_hours,
                json.dumps(entry.platforms),
                entry.game_url,
                entry.image_url,
                entry.genre,
                utcnow_iso(),
            ),
        )
        await self._conn.commit()
