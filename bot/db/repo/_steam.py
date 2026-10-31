"""What Steam knows about a game beyond its achievements (migration 069): the
Steam app it is, its community guides' tips, and its developer's patch notes.

A game's Steam app is found once, like its HLTB entry (`achievement_list_connectors.hltb_*`): three
failed attempts an hour apart, then it is known to have none. Guides and patches
belong to the Steam app, not to our title — an Xbox, a PlayStation and a Steam
version of one game share them — so their read times live on `steam_apps`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from bot.db.repo._sql import (
    STEAM_APP_OF_TITLE,
    earned_at,
    earned_date_is_real,
    earned_since,
    platform_is,
    titles_on,
)
from bot.db.repo._tx import GatedConnection
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
    title_ru: str | None
    text_ru: str | None
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
    _conn: GatedConnection

    STEAM_APPID_ATTEMPTS = 3

    async def title_steam(self, platform: str, title_id: str) -> TitleSteam | None:
        where, params = platform_is(platform, "t.platform")
        cursor = await self._conn.execute(
            f"SELECT t.title_id, t.platform, t.name, t.name_en, t.tips_checked_at,"
            f" {STEAM_APP_OF_TITLE} AS steam_appid FROM achievement_list_connectors t"
            f" WHERE {where} AND t.title_id = ?",
            (*params, title_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        platform = row["platform"]
        appid = row["steam_appid"]
        match = await self.list_hltb_match(platform, row["title_id"])
        return TitleSteam(
            platform=platform,
            title_id=row["title_id"],
            names=tuple(dict.fromkeys(str(n) for n in (row["name_en"], row["name"]) if n)),
            hltb_id=match[0] if match else None,
            steam_appid=appid,
            appid_due=appid is None
            and await self.fetch_due(f"{platform}:{row['title_id']}", "steam_app"),
            tips_checked_at=row["tips_checked_at"],
        )

    async def record_steam_appid(self, platform: str, title_id: str, appid: int | None) -> None:
        """One lookup's answer: the app found is kept as a `steam_twin` id on
        each version of the list (`versions.store_ids`), when it was last asked
        is `fetch_state` ('steam_app'); `None` counts as a failed attempt —
        after the third the list leaves the queue for a month."""
        subject = f"{platform}:{title_id}"
        if appid is None:
            await self.record_fetch(subject, "steam_app", status="error", error="no app")
            return
        for version_id in await self.ensure_list_version(platform, title_id):
            await self.add_store_ids(version_id, [("steam_twin", str(appid))])
        await self._conn.commit()
        await self.record_fetch(subject, "steam_app", status="ok")

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
            column, other = ("tip_ru", "tip_en") if looks_russian(text) else ("tip_en", "tip_ru")
            # A changed tip loses our translation of the old one, to be made
            # again (`GuideTranslator`); the same text keeps it.
            await self._conn.execute(
                f"UPDATE title_achievements SET {column} = ?, tip_source = ?,"
                f"  {other} = CASE WHEN {column} IS NOT DISTINCT FROM ? THEN {other} END,"
                f"  tip_translation = CASE WHEN {column} IS NOT DISTINCT FROM ?"
                " THEN tip_translation END"
                " WHERE platform = ? AND title_id = ? AND achievement_id = ?",
                (text, source, text, text, platform, title_id, achievement_id),
            )
        if complete:
            await self._conn.execute(
                "UPDATE achievement_list_connectors SET tips_checked_at = ? WHERE platform = ? "
                "AND title_id = ?",
                (utcnow_iso(), platform, title_id),
            )
        await self._conn.commit()

    async def titles_with_untranslated_guides(self, limit: int) -> list[tuple[str, str]]:
        """Games with a tip in one language only, `(platform, title_id)`."""
        cursor = await self._conn.execute(
            "SELECT DISTINCT platform, title_id FROM title_achievements"
            " WHERE (tip_en IS NULL) <> (tip_ru IS NULL)"
            " ORDER BY platform, title_id LIMIT ?",
            (limit,),
        )
        return [(row["platform"], str(row["title_id"])) for row in await cursor.fetchall()]

    async def untranslated_guides(
        self, platform: str, title_id: str
    ) -> list[tuple[str, str, str, str, str]]:
        """A game's tips in one language only: `(achievement_id, the language it
        is in, its name, its description, the tip)`, name and description in
        that language where known."""
        cursor = await self._conn.execute(
            "SELECT achievement_id, tip_en, tip_ru, name_en, name_ru,"
            "  description_en, description_ru FROM title_achievements"
            " WHERE platform = ? AND title_id = ? AND (tip_en IS NULL) <> (tip_ru IS NULL)"
            " ORDER BY achievement_id",
            (platform, title_id),
        )
        found = []
        for row in await cursor.fetchall():
            lang = "en" if row["tip_en"] is not None else "ru"
            other = "ru" if lang == "en" else "en"
            name = row[f"name_{lang}"] or row[f"name_{other}"] or ""
            about = row[f"description_{lang}"] or row[f"description_{other}"] or ""
            found.append((row["achievement_id"], lang, name, about, row[f"tip_{lang}"]))
        return found

    async def set_guide_translation(
        self, platform: str, title_id: str, achievement_id: str, *, of: str, lang: str, text: str
    ) -> None:
        """Our translation of a tip into `lang`, kept only while the tip it was
        made from (`of`, in the other language) is still the tip."""
        column, source = ("tip_ru", "tip_en") if lang == "ru" else ("tip_en", "tip_ru")
        await self._conn.execute(
            f"UPDATE title_achievements SET {column} = ?, tip_translation = 'llm'"
            f" WHERE platform = ? AND title_id = ? AND achievement_id = ? AND {source} = ?",
            (text, platform, title_id, achievement_id, of),
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
        one updated (its translation dropped, to be made again from the new
        text; owner, 2026-10-30), and the read time stamped."""
        now = utcnow_iso()
        for patch in patches:
            await self._conn.execute(
                "INSERT INTO game_patches"
                " (steam_appid, gid, title, published_at, text_en, created_at, kind, image_url)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(steam_appid, gid) DO UPDATE SET"
                "  title = excluded.title, published_at = excluded.published_at,"
                "  text_en = excluded.text_en, kind = excluded.kind,"
                "  image_url = excluded.image_url,"
                "  title_ru = CASE WHEN game_patches.title IS NOT DISTINCT FROM excluded.title"
                "    AND game_patches.text_en IS NOT DISTINCT FROM excluded.text_en"
                "    THEN game_patches.title_ru END,"
                "  text_ru = CASE WHEN game_patches.title IS NOT DISTINCT FROM excluded.title"
                "    AND game_patches.text_en IS NOT DISTINCT FROM excluded.text_en"
                "    THEN game_patches.text_ru END",
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

    async def patches_to_translate(
        self, *, max_chars: int, limit: int, appid: int | None = None
    ) -> list[tuple[int, str, str, str]]:
        """Posts with no Russian yet (of one app, or of all), the newest first,
        `(appid, gid, title, text)`; a post longer than `max_chars` stays English."""
        cursor = await self._conn.execute(
            "SELECT steam_appid, gid, title, COALESCE(text_en, '') AS text_en"
            " FROM game_patches WHERE title_ru IS NULL"
            "   AND LENGTH(COALESCE(text_en, '')) <= ?"
            "   AND (?::bigint IS NULL OR steam_appid = ?)"
            " ORDER BY published_at DESC LIMIT ?",
            (max_chars, appid, appid, limit),
        )
        return [
            (int(row["steam_appid"]), row["gid"], row["title"], row["text_en"])
            for row in await cursor.fetchall()
        ]

    async def set_patch_translation(
        self, appid: int, gid: str, *, of: tuple[str, str], title_ru: str, text_ru: str
    ) -> None:
        """A post's Russian, kept only while it is still the post `of` (its
        title and text) — a re-read may have changed it meanwhile."""
        title, text = of
        await self._conn.execute(
            "UPDATE game_patches SET title_ru = ?, text_ru = ?"
            " WHERE steam_appid = ? AND gid = ? AND title = ? AND COALESCE(text_en, '') = ?",
            (title_ru, text_ru, appid, gid, title, text),
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
            # One row a person, the one of the greatest platform — the row
            # SQLite's MAX() handed its bare columns from (#234).
            "SELECT DISTINCT ON (al.person_id) al.person_id, s.platform, s.title_id,"
            "       t.name_ru, t.name_en, t.name"
            " FROM seen_achievements s"
            " JOIN account_links al ON al.platform = s.account_platform"
            "  AND al.external_id = s.xuid AND al.is_active = 1"
            # An excluded person is told nothing (CLAUDE.md, Statistics rules).
            " JOIN users u ON u.id = al.person_id AND u.is_excluded = 0"
            " JOIN achievement_list_connectors t ON t.platform = s.platform AND t.title_id = "
            "s.title_id"
            f" WHERE {STEAM_APP_OF_TITLE} = ?"
            f"  AND {earned_date_is_real('s.')} AND {earned_at('s.')} >= ?"
            " ORDER BY al.person_id, s.platform DESC",
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
            f"         {STEAM_APP_OF_TITLE} AS appid"
            "  FROM played p JOIN achievement_list_connectors t ON t.platform = p.platform AND "
            "t.title_id = p.title_id"
            ") "
            # One card a post (DISTINCT ON), whichever of our games it is.
            "SELECT * FROM (SELECT DISTINCT ON (gp.steam_appid, gp.gid)"
            " gp.steam_appid, gp.gid, gp.kind, gp.title, gp.published_at,"
            "       gp.text_en, gp.title_ru, gp.text_ru, gp.image_url, a.platform, a.title_id,"
            "       a.name, a.name_ru, a.name_en, a.icon_url "
            "FROM game_patches gp JOIN apps a ON a.appid = gp.steam_appid "
            "WHERE gp.published_at >= ? AND gp.published_at < ? "
            "ORDER BY gp.steam_appid, gp.gid, a.platform, a.title_id) AS one_each "
            "ORDER BY published_at DESC, steam_appid, gid "
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
                title_ru=row["title_ru"],
                text_ru=row["text_ru"],
                game=row["name"],
                game_ru=row["name_ru"],
                game_en=row["name_en"],
                game_icon_url=row["icon_url"],
            )
            for row in await cursor.fetchall()
        ]

    async def favorite_games_news(
        self, game_ids: list[int], *, since: str, until: str, limit: int
    ) -> list[GameNewsRow]:
        """The developers' posts dated in [since, until) about these games
        (somebody's favorites, owner, 2026-10-26), newest first, one row per
        post; each names the game by the list most people here played."""
        if not game_ids:
            return []
        cursor = await self._conn.execute(
            "WITH fav(game_id) AS (SELECT value::bigint FROM"
            " jsonb_array_elements_text(?::jsonb)), apps AS ("
            "  SELECT f.game_id, CAST(v.product_id AS INTEGER) AS appid FROM fav f"
            "  JOIN versions v ON v.game_id = f.game_id WHERE v.store = 'steam'"
            "  UNION"
            "  SELECT f.game_id, (j.value->>1)::bigint FROM fav f"
            "  JOIN versions v ON v.game_id = f.game_id, jsonb_array_elements(v.store_ids::jsonb) j"
            "  WHERE j.value->>0 = 'steam_twin'"
            ") "
            # One card a post, of its smallest game id (as MIN() picked it).
            "SELECT * FROM (SELECT DISTINCT ON (gp.steam_appid, gp.gid)"
            " gp.steam_appid, gp.gid, gp.kind, gp.title, gp.published_at,"
            "       gp.text_en, gp.title_ru, gp.text_ru, gp.image_url, a.game_id,"
            "       g.name AS game_name, g.name_ru AS game_name_ru "
            "FROM game_patches gp JOIN apps a ON a.appid = gp.steam_appid "
            "JOIN games g ON g.game_id = a.game_id "
            "WHERE gp.published_at >= ? AND gp.published_at < ? "
            "ORDER BY gp.steam_appid, gp.gid, a.game_id) AS one_each "
            "ORDER BY published_at DESC, steam_appid, gid "
            "LIMIT ?",
            (f"[{','.join(str(int(g)) for g in game_ids)}]", since, until, limit),
        )
        rows = await cursor.fetchall()
        lists: dict[int, tuple[str, str] | None] = {}
        for row in rows:
            game_id = int(row["game_id"])
            if game_id not in lists:
                lists[game_id] = await self.game_list_of(game_id)
        out: list[GameNewsRow] = []
        for row in rows:
            key = lists[int(row["game_id"])]
            if key is None:
                continue
            out.append(
                GameNewsRow(
                    steam_appid=int(row["steam_appid"]),
                    gid=row["gid"],
                    kind=row["kind"],
                    title=row["title"],
                    published_at=row["published_at"],
                    text_en=row["text_en"],
                    image_url=row["image_url"],
                    platform=key[0],
                    title_id=str(key[1]),
                    title_ru=row["title_ru"],
                    text_ru=row["text_ru"],
                    game=row["game_name"],
                    game_ru=row["game_name_ru"],
                    game_en=row["game_name"],
                    game_icon_url=await self.title_icon_url(key[0], key[1]),
                )
            )
        return out

    async def game_patch(self, appid: int, gid: str) -> StoredPatch | None:
        """One post of a game's developer, as a notice about it opens it."""
        cursor = await self._conn.execute(
            "SELECT gid, title, published_at, text_en, title_ru, text_ru, image_url, kind"
            " FROM game_patches WHERE steam_appid = ? AND gid = ?",
            (appid, gid),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return StoredPatch(
            gid=row["gid"],
            title=row["title"],
            published_at=row["published_at"],
            text_en=row["text_en"],
            title_ru=row["title_ru"],
            text_ru=row["text_ru"],
            image_url=row["image_url"],
            kind=row["kind"],
        )

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
            "SELECT t.platform, t.title_id FROM achievement_list_connectors t"
            f" WHERE {STEAM_APP_OF_TITLE} IS NOT NULL"
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
            f"  SELECT DISTINCT {STEAM_APP_OF_TITLE} AS appid"
            "  FROM achievement_list_connectors t"
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
