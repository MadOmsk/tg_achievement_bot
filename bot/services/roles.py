"""Who may do what (owner, 2026-10-29; #232): four roles, one table.

- **user** — everybody: their own things, the feed, the games, the pass,
  invites, the group commands, `/promo`.
- **chat admin** — one per group chat, by Telegram id (they may never have
  used the app): that chat's settings, its messages, its promo, and handing
  the role on to another member. Whoever adds the bot to a group is it;
  removing the bot clears it (`repo.set_chat_admin`).
- **app admin** (`users.role = 'admin'`) — every chat, the people (but not
  deleting them or resetting an account), the season pass's editor, the
  global settings; appoints chat admins.
- **super-admin** (`users.role = 'superadmin'`, and always whoever
  `SUPERADMIN_TG_IDS` names: written into the column on every start, never
  taken down from the app) — everything: the keys, deleting a person,
  resetting an account, giving the roles.

What each action, setting and screen needs is one of `Need`; `Access.allows`
is the one answer, for both admin panels.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from bot.config import Settings
    from bot.db.repo import Repo

SUPERADMIN = "superadmin"
ADMIN = "admin"
USER = "user"
ROLES = (USER, ADMIN, SUPERADMIN)

# What something needs: a chat admin of *its* chat (or anybody above), an
# app admin, or a super-admin.
Need = Literal["chat", "admin", "superadmin"]


def stored(role: str | None) -> str:
    """The role as the app speaks of it: NULL and anything unknown is `user`."""
    return role if role in (ADMIN, SUPERADMIN) else USER


def runs_the_app(role: str | None) -> bool:
    """An app admin or a super-admin."""
    return stored(role) in (ADMIN, SUPERADMIN)


def gives_roles(role: str | None) -> bool:
    return stored(role) == SUPERADMIN


# The mark beside a name in the admins' lists of people.
BADGES = {SUPERADMIN: "👑", ADMIN: "⭐"}


def badge(role: str | None) -> str:
    return BADGES.get(stored(role), "")


@dataclass(frozen=True, slots=True)
class Access:
    """One person's rights: their app role and the chats they admin."""

    role: str = USER
    chats: frozenset[int] = frozenset()

    @property
    def app(self) -> bool:
        return runs_the_app(self.role)

    @property
    def superadmin(self) -> bool:
        return self.role == SUPERADMIN

    @property
    def any(self) -> bool:
        """Anything to administer at all: the admin panel opens."""
        return self.app or bool(self.chats)

    def chat(self, chat_id: int | None) -> bool:
        return self.app or (chat_id is not None and chat_id in self.chats)

    def allows(self, need: Need, chat_id: int | None = None) -> bool:
        if need == "superadmin":
            return self.superadmin
        if need == "admin":
            return self.app
        return self.chat(chat_id)


FULL = Access(role=SUPERADMIN)


async def access_of(repo: Repo, settings: Settings, tg_id: int | None) -> Access:
    """A Telegram account's rights. A person known only by email has a role
    but admins no chat (a chat admin is a Telegram id)."""
    if tg_id is None:
        return Access()
    person = await repo.person_id(tg_id)
    role = await repo.person_role(person) if person is not None else None
    if settings.is_superadmin(tg_id):
        role = SUPERADMIN
    return Access(role=stored(role), chats=frozenset(await repo.chats_admined_by(tg_id)))


async def access_of_person(
    repo: Repo, settings: Settings, person_id: int, tg_id: int | None
) -> Access:
    """`access_of` for the Mini App, which knows the person first."""
    role = await repo.person_role(person_id)
    if settings.is_superadmin(tg_id):
        role = SUPERADMIN
    chats = frozenset(await repo.chats_admined_by(tg_id)) if tg_id is not None else frozenset()
    return Access(role=stored(role), chats=chats)
