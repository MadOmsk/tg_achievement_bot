"""Merging two people (#156, #162; owner, 2026-10-05): the same human signed up
twice — once by email, once by Telegram — and asks for the two to be one.

When a merge comes up: a signed-in person adds a login that already belongs to
somebody else, and proves it — an email by its code, Telegram by the Login
Widget's signature or by writing to the bot from that account. Instead of
"taken", the app is offered the merge (`offer`), shown what each side has
(`preview`), and asked to choose where both have something.

The rules:
- The person signed in now stays (`keep`), with their nickname; the other one
  is folded in and deleted (`absorb`).
- One side empty: take the other's. Both have one (two Xbox accounts, two
  Steam ids, two Telegram accounts, two addresses): the person picks; the
  account not picked is unlinked as any unlink is — its history kept. PSN
  accounts add up to `MAX_PSN_ACCOUNTS`, and past that the person picks which.
- Chats, follows and blocks, sessions, notifications and push devices move;
  settings come from the side used more recently.
- A super-admin's Telegram is never the one let go (`ADMIN_TG_IDS` names them).
- Somebody the bot made a moment ago — a Telegram account's first message —
  has nothing to lose and is folded in at once (`MergeSide.is_empty`).

Offers live in memory, ten minutes: proof is fresh or it is asked again.
"""

from __future__ import annotations

import logging
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from bot.constants import MAX_PSN_ACCOUNTS
from bot.db.repo import MergeChoices, MergeSide, Repo

log = logging.getLogger(__name__)

OFFER_TTL_SECONDS = 600
LINK_TTL_SECONDS = 600
SIDES = ("keep", "absorb")


