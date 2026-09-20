"""Deep-link payload parsing for the group hub's «Подключить Xbox» button
(SPEC 6.3)."""

from __future__ import annotations

from types import SimpleNamespace

from bot.handlers.connect import _parse_connect_payload, _person_id


def test_plain_connect_has_no_origin_chat() -> None:
    assert _parse_connect_payload("connect") == (True, None)


def test_connect_with_a_group_id_extracts_it() -> None:
    # Group chat ids are always negative.
    assert _parse_connect_payload("connect-1001234567890") == (True, -1001234567890)


def test_unrelated_payload_is_not_a_connect_payload() -> None:
    assert _parse_connect_payload("panel") == (False, None)
    assert _parse_connect_payload("") == (False, None)


def test_garbage_after_connect_does_not_crash() -> None:
    assert _parse_connect_payload("connectnonsense") == (False, None)


def test_person_id_returns_from_user_id() -> None:
    msg = SimpleNamespace(
        from_user=SimpleNamespace(id=123, username="user"), chat=SimpleNamespace(id=-100555)
    )
    assert _person_id(msg) == 123  # type: ignore[arg-type]


def test_person_id_returns_none_when_no_from_user() -> None:
    msg = SimpleNamespace(from_user=None, chat=SimpleNamespace(id=-100555))
    assert _person_id(msg) is None  # type: ignore[arg-type]
