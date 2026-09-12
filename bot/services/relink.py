"""Linking an account that somebody — possibly somebody else — already has
(#52, step 2).

Since achievements belong to the account rather than to the person holding
it, linking is no longer a harmless overwrite. Three things can happen at
once, and a person deserves to know which before it does:

- they swap their own account for a different one, and everything the first
  account earned stops counting for them;
- they link an account the bot already knows, and its whole history becomes
  theirs without a single request to the platform;
- they take an account somebody else currently holds, and that person loses
  it — silently, unless we tell them.

This module answers "what would happen" and then performs it. It knows
nothing about Telegram: handlers do the asking and the telling, which is
also why `perform` hands back who the account was taken from instead of
notifying anyone itself.
"""

from __future__ import annotations

from dataclasses import dataclass

from bot.constants import AccountPlatform
from bot.db.repo import PlatformLink, Repo


@dataclass(slots=True)
class LinkPreview:
    """What linking `external_id` would do to this person right now."""

    current: PlatformLink | None
    """The account they hold on this platform today, if any."""

    current_achievements: int
    """How many rows that account has — what they are about to stop seeing."""

    incoming_achievements: int
    """How many the new account already has stored — what they gain for free,
    and the signal that a full backfill is unnecessary."""

    taken_from: int | None
    """Who currently holds the incoming account, when it is not this person."""

    incoming_id: str
    """The account being linked."""

    @property
    def is_switch(self) -> bool:
        """True only for a genuine identity change of *this person's* own
        account. Relinking the same account — after a failure, or just
        running /connect_steam twice — is not a switch."""
        return self.current is not None and self.current.external_id != self.incoming_id

    @property
    def needs_confirmation(self) -> bool:
        """Ask before anything irreversible-looking happens: swapping one's
        own account, or taking one that somebody else holds (2026-09-12,
        user request — a takeover used to go through silently, with only
        the loser finding out afterwards).

        A plain first link, and a relink of the same account, both stay
        silent. Those are the common cases and a prompt there is noise.
        """
        return self.is_switch or self.taken_from is not None


async def preview(repo: Repo, tg_id: int, platform: str, external_id: str) -> LinkPreview:
    current = await repo.get_platform_link(tg_id, platform)
    owner = await repo.account_owner(platform, external_id)
    return LinkPreview(
        current=current,
        current_achievements=(
            await repo.account_achievement_count(platform, current.external_id) if current else 0
        ),
        incoming_achievements=await repo.account_achievement_count(platform, external_id),
        taken_from=owner if owner is not None and owner != tg_id else None,
        incoming_id=external_id,
    )


async def perform(
    repo: Repo, tg_id: int, platform: str, external_id: str, display_name: str | None
) -> int | None:
    """Link it, and return the tg_id it was taken from, if anyone.

    A taken-over Xbox account also loses the previous owner's refresh token:
    it authorises reading *that account*, which is no longer theirs, and
    leaving it would keep the bot polling an account on behalf of someone who
    does not hold it.
    """
    taken_from = await repo.link_platform_account(tg_id, platform, external_id, display_name)
    if taken_from is not None and platform == AccountPlatform.XBOX:
        await repo.delete_token(taken_from)
    return taken_from
