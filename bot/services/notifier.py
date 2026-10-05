"""The app's own notifications (#164; owner, 2026-10-04): what a person is told
about goes to one place, `Notifier.notify`, which

1. keeps it in the person's list (the Mini App's bell), always;
2. pushes it to every browser that allowed push, if the person keeps push on
   (`user_settings.notify_push`, on by default — push is the app's own channel);
3. sends it as a Telegram DM, if the person keeps that on
   (`user_settings.notify_telegram`) and has Telegram at all.

`notify(recipient, kind, **data)`: `data` is what the line is made from, and
may name another person (`person_id`) — the one a tap opens.

Each kind is worded once, in `notifications.ftl`, in the person's own language.
Nothing here imports aiogram: the DM is a function handed in (`send_dm`), so
the service stays out of Telegram's way, as services do. Failures of one
channel never stop the others, nor whatever triggered the notification.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from urllib.parse import urlencode

import httpx

from bot.db.repo import Repo
from bot.i18n import gettext
from bot.services import webpush
from bot.services.crypto import TokenCipher
from bot.services.webpush import VapidKeys
from bot.util import thousands, utcnow

log = logging.getLogger(__name__)

VAPID_KEY_SETTING = "vapid_private_key"

# Whose new posts a person is told about (`user_settings.notify_posts`).
POST_NOTICE_CHOICES = ("friends", "following", "none")
# One game's evening is one post: a person hears of it once in this long,
# however many polls bring its achievements in.
POST_NOTICE_INTERVAL = timedelta(hours=3)


@dataclass(frozen=True, slots=True)
class Kind:
    """What a notification is about, and how it travels."""

    # The Fluent key for the line.
    key: str
    # The person a tap opens (a key of `data`), if the notice is about somebody.
    person_field: str | None = None
    # Whether it also goes as a Telegram DM. Off where the bot already sends a
    # better one of its own (the dead Xbox login's reminder, with its button).
    telegram: bool = True
    # Whether a tap opens the game the notice is about (`platform`, `title_id`
    # in `data`), on that person's progress.
    game: bool = False


KINDS: dict[str, Kind] = {
    "new_follower": Kind("notification-new-follower", "person_id"),
    "new_friend": Kind("notification-new-friend", "person_id"),
    # Somebody followed earned something new (owner, 2026-10-05).
    "new_post": Kind("notification-new-post", "person_id", game=True),
    # The person's Xbox login stopped working (#164): in the list and as a push;
    # the DM is poller/reminders.py's, which carries the relogin button.
    "xbox_login_dead": Kind("notification-xbox-login-dead", telegram=False),
}
UNKNOWN = Kind("notification-unknown")

SendDm = Callable[[int, str], Awaitable[None]]


def wording(kind: str, data: dict[str, Any], locale: str) -> str:
    return gettext(
        "notifications",
        KINDS.get(kind, UNKNOWN).key,
        locale=locale,
        # A count stays a number: Fluent picks a plural form only from a number.
        **{
            k: v if isinstance(v, int) and not isinstance(v, bool) else str(v)
            for k, v in data.items()
        },
    )


class Notifier:
    def __init__(
        self,
        repo: Repo,
        cipher: TokenCipher,
        *,
        send_dm: SendDm | None = None,
        app_url: str | None = None,
        contact: str | None = None,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self._repo = repo
        self._cipher = cipher
        self._send_dm = send_dm
        self._app_url = (app_url or "").strip()
        # Push services want to know whom to write to about this sender.
        self._contact = contact or (self._app_url if self._app_url.startswith("https://") else None)
        self._http = http
        self._keys: VapidKeys | None = None

    @property
    def push_available(self) -> bool:
        """Push needs somewhere for a tap to open, and a contact for the push services."""
        return bool(self._app_url and self._contact)

    async def vapid_keys(self) -> VapidKeys:
        """The server's push key pair, made once and kept encrypted in app_settings:
        a new one would orphan every browser that subscribed with the old."""
        if self._keys is not None:
            return self._keys
        stored = await self._repo.get_app_setting(VAPID_KEY_SETTING)
        if stored:
            self._keys = VapidKeys.from_pem(self._cipher.decrypt(stored.encode()).encode())
        else:
            self._keys = VapidKeys.generate()
            await self._repo.set_app_setting(
                VAPID_KEY_SETTING, self._cipher.encrypt(self._keys.to_pem().decode()).decode()
            )
        return self._keys

    async def notify(self, recipient: int, kind: str, **data: Any) -> None:
        await self._repo.add_notification(recipient, kind, data)
        settings = await self._repo.get_user_settings(recipient)
        locale = settings.locale if settings else "ru"
        text = wording(kind, data, locale)
        if settings is None or settings.notify_push:
            await self._push(recipient, kind, data, text)
        if KINDS.get(kind, UNKNOWN).telegram and (settings is None or settings.notify_telegram):
            await self._telegram(recipient, text)

    async def tell_about_post(
        self, author: int, platform: str, title_id: str, game: str, count: int
    ) -> None:
        """Tell the people following `author` about new achievements in one game,
        each by their own choice (friends, everybody followed, nobody) and only
        if they may see the author's activity. One recipient failing never stops
        the rest."""
        recipients = await self._repo.post_notice_recipients(author)
        if not recipients:
            return
        person = await self._repo.person_row(author)
        if person is None:
            return
        since = (utcnow() - POST_NOTICE_INTERVAL).isoformat(timespec="seconds")
        for recipient in recipients:
            try:
                if not await self._repo.can_view_activity(recipient, author):
                    continue
                if await self._repo.post_noticed_since(
                    recipient, author, platform, title_id, since
                ):
                    continue
                await self.notify(
                    recipient,
                    "new_post",
                    person_id=author,
                    name=person.handle,
                    platform=platform,
                    title_id=title_id,
                    game=game,
                    count=count,
                    pretty=thousands(count),
                    trophies="yes" if platform == "psn" else "no",
                )
            except Exception:
                log.exception("post notice to person_id=%s failed", recipient)

    async def _push(self, person_id: int, kind: str, data: dict[str, Any], text: str) -> None:
        if not self.push_available:
            return
        subscriptions = await self._repo.push_subscriptions_of(person_id)
        if not subscriptions:
            return
        keys = await self.vapid_keys()
        payload = {
            "title": "Unlocked",
            "body": text,
            "url": self._url_for(kind, data),
            "tag": kind,
        }
        client = self._http or httpx.AsyncClient()
        try:
            for sub in subscriptions:
                try:
                    await webpush.send(
                        client,
                        keys,
                        self._contact or "",
                        endpoint=sub.endpoint,
                        p256dh=sub.p256dh,
                        auth=sub.auth,
                        payload=payload,
                    )
                except webpush.SubscriptionGone:
                    await self._repo.delete_push_subscription(sub.endpoint)
                except webpush.PushFailed as exc:
                    log.info("push to person_id=%s refused: %s", person_id, exc)
                    await self._repo.push_refused(sub.endpoint)
                else:
                    await self._repo.push_delivered(sub.endpoint)
        finally:
            if self._http is None:
                await client.aclose()

    async def _telegram(self, person_id: int, text: str) -> None:
        if self._send_dm is None:
            return
        tg_id = await self._repo.tg_id_of(person_id)
        if tg_id is None:
            return
        try:
            await self._send_dm(tg_id, text)
        except Exception as exc:
            # Blocked the bot, never started it: the other channels still hold.
            log.info("notification DM to person_id=%s not sent: %r", person_id, exc)

    def _url_for(self, kind: str, data: dict[str, Any]) -> str:
        """Where a tap opens: the game the notice is about, on that person's
        progress; else the person; else the app."""
        spec = KINDS.get(kind, UNKNOWN)
        query: dict[str, str] = {}
        if spec.person_field and data.get(spec.person_field) is not None:
            query["p"] = str(data[spec.person_field])
        if spec.game and data.get("platform") and data.get("title_id"):
            query["g"] = f"{data['platform']}:{data['title_id']}"
        if not query:
            return self._app_url
        separator = "&" if "?" in self._app_url else "?"
        return f"{self._app_url}{separator}{urlencode(query)}"
