"""Notifications to the operator (SPEC 6.5).

Only events the admin can act on: someone joined, someone left, someone's login
died. Not a log — a log is in logs/bot.log, and a chat that reports every tick
gets muted, taking the useful messages with it.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from aiogram import Bot

from bot.constants import Platform
from bot.db.repo import Repo
from bot.i18n import gettext

log = logging.getLogger(__name__)

_ = lambda key, **kwargs: gettext("notify", key, **kwargs)  # noqa: E731


class AdminNotifier:
    def __init__(self, bot: Bot, repo: Repo, admin_ids: Sequence[int]) -> None:
        self._bot = bot
        self._repo = repo
        self._admin_ids = list(admin_ids)

    async def user_connected(self, tg_id: int, gamertag: str, *, is_new: bool) -> None:
        verb = _("notify-verb-new") if is_new else _("notify-verb-reconnect")
        await self._send(
            f"{_('notify-user-connected', verb=verb, gamertag=gamertag)}\n{await self._who(tg_id)}"
        )

    async def user_disconnected(self, tg_id: int, gamertag: str, reason: str) -> None:
        reason = _(
            {
                "disconnect-command": "notify-reason-command",
                "disconnect-button": "notify-reason-button",
            }.get(reason, reason)
        )
        await self._send(
            f"{_('notify-user-disconnected', gamertag=gamertag, reason=reason)}\n"
            f"{await self._who(tg_id)}"
        )

    async def token_dead(self, tg_id: int) -> None:
        user = await self._repo.get_user(tg_id)
        name = (user.gamertag if user else None) or _("notify-id", tg_id=tg_id)
        await self._send(
            f"{_('notify-token-dead-line1', name=name)}\n{await self._who(tg_id)}\n"
            f"{_('notify-token-dead-line2')}"
        )

    async def service_key_dead(self, platform: str) -> None:
        """A shared service credential died — Steam's API key or PSN's NPSSO
        (poller/service_health.py). Unlike token_dead above, this is not
        about one person: every account on that platform stops being
        polled/resolvable at once until the admin fixes it (SPEC 9,
        M-PSN-1's "мониторинг живости" paragraph)."""
        label = _(
            {
                Platform.STEAM: "notify-platform-steam",
                Platform.PSN: "notify-platform-psn",
            }.get(platform, "notify-platform-unknown"),
            platform=platform,
        )
        # Both shared credentials are admin-panel-managed now (#17 moved
        # Steam's own key off .env alongside PSN's NPSSO) — one fix message
        # covers both. notify-service-key-dead-fix-steam used to say
        # ".env + restart" from before #17, left stale until noticed fixing
        # this alongside the Anthropic key below.
        fix = _("notify-service-key-dead-fix-panel")
        await self._send(_("notify-service-key-dead", label=label, fix=fix))

    async def translation_key_dead(self) -> None:
        """The Anthropic key died (2026-09-09) — a much milder event than
        service_key_dead above: nothing stops working, achievement
        descriptions just stop picking up a translation for whichever
        language the platform itself didn't already provide, silently,
        until the admin sends a new key. Worth its own wording rather than
        stretching service_key_dead's "accounts stopped being polled"
        framing over a service that was never polling accounts at all."""
        await self._send(_("notify-translation-key-dead"))

    async def _who(self, tg_id: int) -> str:
        user = await self._repo.get_user(tg_id)
        username = f"@{user.username}" if user and user.username else _("notify-who-no-username")
        return _("notify-who", tg_id=tg_id, username=username)

    async def _send(self, text: str) -> None:
        for admin_id in self._admin_ids:
            try:
                await self._bot.send_message(admin_id, text)
            except Exception:
                # An admin who blocked the bot must not break the flow that
                # triggered the notification.
                log.info("could not notify admin %s", admin_id)
