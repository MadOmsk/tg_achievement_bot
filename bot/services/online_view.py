"""Rendering /online's table (SPEC 6.3) — shared by the command itself
(handlers/chat.py) and the auto-refresh poller (poller/online_refresh.py,
Follow-up 2026-09-05), so a live-updating table looks exactly like the one
/online posts fresh. Split out of handlers/chat.py so the poller (which must
not import from handlers — services are the one layer both may depend on)
can build the same text.
"""

from __future__ import annotations

from bot.constants import PresenceState
from bot.db.repo import ChatPresenceRow
from bot.i18n import translator
from bot.services.achievements import PLATFORM_ICON, PLATFORM_ICON_UNKNOWN

# The chat's own locale travels in (#48) — the auto-refresh poller renders
# this table for every chat in one loop, so it cannot live in module state.


def presence_text(row: ChatPresenceRow, locale: str) -> str:
    _ = translator("onlineview", locale)
    if row.state == PresenceState.ONLINE and row.title_id:
        return _("onlineview-playing", where=row.title_name or row.title_id)
    if row.state == PresenceState.ONLINE:
        return _("onlineview-online-idle")
    if row.state is not None:
        return _("onlineview-offline")
    return _("onlineview-no-data")


def presence_icon(row: ChatPresenceRow) -> str:
    # Platform colour while online (SPEC 9, M-Steam-2e) — grey for
    # offline/no data regardless of platform. Found live: a pure platform
    # colour made every offline row look the same as an online one at a
    # glance, losing the one signal a colour is actually good for.
    if row.state != PresenceState.ONLINE:
        return PLATFORM_ICON_UNKNOWN
    return PLATFORM_ICON.get(row.platform, PLATFORM_ICON_UNKNOWN)


def _row_name(row: ChatPresenceRow) -> str:
    """The nickname of whichever platform `row.platform` points at — the one
    being played, or (while offline) the last-active one that actually has
    tracked presence; see chat_member_presence()'s docstring. `platform ==
    "none"` means no tracked presence exists anywhere (PSN-only, or never
    polled yet) — falls back to the Telegram name, deliberately *not*
    "@username" (Follow-up 2026-09-08, reverting an earlier attempt): this
    table auto-refreshes every few minutes, and a live "@mention" would ping
    that person's Telegram client on every single refresh.
    """
    if row.platform == "modern" and row.gamertag:
        return row.gamertag
    if row.platform == "steam" and row.steam_display_name:
        return row.steam_display_name
    if row.platform == "psn" and row.psn_display_name:
        return row.psn_display_name
    full_name = " ".join(part for part in (row.first_name, row.last_name) if part)
    if full_name:
        return full_name
    if row.username:
        return row.username  # no "@" on purpose — see the docstring above
    return f"id{row.tg_id}"


def render_online_table(rows: list[ChatPresenceRow], updated_label: str, locale: str) -> str:
    """`updated_label` is a ready-made "HH:MM" in the chat's own timezone
    (Follow-up 2026-09-05, the "Обновлено: …" line) — this module has no
    idea what timezone a chat is in, that's services/stats.py's
    local_now()'s job, done by the caller (handlers/chat.py,
    poller/online_refresh.py alike)."""
    _ = translator("onlineview", locale)
    lines = [_("onlineview-header"), _("onlineview-updated", updated=updated_label), ""]
    for row in rows:
        lines.append(
            _(
                "onlineview-row",
                icon=presence_icon(row),
                name=_row_name(row),
                status=presence_text(row, locale),
            )
        )
    return "\n".join(lines)
