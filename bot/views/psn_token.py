"""The screens of a player's own PSN token (#233; agreed on a navigable mockup,
2026-10-29): one account's token — none, working or dead —, how to get one,
the prompt to paste it, what came of it, removing it; and linking an account
by its token. A view renders and never sends.
"""

from __future__ import annotations

from datetime import date
from html import escape as html_escape

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.constants import Platform
from bot.db.repo import PlatformLink, PsnTokenRow, Repo
from bot.i18n import translator
from bot.services.naming import link_nickname
from bot.services.poll_cadence import load as load_cadence
from bot.util import humanize_ago, parse_iso
from bot.views import Screen
from bot.views.date_picker import format_day_month

#: What a token's state reads as on the PSN screen's button.
TOKEN_MARK = {None: "➕", "active": "✅", "dead": "⚠️"}


def keyboard(*rows: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t, callback_data=c) for t, c in row] for row in rows
        ]
    )


def _day(timestamp: str | None, locale: str) -> str:
    moment = parse_iso(timestamp)
    return format_day_month(moment.date() if moment else date.today(), locale)


async def _slowdown(repo: Repo) -> int:
    return (await load_cadence(repo, "psn")).shared_slowdown


async def _link(repo: Repo, person_id: int, account_id: str) -> PlatformLink | None:
    for link in await repo.platform_links_for(person_id, Platform.PSN):
        if link.external_id == account_id:
            return link
    return None


async def render_token(
    repo: Repo, person_id: int, account_id: str, *, locale: str
) -> Screen | None:
    """One account's token. None when the account is not this person's."""
    link = await _link(repo, person_id, account_id)
    if link is None:
        return None
    _ = translator("psn", locale)
    name = html_escape(link_nickname(link))
    token = await repo.psn_token(account_id)
    back = (_("psn-token-back"), "panel:acc:psn")
    if token is None:
        text = "\n\n".join(
            [
                _("psn-token-title", name=name),
                _("psn-token-none", slowdown=await _slowdown(repo)),
                _("psn-token-gives", slowdown=await _slowdown(repo)),
                _("psn-token-safety"),
            ]
        )
        return Screen(
            text,
            keyboard(
                [(_("psn-token-steps-button"), f"psntok:steps:{account_id}")],
                [(_("psn-token-paste-button"), f"psntok:in:{account_id}")],
                [back],
            ),
        )
    if token.status == "dead":
        text = "\n\n".join(
            [
                _("psn-token-title", name=name),
                _("psn-token-dead", since=_day(token.dead_at, locale)),
            ]
        )
        return Screen(
            text,
            keyboard(
                [(_("psn-token-renew-button"), f"psntok:steps:{account_id}")],
                [(_("psn-token-delete-button"), f"psntok:del:{account_id}")],
                [back],
            ),
        )
    text = "\n\n".join(
        [
            _("psn-token-title", name=name),
            _(
                "psn-token-alive",
                since=_day(token.verified_at, locale),
                checked=humanize_ago(token.checked_at, locale),
            ),
        ]
    )
    return Screen(
        text,
        keyboard(
            [(_("psn-token-replace-button"), f"psntok:in:{account_id}")],
            [(_("psn-token-delete-button"), f"psntok:del:{account_id}")],
            [back],
        ),
    )


def render_steps(name: str | None, account_id: str | None, *, locale: str) -> Screen:
    """How to get a token: for one account (`account_id`), or for linking a
    new one by its token (None)."""
    _ = translator("psn", locale)
    who = f"<b>{html_escape(name)}</b>" if name else _("psn-token-steps-any-account")
    if account_id is None:
        return Screen(
            "\n\n".join([_("psn-token-steps", who=who), _("psn-token-safety")]),
            keyboard(
                [(_("psn-token-paste-button"), "psntok:in:new")],
                [(_("psn-token-cancel"), "psn:add")],
            ),
        )
    return Screen(
        _("psn-token-steps", who=who),
        keyboard(
            [(_("psn-token-paste-button"), f"psntok:in:{account_id}")],
            [(_("psn-token-back"), f"psntok:{account_id}")],
        ),
    )


def render_input(name: str | None, account_id: str | None, *, locale: str) -> Screen:
    _ = translator("psn", locale)
    cancel = f"psntok:{account_id}" if account_id else "psn:add"
    text = _("psn-token-input", name=html_escape(name)) if name else _("psn-token-input-new")
    return Screen(text, keyboard([(_("psn-token-cancel"), cancel)]))


def render_result(
    code: str,
    *,
    name: str | None,
    account_id: str | None,
    other: str | None = None,
    locale: str,
) -> Screen:
    """What came of a pasted token: `ok`, or a PsnTokenError's code."""
    _ = translator("psn", locale)
    retry = f"psntok:in:{account_id or 'new'}"
    back = f"psntok:{account_id}" if account_id else "psn:add"
    if code == "ok":
        return Screen(
            _("psn-token-ok", name=html_escape(name or "")),
            keyboard(
                [(_("psn-token-open-button"), f"psntok:{account_id}")],
                [(_("psn-token-to-psn"), "panel:acc:psn")],
            ),
        )
    text = _(
        f"psn-token-error-{code}",
        name=html_escape(name or ""),
        other=html_escape(other or ""),
    )
    rows: list[list[tuple[str, str]]] = []
    if code in ("refused", "mismatch"):
        rows.append([(_("psn-token-steps-button"), f"psntok:steps:{account_id or 'new'}")])
    rows.append([(_("psn-token-retry-button"), retry)])
    rows.append([(_("psn-token-back"), back)])
    return Screen(text, keyboard(*rows))


def render_delete_confirm(name: str, account_id: str, *, locale: str) -> Screen:
    _ = translator("psn", locale)
    return Screen(
        _("psn-token-delete-confirm", name=html_escape(name)),
        keyboard(
            [
                (_("psn-token-delete-yes"), f"psntok:dely:{account_id}"),
                (_("psn-token-cancel"), f"psntok:{account_id}"),
            ]
        ),
    )


def render_deleted(*, locale: str) -> Screen:
    _ = translator("psn", locale)
    return Screen(_("psn-token-deleted"), keyboard([(_("psn-token-to-psn"), "panel:acc:psn")]))


def token_mark(token: PsnTokenRow | None) -> str:
    return TOKEN_MARK[token.status if token else None]
