"""Web Push (#164): the message encrypted for one browser (RFC 8291,
`aes128gcm`, RFC 8188) and signed for its push service (VAPID, RFC 8292).

Built on `cryptography` and `httpx`, both already dependencies, rather than
pywebpush, which would bring a synchronous HTTP client into an async bot.
`tests/test_webpush.py` checks the encryption against RFC 8291's own example.

Nothing here knows about people or the database: `services/notifier.py` decides
what to send to whom, this only seals and posts one message.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

RECORD_SIZE = 4096
TTL_SECONDS = 24 * 3600
VAPID_LIFETIME_SECONDS = 12 * 3600
TIMEOUT_SECONDS = 15


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def unb64u(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _hkdf(salt: bytes, ikm: bytes, info: bytes, length: int) -> bytes:
    """HKDF-SHA256 with a single block of output, which every length here fits."""
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    return hmac.new(prk, info + b"\x01", hashlib.sha256).digest()[:length]


def _public_bytes(key: ec.EllipticCurvePublicKey) -> bytes:
    return key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )


def encrypt(
    plaintext: bytes,
    ua_public: bytes,
    auth_secret: bytes,
    *,
    sender_key: ec.EllipticCurvePrivateKey | None = None,
    salt: bytes | None = None,
) -> bytes:
    """The body of one push message for the browser whose public key and auth
    secret its subscription gave. `sender_key` and `salt` are fresh per message
    and fixed only by the test against the RFC's example."""
    sender_key = sender_key or ec.generate_private_key(ec.SECP256R1())
    salt = salt or os.urandom(16)
    as_public = _public_bytes(sender_key.public_key())
    receiver = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public)
    shared = sender_key.exchange(ec.ECDH(), receiver)

    key_info = b"WebPush: info\x00" + ua_public + as_public
    ikm = _hkdf(auth_secret, shared, key_info, 32)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)

    # One record: the message, then the delimiter of a last record.
    ciphertext = AESGCM(cek).encrypt(nonce, plaintext + b"\x02", None)
    header = salt + RECORD_SIZE.to_bytes(4, "big") + bytes([len(as_public)]) + as_public
    return header + ciphertext


@dataclass(slots=True)
class VapidKeys:
    """The server's own key pair: the public half goes to browsers when they
    subscribe, the private half signs every message."""

    private: ec.EllipticCurvePrivateKey

    @classmethod
    def generate(cls) -> VapidKeys:
        return cls(ec.generate_private_key(ec.SECP256R1()))

    @classmethod
    def from_pem(cls, pem: bytes) -> VapidKeys:
        key = serialization.load_pem_private_key(pem, password=None)
        assert isinstance(key, ec.EllipticCurvePrivateKey)
        return cls(key)

    def to_pem(self) -> bytes:
        return self.private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )

    @property
    def public_b64(self) -> str:
        return b64u(_public_bytes(self.private.public_key()))

    def token(self, endpoint: str, subject: str, *, now: float | None = None) -> str:
        """The signed JWT a push service checks: for this endpoint's origin, this
        long, from this contact."""
        parts = urlsplit(endpoint)
        claims = {
            "aud": f"{parts.scheme}://{parts.netloc}",
            "exp": int((now or time.time()) + VAPID_LIFETIME_SECONDS),
            "sub": subject,
        }
        header = {"typ": "JWT", "alg": "ES256"}
        signing_input = (
            b64u(json.dumps(header, separators=(",", ":")).encode())
            + "."
            + b64u(json.dumps(claims, separators=(",", ":")).encode())
        )
        der = self.private.sign(signing_input.encode(), ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der)
        return signing_input + "." + b64u(r.to_bytes(32, "big") + s.to_bytes(32, "big"))


class SubscriptionGone(Exception):
    """The browser unsubscribed or the subscription expired: forget it."""


class PushFailed(Exception):
    """The push service refused this time; the subscription may still be good."""


async def send(
    client: httpx.AsyncClient,
    keys: VapidKeys,
    subject: str,
    *,
    endpoint: str,
    p256dh: str,
    auth: str,
    payload: dict[str, object],
) -> None:
    body = encrypt(json.dumps(payload, ensure_ascii=False).encode(), unb64u(p256dh), unb64u(auth))
    headers = {
        "Authorization": f"vapid t={keys.token(endpoint, subject)}, k={keys.public_b64}",
        "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream",
        "TTL": str(TTL_SECONDS),
        "Urgency": "normal",
    }
    try:
        response = await client.post(
            endpoint, content=body, headers=headers, timeout=TIMEOUT_SECONDS
        )
    except httpx.HTTPError as exc:
        raise PushFailed(f"{type(exc).__name__}: {exc!r}") from None
    if response.status_code in (404, 410):
        raise SubscriptionGone(str(response.status_code))
    if response.status_code >= 400:
        raise PushFailed(f"{response.status_code}: {response.text[:200]}")
