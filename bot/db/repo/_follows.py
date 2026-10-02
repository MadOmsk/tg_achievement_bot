"""Follows, blocks and the activity setting (#157, migration 073).

Everything here speaks in person ids (`users.id`). Following is one-way and needs
no consent; two people following each other are friends. A block removes the
follows between the two and stops either finding the other."""

from __future__ import annotations

from dataclasses import dataclass

from bot.services import handles
from bot.services.people import (
    ACTIVITY_CHOICES,
    SEARCH_LIMIT,
    SEARCH_MIN,
    Relation,
    can_view,
)
from bot.util import utcnow_iso


@dataclass(frozen=True, slots=True)
class PersonRow:
    """A person as a list shows them: enough to draw a row and its button."""

    id: int
    tg_id: int | None
    handle: str
    relation: Relation


# The nickname as shown, with its digits — the same form `_sql.HANDLE_SHOWN` gives
# the older queries, here keyed on the `p` alias.
_SHOWN = (
    "CASE WHEN p.handle_number = 0 THEN p.handle"
    " ELSE p.handle || '#' || printf('%04d', p.handle_number) END"
)
# Relation of `?` (the viewer) to `p`, as four columns.
_RELATION = (
    "EXISTS (SELECT 1 FROM follows f WHERE f.follower_id = :me AND f.followee_id = p.id)"
    " AS following,"
    " EXISTS (SELECT 1 FROM follows f WHERE f.follower_id = p.id AND f.followee_id = :me)"
    " AS followed_by,"
    " EXISTS (SELECT 1 FROM blocks b WHERE b.person_id = :me AND b.blocked_id = p.id)"
    " AS blocked,"
    " EXISTS (SELECT 1 FROM blocks b WHERE b.person_id = p.id AND b.blocked_id = :me)"
    " AS blocked_by"
)
_NOT_BLOCKED = (
    " AND NOT EXISTS (SELECT 1 FROM blocks b WHERE (b.person_id = :me AND b.blocked_id = p.id)"
    "   OR (b.person_id = p.id AND b.blocked_id = :me))"
)


def _person(row) -> PersonRow:
    return PersonRow(
        id=row["id"],
        tg_id=row["tg_id"],
        handle=row["shown"],
        relation=Relation(
            following=bool(row["following"]),
            followed_by=bool(row["followed_by"]),
            blocked=bool(row["blocked"]),
            blocked_by=bool(row["blocked_by"]),
        ),
    )


