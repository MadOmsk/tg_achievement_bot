"""Poller target-fetching and presence-state saving, across all three
platforms — one mixin of bot.db.repo.Repo (2026-09-09 split; see this
package's own __init__.py). Behavior is unchanged from before the split.

Trophy-scan polling (psn_pollable_users/psn_poll_state) and presence
polling (psn_presence_pollable_accounts/psn_presence_state) are
deliberately both here, side by side, but unrelated cadences — see
psn_presence_pollable_accounts's own comment.
"""

from __future__ import annotations

from bot.db.repo._models import (
    PollTarget,
    PresenceRow,
    PsnPollTarget,
    PsnPresenceRow,
    PsnPresenceTarget,
    SteamPollTarget,
    SteamPresenceRow,
)
from bot.util import utcnow_iso


class _PollingRepo:
    # ------------------------------------------------------------- polling

    async def pollable_users(self) -> list[PollTarget]:
        """Who the poller is allowed to touch (SPEC 5.5, 6.4).

        Excluded users and dead tokens are filtered out here rather than in the
        poller: every tick for them would be a guaranteed failure.
        """
        cursor = await self._conn.execute(
            "SELECT u.tg_id, u.xuid, p.state, p.title_id, p.title_name,"
            "       p.changed_at, p.last_ach_poll_at, p.updated_at "
            "FROM users u "
            "JOIN tokens t ON t.tg_id = u.tg_id "
            "LEFT JOIN presence_state p ON p.xuid = u.xuid "
            "WHERE u.xuid IS NOT NULL AND u.is_excluded = 0 AND t.status = 'active'"
        )
        return [
            PollTarget(
                tg_id=row["tg_id"],
                xuid=row["xuid"],
                state=row["state"],
                title_id=row["title_id"],
                title_name=row["title_name"],
                changed_at=row["changed_at"],
                last_ach_poll_at=row["last_ach_poll_at"],
                updated_at=row["updated_at"],
            )
            for row in await cursor.fetchall()
        ]

    async def save_presence_state(
        self,
        xuid: str,
        state: str,
        title_id: str | None,
        title_name: str | None,
        *,
        changed: bool,
    ) -> None:
        now = utcnow_iso()
        await self._conn.execute(
            "INSERT INTO presence_state "
            "(xuid, state, title_id, title_name, changed_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(xuid) DO UPDATE SET "
            "  state = excluded.state, title_id = excluded.title_id,"
            "  title_name = excluded.title_name, updated_at = excluded.updated_at,"
            "  changed_at = CASE WHEN ? THEN excluded.changed_at "
            "                 ELSE presence_state.changed_at END",
            (xuid, state, title_id, title_name, now, now, 1 if changed else 0),
        )
        await self._conn.commit()

    async def presence_of(self, xuid: str) -> PresenceRow | None:
        cursor = await self._conn.execute(
            "SELECT xuid, state, title_id, title_name, updated_at FROM presence_state "
            "WHERE xuid = ?",
            (xuid,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return PresenceRow(
            xuid=row["xuid"],
            state=row["state"],
            title_id=row["title_id"],
            title_name=row["title_name"],
            updated_at=row["updated_at"],
        )

    async def steam_presence_of(self, steam_id: str) -> SteamPresenceRow | None:
        """Steam's counterpart of `presence_of` — the admin card's own
        lookup for one person (2026-09-05 follow-up), not the batched
        `steam_pollable_users()` the poller itself uses."""
        cursor = await self._conn.execute(
            "SELECT steam_id, persona_state, gameid, game_name, updated_at "
            "FROM steam_presence_state WHERE steam_id = ?",
            (steam_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return SteamPresenceRow(
            steam_id=row["steam_id"],
            persona_state=row["persona_state"],
            gameid=row["gameid"],
            game_name=row["game_name"],
            updated_at=row["updated_at"],
        )

    async def mark_achievements_polled(self, xuid: str) -> None:
        await self._conn.execute(
            "UPDATE presence_state SET last_ach_poll_at = ? WHERE xuid = ?",
            (utcnow_iso(), xuid),
        )
        await self._conn.commit()

    async def touch_last_online(self, tg_id: int) -> None:
        await self._conn.execute(
            "UPDATE users SET last_online_at = ?, updated_at = ? WHERE tg_id = ?",
            (utcnow_iso(), utcnow_iso(), tg_id),
        )
        await self._conn.commit()

    # ------------------------------------------------------- Steam polling

    async def steam_pollable_users(self) -> list[SteamPollTarget]:
        """Who the Steam poller may look at (SPEC 9, M-Steam-2c) — no `tokens`
        JOIN here unlike `pollable_users()`: Steam has no per-user OAuth at
        all, one shared API key for the whole bot (M-Steam-1)."""
        cursor = await self._conn.execute(
            "SELECT u.tg_id, pl.external_id AS steam_id, p.persona_state, p.gameid,"
            "       p.game_name, p.changed_at, p.last_ach_poll_at, p.updated_at,"
            "       p.last_active_gameid, p.last_active_game_name, p.last_active_at "
            "FROM platform_links pl "
            "JOIN users u ON u.tg_id = pl.tg_id "
            "LEFT JOIN steam_presence_state p ON p.steam_id = pl.external_id "
            "WHERE pl.platform = 'steam' AND u.is_excluded = 0"
        )
        return [
            SteamPollTarget(
                tg_id=row["tg_id"],
                steam_id=row["steam_id"],
                persona_state=row["persona_state"],
                gameid=row["gameid"],
                game_name=row["game_name"],
                changed_at=row["changed_at"],
                last_ach_poll_at=row["last_ach_poll_at"],
                updated_at=row["updated_at"],
                last_active_gameid=row["last_active_gameid"],
                last_active_game_name=row["last_active_game_name"],
                last_active_at=row["last_active_at"],
            )
            for row in await cursor.fetchall()
        ]

    async def save_steam_presence_state(
        self,
        steam_id: str,
        persona_state: int,
        gameid: str | None,
        game_name: str | None,
        *,
        changed: bool,
    ) -> None:
        now = utcnow_iso()
        # last_active_* only moves forward when this tick actually has a
        # gameid — a tick that finds none (presence gap or a real quit)
        # leaves it exactly where it was, which is the whole point: it's
        # what the grace period (poller/steam_presence.py) reads to decide
        # whether "no gameid right now" still means "keep polling the last
        # game anyway". On first-ever insert there's no prior tick to fall
        # back to, so it just starts out matching this one (NULL together
        # with gameid if this row's very first sighting has no game either).
        last_active_at = now if gameid is not None else None
        await self._conn.execute(
            "INSERT INTO steam_presence_state "
            "(steam_id, persona_state, gameid, game_name, changed_at, updated_at,"
            " last_active_gameid, last_active_game_name, last_active_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(steam_id) DO UPDATE SET "
            "  persona_state = excluded.persona_state, gameid = excluded.gameid,"
            "  game_name = excluded.game_name, updated_at = excluded.updated_at,"
            "  changed_at = CASE WHEN ? THEN excluded.changed_at "
            "                 ELSE steam_presence_state.changed_at END,"
            "  last_active_gameid = CASE WHEN excluded.gameid IS NOT NULL"
            "    THEN excluded.gameid ELSE steam_presence_state.last_active_gameid END,"
            "  last_active_game_name = CASE WHEN excluded.gameid IS NOT NULL"
            "    THEN excluded.game_name ELSE steam_presence_state.last_active_game_name END,"
            "  last_active_at = CASE WHEN excluded.gameid IS NOT NULL"
            "    THEN excluded.updated_at ELSE steam_presence_state.last_active_at END",
            (
                steam_id,
                persona_state,
                gameid,
                game_name,
                now,
                now,
                gameid,
                game_name,
                last_active_at,
                1 if changed else 0,
            ),
        )
        await self._conn.commit()

    async def mark_steam_achievements_polled(self, steam_id: str) -> None:
        await self._conn.execute(
            "UPDATE steam_presence_state SET last_ach_poll_at = ? WHERE steam_id = ?",
            (utcnow_iso(), steam_id),
        )
        await self._conn.commit()

    async def delete_steam_presence_state(self, steam_id: str) -> None:
        await self._conn.execute("DELETE FROM steam_presence_state WHERE steam_id = ?", (steam_id,))
        await self._conn.commit()

    # ---------------------------------------------------------- PSN polling

    async def psn_pollable_users(self) -> list[PsnPollTarget]:
        """Who the PSN trophy poller may look at (SPEC 9, M-PSN-2) — no
        `tokens` JOIN, same reasoning as steam_pollable_users above: one
        shared service credential for the whole bot (M-PSN-1), not
        per-user OAuth."""
        cursor = await self._conn.execute(
            "SELECT u.tg_id, pl.external_id AS account_id, pl.display_name AS online_id,"
            "       ps.last_polled_at, COALESCE(ps.backfill_done, 0) AS backfill_done "
            "FROM platform_links pl "
            "JOIN users u ON u.tg_id = pl.tg_id "
            "LEFT JOIN psn_poll_state ps ON ps.account_id = pl.external_id "
            "WHERE pl.platform = 'psn' AND u.is_excluded = 0"
        )
        return [
            PsnPollTarget(
                tg_id=row["tg_id"],
                account_id=row["account_id"],
                online_id=row["online_id"],
                last_polled_at=row["last_polled_at"],
                # No psn_poll_state row yet (a link whose backfill hasn't
                # finished, or hasn't started) reads as not-done — #21.
                backfill_done=bool(row["backfill_done"]),
            )
            for row in await cursor.fetchall()
        ]

    async def touch_psn_poll_state(self, account_id: str) -> None:
        await self._conn.execute(
            "INSERT INTO psn_poll_state (account_id, last_polled_at) VALUES (?, ?) "
            "ON CONFLICT(account_id) DO UPDATE SET last_polled_at = excluded.last_polled_at",
            (account_id, utcnow_iso()),
        )
        await self._conn.commit()

    async def mark_psn_backfill_done(self, account_id: str) -> None:
        """Flip the #21 gate: this account's first-ever backfill has
        finished, so poller/psn_fetcher.py's tick() may now poll it.
        `last_polled_at` (NOT NULL) is stamped too so the first live poll
        waits one debounce interval — a courtesy beat after the full-history
        scan, not a correctness need."""
        await self._conn.execute(
            "INSERT INTO psn_poll_state (account_id, last_polled_at, backfill_done) "
            "VALUES (?, ?, 1) "
            "ON CONFLICT(account_id) DO UPDATE SET backfill_done = 1",
            (account_id, utcnow_iso()),
        )
        await self._conn.commit()

    async def delete_psn_poll_state(self, account_id: str) -> None:
        await self._conn.execute("DELETE FROM psn_poll_state WHERE account_id = ?", (account_id,))
        await self._conn.commit()

    async def psn_backfill_done(self, account_id: str) -> bool:
        """Whether this account's first-ever backfill has finished (#21/#27).
        No psn_poll_state row yet (backfill still running, or crashed before
        it could finish) reads as not done."""
        cursor = await self._conn.execute(
            "SELECT backfill_done FROM psn_poll_state WHERE account_id = ?", (account_id,)
        )
        row = await cursor.fetchone()
        return bool(row["backfill_done"]) if row else False

    async def clear_psn_title_progress(self, account_id: str) -> None:
        """Drop every per-game progress checkpoint for an account — used by
        the admin PSN resync (#27) to recover an account whose first backfill
        crashed partway: a bogus "flat" checkpoint left behind then looks
        identical to "nothing new here" and hides that game's trophies
        forever (#26). Safe: backfill re-reads and re-stores, never
        publishes."""
        await self._conn.execute(
            "DELETE FROM psn_title_progress WHERE account_id = ?", (account_id,)
        )
        await self._conn.commit()

    # ------------------------------------------------- PSN presence polling
    # (issue #1) — its own tiny poller, unrelated to psn_pollable_users/
    # psn_poll_state above (the trophy scan's own cadence): presence has
    # never driven trophy polling on PSN, and this doesn't change that.

    async def psn_presence_pollable_accounts(self) -> list[PsnPresenceTarget]:
        cursor = await self._conn.execute(
            "SELECT u.tg_id, pl.external_id AS account_id, pp.state, pp.title_id,"
            "       pp.title_name, pp.changed_at, pp.updated_at "
            "FROM platform_links pl "
            "JOIN users u ON u.tg_id = pl.tg_id "
            "LEFT JOIN psn_presence_state pp ON pp.account_id = pl.external_id "
            "WHERE pl.platform = 'psn' AND u.is_excluded = 0"
        )
        return [
            PsnPresenceTarget(
                tg_id=row["tg_id"],
                account_id=row["account_id"],
                state=row["state"],
                title_id=row["title_id"],
                title_name=row["title_name"],
                changed_at=row["changed_at"],
                updated_at=row["updated_at"],
            )
            for row in await cursor.fetchall()
        ]

    async def save_psn_presence_state(
        self,
        account_id: str,
        state: str,
        title_id: str | None,
        title_name: str | None,
        *,
        changed: bool,
    ) -> None:
        now = utcnow_iso()
        await self._conn.execute(
            "INSERT INTO psn_presence_state "
            "(account_id, state, title_id, title_name, changed_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(account_id) DO UPDATE SET "
            "  state = excluded.state, title_id = excluded.title_id,"
            "  title_name = excluded.title_name, updated_at = excluded.updated_at,"
            "  changed_at = CASE WHEN ? THEN excluded.changed_at "
            "                 ELSE psn_presence_state.changed_at END",
            (account_id, state, title_id, title_name, now, now, 1 if changed else 0),
        )
        await self._conn.commit()

    async def psn_presence_of(self, account_id: str) -> PsnPresenceRow | None:
        """The admin card's own single-account lookup (mirrors
        `steam_presence_of`) — not the batched `psn_presence_pollable_
        accounts()` the poller itself uses."""
        cursor = await self._conn.execute(
            "SELECT account_id, state, title_id, title_name, updated_at "
            "FROM psn_presence_state WHERE account_id = ?",
            (account_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return PsnPresenceRow(
            account_id=row["account_id"],
            state=row["state"],
            title_id=row["title_id"],
            title_name=row["title_name"],
            updated_at=row["updated_at"],
        )
