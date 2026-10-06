"""Nicknames in the database (#157, migration 072): who holds which, who may
change theirs and when. The rules about what a nickname looks like are in
`services/handles.py`; this is the only place that writes the columns."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from bot.constants import Platform
from bot.services import handles
from bot.util import utcnow_iso


class HandleInvalid(ValueError):
    """Not Latin letters and digits, or not 3-20 of them."""


class HandleTooSoon(Exception):
    """Changed too recently (`CHANGE_COOLDOWN_DAYS`). `available_at` is when it may change again."""

    def __init__(self, available_at: str) -> None:
        super().__init__(available_at)
        self.available_at = available_at


@dataclass(frozen=True, slots=True)
class HandleState:
    handle: handles.Handle | None
    confirmed: bool
    changed_at: str | None


class _HandlesRepo:
    async def handle_state(self, person_id: int) -> HandleState | None:
        cursor = await self._conn.execute(
            "SELECT handle, handle_number, handle_confirmed_at, handle_changed_at "
            "FROM users WHERE id = ?",
            (person_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        handle = handles.Handle(row["handle"], row["handle_number"]) if row["handle"] else None
        return HandleState(handle, bool(row["handle_confirmed_at"]), row["handle_changed_at"])

    async def _numbers_taken(self, norm: str) -> set[int]:
        cursor = await self._conn.execute(
            "SELECT handle_number FROM users WHERE handle_norm = ?", (norm,)
        )
        return {row[0] for row in await cursor.fetchall()}

    async def _store_handle(
        self, person_id: int, name: str, number: int, *, confirmed: bool, changed: bool
    ) -> bool:
        """Write a nickname; False if the unique index says somebody just took it.
        In a transaction of its own (#167): the bare `rollback()` this used to
        call threw away every other coroutine's uncommitted writes as well."""
        now = utcnow_iso()
        try:
            async with self.transaction():
                await self._conn.execute(
                    "UPDATE users SET handle = ?, handle_norm = ?, handle_number = ?, "
                    "  handle_confirmed_at = CASE WHEN ? THEN COALESCE(handle_confirmed_at, ?) "
                    "                             ELSE handle_confirmed_at END, "
                    "  handle_changed_at = CASE WHEN ? THEN ? ELSE handle_changed_at END "
                    "WHERE id = ?",
                    (
                        name,
                        handles.normalize(name),
                        number,
                        confirmed,
                        now,
                        changed,
                        now,
                        person_id,
                    ),
                )
        except sqlite3.IntegrityError:
            return False
        return True

    async def _claim(
        self, person_id: int, name: str, *, confirmed: bool, changed: bool
    ) -> handles.Handle:
        """Take `name`: bare when free, otherwise with four digits nobody else has."""
        norm = handles.normalize(name)
        for _ in range(5):
            taken = await self._numbers_taken(norm)
            candidates = [0] if 0 not in taken else handles.random_numbers(taken)
            for number in candidates:
                if await self._store_handle(
                    person_id, name, number, confirmed=confirmed, changed=changed
                ):
                    return handles.Handle(name, number)
        raise RuntimeError("could not find a free nickname number")

    async def assign_first_handle(
        self, person_id: int, *candidates: str | None
    ) -> handles.Handle | None:
        """Give somebody who has no nickname one made from their names. Not
        confirmed: the Mini App still asks them to keep or change it."""
        state = await self.handle_state(person_id)
        if state is None or state.handle is not None:
            return state.handle if state else None
        return await self._claim(
            person_id, handles.from_text(*candidates), confirmed=False, changed=False
        )

    async def change_handle(self, person_id: int, wanted: str) -> handles.Handle:
        """The person's own choice. The first one (nickname still unconfirmed) is
        free; later ones once per `CHANGE_COOLDOWN_DAYS`. Only the letters' case changing is
        always allowed and keeps the digits."""
        wanted = wanted.strip()
        if not handles.is_valid(wanted):
            raise HandleInvalid(wanted)
        state = await self.handle_state(person_id)
        if state is None:
            raise HandleInvalid(wanted)
        current = state.handle
        if current and handles.normalize(current.name) == handles.normalize(wanted):
            await self._store_handle(
                person_id, wanted, current.number, confirmed=True, changed=False
            )
            return handles.Handle(wanted, current.number)
        if state.confirmed and state.changed_at:
            available = datetime.fromisoformat(state.changed_at) + timedelta(
                days=handles.CHANGE_COOLDOWN_DAYS
            )
            if available > datetime.fromisoformat(utcnow_iso()):
                raise HandleTooSoon(available.isoformat(timespec="seconds"))
        return await self._claim(person_id, wanted, confirmed=True, changed=state.confirmed)

    async def confirm_handle(self, person_id: int) -> None:
        """'Keep it' on the first-visit screen."""
        await self._conn.execute(
            "UPDATE users SET handle_confirmed_at = COALESCE(handle_confirmed_at, ?) "
            "WHERE id = ? AND handle IS NOT NULL",
            (utcnow_iso(), person_id),
        )
        await self._conn.commit()

    async def give_handle(self, person_id: int) -> handles.Handle | None:
        """A first nickname from whatever names this person has: their Telegram
        username, then a platform nickname, then what comes before the @ of
        their email (#162), at last `Player`. Nothing if they already have one."""
        user = await self.get_user(person_id)
        links = [
            link
            for platform in (Platform.PSN, Platform.STEAM)
            for link in await self.platform_links_for(person_id, platform)
        ]
        return await self.assign_first_handle(
            person_id,
            user.username if user else None,
            user.gamertag_modern if user else None,
            user.gamertag if user else None,
            *(link.display_name for link in links),
            user.email.split("@", 1)[0] if user and user.email else None,
        )

    async def give_everyone_a_handle(self) -> int:
        """Start-up: a first nickname for each person who has none. Returns how
        many were given."""
        cursor = await self._conn.execute("SELECT id FROM users WHERE handle IS NULL ORDER BY id")
        ids = [row[0] for row in await cursor.fetchall()]
        for person in ids:
            await self.give_handle(person)
        return len(ids)

    # A picture the person chose (#157, migration 077) lives beside the nickname:
    # both are how the person is shown.
    async def custom_avatar_path(self, person_id: int) -> str | None:
        cursor = await self._conn.execute(
            "SELECT custom_avatar_path FROM users WHERE id = ?", (person_id,)
        )
        row = await cursor.fetchone()
        return row["custom_avatar_path"] if row else None

    async def set_custom_avatar_path(self, person_id: int, path: str | None) -> None:
        await self._conn.execute(
            "UPDATE users SET custom_avatar_path = ? WHERE id = ?", (path, person_id)
        )
        await self._conn.commit()
