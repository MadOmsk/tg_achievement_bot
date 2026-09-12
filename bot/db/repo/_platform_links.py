"""Steam's own achievement schema/rarity caches, and the `accounts` /
`account_links` pair that replaced the old platform_links table (#52) —
one mixin of bot.db.repo.Repo (2026-09-09 split; see this package's own
__init__.py).

An account exists on its own terms here: `accounts` is what the account *is*
(nickname, gamerscore, trophy level, visibility), `account_links` is who has
it and who had it before. Unlinking deactivates a link, it never deletes
anything — so an account's achievements stay attached to the account and are
waiting for whoever links it next.
"""

from __future__ import annotations

import json

from bot.constants import AccountPlatform
from bot.db.repo._models import PlatformLink, SteamSchemaAchievement, TitleProgress
from bot.util import utcnow_iso


class _PlatformLinksRepo:
    # ---------------------------------------------- Steam achievement cache

    async def steam_schema_get_cached(
        self, appid: str
    ) -> tuple[str | None, list[SteamSchemaAchievement]] | None:
        """The game's own achievement list — cached forever, one row per
        appid, never invalidated (SPEC 9, M-Steam-2b): a game's achievements
        don't change between polls the way unlock percentages do."""
        cursor = await self._conn.execute(
            "SELECT game_name, achievements FROM steam_schema_cache WHERE appid = ?",
            (appid,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        achievements = [
            SteamSchemaAchievement(
                apiname=item["apiname"], icon=item["icon"], hidden=item["hidden"]
            )
            for item in json.loads(row["achievements"])
        ]
        return row["game_name"], achievements

    async def steam_schema_cache_result(
        self, appid: str, game_name: str | None, achievements: list[SteamSchemaAchievement]
    ) -> None:
        blob = json.dumps(
            [{"apiname": a.apiname, "icon": a.icon, "hidden": a.hidden} for a in achievements]
        )
        await self._conn.execute(
            "INSERT OR REPLACE INTO steam_schema_cache (appid, game_name, achievements, cached_at) "
            "VALUES (?, ?, ?, ?)",
            (appid, game_name, blob, utcnow_iso()),
        )
        await self._conn.commit()

    async def steam_rarity_get_cached(self, appid: str) -> tuple[dict[str, float], str] | None:
        """Percentages plus their own cache timestamp — unlike the schema
        above, real percentages drift over time, so the caller (services/
        steam/achievements.py) decides whether `cached_at` is too old and
        needs a fresh fetch, this layer just reports what's there."""
        cursor = await self._conn.execute(
            "SELECT percentages, cached_at FROM steam_rarity_cache WHERE appid = ?",
            (appid,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return json.loads(row["percentages"]), row["cached_at"]

    async def steam_rarity_cache_result(self, appid: str, percentages: dict[str, float]) -> None:
        await self._conn.execute(
            "INSERT OR REPLACE INTO steam_rarity_cache (appid, percentages, cached_at) "
            "VALUES (?, ?, ?)",
            (appid, json.dumps(percentages), utcnow_iso()),
        )
        await self._conn.commit()

    # ------------------------------------------------- accounts and links

    # `PlatformLink` is still the read model every caller sees (#52): it is
    # now the join of `accounts` (what the account is) and `account_links`
    # (who has it), rather than one row of the old platform_links table.
    # Keeping that shape spared some forty call sites a rename that would
    # have told them nothing new.
    _LINK_COLUMNS = (
        "SELECT al.tg_id, al.platform, al.external_id, a.display_name, a.secondary_name,"
        "       al.linked_at, a.psn_trophy_level, a.achievements_visible,"
        "       a.achievements_visible_checked_at "
        "FROM account_links al "
        "JOIN accounts a ON a.platform = al.platform AND a.external_id = al.external_id "
    )

    async def link_platform_account(
        self, tg_id: int, platform: str, external_id: str, display_name: str | None
    ) -> int | None:
        """Link an account to a person; returns the tg_id it was taken from,
        when somebody else was holding it.

        Nothing is deleted. The account is remembered independently of who
        has it, and any previous link is deactivated rather than removed —
        so its achievements stay with the account, waiting for whoever links
        it next, and "which account was linked before" is a row rather than
        a guess.

        Taking an account from another person is allowed on purpose (owner
        decision, 2026-09-12: no hard block for now); telling them is the
        caller's job. `idx_links_one_owner` is what makes that a defined
        event rather than two silent owners.
        """
        now = utcnow_iso()
        await self._conn.execute(
            "INSERT INTO accounts (platform, external_id, display_name, first_seen_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(platform, external_id) DO UPDATE SET "
            "  display_name = COALESCE(excluded.display_name, accounts.display_name),"
            "  updated_at = excluded.updated_at",
            (platform, external_id, display_name, now, now),
        )

        cursor = await self._conn.execute(
            "SELECT tg_id FROM account_links "
            "WHERE platform = ? AND external_id = ? AND is_active = 1 AND tg_id != ?",
            (platform, external_id, tg_id),
        )
        row = await cursor.fetchone()
        taken_from = row["tg_id"] if row else None

        # Both deactivations happen before the new link goes in: the account
        # may be held by someone else (idx_links_one_owner), and this person
        # may already hold a different account on the same platform
        # (idx_links_one_active_per_platform). Either index would reject the
        # insert otherwise.
        await self._conn.execute(
            "UPDATE account_links SET is_active = 0, unlinked_at = ? "
            "WHERE platform = ? AND external_id = ? AND is_active = 1",
            (now, platform, external_id),
        )
        await self._conn.execute(
            "UPDATE account_links SET is_active = 0, unlinked_at = ? "
            "WHERE tg_id = ? AND platform = ? AND is_active = 1",
            (now, tg_id, platform),
        )
        await self._conn.execute(
            "INSERT INTO account_links (tg_id, platform, external_id, is_active, linked_at) "
            "VALUES (?, ?, ?, 1, ?) "
            "ON CONFLICT(tg_id, platform, external_id) DO UPDATE SET "
            "  is_active = 1, linked_at = excluded.linked_at, unlinked_at = NULL",
            (tg_id, platform, external_id, now),
        )
        await self._conn.commit()
        return taken_from

    async def update_platform_names(
        self, tg_id: int, platform: str, display_name: str, secondary_name: str | None = None
    ) -> bool:
        """Opportunistic refresh only (SPEC 9, M-Steam-2c, widened to every
        platform by #51) — each poller already holds a fresh nickname inside
        a response it made for another reason, so no request exists just for
        this.

        Writes only when something actually changed, and says whether it
        did: this runs on every presence tick for every linked account, and
        rewriting the same two strings a few times a minute is pure churn.
        A nickname belongs to the account rather than to the link, so this
        reaches `accounts` through whichever one the person holds now.
        """
        cursor = await self._conn.execute(
            "UPDATE accounts SET display_name = ?,"
            "       secondary_name = COALESCE(?, secondary_name), updated_at = ? "
            "WHERE (platform, external_id) IN ("
            "  SELECT platform, external_id FROM account_links"
            "  WHERE tg_id = ? AND platform = ? AND is_active = 1)"
            "  AND (display_name IS NOT ? OR (? IS NOT NULL AND secondary_name IS NOT ?))",
            (
                display_name,
                secondary_name,
                utcnow_iso(),
                tg_id,
                platform,
                display_name,
                secondary_name,
                secondary_name,
            ),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    async def set_platform_secondary_name(
        self, tg_id: int, platform: str, secondary_name: str | None
    ) -> None:
        """The chain's middle step on its own — PSN's previous online ID when
        a rename is noticed (or backfilled once from Sony's legacy endpoint),
        Steam's vanity when it is first read off `profileurl`."""
        await self._conn.execute(
            "UPDATE accounts SET secondary_name = ?, updated_at = ? "
            "WHERE (platform, external_id) IN ("
            "  SELECT platform, external_id FROM account_links"
            "  WHERE tg_id = ? AND platform = ? AND is_active = 1)",
            (secondary_name, utcnow_iso(), tg_id, platform),
        )
        await self._conn.commit()

    async def get_platform_link(self, tg_id: int, platform: str) -> PlatformLink | None:
        cursor = await self._conn.execute(
            self._LINK_COLUMNS + "WHERE al.tg_id = ? AND al.platform = ? AND al.is_active = 1",
            (tg_id, platform),
        )
        row = await cursor.fetchone()
        return _as_platform_link(row) if row is not None else None

    async def platform_links_of(
        self, tg_id: int, *, include_xbox: bool = False
    ) -> list[PlatformLink]:
        """Every account this person holds right now — never a deactivated
        one (#52): an account they no longer have must appear in no screen
        and no statistic.

        Xbox is excluded unless asked for. `PlatformLink` has meant "a
        Steam/PSN link" since it existed, and every caller renders Xbox from
        `users.xuid` on its own line first — returning Xbox here too made
        /stats print the same account twice, once per shape (caught by
        test_zero_limit_shows_every_game_uncapped, which counted its games
        twice). The exclusion goes away with those cache columns in the
        follow-up step, once Xbox is read the same way as everything else.
        """
        clause = "WHERE al.tg_id = ? AND al.is_active = 1 "
        if not include_xbox:
            clause += "AND al.platform != 'xbox' "
        cursor = await self._conn.execute(
            self._LINK_COLUMNS + clause + "ORDER BY al.platform",
            (tg_id,),
        )
        return [_as_platform_link(row) for row in await cursor.fetchall()]

    async def platform_links_all(self, platform: str) -> list[PlatformLink]:
        """Every *active* link on one platform, across every person —
        `platform_links_of` narrowed to one person, this is the bot-wide
        counterpart (2026-09-05, scripts/backfill_steam_titles.py: needs
        every Steam link to reconcile, not any one person's)."""
        cursor = await self._conn.execute(
            self._LINK_COLUMNS + "WHERE al.platform = ? AND al.is_active = 1",
            (platform,),
        )
        return [_as_platform_link(row) for row in await cursor.fetchall()]

    async def set_psn_trophy_level(self, tg_id: int, level: int) -> None:
        await self._conn.execute(
            "UPDATE accounts SET psn_trophy_level = ?, updated_at = ? "
            "WHERE (platform, external_id) IN ("
            "  SELECT platform, external_id FROM account_links"
            "  WHERE tg_id = ? AND platform = 'psn' AND is_active = 1)",
            (level, utcnow_iso(), tg_id),
        )
        await self._conn.commit()

    async def set_achievements_visible(self, tg_id: int, platform: str, visible: bool) -> None:
        now = utcnow_iso()
        await self._conn.execute(
            "UPDATE accounts SET achievements_visible = ?,"
            "       achievements_visible_checked_at = ?, updated_at = ? "
            "WHERE (platform, external_id) IN ("
            "  SELECT platform, external_id FROM account_links"
            "  WHERE tg_id = ? AND platform = ? AND is_active = 1)",
            (int(visible), now, now, tg_id, platform),
        )
        await self._conn.commit()

    async def unlink_platform_account(self, tg_id: int, platform: str) -> None:
        """Deactivate, never delete (#52) — the account and everything it
        earned stay where they are, so relinking it later finds its history
        waiting instead of paying for a full backfill all over again."""
        await self._conn.execute(
            "UPDATE account_links SET is_active = 0, unlinked_at = ? "
            "WHERE tg_id = ? AND platform = ? AND is_active = 1",
            (utcnow_iso(), tg_id, platform),
        )
        await self._conn.commit()

    async def account_owner(self, platform: str, external_id: str) -> int | None:
        """Who holds this account right now, if anyone."""
        cursor = await self._conn.execute(
            "SELECT tg_id FROM account_links "
            "WHERE platform = ? AND external_id = ? AND is_active = 1",
            (platform, external_id),
        )
        row = await cursor.fetchone()
        return row["tg_id"] if row else None

    async def account_achievement_count(self, platform: str, external_id: str) -> int:
        """How much this account has earned, regardless of who holds it —
        what a person is about to gain or stop seeing when a link changes
        (#52, services/relink.py)."""
        cursor = await self._conn.execute(
            "SELECT COUNT(*) FROM seen_achievements WHERE account_platform = ? AND xuid = ?",
            (platform, external_id),
        )
        row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def save_title_groups(
        self, title_id: str, groups: list[tuple[str, str | None, int]]
    ) -> None:
        """The base game plus one row per DLC (#46) — cached forever, like
        every other "the game's own shape" fact here, because it only
        changes when the publisher ships new trophies."""
        now = utcnow_iso()
        for group_id, name, total in groups:
            await self._conn.execute(
                "INSERT INTO title_groups (title_id, group_id, name, total, updated_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(title_id, group_id) DO UPDATE SET "
                "  name = excluded.name, total = excluded.total,"
                "  updated_at = excluded.updated_at",
                (title_id, group_id, name, total, now),
            )
        await self._conn.commit()

    async def has_title_groups(self, title_id: str) -> bool:
        cursor = await self._conn.execute(
            "SELECT 1 FROM title_groups WHERE title_id = ? LIMIT 1", (title_id,)
        )
        return await cursor.fetchone() is not None

    async def psn_title_needs_widening(self, external_id: str, title_id: str) -> bool:
        """Does this account already hold trophies for this game that were
        stored back when only the base group was ever fetched? (#46)

        Every row written before that carries a NULL `trophy_group_id` and
        every row written since carries one, so "has rows, none of them
        grouped" is an exact, self-clearing description of a game whose DLC
        trophies are about to be discovered all at once. `title_groups`
        could not answer this — it is shared by everyone who owns the game,
        so the second person to unlock something there would look "already
        widened" while their own DLC trophies had never been fetched.

        No rows at all is *not* widening: that is simply a game this person
        has just started, and its trophies are as new as they look.
        """
        cursor = await self._conn.execute(
            "SELECT COUNT(*), COUNT(trophy_group_id) FROM seen_achievements "
            "WHERE account_platform = ? AND xuid = ? AND title_id = ?",
            (AccountPlatform.PSN, external_id, title_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return False
        stored, grouped = int(row[0]), int(row[1])
        return stored > 0 and grouped == 0

    async def title_progress(
        self, account_platform: str, external_id: str, title_id: str, group_id: str | None = None
    ) -> TitleProgress | None:
        """(unlocked, total) for one game on one account, or None when the
        total is not something the bot knows (#46).

        Where the total comes from differs per platform, and only two of
        three have one at all:

        - Xbox states it directly in `title_history`, which the poller
          refreshes anyway;
        - Steam has no per-user total, but `steam_schema_cache` holds the
          game's whole achievement list, so its length is the total;
        - PSN reports progress as a percentage and never a count, but the
          trophy-title list it already fetches carries `defined_trophies`;
          that sum is kept on `titles.achievements_total`, so the counter
          reads the same on all three platforms (#46, owner decision:
          a count everywhere rather than a percentage on one).

        None only when the total genuinely is not known yet — a game polled
        before this shipped, or a Steam schema not cached. The counter is
        then left off that line rather than invented.
        """
        if account_platform == AccountPlatform.XBOX:
            cursor = await self._conn.execute(
                "SELECT achievements_unlocked, achievements_total FROM title_history "
                "WHERE xuid = ? AND title_id = ?",
                (external_id, title_id),
            )
            row = await cursor.fetchone()
            if row is None or not row["achievements_total"]:
                return None
            return TitleProgress(
                unlocked=int(row["achievements_unlocked"] or 0),
                total=int(row["achievements_total"]),
            )

        if account_platform == AccountPlatform.STEAM:
            cached = await self.steam_schema_get_cached(title_id)
            if cached is None or not cached[1]:
                return None
            cursor = await self._conn.execute(
                "SELECT COUNT(*) FROM seen_achievements "
                "WHERE account_platform = ? AND xuid = ? AND title_id = ?",
                (account_platform, external_id, title_id),
            )
            row = await cursor.fetchone()
            return TitleProgress(unlocked=int(row[0]) if row else 0, total=len(cached[1]))

        cursor = await self._conn.execute(
            "SELECT achievements_total FROM titles WHERE title_id = ?", (title_id,)
        )
        row = await cursor.fetchone()
        if row is None or not row["achievements_total"]:
            return None
        total = int(row["achievements_total"])
        cursor = await self._conn.execute(
            "SELECT COUNT(*) FROM seen_achievements "
            "WHERE account_platform = ? AND xuid = ? AND title_id = ?",
            (account_platform, external_id, title_id),
        )
        row = await cursor.fetchone()
        progress = TitleProgress(unlocked=int(row[0]) if row else 0, total=total)
        if group_id is None:
            return progress

        # Sony gives every title at least a 'default' group, so "has groups"
        # is not the question — "is it split into more than one" is. A game
        # with a single group would render a second line saying exactly what
        # the first one already said.
        cursor = await self._conn.execute(
            "SELECT COUNT(*) FROM title_groups WHERE title_id = ?", (title_id,)
        )
        row = await cursor.fetchone()
        if row is None or int(row[0]) < 2:
            return progress

        cursor = await self._conn.execute(
            "SELECT name, total FROM title_groups WHERE title_id = ? AND group_id = ?",
            (title_id, group_id),
        )
        group = await cursor.fetchone()
        if group is None:
            return progress
        cursor = await self._conn.execute(
            "SELECT COUNT(*) FROM seen_achievements "
            "WHERE account_platform = ? AND xuid = ? AND title_id = ?"
            "  AND trophy_group_id = ?",
            (account_platform, external_id, title_id, group_id),
        )
        earned = await cursor.fetchone()
        progress.group_name = group["name"]
        progress.group_total = int(group["total"])
        progress.group_unlocked = int(earned[0]) if earned else 0
        progress.group_is_default = group_id == "default"
        return progress

    async def account_latest_unlock(self, platform: str, external_id: str) -> str | None:
        """The newest unlock we already hold for this account — where a
        relink's delta starts (#52). None when the account is new to us, and
        then only a full backfill will do."""
        cursor = await self._conn.execute(
            "SELECT MAX(unlocked_at) FROM seen_achievements "
            "WHERE account_platform = ? AND xuid = ?",
            (platform, external_id),
        )
        row = await cursor.fetchone()
        return row[0] if row else None

    async def account_has_history(self, platform: str, external_id: str) -> bool:
        """Whether anything was ever recorded for this account — the signal
        that a relink can run a delta instead of a full backfill (#52)."""
        cursor = await self._conn.execute(
            "SELECT 1 FROM seen_achievements WHERE account_platform = ? AND xuid = ? LIMIT 1",
            (platform, external_id),
        )
        return await cursor.fetchone() is not None


def _as_platform_link(row) -> PlatformLink:
    return PlatformLink(
        tg_id=row["tg_id"],
        platform=row["platform"],
        external_id=row["external_id"],
        display_name=row["display_name"],
        secondary_name=row["secondary_name"],
        linked_at=row["linked_at"],
        psn_trophy_level=row["psn_trophy_level"],
        achievements_visible=(
            bool(row["achievements_visible"]) if row["achievements_visible"] is not None else None
        ),
        achievements_visible_checked_at=row["achievements_visible_checked_at"],
    )
