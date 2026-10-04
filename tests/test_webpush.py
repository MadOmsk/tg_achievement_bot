"""Web Push encryption and signing (#164), checked against RFC 8291's example
and by decrypting what was sealed the way a browser does."""

from __future__ import annotations

import json

import httpx
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from bot.services import webpush
from bot.services.webpush import VapidKeys, b64u, unb64u

# RFC 8291, section 5.
PLAINTEXT = b"When I grow up, I want to be a watermelon"
AS_PRIVATE = "yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"
UA_PRIVATE = "q1dXpw3UpT5VOmu_cf_v6ih07Aems3njxI-JWgLcM94"
UA_PUBLIC = (
    "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4"
)
SALT = "DGv6ra1nlYgDCS1FRnbzlw"
AUTH = "BTBZMqHH6r4Tts7J_aSIgg"
EXPECTED = (
    "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocIn"
    "mYWAmS6TlzAC8wEqKK6PBru3jl7A_yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNW"
    "QexSgSxsj_Qulcy4a-fN"
)


def _private(b64: str) -> ec.EllipticCurvePrivateKey:
    return ec.derive_private_key(int.from_bytes(unb64u(b64), "big"), ec.SECP256R1())


def test_encryption_matches_the_rfc_example() -> None:
    body = webpush.encrypt(
        PLAINTEXT,
        unb64u(UA_PUBLIC),
        unb64u(AUTH),
        sender_key=_private(AS_PRIVATE),
        salt=unb64u(SALT),
    )
    assert b64u(body) == EXPECTED


def _decrypt(body: bytes, ua_private: ec.EllipticCurvePrivateKey, auth: bytes) -> bytes:
    """What a browser does with the body."""
    salt, idlen = body[:16], body[20]
    as_public = body[21 : 21 + idlen]
    ciphertext = body[21 + idlen :]
    ua_public = webpush._public_bytes(ua_private.public_key())
    sender = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_public)
    shared = ua_private.exchange(ec.ECDH(), sender)
    ikm = webpush._hkdf(auth, shared, b"WebPush: info\x00" + ua_public + as_public, 32)
    cek = webpush._hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = webpush._hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    padded = AESGCM(cek).decrypt(nonce, ciphertext, None)
    assert padded.endswith(b"\x02")
    return padded[:-1]


def test_a_fresh_message_opens_with_the_browsers_key() -> None:
    browser = ec.generate_private_key(ec.SECP256R1())
    auth = b"0123456789abcdef"
    body = webpush.encrypt("Привет".encode(), webpush._public_bytes(browser.public_key()), auth)
    assert _decrypt(body, browser, auth).decode() == "Привет"
    # Fresh salt and key each time: two sealings of one message differ.
    again = webpush.encrypt(b"x", webpush._public_bytes(browser.public_key()), auth)
    assert again[:16] != body[:16]


def test_the_vapid_token_is_signed_for_the_push_service() -> None:
    keys = VapidKeys.generate()
    token = keys.token(
        "https://fcm.googleapis.com/fcm/send/abc", "mailto:bot@example.com", now=1000
    )
    head, claims, signature = token.split(".")
    assert json.loads(unb64u(head)) == {"typ": "JWT", "alg": "ES256"}
    assert json.loads(unb64u(claims)) == {
        "aud": "https://fcm.googleapis.com",
        "exp": 1000 + webpush.VAPID_LIFETIME_SECONDS,
        "sub": "mailto:bot@example.com",
    }
    raw = unb64u(signature)
    der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
    keys.private.public_key().verify(der, f"{head}.{claims}".encode(), ec.ECDSA(hashes.SHA256()))
    # The key survives being stored and read back.
    assert VapidKeys.from_pem(keys.to_pem()).public_b64 == keys.public_b64


async def test_a_gone_subscription_is_told_apart_from_a_refusal() -> None:
    browser = ec.generate_private_key(ec.SECP256R1())
    sub = {
        "endpoint": "https://push.example.com/abc",
        "p256dh": b64u(webpush._public_bytes(browser.public_key())),
        "auth": b64u(b"0123456789abcdef"),
    }
    seen: list[httpx.Request] = []

    def answer(status: int):
        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(status)

        return handler

    keys = VapidKeys.generate()
    async with httpx.AsyncClient(transport=httpx.MockTransport(answer(201))) as client:
        await webpush.send(client, keys, "mailto:a@b.co", payload={"title": "t"}, **sub)
    request = seen[-1]
    assert request.headers["Content-Encoding"] == "aes128gcm"
    assert request.headers["Authorization"].startswith("vapid t=")
    assert json.loads(_decrypt(request.content, browser, b"0123456789abcdef")) == {"title": "t"}

    async with httpx.AsyncClient(transport=httpx.MockTransport(answer(410))) as client:
        with pytest.raises(webpush.SubscriptionGone):
            await webpush.send(client, keys, "mailto:a@b.co", payload={}, **sub)
    async with httpx.AsyncClient(transport=httpx.MockTransport(answer(429))) as client:
        with pytest.raises(webpush.PushFailed):
            await webpush.send(client, keys, "mailto:a@b.co", payload={}, **sub)
