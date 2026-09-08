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
from bot.i18n import gettext
from bot.services.achievements import PLATFORM_ICON, PLATFORM_ICON_UNKNOWN
from bot.services.tables import resolve_display_name

_ = lambda key, **kwargs: gettext("onlineview", key, **kwargs)  # noqa: E731


def presence_text(row: ChatPresenceRow) -> str:
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


def render_online_table(rows: list[ChatPresenceRow], updated_label: str) -> str:
    """`updated_label` is a ready-made "HH:MM" in the chat's own timezone
    (Follow-up 2026-09-05, the "Обновлено: …" line) — this module has no
    idea what timezone a chat is in, that's services/stats.py's
    local_now()'s job, done by the caller (handlers/chat.py,
    poller/online_refresh.py alike)."""
    lines = [_("onlineview-header"), _("onlineview-updated", updated=updated_label), ""]
    for row in rows:
        name = (
            resolve_display_name(
                username=row.username,
                first_name=row.first_name,
                last_name=row.last_name,
                gamertag=row.gamertag,
            )
            or f"id{row.tg_id}"
        )
        lines.append(
            _("onlineview-row", icon=presence_icon(row), name=name, status=presence_text(row))
        )
    return "\n".join(lines)
