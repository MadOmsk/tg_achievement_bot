"""The super-admin's API load (owner, 2026-10-12): every outside API's
requests over 5 minutes, an hour and a day; Xbox per account."""

from __future__ import annotations

import pytest

from bot.services import api_usage
from bot.services.admin_status import AdminStatus, MailUsage, api_load
from bot.views.admin_home import usage_rows


@pytest.fixture(autouse=True)
def _clean() -> None:
    api_usage.reset()
    yield
    api_usage.reset()


def _status(api, server: str | None = "smtp.example.com") -> AdminStatus:
    return AdminStatus(
        users=0,
        excluded=0,
        xbox_linked=0,
        xbox_active=0,
        xbox_broken=0,
        steam_linked=0,
        psn_linked=0,
        chats=0,
        api=api,
        mail=MailUsage(1, 100, 2, 300, server),
        credentials=[],
    )


def test_xbox_is_counted_per_account_median_and_busiest() -> None:
    """Owner, 2026-10-12: the median account and the busiest; a quiet
    account counts as nought."""
    for _ in range(19):
        api_usage.record(api_usage.XBOX, 2)
    for _ in range(3):
        api_usage.record(api_usage.XBOX, 3)
    api_usage.record(api_usage.XBOX, 4)
    five = api_load(accounts=5).xbox[0]
    assert (five.median, five.most) == (1, 19)  # 0, 0, 1, 3, 19
    assert api_load(accounts=3).xbox[0].median == 3  # 1, 3, 19
    assert api_load(accounts=0).xbox[2].most == 19


def test_the_lines_come_in_order_with_their_windows() -> None:
    for _ in range(3):
        api_usage.record(api_usage.STEAM)
    api_usage.record(api_usage.PSN)
    api_usage.record(api_usage.ANTHROPIC, tokens=1500)
    rows = usage_rows(_status(api_load(accounts=0)), locale="ru")
    assert [label for label, _ in rows] == [
        "API XBOX (медиана/макс. на аккаунт)",
        "API Steam",
        "API PSN",
        "API Anthropic",
        "Писем с кодами (smtp.example.com)",
    ]
    values = dict(rows)
    assert values["API XBOX (медиана/макс. на аккаунт)"] == "5 мин 0/0 · час 0/0 · сутки 0/0"
    assert values["API Steam"] == "5 мин 3 · час 3 · сутки 3/100 000"
    assert values["API PSN"] == "5 мин 1 · час 1 · сутки 1"
    assert values["API Anthropic"] == "час 1 запр. · 1 500 ток. · сутки 1 запр. · 1 500 ток."
    assert values["Писем с кодами (smtp.example.com)"] == "за час 1/100 · за сутки 2/300"


def test_no_mail_server_names_none() -> None:
    rows = usage_rows(_status(api_load(0), server=None), locale="en")
    assert rows[-1][0] == "Sign-in emails"


def test_a_median_between_two_keeps_one_decimal() -> None:
    api_usage.record(api_usage.XBOX, 1)
    rows = usage_rows(_status(api_load(accounts=2)), locale="ru")
    assert dict(rows)["API XBOX (медиана/макс. на аккаунт)"].startswith("5 мин 0,5/1")


def test_a_request_older_than_a_window_leaves_it(monkeypatch) -> None:
    clock = [1000.0]
    monkeypatch.setattr(api_usage, "_now", lambda: clock[0])
    api_usage.record(api_usage.STEAM)
    clock[0] += 400
    assert api_usage.count(api_usage.STEAM, api_usage.FIVE_MINUTES) == 0
    assert api_usage.count(api_usage.STEAM, api_usage.HOUR) == 1
    clock[0] += api_usage.DAY
    assert api_usage.count(api_usage.STEAM, api_usage.DAY) == 0


async def test_the_model_answers_tokens_are_noted() -> None:
    import httpx

    from bot.services.translate.client import _note

    _note(httpx.Response(200, json={"usage": {"input_tokens": 120, "output_tokens": 30}}))
    _note(httpx.Response(500))
    assert api_usage.count(api_usage.ANTHROPIC, api_usage.HOUR) == 2
    assert api_usage.tokens(api_usage.ANTHROPIC, api_usage.HOUR) == 150
