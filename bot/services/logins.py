"""The ways a person signs in, as the super-admin's user card lists them
(owner, 2026-10-07).

One list for both admin panels — the bot's `/admin` card and the Mini App's
admin card render it. A new way in (#162: Google, Discord, …) is one more
entry in `KINDS` and in `logins_of`, plus its `admin-logins-<kind>` string;
both cards show it, linked or not.
"""

from __future__ import annotations

from dataclasses import dataclass

from bot.db.repo import User

# In the order the cards list them.
KINDS = ("telegram", "email")


@dataclass(frozen=True, slots=True)
class Login:
    kind: str
    linked: bool
    # What identifies it, as the super-admin needs it for a lookup — a
    # Telegram id is a string here, never a number Fluent would group.
    username: str | None = None
    ident: str | None = None


def logins_of(user: User) -> list[Login]:
    """Every kind of login, linked or not, in `KINDS` order."""
    found = {
        "telegram": Login(
            "telegram",
            user.tg_id is not None,
            username=user.username if user.tg_id is not None else None,
            ident=str(user.tg_id) if user.tg_id is not None else None,
        ),
        "email": Login("email", bool(user.email), ident=user.email or None),
    }
    return [found[kind] for kind in KINDS]
