"""The /admin home screen's own render (Follow-up 2026-09-06) — split out of
handlers/admin.py so poller/admin_refresh.py can reuse the exact same
rendering the manual command uses, same relationship views/online.py
already has with handlers/chat.py's /online and poller/online_refresh.py.

What it shows is `services/admin_status.py`'s, the same object the Mini
App's admin home serializes (#176); this module only words it.

Only the *home* screen lives here — /admin's sub-screens (users list, a
chat's card, the PSN test screen, ...) are still handlers/admin.py's own,
same as /online has no auto-refreshing equivalent for /who's picker.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.constants import TokenStatus
from bot.db.repo import Repo
from bot.i18n import translator
from bot.services.admin_credentials import AdminCredentials
from bot.services.admin_status import AdminStatus, admin_status
from bot.services.stats import local_now
from bot.util import humanize_ago

# Europe/Moscow — same default the rest of the project falls back to
# (schema.sql's chat_settings.tz_offset_min, config.py's Settings.tz) when
# nothing more specific applies. The admin panel isn't scoped to any one
# chat, so there is no per-chat offset to read here the way /online has.
_DEFAULT_TZ_OFFSET_MIN = 180


async def _key_status_line(
    status: str, checked_at: str | None, *, active_value: str, locale: str
) -> str:
    """Common rendering for the two shared-credential status lines below
    (SPEC 9, M-PSN-1's "мониторинг живости" paragraph, applied to Steam
    too) — a bare word would hide a stale check, so this always says when
    it last actually ran."""
    _ = translator("adminview", locale)
    if status == active_value:
        return (
            _("adminview-key-alive-checked", ago=humanize_ago(checked_at, locale))
            if checked_at
            else _("adminview-key-alive")
        )
    return (
        _("adminview-key-stale-checked", ago=humanize_ago(checked_at, locale))
        if checked_at
        else _("adminview-key-stale")
    )


def _number(value: float, locale: str) -> str:
    """A count as the reader writes it: thousands apart, one decimal at most."""
    if float(value).is_integer():
        text = f"{int(value):,}".replace(",", "\u00a0")
    else:
        text = f"{value:,.1f}".replace(",", "\u00a0")
        if locale == "ru":
            text = text.replace(".", ",")
    return text


def _span(span: float, _) -> str:
    return _(f"adminview-span-{int(span)}")


def usage_rows(status: AdminStatus, *, locale: str) -> list[tuple[str, str]]:
    """Each outside API's load and the sign-in emails, as (label, value) —
    the one wording both admin panels show (owner, 2026-10-12): Xbox per
    account (the median account / the busiest), Steam and PSN over 5 minutes,
    an hour and a day, the model's tokens over an hour and a day."""
    _ = translator("adminview", locale)

    def n(value: float) -> str:
        return _number(value, locale)

    def counted(windows) -> str:
        return " · ".join(
            f"{_span(w.span, _)} {n(w.used)}" + (f"/{n(w.limit)}" if w.limit else "")
            for w in windows
        )

    api = status.api
    xbox = " · ".join(f"{_span(w.span, _)} {n(w.median)}/{n(w.most)}" for w in api.xbox)
    anthropic = " · ".join(
        f"{_span(w.span, _)} "
        + _("adminview-api-tokens", requests=n(w.requests), tokens=n(w.tokens))
        for w in api.anthropic
    )
    mail = status.mail
    octopus = [(_("adminview-octopus"), _octopus_value(status, _))] if status.octopus else []
    return [
        (_("adminview-api-xbox"), xbox),
        (_("adminview-api-steam"), counted(api.steam)),
        (_("adminview-api-psn"), counted(api.psn)),
        (_("adminview-api-anthropic"), anthropic),
        *octopus,
        (
            _("adminview-mail-label", server=mail.server)
            if mail.server
            else _("adminview-mail-label-none"),
            _(
                "adminview-mail-usage",
                hour=mail.hour,
                hour_limit=mail.hour_limit,
                day=mail.day,
                day_limit=mail.day_limit,
            ),
        ),
    ]


