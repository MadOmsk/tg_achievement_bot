"""Merging two people into one (#156, #162): the same human signed up twice —
by email and by Telegram — and asks for the two to be one. The rules (what may
be merged, who chooses what) are `services/merge.py`'s; this moves the rows, in
one transaction, so a merge either happens whole or not at all."""

from __future__ import annotations

from dataclasses import dataclass, field

from bot.util import utcnow_iso

# Platforms where a person holds one account (PSN takes several, #10).
SINGLE = ("xbox", "steam")


@dataclass(slots=True)
class MergeSide:
    """What one of the two people brings."""

    person_id: int
    handle: str | None
    tg_id: int | None
    username: str | None
    email: str | None
    updated_at: str | None
    # platform -> [(external_id, display name)], active links only
    accounts: dict[str, list[tuple[str, str | None]]] = field(default_factory=dict)
    follows: int = 0
    chats: int = 0

    @property
    def is_empty(self) -> bool:
        """Nothing to lose: no address, no accounts, nobody followed, no chat —
        a person the bot made a moment ago, the first time a Telegram account
        wrote to it."""
        has_accounts = any(self.accounts.values())
        return not (self.email or has_accounts or self.follows or self.chats)


@dataclass(slots=True)
class MergeChoices:
    """Which side wins where both have something (`keep` or `absorb`); PSN is the
    list of account ids to keep."""

    xbox: str = "keep"
    steam: str = "keep"
    telegram: str = "keep"
    email: str = "keep"
    psn: list[str] | None = None


