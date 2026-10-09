"""Passkeys (owner, 2026-10-08): a key kept on a phone or a computer signs its
person in, in place of an email's code.

The checking itself is py_webauthn's: what the browser sent, against the
challenge given out, the app's own origin and the key's public half. What is
here is the rest — whose domain the keys belong to, the one-time challenges
(in memory, five minutes, like a sign-up waiting for its invite), and a name a
person can tell their keys apart by.
"""

from __future__ import annotations

import json
import re
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.exceptions import InvalidAuthenticationResponse, InvalidRegistrationResponse
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    AuthenticatorTransport,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from bot.db.repo import PasskeyRow

CHALLENGE_TTL_SECONDS = 300
# Never more than this many challenges waiting at once: an unanswered one costs
# memory, and nobody needs hundreds in five minutes.
_MAX_PENDING = 500
RP_NAME = "Unlocked"


class PasskeyError(Exception):
    """What the browser sent does not prove anything: a stale or unknown
    challenge, another site's key, a forged signature."""


@dataclass(frozen=True, slots=True)
class NewPasskey:
    id: str
    public_key: bytes
    sign_count: int
    transports: list[str]


@dataclass(slots=True)
class _Pending:
    challenge: bytes
    purpose: str
    person_id: int | None
    expires: float


def _origin_of(url: str) -> tuple[str, str] | None:
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        return None
    port = f":{parts.port}" if parts.port and parts.port != 443 else ""
    return f"https://{parts.hostname}{port}", parts.hostname


def device_name(user_agent: str | None) -> str | None:
    """ "iPhone · Safari", "Windows · Chrome": enough to tell one's keys apart."""
    ua = user_agent or ""
    device = next(
        (
            label
            for pattern, label in (
                (r"iPhone", "iPhone"),
                (r"iPad", "iPad"),
                (r"Android", "Android"),
                (r"Windows", "Windows"),
                (r"Macintosh|Mac OS X", "Mac"),
                (r"CrOS", "ChromeOS"),
                (r"Linux", "Linux"),
            )
            if re.search(pattern, ua)
        ),
        None,
    )
    browser = next(
        (
            label
            for pattern, label in (
                (r"Edg/", "Edge"),
                (r"OPR/|Opera", "Opera"),
                (r"YaBrowser", "Yandex"),
                (r"SamsungBrowser", "Samsung Internet"),
                (r"Firefox/|FxiOS", "Firefox"),
                (r"Chrome/|CriOS", "Chrome"),
                (r"Safari/", "Safari"),
            )
            if re.search(pattern, ua)
        ),
        None,
    )
    name = " · ".join(part for part in (device, browser) if part)
    return name or None


class Passkeys:
    """The app's passkeys, bound to the host the Mini App is served from."""

    REGISTER = "register"
    SIGN_IN = "sign_in"

    def __init__(self, origin: str, rp_id: str) -> None:
        self.origin = origin
        self.rp_id = rp_id
        self._pending: dict[str, _Pending] = {}

    @classmethod
    def for_app(cls, mini_app_url: str | None) -> Passkeys | None:
        """None without an https address for the app: a key belongs to a domain."""
        found = _origin_of(mini_app_url or "")
        return cls(*found) if found else None

    def _put(self, challenge: bytes, purpose: str, person_id: int | None) -> str:
        now = time.monotonic()
        for token in [t for t, p in self._pending.items() if p.expires <= now]:
            del self._pending[token]
        while len(self._pending) >= _MAX_PENDING:
            del self._pending[next(iter(self._pending))]
        token = secrets.token_urlsafe(24)
        self._pending[token] = _Pending(challenge, purpose, person_id, now + CHALLENGE_TTL_SECONDS)
        return token

    def _take(self, token: object, purpose: str, person_id: int | None) -> bytes:
        """The challenge given out under `token`, once."""
        pending = self._pending.pop(str(token), None) if token else None
        if (
            pending is None
            or pending.expires <= time.monotonic()
            or pending.purpose != purpose
            or pending.person_id != person_id
        ):
            raise PasskeyError("expired")
        return pending.challenge

    def registration_options(
        self, person_id: int, name: str, existing: list[PasskeyRow]
    ) -> dict[str, Any]:
        """What `navigator.credentials.create` needs, and the token to answer with.
        The key is discoverable: signing in with it needs no address typed."""
        options = generate_registration_options(
            rp_id=self.rp_id,
            rp_name=RP_NAME,
            user_id=f"p{person_id}".encode(),
            user_name=name,
            user_display_name=name,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.REQUIRED,
                user_verification=UserVerificationRequirement.PREFERRED,
            ),
            exclude_credentials=[_descriptor(key) for key in existing],
        )
        token = self._put(options.challenge, self.REGISTER, person_id)
        return {"token": token, "options": json.loads(options_to_json(options))}

    def finish_registration(self, token: object, person_id: int, credential: Any) -> NewPasskey:
        challenge = self._take(token, self.REGISTER, person_id)
        try:
            verified = verify_registration_response(
                credential=credential,
                expected_challenge=challenge,
                expected_rp_id=self.rp_id,
                expected_origin=self.origin,
            )
        except (InvalidRegistrationResponse, ValueError, TypeError, KeyError) as exc:
            raise PasskeyError("invalid") from exc
        response = credential.get("response", {}) if isinstance(credential, dict) else {}
        transports = response.get("transports") if isinstance(response, dict) else None
        return NewPasskey(
            id=bytes_to_base64url(verified.credential_id),
            public_key=verified.credential_public_key,
            sign_count=verified.sign_count,
            transports=[str(t) for t in transports or [] if isinstance(t, str)],
        )

    def sign_in_options(self, keys: list[PasskeyRow]) -> dict[str, Any]:
        """What `navigator.credentials.get` needs: the keys of the address typed."""
        options = generate_authentication_options(
            rp_id=self.rp_id,
            allow_credentials=[_descriptor(key) for key in keys],
            user_verification=UserVerificationRequirement.PREFERRED,
        )
        token = self._put(options.challenge, self.SIGN_IN, None)
        return {"token": token, "options": json.loads(options_to_json(options))}

    @staticmethod
    def credential_id(credential: Any) -> str | None:
        """Which key answered — to find its public half before checking it."""
        if isinstance(credential, dict) and isinstance(credential.get("id"), str):
            return credential["id"]
        return None

    def finish_sign_in(self, token: object, credential: Any, key: PasskeyRow) -> int:
        """Checks the answer against the stored key; returns its new count."""
        challenge = self._take(token, self.SIGN_IN, None)
        try:
            verified = verify_authentication_response(
                credential=credential,
                expected_challenge=challenge,
                expected_rp_id=self.rp_id,
                expected_origin=self.origin,
                credential_public_key=key.public_key,
                credential_current_sign_count=key.sign_count,
            )
        except (InvalidAuthenticationResponse, ValueError, TypeError, KeyError) as exc:
            raise PasskeyError("invalid") from exc
        return verified.new_sign_count


def _descriptor(key: PasskeyRow) -> PublicKeyCredentialDescriptor:
    known = {t.value for t in AuthenticatorTransport}
    return PublicKeyCredentialDescriptor(
        id=base64url_to_bytes(key.id),
        transports=[AuthenticatorTransport(t) for t in key.transports if t in known] or None,
    )