class _FollowsRepo:
    async def person_id(self, tg_id: int) -> int | None:
        cursor = await self._conn.execute("SELECT id FROM users WHERE tg_id = ?", (tg_id,))
        row = await cursor.fetchone()
        return row["id"] if row else None

    async def relation(self, me: int, other: int) -> Relation:
        cursor = await self._conn.execute(
            "SELECT " + _RELATION + " FROM users p WHERE p.id = :other",
            {"me": me, "other": other},
        )
        row = await cursor.fetchone()
        if row is None:
            return Relation()
        return Relation(
            following=bool(row["following"]),
            followed_by=bool(row["followed_by"]),
            blocked=bool(row["blocked"]),
            blocked_by=bool(row["blocked_by"]),
        )

    async def follow(self, me: int, other: int) -> bool:
        """Follow somebody. False when it changed nothing: oneself, a person who
        does not exist, a block either way, or already following."""
        if me == other:
            return False
        relation = await self.relation(me, other)
        if relation.blocked or relation.blocked_by or relation.following:
            return False
        cursor = await self._conn.execute(
            "INSERT OR IGNORE INTO follows (follower_id, followee_id, created_at) "
            "SELECT ?, id, ? FROM users WHERE id = ?",
            (me, utcnow_iso(), other),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    async def unfollow(self, me: int, other: int) -> None:
        await self._conn.execute(
            "DELETE FROM follows WHERE follower_id = ? AND followee_id = ?", (me, other)
        )
        await self._conn.commit()

    async def remove_follower(self, me: int, other: int) -> None:
        """Make `other` stop following `me`, without a block."""
        await self.unfollow(other, me)

    async def block(self, me: int, other: int) -> bool:
        if me == other:
            return False
        cursor = await self._conn.execute(
            "INSERT OR IGNORE INTO blocks (person_id, blocked_id, created_at) "
            "SELECT ?, id, ? FROM users WHERE id = ?",
            (me, utcnow_iso(), other),
        )
        await self._conn.execute(
            "DELETE FROM follows WHERE (follower_id = ? AND followee_id = ?)"
            " OR (follower_id = ? AND followee_id = ?)",
            (me, other, other, me),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    async def unblock(self, me: int, other: int) -> None:
        await self._conn.execute(
            "DELETE FROM blocks WHERE person_id = ? AND blocked_id = ?", (me, other)
        )
        await self._conn.commit()

    async def _list(self, me: int, where: str, params: dict) -> list[PersonRow]:
        cursor = await self._conn.execute(
            "SELECT p.id, p.tg_id, " + _SHOWN + " AS shown, " + _RELATION + " FROM users p "
            "WHERE p.handle IS NOT NULL AND p.is_excluded = 0 " + where + " "
            "ORDER BY p.handle_norm, p.handle_number",
            {"me": me, **params},
        )
        return [_person(row) for row in await cursor.fetchall()]

    async def person_with_relation(self, me: int, other: int) -> PersonRow | None:
        rows = await self._list(me, " AND p.id = :other", {"other": other})
        return rows[0] if rows else None

    async def person_row(self, person: int) -> PersonRow | None:
        """A person with no relation to anybody, for a message that names them."""
        return await self.person_with_relation(person, person)

    async def following_of(self, me: int) -> list[PersonRow]:
        return await self._list(
            me,
            " AND p.id IN (SELECT followee_id FROM follows WHERE follower_id = :me)" + _NOT_BLOCKED,
            {},
        )

    async def followers_of(self, me: int) -> list[PersonRow]:
        return await self._list(
            me,
            " AND p.id IN (SELECT follower_id FROM follows WHERE followee_id = :me)" + _NOT_BLOCKED,
            {},
        )

    async def blocked_by(self, me: int) -> list[PersonRow]:
        return await self._list(
            me, " AND p.id IN (SELECT blocked_id FROM blocks WHERE person_id = :me)", {}
        )

    async def follow_counts(self, person: int) -> tuple[int, int]:
        """(followers, following)."""
        cursor = await self._conn.execute(
            "SELECT (SELECT COUNT(*) FROM follows WHERE followee_id = :p),"
            "       (SELECT COUNT(*) FROM follows WHERE follower_id = :p)",
            {"p": person},
        )
        row = await cursor.fetchone()
        return row[0], row[1]

    async def search_people(self, me: int, query: str) -> list[PersonRow]:
        """By nickname only: a prefix of at least three characters, or an exact
        `Name#1234`. Never oneself, a blocked person either way, or an excluded one."""
        name, _, digits = query.strip().partition("#")
        norm = handles.normalize(name)
        if len(norm) < SEARCH_MIN or not norm.isalnum() or not norm.isascii():
            return []
        if digits:
            if not digits.isdigit():
                return []
            where = " AND p.handle_norm = :norm AND p.handle_number = :number"
            params = {"norm": norm, "number": int(digits)}
        else:
            where = " AND p.handle_norm LIKE :prefix"
            params = {"prefix": norm + "%"}
        rows = await self._list(me, where + " AND p.id != :me" + _NOT_BLOCKED, params)
        return rows[:SEARCH_LIMIT]

    async def suggested_people(self, me: int) -> list[PersonRow]:
        """People who share a chat with `me` (subscribed or seen writing there) and
        whom `me` does not follow yet, those sharing the most chats first."""
        cursor = await self._conn.execute(
            "WITH mine AS ("
            "  SELECT chat_id FROM subscriptions"
            "  WHERE tg_id = (SELECT tg_id FROM users WHERE id = :me)"
            "  UNION"
            "  SELECT chat_id FROM chat_seen"
            "  WHERE tg_id = (SELECT tg_id FROM users WHERE id = :me)"
            "), others AS ("
            "  SELECT tg_id, chat_id FROM subscriptions"
            "  UNION SELECT tg_id, chat_id FROM chat_seen"
            "), shared AS ("
            "  SELECT o.tg_id, COUNT(*) AS n FROM others o JOIN mine m ON m.chat_id = o.chat_id"
            "  GROUP BY o.tg_id"
            ") "
            "SELECT p.id, p.tg_id, " + _SHOWN + " AS shown, " + _RELATION + " "
            "FROM shared s JOIN users p ON p.tg_id = s.tg_id "
            "WHERE p.id != :me AND p.handle IS NOT NULL AND p.is_excluded = 0"
            "  AND NOT EXISTS (SELECT 1 FROM follows f"
            "    WHERE f.follower_id = :me AND f.followee_id = p.id)" + _NOT_BLOCKED + " "
            "ORDER BY s.n DESC, p.handle_norm LIMIT :limit",
            {"me": me, "limit": SEARCH_LIMIT},
        )
        return [_person(row) for row in await cursor.fetchall()]

    async def activity_visible(self, person: int) -> str:
        cursor = await self._conn.execute(
            "SELECT activity_visible FROM users WHERE id = ?", (person,)
        )
        row = await cursor.fetchone()
        return row["activity_visible"] if row else "nobody"

    async def set_activity_visible(self, person: int, value: str) -> None:
        if value not in ACTIVITY_CHOICES:
            raise ValueError(value)
        await self._conn.execute(
            "UPDATE users SET activity_visible = ? WHERE id = ?", (value, person)
        )
        await self._conn.commit()

    async def can_view_activity(self, viewer: int, target: int) -> bool:
        """The one answer to "may this person see that one's activity?"."""
        if viewer == target:
            return True
        return can_view(await self.activity_visible(target), await self.relation(viewer, target))
