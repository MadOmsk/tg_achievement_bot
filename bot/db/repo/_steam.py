"""What Steam knows about a game beyond its achievements (migration 069): the
Steam app it is, its community guides' tips, and its developer's patch notes.

A game's Steam app is found once, like its HLTB entry (`titles.hltb_*`): three
failed attempts an hour apart, then it is known to have none. Guides and patches
belong to the Steam app, not to our title — an Xbox, a PlayStation and a Steam
version of one game share them — so their read times live on `steam_apps`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import aiosqlite

from bot.db.repo._sql import (
    earned_at,
    earned_date_is_real,
    earned_since,
    platform_is,
    titles_on,
)
from bot.util import looks_russian, utcnow_iso


@dataclass(frozen=True, slots=True)
class StoredPatch:
    gid: str
    title: str
    published_at: str
    text_en: str | None
    title_ru: str | None
    text_ru: str | None
    # "patch" or "news" (migration 084), and the post's first picture.
    kind: str = "patch"
    image_url: str | None = None


@dataclass(frozen=True, slots=True)
class GameNewsRow:
    """One post of a game's developer, with the game it is about (ours)."""

    steam_appid: int
    gid: str
    kind: str
    title: str
    published_at: str
    text_en: str | None
    image_url: str | None
    platform: str
    title_id: str
    game: str
    game_ru: str | None
    game_en: str | None
    game_icon_url: str | None


@dataclass(frozen=True, slots=True)
class TitleSteam:
    """A game as the Steam lookups need it."""

    platform: str
    title_id: str
    names: tuple[str, ...]
    hltb_id: int | None
    steam_appid: int | None
    # True when no Steam app is known yet and it is time to look again.
    appid_due: bool
    tips_checked_at: str | None