class _MergeRepo:
    async def merge_side(self, person_id: int) -> MergeSide | None:
        cursor = await self._conn.execute(
            "SELECT id, handle, handle_number, tg_id, username, email, updated_at"
            " FROM users WHERE id = ?",
            (person_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        handle = row["handle"]
        if handle and row["handle_number"]:
            handle = f"{handle}#{row['handle_number']:04d}"
        side = MergeSide(
            person_id=row["id"],
            handle=handle,
            tg_id=row["tg_id"],
            username=row["username"],
            email=row["email"],
            updated_at=row["updated_at"],
        )
        cursor = await self._conn.execute(
            "SELECT al.platform, al.external_id, a.display_name FROM account_links al"
            " JOIN accounts a ON a.platform = al.platform AND a.external_id = al.external_id"
            " WHERE al.person_id = ? AND al.is_active = 1 ORDER BY al.linked_at",
            (person_id,),
        )
        for link in await cursor.fetchall():
            side.accounts.setdefault(link["platform"], []).append(
                (link["external_id"], link["display_name"])
            )
        cursor = await self._conn.execute(
            "SELECT (SELECT COUNT(*) FROM follows WHERE follower_id = :p OR followee_id = :p),"
            "       (SELECT COUNT(*) FROM subscriptions WHERE person_id = :p)",
            {"p": person_id},
        )
        counts = await cursor.fetchone()
        side.follows, side.chats = int(counts[0]), int(counts[1])
        return side

    async def merge_people(self, keep: int, absorb: int, choices: MergeChoices) -> list[str]:
        """Fold `absorb` into `keep` and delete `absorb`. Returns the pictures on
        disk nobody shows any more, for the caller to delete. The caller has
        checked the choices (`services/merge.py`)."""
        now = utcnow_iso()
        conn = self._conn
        a = {"keep": keep, "absorb": absorb, "now": now}
        async with self.transaction():
            # Checked at commit, not per statement: a Telegram id moving from one
            # row to the other is briefly nobody's, and `chat_seen` points at it.
            # The pragma lasts for the open transaction only, so it goes inside.
            await conn.execute("PRAGMA defer_foreign_keys = ON")
            # Whose Xbox account stays decides whose Xbox login stays with it.
            cursor = await conn.execute(
                "SELECT person_id FROM account_links"
                " WHERE person_id IN (?, ?) AND platform = 'xbox' AND is_active = 1",
                (keep, absorb),
            )
            with_xbox = {row["person_id"] for row in await cursor.fetchall()}
            if with_xbox == {keep, absorb}:
                xbox_side = keep if choices.xbox == "keep" else absorb
            else:
                xbox_side = next(iter(with_xbox), None)

            # ---------------------------------------------------- accounts
            for platform in SINGLE:
                loser = absorb if getattr(choices, platform) == "keep" else keep
                await conn.execute(
                    "UPDATE account_links SET is_active = 0, unlinked_at = :now"
                    " WHERE person_id = :loser AND platform = :platform AND is_active = 1"
                    "   AND EXISTS (SELECT 1 FROM account_links o WHERE o.platform = :platform"
                    "     AND o.is_active = 1 AND o.person_id = :other)",
                    {
                        "now": now,
                        "loser": loser,
                        "platform": platform,
                        "other": keep if loser == absorb else absorb,
                    },
                )
            if choices.psn is not None:
                keep_ids = ",".join("?" * len(choices.psn)) or "NULL"
                await conn.execute(
                    "UPDATE account_links SET is_active = 0, unlinked_at = ?"
                    " WHERE person_id IN (?, ?) AND platform = 'psn' AND is_active = 1"
                    f"   AND external_id NOT IN ({keep_ids})",
                    (now, keep, absorb, *choices.psn),
                )
            # The Xbox login belongs to the Xbox account that stays; a login with
            # no account behind it any more goes.
            await conn.execute(
                "DELETE FROM tokens WHERE person_id IN (?, ?) AND person_id IS NOT ?",
                (keep, absorb, xbox_side),
            )
            await conn.execute("UPDATE tokens SET person_id = :keep WHERE person_id = :absorb", a)
            # Both may have held one account at some time: keep one row of it.
            await conn.execute(
                "DELETE FROM account_links WHERE person_id = :keep AND is_active = 0"
                "  AND EXISTS (SELECT 1 FROM account_links o WHERE o.person_id = :absorb"
                "    AND o.platform = account_links.platform"
                "    AND o.external_id = account_links.external_id)",
                a,
            )
            await conn.execute(
                "UPDATE OR IGNORE account_links SET person_id = :keep WHERE person_id = :absorb", a
            )

            # ------------------------------------------- chats and people
            await conn.execute(
                "INSERT OR IGNORE INTO subscriptions (chat_id, person_id, created_at)"
                " SELECT chat_id, :keep, created_at FROM subscriptions WHERE person_id = :absorb",
                a,
            )
            for column, other in (("follower_id", "followee_id"), ("followee_id", "follower_id")):
                await conn.execute(
                    f"INSERT OR IGNORE INTO follows ({column}, {other}, created_at)"
                    f" SELECT :keep, {other}, created_at FROM follows"
                    f" WHERE {column} = :absorb AND {other} != :keep",
                    a,
                )
            for column, other in (("person_id", "blocked_id"), ("blocked_id", "person_id")):
                await conn.execute(
                    f"INSERT OR IGNORE INTO blocks ({column}, {other}, created_at)"
                    f" SELECT :keep, {other}, created_at FROM blocks"
                    f" WHERE {column} = :absorb AND {other} != :keep",
                    a,
                )
            for table in ("web_sessions", "notifications", "push_subscriptions", "passkeys"):
                await conn.execute(
                    f"UPDATE {table} SET person_id = :keep WHERE person_id = :absorb", a
                )
            # The codes one made and the one one came by (#167): left behind,
            # deleting the absorbed row took them with it — who came by a code
            # is kept and shown.
            await conn.execute(
                "UPDATE invites SET created_by = :keep WHERE created_by = :absorb", a
            )
            await conn.execute("UPDATE invites SET used_by = :keep WHERE used_by = :absorb", a)
            # When each pair last pinged and unfollowed: the follow limits hold
            # for the person who stays.
            for column, other in (("follower_id", "followee_id"), ("followee_id", "follower_id")):
                await conn.execute(
                    f"INSERT OR IGNORE INTO follow_log ({column}, {other}, notified_at,"
                    "  unfollowed_at)"
                    f" SELECT :keep, {other}, notified_at, unfollowed_at FROM follow_log"
                    f" WHERE {column} = :absorb AND {other} != :keep",
                    a,
                )

            # ------------------------------------------------- the person
            cursor = await conn.execute(
                "SELECT id, tg_id, username, first_name, last_name, photo_file_id,"
                " photo_unique_id, photo_checked_at, photo_path, custom_avatar_path, email,"
                " email_linked_at, updated_at, activity_visible, is_excluded, last_online_at,"
                " created_at FROM users WHERE id IN (?, ?)",
                (keep, absorb),
            )
            rows = {row["id"]: row for row in await cursor.fetchall()}
            k, b = rows[keep], rows[absorb]
            gone: list[str] = []

            # Settings come from the side used more recently.
            if (b["updated_at"] or "") > (k["updated_at"] or ""):
                await conn.execute("DELETE FROM user_settings WHERE person_id = :keep", a)
                await conn.execute(
                    "UPDATE user_settings SET person_id = :keep WHERE person_id = :absorb", a
                )
                activity_visible = b["activity_visible"]
            else:
                activity_visible = k["activity_visible"]

            telegram = k
            if b["tg_id"] is not None and (k["tg_id"] is None or choices.telegram == "absorb"):
                telegram = b
            dropped_tg = (k if telegram is b else b)["tg_id"]
            email_row = b if (b["email"] and (not k["email"] or choices.email == "absorb")) else k
            avatar = k["custom_avatar_path"] or b["custom_avatar_path"]
            for row in (k, b):
                if row["custom_avatar_path"] and row["custom_avatar_path"] != avatar:
                    gone.append(row["custom_avatar_path"])
                if row is not telegram and row["photo_path"]:
                    gone.append(row["photo_path"])

            # The absorbed row lets go of what is unique first.
            await conn.execute("UPDATE users SET tg_id = NULL, email = NULL WHERE id = :absorb", a)
            await conn.execute(
                "UPDATE users SET tg_id = ?, username = ?, first_name = ?, last_name = ?,"
                " photo_file_id = ?, photo_unique_id = ?, photo_checked_at = ?, photo_path = ?,"
                " email = ?, email_linked_at = ?, custom_avatar_path = ?, activity_visible = ?,"
                " is_excluded = ?, last_online_at = ?, created_at = ?, updated_at = ?"
                " WHERE id = ?",
                (
                    telegram["tg_id"],
                    telegram["username"],
                    telegram["first_name"],
                    telegram["last_name"],
                    telegram["photo_file_id"],
                    telegram["photo_unique_id"],
                    telegram["photo_checked_at"],
                    telegram["photo_path"],
                    email_row["email"],
                    email_row["email_linked_at"],
                    avatar,
                    activity_visible,
                    max(int(k["is_excluded"]), int(b["is_excluded"])),
                    max(k["last_online_at"] or "", b["last_online_at"] or "") or None,
                    min(k["created_at"], b["created_at"]),
                    now,
                    keep,
                ),
            )
            # A Telegram account let go of is nobody's, as after removing it.
            if dropped_tg is not None:
                await conn.execute("DELETE FROM chat_seen WHERE tg_id = ?", (dropped_tg,))
            await conn.execute("DELETE FROM users WHERE id = :absorb", a)
        return gone
