"""Invites (owner, 2026-10-05): for now somebody new gets in through a browser —
by email, or by Telegram's Login Widget — only with a code a member made in
Settings. Inside Telegram (the bot, the Mini App there) nobody needs one: those
people come from the community's own chats. A code lets one person in, does not
expire, and every member may make as many as they like.

A code is `XXXX-XXXX-XXXX-XXXX` from an alphabet without the look-alikes (no
0/O, 1/I/L): 16 of 31 symbols, about 79 bits — not guessable, easy to read out.

A sign-in that proved its email or Telegram but has no code yet waits here, in
memory, for `PENDING_SECONDS`: the person types the code next, and nobody proves
the address twice.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from typing import Any

ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
GROUPS = 4
GROUP_SIZE = 4
PENDING_SECONDS = 15 * 60


def new_code() -> str:
    chars = "".join(secrets.choice(ALPHABET) for _ in range(GROUPS * GROUP_SIZE))
    return "-".join(chars[i : i + GROUP_SIZE] for i in range(0, len(chars), GROUP_SIZE))


def normalize(raw: object) -> str | None:
    """A typed or pasted code in its stored form, or None if it cannot be one:
    any case, any spaces or dashes."""
    if not isinstance(raw, str):
        return None
    chars = "".join(ch for ch in raw.upper() if ch.isalnum())
    if len(chars) != GROUPS * GROUP_SIZE or any(ch not in ALPHABET for ch in chars):
        return None
    return "-".join(chars[i : i + GROUP_SIZE] for i in range(0, len(chars), GROUP_SIZE))


@dataclass
class PendingSignups:
    """Proved sign-ins waiting for a code: token → what was proved."""

    ttl: float = PENDING_SECONDS
    _items: dict[str, tuple[float, dict[str, Any]]] = field(default_factory=dict)

    def put(self, proof: dict[str, Any]) -> str:
        self._sweep()
        token = secrets.token_urlsafe(24)
        self._items[token] = (time.monotonic() + self.ttl, proof)
        return token

    def get(self, token: object) -> dict[str, Any] | None:
        self._sweep()
        item = self._items.get(token) if isinstance(token, str) else None
        return item[1] if item else None

    def drop(self, token: str) -> None:
        self._items.pop(token, None)

    def _sweep(self) -> None:
        now = time.monotonic()
        for token in [t for t, (until, _) in self._items.items() if until <= now]:
            del self._items[token]