class MergeRefused(Exception):
    """The choices are not allowed (`admin`) or do not fit (`choices`), or there
    is nothing to merge any more (`gone`)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(slots=True)
class _Offer:
    absorb: int
    created: float


class PeopleMerge:
    def __init__(
        self,
        repo: Repo,
        is_admin: Callable[[int | None], bool],
        *,
        on_merged: Callable[[int, int], Awaitable[None]] | None = None,
        forget_picture: Callable[[str], None] | None = None,
    ) -> None:
        self._repo = repo
        self._is_admin = is_admin
        self._on_merged = on_merged
        self._forget_picture = forget_picture
        self._offers: dict[int, _Offer] = {}
        self._link_tokens: dict[str, tuple[int, float]] = {}
        # A link opened from a Telegram account that already is somebody: that
        # somebody says yes in the bot before any merge is offered.
        self._confirmations: dict[int, tuple[int, int, float]] = {}

    # ------------------------------------------------------------- offers

    def offer(self, keep: int, absorb: int) -> None:
        """`keep` proved they also are `absorb`; the merge waits for their word."""
        self._offers[keep] = _Offer(absorb, time.monotonic())

    def pending(self, keep: int) -> int | None:
        offer = self._offers.get(keep)
        if offer is None or time.monotonic() - offer.created > OFFER_TTL_SECONDS:
            self._offers.pop(keep, None)
            return None
        return offer.absorb

    def drop(self, keep: int) -> None:
        self._offers.pop(keep, None)

    # ------------------------------------------- linking Telegram by a link

    def link_token(self, person: int) -> str:
        """A one-time token for `t.me/<bot>?start=link_<token>`: whoever opens
        the bot with it from Telegram is adding that Telegram to `person`."""
        now = time.monotonic()
        self._link_tokens = {
            t: v for t, v in self._link_tokens.items() if now - v[1] <= LINK_TTL_SECONDS
        }
        token = secrets.token_urlsafe(16)
        self._link_tokens[token] = (person, now)
        return token

    def redeem(self, token: str) -> int | None:
        entry = self._link_tokens.pop(token, None)
        if entry is None or time.monotonic() - entry[1] > LINK_TTL_SECONDS:
            return None
        return entry[0]

    def ask_to_confirm(self, tg_id: int, keep: int, absorb: int) -> None:
        """`absorb` opened `keep`'s link from their Telegram. Opening a link is
        not consent — anybody can be sent one — so the merge is offered to
        `keep` only once `absorb` says yes in the bot (`confirmed`)."""
        self._confirmations[tg_id] = (keep, absorb, time.monotonic())

    def confirmed(self, tg_id: int) -> tuple[int, int] | None:
        """The (keep, absorb) this Telegram account was asked about, once."""
        entry = self._confirmations.pop(tg_id, None)
        if entry is None or time.monotonic() - entry[2] > OFFER_TTL_SECONDS:
            return None
        return entry[0], entry[1]

    # ------------------------------------------------------------ preview

    async def preview(self, keep: int, absorb: int) -> dict[str, Any] | None:
        """What each side brings and where the person must choose; None when one
        of them is gone."""
        k = await self._repo.merge_side(keep)
        b = await self._repo.merge_side(absorb)
        if k is None or b is None:
            return None
        conflicts: dict[str, Any] = {}
        for platform in ("xbox", "steam"):
            mine, theirs = k.accounts.get(platform, []), b.accounts.get(platform, [])
            if mine and theirs and mine[0][0] != theirs[0][0]:
                conflicts[platform] = {"keep": _named(mine[0]), "absorb": _named(theirs[0])}
        psn = k.accounts.get("psn", []) + b.accounts.get("psn", [])
        if len(psn) > MAX_PSN_ACCOUNTS:
            conflicts["psn"] = {
                "accounts": [_named(item) for item in psn],
                "max": MAX_PSN_ACCOUNTS,
            }
        if k.tg_id is not None and b.tg_id is not None:
            conflicts["telegram"] = {
                "keep": {"name": k.username, "admin": self._is_admin(k.tg_id)},
                "absorb": {"name": b.username, "admin": self._is_admin(b.tg_id)},
            }
        if k.email and b.email and k.email != b.email:
            conflicts["email"] = {"keep": k.email, "absorb": b.email}
        return {
            "keep": _side_json(k),
            "absorb": _side_json(b),
            "conflicts": conflicts,
        }

    # ------------------------------------------------------------ merging

    async def merge(self, keep: int, absorb: int, raw: dict[str, Any] | None = None) -> None:
        """Fold `absorb` into `keep` with the person's choices (`raw`, as the app
        sends them). Raises MergeRefused."""
        preview = await self.preview(keep, absorb)
        if preview is None:
            raise MergeRefused("gone")
        choices = _choices(preview["conflicts"], raw or {})
        k = await self._repo.merge_side(keep)
        b = await self._repo.merge_side(absorb)
        assert k is not None and b is not None
        # A super-admin is named by Telegram id: theirs is never the one let go.
        dropped = None
        if k.tg_id is not None and b.tg_id is not None:
            dropped = b.tg_id if choices.telegram == "keep" else k.tg_id
        if self._is_admin(dropped):
            raise MergeRefused("admin")
        gone = await self._repo.merge_people(keep, absorb, choices)
        self.drop(keep)
        for path in gone:
            if self._forget_picture is not None:
                self._forget_picture(path)
        if self._on_merged is not None:
            try:
                await self._on_merged(keep, absorb)
            except Exception:
                log.exception("after-merge cleanup failed for person_id=%s", keep)
        log.info("person_id=%s was merged into person_id=%s", absorb, keep)

    async def absorb_if_empty(self, keep: int, absorb: int) -> bool:
        """Fold in at once a person with nothing to lose (a Telegram account's
        first message made them); False when there is something to ask about."""
        side = await self._repo.merge_side(absorb)
        if side is None or not side.is_empty:
            return False
        await self.merge(keep, absorb)
        return True


def _named(item: tuple[str, str | None]) -> dict[str, str | None]:
    return {"id": item[0], "name": item[1]}


def _side_json(side: MergeSide) -> dict[str, Any]:
    return {
        "person_id": side.person_id,
        "handle": side.handle,
        "email": side.email,
        "telegram": side.username if side.tg_id is not None else None,
        "has_telegram": side.tg_id is not None,
        "accounts": {
            platform: [_named(item) for item in items] for platform, items in side.accounts.items()
        },
        "follows": side.follows,
        "chats": side.chats,
    }


def _choices(conflicts: dict[str, Any], raw: dict[str, Any]) -> MergeChoices:
    """The person's answers, checked against the conflicts: every conflict
    answered, nothing else invented."""
    choices = MergeChoices()
    for name in ("xbox", "steam", "telegram", "email"):
        if name in conflicts:
            value = raw.get(name)
            if value not in SIDES:
                raise MergeRefused("choices")
            setattr(choices, name, value)
    if "psn" in conflicts:
        offered = {item["id"] for item in conflicts["psn"]["accounts"]}
        wanted = raw.get("psn")
        if (
            not isinstance(wanted, list)
            or not wanted
            or len(wanted) > conflicts["psn"]["max"]
            or not set(map(str, wanted)) <= offered
        ):
            raise MergeRefused("choices")
        choices.psn = [str(item) for item in wanted]
    return choices
