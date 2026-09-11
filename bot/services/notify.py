"""Notifications to the operator (SPEC 6.5).

Only events the admin can act on: someone joined, someone left, someone's login
died. Not a log — a log is in logs/bot.log, and a chat that reports every tick
gets muted, taking the useful messages with it.

Every notification is built once per recipient, in that admin's own language
(#48): there can be more than one admin, and they need not share a locale, so
the text cannot be composed before `_send` knows who it is going to.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence

from aiogram import Bot

from bot.constants import Platform
from bot.db.repo import Repo
from bot.i18n import translator

log = logging.getLogger(__name__)


class AdminNotifier:
    def __init__(self, bot: Bot, repo: Repo, admin_ids: Sequence[int]) -> None:
        self._bot = bot
        self._repo = repo
        self._admin_ids = list(admin_ids)

    async def user_connected(self, tg_id: int, gamertag: str, *, is_new: bool) -> None:
        async def build(locale: str) -> str:
            _ = translator("notify", locale)
            verb = _("notify-verb-new") if is_new else _("notify-verb-reconnect")
            who = await self._who(tg_id, locale)
            return f"{_('notify-user-connected', verb=verb, gamertag=gamertag)}\n{who}"

        await self._send(build)

    async def user_disconnected(self, tg_id: int, gamertag: str, reason: str) -> None:
        async def build(locale: str) -> str:
            _ = translator("notify", locale)
            reason_text = _(
                {
                    "disconnect-command": "notify-reason-command",
                    "disconnect-button": "notify-reason-button",
                }.get(reason, reason)
            )
            who = await self._who(tg_id, locale)
            return f"{_('notify-user-disconnected', gamertag=gamertag, reason=reason_text)}\n{who}"

        await self._send(build)

    async def token_dead(self, tg_id: int) -> None:
        async def build(locale: str) -> str:
            _ = translator("notify", locale)
            user = await self._repo.get_user(tg_id)
            name = (user.gamertag if user else None) or _("notify-id", tg_id=tg_id)
            who = await self._who(tg_id, locale)
            return (
                f"{_('notify-token-dead-line1', name=name)}\n{who}\n{_('notify-token-dead-line2')}"
            )

        await self._send(build)

    async def service_key_dead(self, platform: str) -> None:
        """A shared service credential died — Steam's API key or PSN's NPSSO
        (poller/service_health.py). Unlike token_dead above, this is not
        about one person: every account on that platform stops being
        polled/resolvable at once until the admin fixes it (SPEC 9,
        M-PSN-1's "мониторинг живости" paragraph)."""

        async def build(locale: str) -> str:
            _ = translator("notify", locale)
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
            return _("notify-service-key-dead", label=label, fix=fix)

        await self._send(build)

    async def translation_key_dead(self) -> None:
        """The Anthropic key died (2026-09-09) — a much milder event than
        service_key_dead above: nothing stops working, achievement
        descriptions just stop picking up a translation for whichever
        language the platform itself didn't already provide, silently,
        until the admin sends a new key. Worth its own wording rather than
        stretching service_key_dead's "accounts stopped being polled"
        framing over a service that was never polling accounts at all."""

        async def build(locale: str) -> str:
            return translator("notify", locale)("notify-translation-key-dead")

        await self._send(build)

    async def _who(self, tg_id: int, locale: str) -> str:
        _ = translator("notify", locale)
        user = await self._repo.get_user(tg_id)
        username = f"@{user.username}" if user and user.username else _("notify-who-no-username")
        return _("notify-who", tg_id=tg_id, username=username)

    async def _send(self, build: Callable[[str], Awaitable[str]]) -> None:
        for admin_id in self._admin_ids:
            try:
                text = await build(await self._repo.user_locale(admin_id))
                await self._bot.send_message(admin_id, text)
            except Exception:
                # An admin who blocked the bot must not break the flow that
                # triggered the notification.
                log.info("could not notify admin %s", admin_id)
