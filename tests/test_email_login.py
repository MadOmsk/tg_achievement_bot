"""Signing in by email and the logins a person keeps (#162)."""

from __future__ import annotations

import hashlib
import hmac
import re
import time
from datetime import timedelta

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from bot.db.repo import Repo
from bot.services import email_login
from bot.services.email import EmailSendError, SmtpSender, build_sender
from bot.services.email_login import (
    CodeExpired,
    CodeWrong,
    EmailInvalid,
    EmailLogin,
    EmailTooSoon,
    normalize_email,
)
from bot.util import utcnow
from bot.web.mini_api import cors_middleware, setup_mini_api


class FakeSender:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[tuple[str, str, str]] = []
        self.fail = fail

    async def send(self, to: str, subject: str, text: str) -> None:
        if self.fail:
            raise EmailSendError("down")
        self.sent.append((to, subject, text))

    def last_code(self) -> str:
        match = re.search(r"\b(\d{6})\b", self.sent[-1][2])
        assert match is not None
        return match.group(1)


def _widget(token: str, tg_id: int = 42) -> dict[str, str]:
    fields = {"id": str(tg_id), "first_name": "Test", "username": "tester"}
    fields["auth_date"] = str(int(time.time()) - 5)
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hashlib.sha256(token.encode()).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return fields


def _wrong(code: str) -> str:
    return f"{(int(code) + 1) % 10**6:06d}"


# ----------------------------------------------------------------- the rules


def test_an_address_is_lower_cased_and_checked_loosely() -> None:
    assert normalize_email("  Ada@Example.COM ") == "ada@example.com"
    for bad in ("", "ada", "ada@", "@example.com", "ada@example", "a b@example.com"):
        with pytest.raises(EmailInvalid):
            normalize_email(bad)


async def test_a_code_works_once_and_only_its_hash_is_kept(repo: Repo) -> None:
    sender = FakeSender()
    login = EmailLogin(repo, sender, b"secret")
    await login.send_code("Ada@Example.com", email_login.SIGN_IN, locale="en")
    assert sender.sent[0][0] == "ada@example.com"
    code = sender.last_code()

    stored = await repo.live_email_code("ada@example.com", email_login.SIGN_IN)
    assert stored is not None and code not in stored.code_hash

    assert await login.check_code("ada@example.com", code, email_login.SIGN_IN) == (
        "ada@example.com"
    )
    with pytest.raises(CodeExpired):
        await login.check_code("ada@example.com", code, email_login.SIGN_IN)


async def test_wrong_guesses_run_out(repo: Repo) -> None:
    sender = FakeSender()
    login = EmailLogin(repo, sender, b"secret")
    await login.send_code("ada@example.com", email_login.SIGN_IN, locale="ru")
    code = sender.last_code()
    for left in range(email_login.MAX_ATTEMPTS - 1, 0, -1):
        with pytest.raises(CodeWrong) as wrong:
            await login.check_code("ada@example.com", _wrong(code), email_login.SIGN_IN)
        assert wrong.value.attempts_left == left
    with pytest.raises(CodeExpired):
        await login.check_code("ada@example.com", _wrong(code), email_login.SIGN_IN)
    # Spent: even the right code is no good now.
    with pytest.raises(CodeExpired):
        await login.check_code("ada@example.com", code, email_login.SIGN_IN)


async def test_a_code_expires(repo: Repo) -> None:
    sender = FakeSender()
    login = EmailLogin(repo, sender, b"secret")
    await login.send_code("ada@example.com", email_login.SIGN_IN, locale="ru")
    await repo._conn.execute(
        "UPDATE email_codes SET expires_at = ?",
        ((utcnow() - timedelta(seconds=1)).isoformat(timespec="seconds"),),
    )
    with pytest.raises(CodeExpired):
        await login.check_code("ada@example.com", sender.last_code(), email_login.SIGN_IN)


async def test_codes_are_rationed_per_address(repo: Repo) -> None:
    sender = FakeSender()
    login = EmailLogin(repo, sender, b"secret")
    await login.send_code("ada@example.com", email_login.SIGN_IN, locale="ru")
    with pytest.raises(EmailTooSoon) as soon:
        await login.send_code("ada@example.com", email_login.SIGN_IN, locale="ru")
    assert 0 < soon.value.retry_after <= email_login.RESEND_SECONDS

    # Spread over the hour, the cap still holds.
    await repo._conn.execute("DELETE FROM email_codes")
    for minutes in range(email_login.MAX_CODES_PER_HOUR):
        await repo._conn.execute(
            "INSERT INTO email_codes (email, purpose, code_hash, created_at, expires_at)"
            " VALUES ('ada@example.com', 'sign_in', 'x', ?, ?)",
            ((utcnow() - timedelta(minutes=50 - minutes * 5)).isoformat(timespec="seconds"),) * 2,
        )
    with pytest.raises(EmailTooSoon):
        await login.send_code("ada@example.com", email_login.SIGN_IN, locale="ru")
    # Another address is not affected.
    await login.send_code("bob@example.com", email_login.SIGN_IN, locale="ru")


