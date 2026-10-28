"""Who may run the app (owner, 2026-10-28): three roles, the person's
`users.role`. A super-admin does everything and gives the roles; an admin
does everything but give them; anybody else is an ordinary person. The
super-admins named in `SUPERADMIN_TG_IDS` always are one: they are written
into the column on every start and can't be taken down from the app."""

from __future__ import annotations

SUPERADMIN = "superadmin"
ADMIN = "admin"
USER = "user"
ROLES = (USER, ADMIN, SUPERADMIN)


def stored(role: str | None) -> str:
    """The role as the app speaks of it: NULL and anything unknown is `user`."""
    return role if role in (ADMIN, SUPERADMIN) else USER


def runs_the_app(role: str | None) -> bool:
    """The admin panels, the pass's editor: an admin or a super-admin."""
    return stored(role) in (ADMIN, SUPERADMIN)


def gives_roles(role: str | None) -> bool:
    return stored(role) == SUPERADMIN
