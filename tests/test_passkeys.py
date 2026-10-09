"""Passkeys (owner, 2026-10-08): added in Settings, asked for at sign-in in
place of an email's code.

A software authenticator stands in for the phone: a real P-256 key, real CBOR
and a real signature, so py_webauthn checks exactly what a browser would send.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import struct

import cbor2
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from bot.db.repo import Repo
from bot.services.email_login import EmailLogin
from bot.services.passkeys import Passkeys, device_name
from bot.web.mini_api import cors_middleware, setup_mini_api

ORIGIN = "https://app.example"
RP_ID = "app.example"


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64url(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class SoftKey:
    """One passkey on a pretend phone."""

    def __init__(self, credential_id: bytes = b"key-one", origin: str = ORIGIN) -> None:
        self.private = ec.generate_private_key(ec.SECP256R1())
        self.id = credential_id
        self.count = 0
        self.origin = origin
        self.user_handle: bytes | None = None

    def _cose(self) -> bytes:
        numbers = self.private.public_key().public_numbers()
        return cbor2.dumps(
            {
                1: 2,
                3: -7,
                -1: 1,
                -2: numbers.x.to_bytes(32, "big"),
                -3: numbers.y.to_bytes(32, "big"),
            }
        )

    def _client_data(self, kind: str, challenge: str) -> bytes:
        return json.dumps({"type": kind, "challenge": challenge, "origin": self.origin}).encode()

    def create(self, options: dict) -> dict:
        self.user_handle = unb64url(options["user"]["id"])
        client_data = self._client_data("webauthn.create", options["challenge"])
        auth_data = (
            hashlib.sha256(options["rp"]["id"].encode()).digest()
            + bytes([0x45])  # user present, verified, credential data attached
            + struct.pack(">I", self.count)
            + bytes(16)
            + struct.pack(">H", len(self.id))
            + self.id
            + self._cose()
        )
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        return {
            "id": b64url(self.id),
            "rawId": b64url(self.id),
            "type": "public-key",
            "response": {
                "clientDataJSON": b64url(client_data),
                "attestationObject": b64url(attestation),
                "transports": ["internal", "hybrid"],
            },
        }

    def get(self, options: dict, *, forge: bool = False) -> dict:
        self.count += 1
        client_data = self._client_data("webauthn.get", options["challenge"])
        auth_data = (
            hashlib.sha256(options["rpId"].encode()).digest()
            + bytes([0x05])
            + struct.pack(">I", self.count)
        )
        signed = auth_data + hashlib.sha256(client_data).digest()
        signer = ec.generate_private_key(ec.SECP256R1()) if forge else self.private
        signature = signer.sign(signed, ec.ECDSA(hashes.SHA256()))
        return {
            "id": b64url(self.id),
            "rawId": b64url(self.id),
            "type": "public-key",
            "response": {
                "clientDataJSON": b64url(client_data),
                "authenticatorData": b64url(auth_data),
                "signature": b64url(signature),
                "userHandle": b64url(self.user_handle or b""),
            },
        }


class FakeSender:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    async def send(self, to: str, subject: str, text: str) -> None:
        self.sent.append((to, subject, text))

    def last_code(self) -> str:
        match = re.search(r"\b(\d{6})\b", self.sent[-1][2])
        assert match is not None
        return match.group(1)


async def _client(repo: Repo, settings, sender: FakeSender | None = None) -> TestClient:
    app = web.Application(middlewares=[cors_middleware()])
    login = EmailLogin(repo, sender, b"secret") if sender is not None else None
    setup_mini_api(app, settings, repo, email_login=login, passkeys=Passkeys(ORIGIN, RP_ID))
    client = TestClient(TestServer(app))
    await client.start_server()
    return client


async def _signed_in(client: TestClient, repo: Repo, email: str) -> int:
    """A person with an address, signed in through a session of their own."""
    person = await repo.create_email_person(email)
    token = await repo.create_session(person, "test")
    client.session.cookie_jar.update_cookies({"ab_session": token})
    return person


async def _add_key(client: TestClient, key: SoftKey) -> dict:
    options = await (await client.post("/api/mini/me/passkeys/options")).json()
    added = await client.post(
        "/api/mini/me/passkeys",
        json={"token": options["token"], "credential": key.create(options["options"])},
        headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0) Safari/604.1"},
    )
    assert added.status == 200
    return await added.json()


async def _ask(client: TestClient, email: str = "ada@example.com") -> dict:
    """The sign-in screen typing an address on a browser that can use keys."""
    asked = await (
        await client.post("/api/mini/auth/email/start", json={"email": email, "passkey": True})
    ).json()
    assert asked["passkey"] is True
    return asked


async def test_a_key_is_added_listed_and_removed(repo: Repo, settings) -> None:
    client = await _client(repo, settings)
    try:
        await _signed_in(client, repo, "ada@example.com")
        listed = await (await client.get("/api/mini/me/passkeys")).json()
        assert listed == {"available": True, "keys": []}

        key = SoftKey()
        after = await _add_key(client, key)
        [row] = after["keys"]
        assert row["id"] == b64url(key.id)
        assert row["name"] == "iPhone · Safari"

        # The same key twice is refused, and the phone is told not to make it.
        options = await (await client.post("/api/mini/me/passkeys/options")).json()
        assert [c["id"] for c in options["options"]["excludeCredentials"]] == [b64url(key.id)]

        gone = await client.delete(f"/api/mini/me/passkeys/{row['id']}")
        assert (await gone.json())["keys"] == []
    finally:
        await client.close()


async def test_a_key_signs_its_person_in(repo: Repo, settings) -> None:
    client = await _client(repo, settings)
    try:
        person = await _signed_in(client, repo, "ada@example.com")
        key = SoftKey()
        await _add_key(client, key)
        client.session.cookie_jar.clear()
        assert (await client.get("/api/mini/me")).status == 401

        options = await _ask(client)
        signed = await client.post(
            "/api/mini/auth/passkey/verify",
            json={"token": options["token"], "credential": key.get(options["options"])},
        )
        assert signed.status == 200
        me = await (await client.get("/api/mini/me")).json()
        assert me["person_id"] == person
        [stored] = await repo.passkeys_of(person)
        assert stored.sign_count == 1 and stored.last_used_at is not None
    finally:
        await client.close()


async def test_a_forged_or_replayed_answer_signs_nobody_in(repo: Repo, settings) -> None:
    client = await _client(repo, settings)
    try:
        await _signed_in(client, repo, "ada@example.com")
        key = SoftKey()
        await _add_key(client, key)
        client.session.cookie_jar.clear()

        options = await _ask(client)
        forged = await client.post(
            "/api/mini/auth/passkey/verify",
            json={"token": options["token"], "credential": key.get(options["options"], forge=True)},
        )
        assert (forged.status, (await forged.json())["error"]) == (400, "invalid")

        # A challenge answers once: the token is spent even by a failed try.
        again = await client.post(
            "/api/mini/auth/passkey/verify",
            json={"token": options["token"], "credential": key.get(options["options"])},
        )
        assert (await again.json())["error"] == "expired"

        # Another site's page cannot use the key's answer here.
        elsewhere = SoftKey(origin="https://evil.example")
        elsewhere.private, elsewhere.id = key.private, key.id
        options = await _ask(client)
        foreign = await client.post(
            "/api/mini/auth/passkey/verify",
            json={"token": options["token"], "credential": elsewhere.get(options["options"])},
        )
        assert (await foreign.json())["error"] == "invalid"

        # A key the app does not know.
        stranger = SoftKey(b"unknown")
        options = await _ask(client)
        unknown = await client.post(
            "/api/mini/auth/passkey/verify",
            json={"token": options["token"], "credential": stranger.get(options["options"])},
        )
        assert (await unknown.json())["error"] == "unknown_key"
        assert (await client.get("/api/mini/me")).status == 401
    finally:
        await client.close()


async def test_an_address_with_a_key_asks_for_the_key_not_a_code(repo: Repo, settings) -> None:
    sender = FakeSender()
    client = await _client(repo, settings, sender)
    try:
        person = await _signed_in(client, repo, "ada@example.com")
        key = SoftKey()
        await _add_key(client, key)
        client.session.cookie_jar.clear()

        asked = await (
            await client.post(
                "/api/mini/auth/email/start", json={"email": "ada@example.com", "passkey": True}
            )
        ).json()
        assert asked["passkey"] is True
        assert [c["id"] for c in asked["options"]["allowCredentials"]] == [b64url(key.id)]
        assert sender.sent == []
        signed = await client.post(
            "/api/mini/auth/passkey/verify",
            json={"token": asked["token"], "credential": key.get(asked["options"])},
        )
        assert signed.status == 200
        assert (await (await client.get("/api/mini/me")).json())["person_id"] == person
        client.session.cookie_jar.clear()

        # The key not at hand: the app asks for the code instead.
        code = await client.post(
            "/api/mini/auth/email/start", json={"email": "ada@example.com", "passkey": False}
        )
        assert code.status == 200 and "passkey" not in await code.json()
        assert len(sender.sent) == 1

        # An address without a key gets its code as before.
        other = await repo.create_email_person("bob@example.com")
        assert other is not None
        plain = await client.post(
            "/api/mini/auth/email/start", json={"email": "bob@example.com", "passkey": True}
        )
        assert "passkey" not in await plain.json()
        assert len(sender.sent) == 2
    finally:
        await client.close()


async def test_keys_need_the_apps_https_address(repo: Repo, settings) -> None:
    assert Passkeys.for_app(None) is None
    assert Passkeys.for_app("http://app.example/") is None
    keys = Passkeys.for_app("https://xbox.example.com/app/")
    assert keys is not None
    assert (keys.origin, keys.rp_id) == ("https://xbox.example.com", "xbox.example.com")

    app = web.Application(middlewares=[cors_middleware()])
    setup_mini_api(app, settings, repo)
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        config = await (await client.get("/api/mini/auth/config")).json()
        assert config["passkey"] is (settings.mini_app_url or "").startswith("https://")
    finally:
        await client.close()


def test_a_key_is_named_by_its_device() -> None:
    assert device_name("Mozilla/5.0 (Windows NT 10.0) Chrome/130.0 Safari/537.36") == (
        "Windows · Chrome"
    )
    assert device_name("Mozilla/5.0 (Linux; Android 15) Chrome/130.0 Mobile") == "Android · Chrome"
    assert device_name(None) is None