class _SteamRepo:
    _conn: aiosqlite.Connection

    STEAM_APPID_ATTEMPTS = 3

    async def title_steam(self, platform: str, title_id: str) -> TitleSteam | None:
        where, params = platform_is(platform)
        cursor = await self._conn.execute(
            "SELECT title_id, platform, name, name_en, hltb_id, steam_appid,"
            "  tips_checked_at,"
            "  (steam_appid IS NULL"
            f"   AND steam_appid_attempts < {self.STEAM_APPID_ATTEMPTS}"
            "   AND (steam_appid_checked_at IS NULL"
            "        OR steam_appid_checked_at < strftime('%Y-%m-%dT%H:%M:%S', 'now', '-1 hour'))"
            "  ) AS appid_due "
            f"FROM titles WHERE {where} AND title_id = ?",
            (*params, title_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        platform = row["platform"]
        appid = row["steam_appid"]
        # A Steam game is its own Steam app.
        if platform == "steam" and str(row["title_id"]).isdigit():
            appid = int(row["title_id"])
        return TitleSteam(
            platform=platform,
            title_id=row["title_id"],
            names=tuple(dict.fromkeys(str(n) for n in (row["name_en"], row["name"]) if n)),
            hltb_id=row["hltb_id"],
            steam_appid=appid,
            appid_due=appid is None and bool(row["appid_due"]),
            tips_checked_at=row["tips_checked_at"],
        )

    async def record_steam_appid(self, platform: str, title_id: str, appid: int | None) -> None:
        """One lookup's answer; `None` counts as a failed attempt."""
        if appid is not None:
            await self._conn.execute(
                "UPDATE titles SET steam_appid = ?, steam_appid_checked_at = ?,"
                " steam_appid_attempts = steam_appid_attempts + 1"
                " WHERE platform = ? AND title_id = ?",
                (appid, utcnow_iso(), platform, title_id),
            )
        else:
            await self._conn.execute(
                "UPDATE titles SET steam_appid_attempts = steam_appid_attempts + 1,"
                " steam_appid_checked_at = ? WHERE platform = ? AND title_id = ?",
                (utcnow_iso(), platform, title_id),
            )
        await self._conn.commit()

    async def steam_app_checked(self, appid: int) -> tuple[str | None, str | None]:
        """(guides_checked_at, patches_checked_at) — both None for an app never read."""
        cursor = await self._conn.execute(
            "SELECT guides_checked_at, patches_checked_at FROM steam_apps WHERE appid = ?",
            (appid,),
        )
        row = await cursor.fetchone()
        return (row["guides_checked_at"], row["patches_checked_at"]) if row else (None, None)

    async def guide_read(
        self, platform: str, title_id: str, guide_id: str
    ) -> tuple[str, dict[str, list[tuple[int, int]]]] | None:
        """(fingerprint, answer) of the last time the model was asked about this
        guide for this game — the answer as {achievement id: [(first, last), ...]}
        line ranges — or None when it never was."""
        cursor = await self._conn.execute(
            "SELECT fingerprint, answer FROM title_guide_reads"
            " WHERE platform = ? AND title_id = ? AND guide_id = ?",
            (platform, title_id, guide_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        try:
            stored = json.loads(row["answer"])
            answer = {
                str(key): [(int(a), int(b)) for a, b in ranges] for key, ranges in stored.items()
            }
        except (ValueError, TypeError, AttributeError):
            return None
        return row["fingerprint"], answer

    async def save_guide_read(
        self,
        platform: str,
        title_id: str,
        guide_id: str,
        fingerprint: str,
        answer: dict[str, list[tuple[int, int]]],
    ) -> None:
        await self._conn.execute(
            "INSERT INTO title_guide_reads"
            " (platform, title_id, guide_id, fingerprint, answer, checked_at)"
            " VALUES (?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(platform, title_id, guide_id) DO UPDATE SET"
            "  fingerprint = excluded.fingerprint, answer = excluded.answer,"
            "  checked_at = excluded.checked_at",
            (platform, title_id, guide_id, fingerprint, json.dumps(answer), utcnow_iso()),
        )
        await self._conn.commit()

    async def mark_steam_guides_read(self, appid: int) -> None:
        await self._conn.execute(
            "INSERT INTO steam_apps (appid, guides_checked_at) VALUES (?, ?)"
            " ON CONFLICT(appid) DO UPDATE SET guides_checked_at = excluded.guides_checked_at",
            (appid, utcnow_iso()),
        )
        await self._conn.commit()

    async def replace_title_tips(
        self,
        platform: str,
        title_id: str,
        tips: dict[str, tuple[str, str]],
        *,
        complete: bool,
    ) -> None:
        """The tips worked out from the guides, by achievement id: (text, guide id).
        A text sits in the column of its own language. A complete read replaces the
        game's tips and stamps the time; a partial one (Steam held some
        guides back) only adds, so what an earlier read found is not lost. A
        read that found no tip at all never clears the ones already stored: a
        hiccup (a guide list that came back empty, pages that failed) would
        otherwise take a game's tips away until its next month."""
        if complete and tips:
            await self._conn.execute(
                "UPDATE title_achievements SET tip_en = NULL, tip_ru = NULL,"
                " tip_source = NULL, tip_translation = NULL"
                " WHERE platform = ? AND title_id = ?",
                (platform, title_id),
            )
        for achievement_id, (text, source) in tips.items():
            column = "tip_ru" if looks_russian(text) else "tip_en"
            await self._conn.execute(
                f"UPDATE title_achievements SET {column} = ?, tip_source = ?"
                " WHERE platform = ? AND title_id = ? AND achievement_id = ?",
                (text, source, platform, title_id, achievement_id),
            )
        if complete:
            await self._conn.execute(
                "UPDATE titles SET tips_checked_at = ? WHERE platform = ? AND title_id = ?",
                (utcnow_iso(), platform, title_id),
            )
        await self._conn.commit()

    async def title_tips(
        self, platform: str, title_id: str
    ) -> dict[str, tuple[str | None, str | None]]:
        """(tip_en, tip_ru) for each achievement of the game that has a tip."""
        cursor = await self._conn.execute(
            "SELECT achievement_id, tip_en, tip_ru FROM title_achievements"
            " WHERE platform = ? AND title_id = ?"
            " AND (tip_en IS NOT NULL OR tip_ru IS NOT NULL)",
            (platform, title_id),
        )
        return {
            row["achievement_id"]: (row["tip_en"], row["tip_ru"]) for row in await cursor.fetchall()
        }

    async def save_game_patches(self, appid: int, patches: list[StoredPatch]) -> None:
        """What one read of the app's news found — new patches added, a changed
        one updated (its translation kept), and the read time stamped."""
        now = utcnow_iso()
        for patch in patches:
            await self._conn.execute(
                "INSERT INTO game_patches"
                " (steam_appid, gid, title, published_at, text_en, created_at, kind, image_url)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(steam_appid, gid) DO UPDATE SET"
                "  title = excluded.title, published_at = excluded.published_at,"
                "  text_en = excluded.text_en, kind = excluded.kind,"
                "  image_url = excluded.image_url",
                (
                    appid,
                    patch.gid,
                    patch.title,
                    patch.published_at,
                    patch.text_en,
                    now,
                    patch.kind,
                    patch.image_url,
                ),
            )
        await self._conn.execute(
            "INSERT INTO steam_apps (appid, patches_checked_at) VALUES (?, ?)"
            " ON CONFLICT(appid) DO UPDATE SET patches_checked_at = excluded.patches_checked_at",
            (appid, now),
        )
        await self._conn.commit()

    async def game_patch_gids(self, appid: int) -> set[str]:
        """The posts of the app already stored."""
        cursor = await self._conn.execute(
            "SELECT gid FROM game_patches WHERE steam_appid = ?", (appid,)
        )
        return {row[0] for row in await cursor.fetchall()}

    async def game_news_readers(
        self, appid: int, *, played_since: str
    ) -> list[tuple[int, str, str, str | None, str | None, str]]:
        """Who plays the Steam app's game: everybody who earned something in one
        of our games that is this app since `played_since`, with that game —
        `(person_id, platform, title_id, name_ru, name_en, name)`, one row each."""
        cursor = await self._conn.execute(
            "SELECT al.person_id, MAX(s.platform) AS platform, s.title_id,"
            "       t.name_ru, t.name_en, t.name"
            " FROM seen_achievements s"
            " JOIN account_links al ON al.platform = s.account_platform"
            "  AND al.external_id = s.xuid AND al.is_active = 1"
            # An excluded person is told nothing (CLAUDE.md, Statistics rules).
            " JOIN users u ON u.id = al.person_id AND u.is_excluded = 0"
            " JOIN titles t ON t.platform = s.platform AND t.title_id = s.title_id"
            " WHERE (CASE WHEN s.platform = 'steam' THEN CAST(t.title_id AS INTEGER)"
            "        ELSE t.steam_appid END) = ?"
            f"  AND {earned_date_is_real('s.')} AND {earned_at('s.')} >= ?"
            " GROUP BY al.person_id"
            " ORDER BY al.person_id",
            (appid, played_since),
        )
        return [
            (
                int(row["person_id"]),
                row["platform"],
                row["title_id"],
                row["name_ru"],
                row["name_en"],
                row["name"],
            )
            for row in await cursor.fetchall()
        ]

    async def games_news(
        self,
        members: list[int],
        *,
        played_since: str,
        since: str,
        until: str,
        limit: int,
    ) -> list[GameNewsRow]:
        """The developers' posts dated in [since, until) about the games these
        people earned something in since `played_since`, newest first — one row
        per post, even when two of our games (an Xbox and a Steam version) are
        one Steam app. Dates are ISO; `since`/`until` compare with the post's day."""
        ids = ",".join(str(int(m)) for m in members) or "NULL"
        cursor = await self._conn.execute(
            "WITH played AS ("
            "  SELECT s.title_id, s.platform"
            "  FROM seen_achievements s"
            "  JOIN account_links al ON al.platform = s.account_platform"
            "   AND al.external_id = s.xuid AND al.is_active = 1"
            f"  WHERE al.person_id IN ({ids}) AND {earned_date_is_real('s.')}"
            f"    AND {earned_at('s.')} >= ?"
            "  GROUP BY s.platform, s.title_id"
            "), apps AS ("
            "  SELECT p.title_id, p.platform, t.name, t.name_ru, t.name_en, t.icon_url,"
            "         CASE WHEN p.platform = 'steam' THEN CAST(t.title_id AS INTEGER)"
            "              ELSE t.steam_appid END AS appid"
            "  FROM played p JOIN titles t ON t.platform = p.platform AND t.title_id = p.title_id"
            ") "
            "SELECT gp.steam_appid, gp.gid, gp.kind, gp.title, gp.published_at,"
            "       gp.text_en, gp.image_url, a.platform, a.title_id,"
            "       a.name, a.name_ru, a.name_en, a.icon_url "
            "FROM game_patches gp JOIN apps a ON a.appid = gp.steam_appid "
            "WHERE gp.published_at >= ? AND gp.published_at < ? "
            "GROUP BY gp.steam_appid, gp.gid "
            "ORDER BY gp.published_at DESC, gp.steam_appid, gp.gid "
            "LIMIT ?",
            (played_since, since, until, limit),
        )
        return [
            GameNewsRow(
                steam_appid=int(row["steam_appid"]),
                gid=row["gid"],
                kind=row["kind"],
                title=row["title"],
                published_at=row["published_at"],
                text_en=row["text_en"],
                image_url=row["image_url"],
                platform=row["platform"],
                title_id=str(row["title_id"]),
                game=row["name"],
                game_ru=row["name_ru"],
                game_en=row["name_en"],
                game_icon_url=row["icon_url"],
            )
            for row in await cursor.fetchall()
        ]

    async def game_patches(self, appid: int, limit: int) -> list[StoredPatch]:
        """The developer's latest posts, patches and news both — the game page's
        «Обновления» tab, filtered there by `kind`."""
        cursor = await self._conn.execute(
            "SELECT gid, title, published_at, text_en, title_ru, text_ru, image_url, kind"
            " FROM game_patches"
            " WHERE steam_appid = ? ORDER BY published_at DESC LIMIT ?",
            (appid, limit),
        )
        return [
            StoredPatch(
                gid=row["gid"],
                title=row["title"],
                published_at=row["published_at"],
                text_en=row["text_en"],
                title_ru=row["title_ru"],
                text_ru=row["text_ru"],
                image_url=row["image_url"],
                kind=row["kind"],
            )
            for row in await cursor.fetchall()
        ]

    async def titles_due_for_tips(
        self, *, played_since: str, stale_before: str, limit: int
    ) -> list[tuple[str, str]]:
        """Games with a Steam app that somebody earned something in since
        `played_since` and whose tips were last worked out before `stale_before`,
        the longest-waiting first. A game never worked out is a visit's or a
        first achievement's job, not the schedule's."""
        cursor = await self._conn.execute(
            "SELECT t.platform, t.title_id FROM titles t"
            " WHERE (t.steam_appid IS NOT NULL OR t.platform = 'steam')"
            "   AND t.tips_checked_at IS NOT NULL AND t.tips_checked_at < ?"
            "   AND EXISTS (SELECT 1 FROM seen_achievements s"
            f"               WHERE {titles_on()} AND {earned_since('s.')})"
            " ORDER BY t.tips_checked_at LIMIT ?",
            (stale_before, played_since, limit),
        )
        return [(row["platform"], str(row["title_id"])) for row in await cursor.fetchall()]

    async def steam_apps_due_for_patches(
        self, *, played_since: str, stale_before: str, limit: int
    ) -> list[int]:
        """Steam apps of games somebody earned something in since `played_since`
        whose patches were last read before `stale_before` (or never), the
        longest-waiting first."""
        cursor = await self._conn.execute(
            "WITH active AS ("
            "  SELECT DISTINCT CASE WHEN t.platform = 'steam' THEN CAST(t.title_id AS INTEGER)"
            "                       ELSE t.steam_appid END AS appid"
            "  FROM titles t"
            "  WHERE EXISTS (SELECT 1 FROM seen_achievements s"
            f"               WHERE {titles_on()} AND {earned_since('s.')})"
            ") "
            "SELECT a.appid FROM active a"
            " LEFT JOIN steam_apps sa ON sa.appid = a.appid"
            " WHERE a.appid IS NOT NULL"
            "   AND (sa.patches_checked_at IS NULL OR sa.patches_checked_at < ?)"
            " ORDER BY sa.patches_checked_at IS NOT NULL, sa.patches_checked_at"
            " LIMIT ?",
            (played_since, stale_before, limit),
        )
        return [int(row["appid"]) for row in await cursor.fetchall()]