async def test_a_new_code_replaces_the_old_one(repo: Repo) -> None:
    sender = FakeSender()
    login = EmailLogin(repo, sender, b"secret")
    await login.send_code("ada@example.com", email_login.SIGN_IN, locale="ru")
    first = sender.last_code()
    await repo._conn.execute("UPDATE email_codes SET created_at = '2000-01-01T00:00:00'")
    await login.send_code("ada@example.com", email_login.SIGN_IN, locale="ru")
    second = sender.last_code()
    if first != second:
        with pytest.raises((CodeWrong, CodeExpired)):
            await login.check_code("ada@example.com", first, email_login.SIGN_IN)
    assert await login.check_code("ada@example.com", second, email_login.SIGN_IN)


async def test_a_link_code_belongs_to_the_person_who_asked(repo: Repo) -> None:
    sender = FakeSender()
    login = EmailLogin(repo, sender, b"secret")
    asker = await repo.ensure_user(1)
    other = await repo.ensure_user(2)
    await login.send_code("ada@example.com", email_login.LINK, locale="ru", person_id=asker)
    with pytest.raises(CodeExpired):
        await login.check_code(
            "ada@example.com", sender.last_code(), email_login.LINK, person_id=other
        )
    assert await login.check_code(
        "ada@example.com", sender.last_code(), email_login.LINK, person_id=asker
    )


def test_the_sender_follows_the_settings(settings) -> None:
    assert build_sender(settings) is None
    settings.email_log_codes = True
    assert build_sender(settings) is not None
    settings.smtp_host, settings.smtp_from = "mail.example.com", "bot@example.com"
    assert isinstance(build_sender(settings), SmtpSender)


# ----------------------------------------------------------------- the routes


async def _client(repo: Repo, settings, sender: FakeSender | None) -> TestClient:
    app = web.Application(middlewares=[cors_middleware()])
    login = EmailLogin(repo, sender, b"secret") if sender is not None else None
    setup_mini_api(app, settings, repo, email_login=login)
    client = TestClient(TestServer(app))
    await client.start_server()
    return client


async def _sign_in(client: TestClient, sender: FakeSender, email: str) -> None:
    start = await client.post("/api/mini/auth/email/start", json={"email": email, "locale": "en"})
    assert start.status == 200
    ok = await client.post(
        "/api/mini/auth/email/verify",
        json={"email": email, "code": sender.last_code(), "locale": "en"},
    )
    assert ok.status == 200


async def test_without_a_mail_server_email_is_not_offered(repo: Repo, settings) -> None:
    client = await _client(repo, settings, None)
    try:
        assert (await (await client.get("/api/mini/auth/config")).json())["email"] is False
        start = await client.post("/api/mini/auth/email/start", json={"email": "a@b.co"})
        assert (start.status, (await start.json())["error"]) == (503, "unavailable")
    finally:
        await client.close()


async def test_a_new_address_becomes_a_new_person_without_telegram(repo: Repo, settings) -> None:
    sender = FakeSender()
    client = await _client(repo, settings, sender)
    try:
        assert (await (await client.get("/api/mini/auth/config")).json())["email"] is True
        bad = await client.post("/api/mini/auth/email/start", json={"email": "nope"})
        assert (await bad.json())["error"] == "invalid"

        await _sign_in(client, sender, "Ada@Example.com")
        me = await (await client.get("/api/mini/me")).json()
        assert me["tg_id"] is None
        assert me["is_admin"] is False
        assert me["handle"]["display"]  # everybody has a nickname
        assert me["settings"]["locale"] == "en"
        person = await repo.person_by_email("ada@example.com")
        assert person is not None

        logins = await (await client.get("/api/mini/me/logins")).json()
        assert logins["email"] == "ada@example.com"
        assert logins["telegram"]["linked"] is False
        # The only way in cannot be removed.
        assert logins["email_removable"] is False
        gone = await client.delete("/api/mini/me/email")
        assert (await gone.json())["error"] == "last_login"

        # Signing in again finds the same person.
        await client.post("/api/mini/auth/logout")
        client.session.cookie_jar.clear()
        await repo._conn.execute("UPDATE email_codes SET created_at = '2000-01-01T00:00:00'")
        await _sign_in(client, sender, "ada@example.com")
        assert await repo.person_by_email("ada@example.com") == person
        cursor = await repo._conn.execute("SELECT COUNT(*) FROM users")
        assert (await cursor.fetchone())[0] == 1
    finally:
        await client.close()