def usage_by_credential(status: AdminStatus, *, locale: str) -> dict[str, str]:
    """The load line of each credential that has one, for its own key screen
    (#233): Steam, PSN, Anthropic and the mail login."""
    rows = usage_rows(status, locale=locale)
    names = ["xbox", "steam", "psn", "anthropic"] + (["octopus"] if status.octopus else [])
    named = dict(zip(names, (value for _label, value in rows), strict=False))
    named["smtp"] = rows[-1][1]
    return named


def _octopus_value(status: AdminStatus, _) -> str:
    """The octopus on one line (owner, 2026-10-25): on or off, its queue,
    how many it assembled in the last hour and day, the failures, the last."""
    o = status.octopus
    assert o is not None
    parts = [
        _("adminview-octopus-on", per_tick=o.per_tick) if o.on else _("adminview-octopus-off"),
        _("adminview-octopus-queue", queue=o.queue, retrying=o.retrying),
        _("adminview-octopus-done", hour=o.hour, day=o.day),
        _("adminview-octopus-failed", failed=o.failed_hour),
    ]
    if o.last_name and o.last_at:
        at = datetime.fromisoformat(o.last_at) + timedelta(minutes=_DEFAULT_TZ_OFFSET_MIN)
        parts.append(
            _(
                "adminview-octopus-last",
                name=o.last_name,
                at=at.strftime("%H:%M"),
                versions=o.last_versions,
                review=o.last_review,
            )
        )
    return " · ".join(parts)


async def render_admin_home(
    repo: Repo,
    credentials: AdminCredentials,
    *,
    locale: str,
    keys: bool = True,
) -> tuple[str, InlineKeyboardMarkup]:
    """The home; `keys` is the super-admin's alone (#232): an app admin's
    has no «Ключи»."""
    _ = translator("adminview", locale)
    status = await admin_status(repo, credentials=credentials)

    async def key_line(name: str, not_configured: str) -> str:
        # Steam's key is admin-settable and can be genuinely "not configured"
        # (#17), as PSN's NPSSO can, so both get the same three-way line.
        state = status.credential(name)
        if state is None or not state.configured:
            return _(not_configured)
        return await _key_status_line(
            state.status or TokenStatus.ACTIVE,
            state.checked_at,
            active_value=TokenStatus.ACTIVE,
            locale=locale,
        )

    # Same "always show when this was last true" treatment /online's table
    # gives its own header — this screen refreshes itself on a timer
    # (poller/admin_refresh.py), so a bare title alone would leave no way to
    # tell a fresh render from one that silently stopped updating.
    updated_label = local_now(_DEFAULT_TZ_OFFSET_MIN).strftime("%H:%M")
    rows = usage_rows(status, locale=locale)

    text = _(
        "adminview-home",
        updated=updated_label,
        users=status.users,
        excluded=status.excluded,
        xbox_linked=status.xbox_linked,
        xbox_active=status.xbox_active,
        xbox_broken=status.xbox_broken,
        steam_linked=status.steam_linked,
        psn_linked=status.psn_linked,
        chats=status.chats,
        api_lines="\n".join(f"{label}: {value}" for label, value in rows[:-1]),
        steam_key_line=await key_line("steam", "adminview-steam-not-configured"),
        psn_key_line=await key_line("psn", "adminview-psn-not-configured"),
        mail_line=f"{rows[-1][0]}: {rows[-1][1]}",
    )
    keys_row = [InlineKeyboardButton(text=_("adminview-btn-keys"), callback_data="a:keys")]
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translator("admin", locale)("admin-settings-button"),
                    callback_data="a:set",
                )
            ],
            [InlineKeyboardButton(text=_("adminview-btn-users"), callback_data="a:users:0")],
            [InlineKeyboardButton(text=_("adminview-btn-chats"), callback_data="a:chats")],
        ]
        + ([keys_row] if keys else [])
    )
    return text, keyboard
