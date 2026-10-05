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
        # Everybody has a nickname: here the part of the address before the @.
        assert me["handle"]["display"].startswith("ada")
        assert me["settings"]["locale"] == "en"
        person = await repo.person_by_email("ada@example.com")
        assert person is not None

        logins = await (await client.get("/api/mini/me/logins")).json()
        assert logins["email"] == "ada@example.com"
        assert logins["telegram"]["linked"] is False
        # Email is the main way in: there is no way to remove it.
        assert "email_removable" not in logins
        assert (await client.delete("/api/mini/me/email")).status == 404

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
        # Even with Telegram linked, the address stays.
        assert (await client.delete("/api/mini/me/email")).status == 404
        assert await repo.person_by_email("ada@example.com") is not None

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


# --------------------------------------------------------- taking Telegram away


def _init_data(token: str, tg_id: int) -> str:
    import json as _json
    from urllib.parse import urlencode

    user = _json.dumps({"id": tg_id, "first_name": "Test", "username": "t"}, separators=(",", ":"))
    pairs = {"auth_date": str(int(time.time())), "user": user}
    check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(pairs)


async def test_telegram_can_be_taken_away_while_an_address_is_left(repo: Repo, settings) -> None:
    sender = FakeSender()
    client = await _client(repo, settings, sender)
    token = settings.bot_token.get_secret_value()
    try:
        await _sign_in(client, sender, "ada@example.com")
        await client.post("/api/mini/me/telegram", json=_widget(token, tg_id=77))
        person = await repo.person_by_email("ada@example.com")
        assert person is not None
        await repo.upsert_chat(-100, "Chat", 77)
        await repo.subscribe(-100, person)
        await repo.record_chat_seen(-100, 77)

        logins = await (await client.get("/api/mini/me/logins")).json()
        assert logins["telegram"]["removable"] is True

        # Inside Telegram the same request is refused: the app signs in with it.
        inside = await client.delete(
            "/api/mini/me/telegram", headers={"X-Telegram-Init-Data": _init_data(token, 77)}
        )
        assert (await inside.json())["error"] == "in_telegram"

        gone = await client.delete("/api/mini/me/telegram")
        body = await gone.json()
        assert gone.status == 200 and body["telegram"]["linked"] is False
        user = await repo.get_user(person)
        assert user is not None and user.tg_id is None and user.username is None
        assert user.handle  # the nickname stays
        assert await repo.chats_of_user(person) == []
        assert await repo.user_chats(77) == []

        # That Telegram account is nobody's now: it signs in as a new person.
        client.session.cookie_jar.clear()
        again = await client.post("/api/mini/auth/telegram", json=_widget(token, tg_id=77))
        assert again.status == 200
        assert await repo.person_id(77) not in (None, person)
    finally:
        await client.close()


async def test_telegram_stays_when_it_is_the_last_way_in_or_an_admins(repo: Repo, settings) -> None:
    sender = FakeSender()
    client = await _client(repo, settings, sender)
    token = settings.bot_token.get_secret_value()
    try:
        await client.post("/api/mini/auth/telegram", json=_widget(token, tg_id=42))
        lone = await client.delete("/api/mini/me/telegram")
        assert (lone.status, (await lone.json())["error"]) == (409, "last_login")

        # An address now, but a super-admin keeps their Telegram all the same.
        await client.post("/api/mini/me/email/start", json={"email": "boss@example.com"})
        await client.post(
            "/api/mini/me/email/verify",
            json={"email": "boss@example.com", "code": sender.last_code()},
        )
        settings.admin_tg_ids = [42]
        logins = await (await client.get("/api/mini/me/logins")).json()
        assert logins["telegram"]["blocked"] == "admin"
        admin = await client.delete("/api/mini/me/telegram")
        assert (await admin.json())["error"] == "admin"
        assert await repo.person_id(42) is not None
    finally:
        await client.close()


# ------------------------------------------------- the dev server's no-code mode


async def test_the_no_code_mode_takes_the_address_as_proved(repo: Repo, settings) -> None:
    from bot.services.email_login import TrustingEmailLogin
    from bot.web.mini_logins import build_email_login

    settings.email_skip_code = True
    login = build_email_login(settings, repo)
    assert isinstance(login, TrustingEmailLogin)

    app = web.Application(middlewares=[cors_middleware()])
    setup_mini_api(app, settings, repo)
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        start = await (
            await client.post("/api/mini/auth/email/start", json={"email": "Dev@Example.com"})
        ).json()
        assert start["skip_code"] is True
        signed = await client.post(
            "/api/mini/auth/email/verify", json={"email": "dev@example.com", "code": ""}
        )
        assert signed.status == 200
        assert (await client.get("/api/mini/me")).status == 200
    finally:
        await client.close()


def test_the_no_code_mode_never_runs_beside_a_mail_server(repo: Repo, settings) -> None:
    from bot.services.email_login import TrustingEmailLogin
    from bot.web.mini_logins import build_email_login

    settings.email_skip_code = True
    settings.smtp_host, settings.smtp_from = "mail.example.com", "bot@example.com"
    login = build_email_login(settings, repo)
    assert login is not None and not isinstance(login, TrustingEmailLogin)
    assert login.skips_code is False