async def test_a_wrong_code_says_how_many_tries_are_left(repo: Repo, settings) -> None:
    sender = FakeSender()
    client = await _client(repo, settings, sender)
    try:
        await client.post("/api/mini/auth/email/start", json={"email": "ada@example.com"})
        wrong = await client.post(
            "/api/mini/auth/email/verify",
            json={"email": "ada@example.com", "code": _wrong(sender.last_code())},
        )
        body = await wrong.json()
        assert (wrong.status, body["error"]) == (400, "wrong_code")
        assert body["attempts_left"] == email_login.MAX_ATTEMPTS - 1
        again = await client.post("/api/mini/auth/email/start", json={"email": "ada@example.com"})
        assert (again.status, (await again.json())["error"]) == (429, "too_soon")
        assert (await client.get("/api/mini/me")).status == 401
    finally:
        await client.close()


async def test_a_mail_failure_is_said_plainly(repo: Repo, settings) -> None:
    client = await _client(repo, settings, FakeSender(fail=True))
    try:
        start = await client.post("/api/mini/auth/email/start", json={"email": "a@b.co"})
        assert (start.status, (await start.json())["error"]) == (502, "send_failed")
    finally:
        await client.close()


async def test_an_email_person_adds_telegram(repo: Repo, settings) -> None:
    sender = FakeSender()
    client = await _client(repo, settings, sender)
    token = settings.bot_token.get_secret_value()
    try:
        await _sign_in(client, sender, "ada@example.com")
        linked = await client.post("/api/mini/me/telegram", json=_widget(token, tg_id=77))
        assert linked.status == 200
        assert (await linked.json())["telegram"]["linked"] is True
        assert (await (await client.get("/api/mini/me")).json())["tg_id"] == 77
        assert await repo.person_id(77) == await repo.person_by_email("ada@example.com")
        # Now the address may go: Telegram is left to sign in with.
        gone = await client.delete("/api/mini/me/email")
        assert (await gone.json())["email"] is None

        # A Telegram account somebody else has is refused.
        await repo.ensure_user(88, "other")
        await repo._conn.execute("UPDATE users SET tg_id = NULL WHERE tg_id = 77")
        taken = await client.post("/api/mini/me/telegram", json=_widget(token, tg_id=88))
        assert (await taken.json())["error"] == "taken"
    finally:
        await client.close()


async def test_a_telegram_person_adds_an_address(repo: Repo, settings) -> None:
    sender = FakeSender()
    client = await _client(repo, settings, sender)
    token = settings.bot_token.get_secret_value()
    try:
        assert (
            await client.post("/api/mini/auth/telegram", json=_widget(token, tg_id=42))
        ).status == 200
        start = await client.post("/api/mini/me/email/start", json={"email": "Ada@Example.com"})
        assert start.status == 200
        done = await client.post(
            "/api/mini/me/email/verify",
            json={"email": "ada@example.com", "code": sender.last_code()},
        )
        body = await done.json()
        assert body["email"] == "ada@example.com"
        assert body["email_removable"] is True
        assert await repo.person_by_email("ada@example.com") == await repo.person_id(42)

        # Somebody else's address is refused before any mail goes out.
        other = await repo.create_email_person("bob@example.com")
        assert other
        sent = len(sender.sent)
        taken = await client.post("/api/mini/me/email/start", json={"email": "bob@example.com"})
        assert (taken.status, (await taken.json())["error"]) == (409, "taken")
        assert len(sender.sent) == sent
    finally:
        await client.close()


async def test_a_person_without_telegram_can_be_deleted(repo: Repo, settings) -> None:
    sender = FakeSender()
    client = await _client(repo, settings, sender)
    try:
        await _sign_in(client, sender, "ada@example.com")
        assert (await client.delete("/api/mini/me")).status == 200
        assert await repo.person_by_email("ada@example.com") is None
    finally:
        await client.close()
