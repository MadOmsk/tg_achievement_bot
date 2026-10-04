"""The app's own notifications (#164): the list, push and the Telegram DM, each
behind its own switch."""

from __future__ import annotations

import json

import httpx
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import ec

from bot.db.repo import Repo
from bot.services import webpush
from bot.services.crypto import TokenCipher
from bot.services.notifier import VAPID_KEY_SETTING, Notifier
from bot.web.mini_api import cors_middleware, setup_mini_api

APP_URL = "https://app.example.com/app/"


def _browser() -> dict[str, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    return {
        "p256dh": webpush.b64u(webpush._public_bytes(key.public_key())),
        "auth": webpush.b64u(b"0123456789abcdef"),
    }


class _PushService:
    """Stands in for the browsers' push services: answers by endpoint."""

    def __init__(self, gone: set[str] = frozenset()) -> None:
        self.gone = set(gone)
        self.got: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.got.append(str(request.url))
        return httpx.Response(410 if str(request.url) in self.gone else 201)


def _notifier(repo: Repo, service: _PushService, sent: list[tuple[int, str]]) -> Notifier:
    async def send_dm(tg_id: int, text: str) -> None:
        sent.append((tg_id, text))

    return Notifier(
        repo,
        TokenCipher(Fernet.generate_key().decode()),
        send_dm=send_dm,
        app_url=APP_URL,
        contact="mailto:bot@example.com",
        http=httpx.AsyncClient(transport=httpx.MockTransport(service)),
    )


async def test_a_notice_reaches_every_channel_that_is_on(repo: Repo) -> None:
    ada = await repo.ensure_user(1, "ada")
    bob = await repo.ensure_user(2, "bob")
    assert ada and bob
    await repo.save_push_subscription(ada, "https://push.example/a", **_browser(), user_agent=None)
    await repo.save_push_subscription(
        ada, "https://push.example/gone", **_browser(), user_agent=None
    )
    service, sent = _PushService(gone={"https://push.example/gone"}), []
    notifier = _notifier(repo, service, sent)

    await notifier.notify(ada, "new_follower", person_id=bob, name="bob")

    rows = await repo.notifications_of(ada)
    assert [(row.kind, row.data["name"]) for row in rows] == [("new_follower", "bob")]
    assert sorted(service.got) == ["https://push.example/a", "https://push.example/gone"]
    assert sent == [(1, "У тебя новый подписчик — bob")]
    # A browser that unsubscribed is forgotten; the other stays.
    assert [s.endpoint for s in await repo.push_subscriptions_of(ada)] == ["https://push.example/a"]


async def test_the_switches_are_the_persons_own(repo: Repo) -> None:
    ada = await repo.ensure_user(1, "ada")
    assert ada
    await repo.update_user_settings(ada, notify_push=0, notify_telegram=0, locale="en")
    await repo.save_push_subscription(ada, "https://push.example/a", **_browser(), user_agent=None)
    service, sent = _PushService(), []

    await _notifier(repo, service, sent).notify(ada, "new_friend", person_id=2, name="bob")

    # Only the list: no push, no DM.
    assert len(await repo.notifications_of(ada)) == 1
    assert service.got == [] and sent == []


async def test_somebody_without_telegram_gets_no_dm(repo: Repo) -> None:
    ada = await repo.create_email_person("ada@example.com")
    service, sent = _PushService(), []
    await _notifier(repo, service, sent).notify(ada, "new_follower", person_id=2, name="bob")
    assert sent == []
    assert await repo.unread_notifications(ada) == 1


async def test_the_push_key_is_made_once_and_kept_encrypted(repo: Repo) -> None:
    notifier = _notifier(repo, _PushService(), [])
    first = await notifier.vapid_keys()
    stored = await repo.get_app_setting(VAPID_KEY_SETTING)
    assert stored and "PRIVATE KEY" not in stored
    again = Notifier(repo, notifier._cipher, app_url=APP_URL, contact="mailto:a@b.co")
    assert (await again.vapid_keys()).public_b64 == first.public_b64


async def test_the_list_and_the_subscription_routes(repo: Repo, settings) -> None:
    ada = await repo.ensure_user(1, "ada")
    assert ada
    await repo.update_user_settings(ada, locale="en")
    sent: list[tuple[int, str]] = []
    notifier = _notifier(repo, _PushService(), sent)
    app = web.Application(middlewares=[cors_middleware()])
    setup_mini_api(app, settings, repo, notifications=notifier)
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        token = await repo.create_session(ada, "test")
        client.session.cookie_jar.update_cookies({"ab_session": token})

        key = await (await client.get("/api/mini/push/key")).json()
        assert key["available"] is True and key["public_key"]

        bad = await client.post("/api/mini/push/subscription", json={"endpoint": "http://x"})
        assert bad.status == 400
        sub = {"endpoint": "https://push.example/a", "keys": _browser()}
        assert (await client.post("/api/mini/push/subscription", json=sub)).status == 200
        assert len(await repo.push_subscriptions_of(ada)) == 1

        await notifier.notify(ada, "new_friend", person_id=2, name="bob")
        listing = await (await client.get("/api/mini/notifications")).json()
        assert listing["unread"] == 1
        [item] = listing["items"]
        assert (item["text"], item["person_id"], item["read"]) == (
            "You and bob are friends now",
            2,
            False,
        )
        me = await (await client.get("/api/mini/me")).json()
        assert me["notifications_unread"] == 1
        assert me["settings"]["notify_push"] is True

        await client.post("/api/mini/notifications/read")
        assert (await (await client.get("/api/mini/notifications")).json())["unread"] == 0

        patched = await client.patch("/api/mini/settings", json={"notify_telegram": False})
        assert (await patched.json())["settings"]["notify_telegram"] is False

        gone = await client.delete("/api/mini/push/subscription", data=json.dumps(sub))
        assert gone.status == 200
        assert await repo.push_subscriptions_of(ada) == []
    finally:
        await client.close()
