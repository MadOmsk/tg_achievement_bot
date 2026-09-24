"""The super-admin panel's screens (#63).

Everything /admin draws: the home card, the keys screen, the user list and
one person's card, the chat list and one chat's card with its three
sub-screens, the numeric-limit menus, the wipe confirmations. The handler
file next door keeps the routing, the text-input state machine, and the
actions themselves — resyncs, resets, deletions.

The home card itself is in views/admin_home.py, separate for the older
reason: poller/admin_refresh.py redraws it on a timer.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.constants import (
    Platform,
    PresenceState,
    TokenStatus,
)
from bot.db.repo import AdminUserRow, ChatTarget, PlatformLink, Repo, User
from bot.i18n import translator
from bot.services.admin_settings import (
    DEFAULT_RARITY_MODE_DEFAULT,
    DEFAULT_RARITY_MODE_KEY,
    DEFAULT_SHOW_LINKS_DEFAULT,
    DEFAULT_SHOW_LINKS_KEY,
    FLOOD_LIMIT_MAX,
    FLOOD_LIMIT_MIN,
    FLOOD_WINDOW_MAX,
    FLOOD_WINDOW_MIN,
    NUMERIC_SETTINGS,
    PAGE_SIZE,
    STATUS_ICON,
    TOAST_PREVIEW_MAX_CHARS,
    VISIBILITY_ICON,
    NumericSetting,
)
from bot.services.naming import (
    account_nickname,
    person_name,
    subscriber_names,
    xbox_nickname,
)
from bot.services.psn.auth import STATUS_NOT_CONFIGURED as PSN_NOT_CONFIGURED
from bot.services.psn.auth import PsnAuth
from bot.services.stats import month_cutoff_utc, today_cutoff_utc
from bot.services.steam.auth import STATUS_NOT_CONFIGURED as STEAM_NOT_CONFIGURED
from bot.services.steam.auth import SteamAuth
from bot.services.translate.auth import STATUS_NOT_CONFIGURED as ANTHROPIC_NOT_CONFIGURED
from bot.services.translate.auth import AnthropicAuth
from bot.util import humanize_ago
from bot.views import Screen
from bot.views.inline_lists import InlineListing, button_rows, page_nav, paginate
from bot.views.keyboards import (
    COMMON_OFFSETS_HOURS,
    format_offset,
    format_rarity,
    locale_name,
)
from bot.views.lists import Listing, truncate_name
from bot.views.parts import (
    COMPLETED_BADGE_PSN,
    COMPLETED_BADGE_STEAM,
    COMPLETED_BADGE_XBOX,
    plural_achievements,
    plural_trophies,
    visibility_status_text,
)


async def find_chat(repo: Repo, chat_id: int) -> ChatTarget | None:
    return next((c for c in await repo.admin_chats() if c.chat_id == chat_id), None)


def _cancel_input_keyboard(*, locale: str) -> InlineKeyboardMarkup:
    _ = translator("admin", locale)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("admin-cancel"), callback_data="a:psncancel")]
        ]
    )


# ---- Platform keys (#17) ----


async def render_keys(
    steam_auth: SteamAuth, psn_auth: PsnAuth, anthropic_auth: AnthropicAuth, *, locale: str
) -> tuple[str, InlineKeyboardMarkup]:
    _ = translator("admin", locale)
    steam_configured = await steam_auth.status() != STEAM_NOT_CONFIGURED
    psn_configured = await psn_auth.status() != PSN_NOT_CONFIGURED
    anthropic_configured = await anthropic_auth.status() != ANTHROPIC_NOT_CONFIGURED
    text = _(
        "admin-keys-screen",
        steam=_("admin-keys-set") if steam_configured else _("admin-keys-unset"),
        psn=_("admin-keys-set") if psn_configured else _("admin-keys-unset"),
        anthropic=_("admin-keys-set") if anthropic_configured else _("admin-keys-unset"),
    )
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=_("admin-keys-psn-change") if psn_configured else _("admin-keys-psn-add"),
            callback_data="a:keyset:psn",
        )
    )
    if psn_configured:
        builder.row(
            InlineKeyboardButton(text=_("admin-keys-psn-clear"), callback_data="a:keyclr:psn")
        )
    builder.row(
        InlineKeyboardButton(
            text=_("admin-keys-steam-change") if steam_configured else _("admin-keys-steam-add"),
            callback_data="a:keyset:steam",
        )
    )
    if steam_configured:
        builder.row(
            InlineKeyboardButton(text=_("admin-keys-steam-clear"), callback_data="a:keyclr:steam")
        )
    builder.row(
        InlineKeyboardButton(
            text=_("admin-keys-anthropic-change")
            if anthropic_configured
            else _("admin-keys-anthropic-add"),
            callback_data="a:keyset:anthropic",
        )
    )
    if anthropic_configured:
        builder.row(
            InlineKeyboardButton(
                text=_("admin-keys-anthropic-clear"), callback_data="a:keyclr:anthropic"
            )
        )
    builder.row(InlineKeyboardButton(text=_("admin-back"), callback_data="a:home"))
    return text, builder.as_markup()


def _format_limit(key: str, value: str, *, locale: str) -> str:
    _ = translator("admin", locale)
    spec = NUMERIC_SETTINGS[key]
    return _(spec.zero_label) if value == "0" else value


def _setting_label(spec: NumericSetting, *, locale: str) -> str:
    _ = translator("admin", locale)
    return _(spec.label)


def _hour_grid_markup(
    current: str, set_prefix: str, tz_callback: str, back_callback: str, *, locale: str
) -> InlineKeyboardMarkup:
    _ = translator("admin", locale)
    builder = InlineKeyboardBuilder()
    for hour in range(24):
        label = f"{hour:02d}"
        mark = "• " if current.startswith(label) else ""
        builder.add(
            InlineKeyboardButton(text=f"{mark}{label}", callback_data=f"{set_prefix}{hour}")
        )
    builder.adjust(6)
    builder.row(InlineKeyboardButton(text=_("admin-timezone-button"), callback_data=tz_callback))
    builder.row(InlineKeyboardButton(text=_("admin-back"), callback_data=back_callback))
    return builder.as_markup()


def _tz_grid_markup(
    current_minutes: int, set_prefix: str, manual_callback: str, back_callback: str, *, locale: str
) -> InlineKeyboardMarkup:
    _ = translator("admin", locale)
    builder = InlineKeyboardBuilder()
    for hours in COMMON_OFFSETS_HOURS:
        minutes = hours * 60
        mark = "• " if minutes == current_minutes else ""
        builder.add(
            InlineKeyboardButton(
                text=f"{mark}{format_offset(minutes)}", callback_data=f"{set_prefix}{minutes}"
            )
        )
    builder.adjust(4)
    builder.row(
        InlineKeyboardButton(text=_("admin-timezone-manual"), callback_data=manual_callback)
    )
    builder.row(InlineKeyboardButton(text=_("admin-back"), callback_data=back_callback))
    return builder.as_markup()


def _toast_preview(preview: str) -> str:
    collapsed = " ".join(preview.splitlines())
    if len(collapsed) <= TOAST_PREVIEW_MAX_CHARS:
        return collapsed
    return collapsed[: TOAST_PREVIEW_MAX_CHARS - 1] + "…"


async def render_new_user_defaults(repo: Repo, *, locale: str) -> tuple[str, InlineKeyboardMarkup]:
    """Settings that only ever apply at the moment someone new subscribes —
    grouped on their own screen (2026-09-05 follow-up) rather than sitting
    on the home screen forever, since none of them affect anyone already
    subscribed. Just default_rarity_mode for now (SPEC 9, M-Steam-2e's own
    Repo.subscribe reads it) — the natural home for anything else of the
    same shape added later."""
    _ = translator("admin", locale)
    default_rarity_mode = await repo.get_app_setting(
        DEFAULT_RARITY_MODE_KEY, DEFAULT_RARITY_MODE_DEFAULT
    )
    assert default_rarity_mode is not None  # a default was given above
    default_show_links = await repo.get_int_setting(
        DEFAULT_SHOW_LINKS_KEY, int(DEFAULT_SHOW_LINKS_DEFAULT)
    )

    text = _("admin-new-users-screen")
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_(
                        "admin-default-rarity",
                        rarity=format_rarity(default_rarity_mode),
                    ),
                    callback_data="a:defaultrarity",
                )
            ],
            [
                InlineKeyboardButton(
                    text=_(
                        "admin-default-links",
                        visible=_("admin-yes") if default_show_links else _("admin-no"),
                    ),
                    callback_data="a:defaultlinks",
                )
            ],
            [InlineKeyboardButton(text=_("admin-back"), callback_data="a:home")],
        ]
    )
    return text, keyboard


async def render_user_list(
    repo: Repo, page: int, *, locale: str
) -> tuple[str, InlineKeyboardMarkup]:
    _ = translator("admin", locale)
    users = await repo.admin_users()
    if not users:
        return _("admin-users-empty"), _back_home(locale=locale)

    # By tg_id, not xuid (2026-09-05 follow-up) — the old xuid-keyed lookup
    # showed 0 for a Steam-only person's achievements, and only the Xbox
    # half of the count for someone with both platforms.
    today = await repo.achievement_counts_by_tg_id(today_cutoff_utc())
    # This aggregate spans every user, with no single person's timezone to
    # key the calendar-month boundary off (#14) — the project default
    # (Europe/Moscow, +180) is the reference, same as admin_view.py's own
    # "updated HH:MM".
    month = await repo.achievement_counts_by_tg_id(month_cutoff_utc(180))

    shown = paginate(users, page, PAGE_SIZE)

    rows = []
    buttons = []
    for user in shown.items:
        # The person chain (#51), not "whichever platform answered first" —
        # this list is a roster of people, and its rows are how the operator
        # finds one. The bare id stays reachable as the last step, which on
        # this screen is diagnostic rather than a bad label.
        name = person_name(
            tg_id=user.tg_id,
            first_name=user.first_name,
            last_name=user.last_name,
            username=user.username,
            xbox=xbox_nickname(gamertag_modern=user.gamertag_modern, gamertag=user.gamertag),
            steam=user.steam_name,
            psn=user.psn_online_id,
        )
        rows.append(
            _(
                "admin-users-row",
                icon=_icon(user),
                name=truncate_name(name, 14),
                ago=humanize_ago(user.last_online_at, locale),
                today=today.get(user.tg_id, (0, 0))[0],
                month=month.get(user.tg_id, (0, 0))[0],
                note=_note(user, locale=locale),
            )
        )
        buttons.append(
            [InlineKeyboardButton(text=f"{_icon(user)} {name}", callback_data=f"a:u:{user.tg_id}")]
        )

    # The one screen that is both kinds of list at once, which is why the loop
    # above fills two collections: `Listing` renders the text half, an
    # `InlineListing` the tappable one, off the same people in the same order.
    keyboard = InlineListing(
        rows=buttons,
        nav=page_nav(shown, "a:users:", noop="a:noop"),
        tail=_back_row(locale=locale),
    ).markup()

    # A roster, not a report section, so it is never quoted (#64) — the whole
    # point is to skim it at a glance, same reasoning /online has. The rows
    # and their wrapper are Listing's own job; the header (with its page
    # count) and the trailing column hint stay outside it, exactly as the
    # blank-line spacing between them always looked.
    # The header no longer repeats the page count: it now sits on the
    # navigation row right below, between the arrows that act on it.
    body = Listing(rows=rows, quoted=False).body()
    text = "\n\n".join([_("admin-users-header"), body, _("admin-users-columns")])
    return text, keyboard


def _admin_tg_header(user: User, *, locale: str) -> str:
    """Telegram identity, always shown in full (2026-09-08 user request) —
    unlike /stats' header (one best single name), the admin needs to see
    everything at once for lookups. The bare tg_id is never "@"-prefixed:
    it isn't a real, resolvable username, only a genuine `user.username` is
    (mentioning a nonexistent "@<number>" account risks nothing today, but
    a real account could later register that exact numeric string as its
    username and retroactively become a target of every old message that
    did this)."""
    _ = translator("admin", locale)
    bits = []
    full_name = " ".join(part for part in (user.first_name, user.last_name) if part)
    if full_name:
        bits.append(full_name)
    if user.username:
        bits.append(f"@{user.username}")
    # As a string, not an int: Fluent formats a number for the locale, and
    # this one came out as "tg_id 127 383 366" — an identifier is not a
    # quantity, and that form is not even searchable.
    bits.append(_("admin-user-tgid", tg_id=str(user.tg_id)))
    return _("admin-user-header", identity=", ".join(bits))


async def _xbox_admin_block(repo: Repo, user: User, today_count: int, *, locale: str) -> list[str]:
    """One block, five fixed lines (2026-09-08 restructure, user request):
    nickname, id, status (+ when last checked), achievements, last online —
    each its own line instead of the old single achievements-and-all header
    line, so a long line no longer buries the id next to the nickname."""
    _ = translator("admin", locale)
    count = await repo.xbox_achievement_count(user.tg_id)
    completed = await repo.xbox_completed_games_count(user.xuid)
    parts = [plural_achievements(count, locale)]
    if completed:
        parts.append(f"{completed} {COMPLETED_BADGE_XBOX}")
    parts.append(_("admin-today-tag", count=today_count))
    parts.append(_("admin-gamerscore-tag", score=user.gamerscore or 0))

    token = await repo.get_token(user.tg_id)
    presence = await repo.presence_of(user.xuid)
    login = _("admin-login-not-connected")
    if token is not None:
        login = {
            TokenStatus.ACTIVE: _(
                "admin-login-active", ago=humanize_ago(token.last_refresh_at, locale)
            ),
            TokenStatus.INVALID: _("admin-login-invalid"),
            TokenStatus.REVOKED: _("admin-login-revoked"),
        }.get(token.status, token.status)

    online = _("admin-no-data")
    if presence is not None:
        # Presence gives no name for PC titles, so fall back to the cache
        # the poller fills — an id in the card tells the admin nothing.
        game = presence.title_name or ""
        if not game and presence.title_id:
            game = await repo.title_name(presence.title_id) or presence.title_id
        game = game or _("admin-no-game")
        online = (
            _(
                "admin-online-playing",
                ago=humanize_ago(presence.updated_at, locale),
                game=game,
            )
            if presence.state == PresenceState.ONLINE
            else humanize_ago(presence.updated_at, locale)
        )
    return [
        _(
            "admin-xbox-header",
            gamertag=xbox_nickname(
                gamertag_modern=user.gamertag_modern, gamertag=user.gamertag, xuid=user.xuid
            ),
        ),
        _("admin-xuid-tag", xuid=user.xuid),
        _("admin-login-row", login=login),
        "  ·  ".join(parts),
        _("admin-online-row", online=online),
    ]


async def _steam_admin_block(
    repo: Repo, link: PlatformLink, today_count: int, *, locale: str
) -> list[str]:
    """Steam's counterpart of `_xbox_admin_block` — same five-line shape,
    its "status" line is achievement *visibility* (there is no login/token
    to be active or dead), worded exactly like /panel's own status
    (`visibility_status_text`, shared so the two never drift)."""
    _ = translator("admin", locale)
    count = await repo.platform_achievement_count(link.tg_id, Platform.STEAM)
    completed = await repo.steam_completed_games_count(link.tg_id)
    parts = [plural_achievements(count, locale)]
    if completed:
        parts.append(f"{completed} {COMPLETED_BADGE_STEAM}")
    parts.append(_("admin-today-tag", count=today_count))

    steam_presence = await repo.steam_presence_of(link.external_id)
    online = _("admin-no-data")
    if steam_presence is not None:
        game = steam_presence.game_name or (_("admin-no-game") if steam_presence.gameid else "")
        is_online = (steam_presence.persona_state or 0) != 0
        online = (
            _(
                "admin-online-playing",
                ago=humanize_ago(steam_presence.updated_at, locale),
                game=game,
            )
            if is_online and game
            else (
                _("admin-online-idle")
                if is_online
                else humanize_ago(steam_presence.updated_at, locale)
            )
        )
    return [
        _(
            "admin-steam-header",
            name=account_nickname(
                Platform.STEAM,
                display_name=link.display_name,
                secondary_name=link.secondary_name,
                external_id=link.external_id,
            ),
        ),
        _("admin-steamid-tag", external_id=link.external_id),
        _("admin-login-row", login=visibility_status_text(link, locale)),
        "  ·  ".join(parts),
        _("admin-online-row", online=online),
    ]


async def _psn_admin_block(
    repo: Repo, link: PlatformLink, today_count: int, *, locale: str
) -> list[str]:
    """PSN's counterpart — five lines now, same shape as Xbox/Steam
    (issue #1's presence poller, poller/psn_presence.py): trophy sync
    itself still has no presence hook at all (that's a separate, permanent
    design decision — see CLAUDE.md's PSN section), but /online's presence
    tracking is unrelated to it, so this block gets its "last online" line
    back same as the other two platforms."""
    _ = translator("admin", locale)
    count = await repo.platform_achievement_count(link.tg_id, Platform.PSN)
    platinum = await repo.psn_platinum_count(link.tg_id)
    parts = [plural_trophies(count, locale)]
    if platinum:
        parts.append(f"{platinum} {COMPLETED_BADGE_PSN}")
    parts.append(_("admin-today-tag", count=today_count))
    if link.psn_trophy_level is not None:
        parts.append(_("admin-psn-level-tag", level=link.psn_trophy_level))

    psn_presence = await repo.psn_presence_of(link.external_id)
    online = _("admin-no-data")
    if psn_presence is not None:
        game = psn_presence.title_name or (_("admin-no-game") if psn_presence.title_id else "")
        is_online = psn_presence.state == PresenceState.ONLINE
        online = (
            _(
                "admin-online-playing",
                ago=humanize_ago(psn_presence.updated_at, locale),
                game=game,
            )
            if is_online and game
            else (
                _("admin-online-idle")
                if is_online
                else humanize_ago(psn_presence.updated_at, locale)
            )
        )
    return [
        _(
            "admin-psn-header",
            name=account_nickname(
                Platform.PSN,
                display_name=link.display_name,
                secondary_name=link.secondary_name,
                external_id=link.external_id,
            ),
        ),
        _("admin-psn-id-tag", external_id=link.external_id),
        _("admin-login-row", login=visibility_status_text(link, locale)),
        "  ·  ".join(parts),
        _("admin-online-row", online=online),
    ]


async def render_user_card(
    repo: Repo, tg_id: int, *, locale: str
) -> tuple[str, InlineKeyboardMarkup]:
    _ = translator("admin", locale)
    user = await repo.get_user(tg_id)
    steam_link = await repo.get_platform_link(tg_id, Platform.STEAM)
    psn_link = await repo.get_platform_link(tg_id, Platform.PSN)
    # Used to bail out on `not user.xuid` alone (2026-09-05 follow-up) — a
    # A Steam-only person got a "user not found" result in the admin panel,
    # same class of gap /stats had before it learned to work without Xbox.
    if user is None or (not user.xuid and steam_link is None and psn_link is None):
        return _("admin-user-not-found"), _back_home(locale=locale)

    today_xbox, today_steam, today_psn = await repo.achievement_platform_breakdown(
        tg_id, today_cutoff_utc()
    )
    chats = await repo.chats_of_user(tg_id)

    # Telegram identity first (2026-09-08 user request), then one block per
    # connected platform in the one display order — Xbox, PlayStation, Steam
    # (constants.platform_display_rank) — each block grouping everything about
    # that platform together (nickname/id, status, achievements, last online
    # where it applies), five fixed lines each (2026-09-08 restructure)
    # instead of one crowded header line.
    lines = [_admin_tg_header(user, locale=locale), ""]
    if user.xuid:
        lines += await _xbox_admin_block(repo, user, today_xbox, locale=locale)
        lines.append("")
    if psn_link is not None:
        lines += await _psn_admin_block(repo, psn_link, today_psn, locale=locale)
        lines.append("")
    if steam_link is not None:
        lines += await _steam_admin_block(repo, steam_link, today_steam, locale=locale)
        lines.append("")

    # The combined cross-platform counters line that used to follow here
    # was dropped (2026-09-08, user request) — each platform block above
    # already has its own achievements line, and a combined total added
    # nothing beyond that.
    lines += [
        _(
            "admin-subscribed",
            chats=", ".join(f"«{c}»" for c in chats) if chats else _("admin-nowhere"),
        ),
    ]
    text = "\n".join(lines)
    if user.is_excluded:
        text += "\n\n" + _("admin-excluded")

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=_("admin-restore") if user.is_excluded else _("admin-exclude"),
            callback_data=f"a:excl:{tg_id}:{0 if user.is_excluded else 1}",
        )
    )
    if user.xuid:
        builder.row(
            InlineKeyboardButton(
                text=_("admin-refresh-xbox"), callback_data=f"a:sync:xbox:{tg_id}"
            ),
            InlineKeyboardButton(text=_("admin-reset-xbox"), callback_data=f"a:reset:xbox:{tg_id}"),
        )
    if psn_link is not None:
        builder.row(
            InlineKeyboardButton(text=_("admin-refresh-psn"), callback_data=f"a:sync:psn:{tg_id}"),
            InlineKeyboardButton(text=_("admin-reset-psn"), callback_data=f"a:reset:psn:{tg_id}"),
        )
    if steam_link is not None:
        builder.row(
            InlineKeyboardButton(
                text=_("admin-refresh-steam"), callback_data=f"a:sync:steam:{tg_id}"
            ),
            InlineKeyboardButton(
                text=_("admin-reset-steam"), callback_data=f"a:reset:steam:{tg_id}"
            ),
        )
    builder.row(InlineKeyboardButton(text=_("admin-delete-user"), callback_data=f"a:udel:{tg_id}"))
    builder.row(InlineKeyboardButton(text=_("admin-back-to-users"), callback_data="a:users:0"))
    return text, builder.as_markup()


# Plain platform names for the confirm prompt's own sentence — distinct
# from the "🔄 Обновить X" / "🗑 Сброс X" button labels, which read wrong
# spliced into "Стереть базу <label> для...".


async def render_chat_list(repo: Repo, *, locale: str) -> tuple[str, InlineKeyboardMarkup]:
    """Unlike the user list above, this one is buttons only — a chat row is
    two facts wide, and both fit on the button, so there is no separate text
    row to write. It used to call `Listing` with an empty row list to look
    like it shared the text machinery; that rendered nothing, and a keyboard
    list now has machinery of its own to share instead."""
    _ = translator("admin", locale)
    chats = await repo.admin_chats()
    if not chats:
        return _("admin-chats-empty"), _back_home(locale=locale)

    def label(chat: ChatTarget) -> str:
        return _(
            "admin-chat-list-row",
            mark="" if chat.is_active else "⏸ ",
            title=chat.title or chat.chat_id,
            subscribers=chat.subscribers,
        )

    keyboard = InlineListing(
        rows=button_rows(chats, label, lambda chat: f"a:chat:{chat.chat_id}"),
        tail=_back_row(locale=locale),
    ).markup()
    return _("admin-chats-header"), keyboard


async def render_chat_card(
    repo: Repo, chat_id: int, *, locale: str, section: str | None = None
) -> tuple[str, InlineKeyboardMarkup]:
    """The chat card. `section` picks which keyboard goes under it: the root
    card, or one of its three sub-screens (2026-09-11, user request — the
    rows that used to cram two to four buttons side by side each became a
    submenu instead). The *text* never changes, so a person tuning the
    anti-flood window still sees the whole chat's state above the buttons,
    and every toggle redraws the section it lives in rather than throwing
    the person back to the root."""
    _ = translator("admin", locale)
    chat = await find_chat(repo, chat_id)
    if chat is None:
        return _("admin-chat-not-found-period"), _back_home(locale=locale)

    names = subscriber_names(await repo.chat_subscribers(chat_id))
    threshold_label = f"{chat.rare_threshold_percent:g}%"
    zone_label = format_offset(chat.tz_offset_min)
    flood_label = (
        _("admin-chat-flood-value", limit=chat.flood_limit, window=chat.flood_window_minutes)
        if chat.flood_limit > 0
        else _("admin-chat-flood-off")
    )
    text = _(
        "admin-chat-card",
        title=chat.title or chat_id,
        state=_("admin-active") if chat.is_active else _("admin-inactive"),
        subscribers=chat.subscribers,
        threshold=threshold_label,
        summary=_("admin-yes") if chat.daily_summary else _("admin-no"),
        time=chat.daily_summary_time,
        offset=zone_label,
        min_score=chat.min_gamerscore,
        flood=flood_label,
        locale_name=locale_name(chat.locale),
        names=(
            _("admin-subscribers-list", names=", ".join(names))
            if names
            else _("admin-no-subscribers")
        ),
    )
    builder = InlineKeyboardBuilder()
    back_to_card = InlineKeyboardButton(text=_("admin-back"), callback_data=f"a:chat:{chat_id}")
    summary_state = _("admin-enabled") if chat.daily_summary else _("admin-disabled-state")

    if section == "summary":
        builder.row(
            InlineKeyboardButton(
                text=_("admin-chat-summary-button", state=summary_state),
                callback_data=f"a:cds:{chat_id}",
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=_("admin-chat-time-button", time=chat.daily_summary_time, offset=zone_label),
                callback_data=f"a:ctime:{chat_id}",
            )
        )
        builder.row(back_to_card)
        return text, builder.as_markup()

    if section == "flood":
        builder.row(
            InlineKeyboardButton(
                text=_(
                    "admin-chat-flood-toggle-button",
                    state=_("admin-enabled") if chat.flood_limit > 0 else _("admin-disabled-state"),
                ),
                callback_data=f"a:cfltoggle:{chat_id}",
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=_("admin-chat-flood-button", limit=chat.flood_limit),
                callback_data=f"a:cfl:{chat_id}",
            ),
            InlineKeyboardButton(
                text=_("admin-chat-flood-window-button", window=chat.flood_window_minutes),
                callback_data=f"a:cflw:{chat_id}",
            ),
        )
        builder.row(back_to_card)
        return text, builder.as_markup()

    if section == "messages":
        # One wipe action per row here: these are the destructive ones, and a
        # cramped row of four 🗑 buttons was exactly what made them easy to
        # mistap (2026-09-11, user request).
        builder.row(
            InlineKeyboardButton(text=_("admin-delete-last"), callback_data=f"a:cdellast:{chat_id}")
        )
        builder.row(
            InlineKeyboardButton(text=_("admin-wipe-bot-24h"), callback_data=f"a:cwipe:{chat_id}")
        )
        builder.row(
            InlineKeyboardButton(
                text=_("admin-wipe-system-24h"), callback_data=f"a:cswipe:{chat_id}"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=_("admin-wipe-system-all"), callback_data=f"a:cswipeall:{chat_id}"
            )
        )
        builder.row(back_to_card)
        return text, builder.as_markup()

    # The root card: one entry per group, each carrying the state a person
    # would otherwise have to open the submenu to read.
    builder.row(
        InlineKeyboardButton(
            text=_("admin-chat-threshold-button", threshold=threshold_label),
            callback_data=f"a:crt:{chat_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=_("admin-chat-summary-menu-button", state=summary_state),
            callback_data=f"a:msum:{chat_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=_("admin-chat-flood-menu-button", value=flood_label),
            callback_data=f"a:mflood:{chat_id}",
        )
    )
    # The chat's own language (#48) — a group cannot be per-viewer, so this
    # is one shared setting, currently the super-admin's to move (issue #47
    # is about handing every chat setting to a chat admin, this one too).
    builder.row(
        InlineKeyboardButton(
            text=_("admin-chat-locale-button", name=locale_name(chat.locale)),
            callback_data=f"a:cloc:{chat_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=_("admin-disable-chat") if chat.is_active else _("admin-enable-chat"),
            callback_data=f"a:coff:{chat_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=_("admin-chat-messages-menu-button"), callback_data=f"a:mdel:{chat_id}"
        )
    )
    builder.row(InlineKeyboardButton(text=_("admin-back-to-chats"), callback_data="a:chats"))
    return text, builder.as_markup()


# ------------------------------------------------------------------- helpers


def _back_row(*, locale: str) -> list[InlineKeyboardButton]:
    """The way out, as a row — every list screen here ends in one."""
    _ = translator("admin", locale)
    return [InlineKeyboardButton(text=_("admin-back"), callback_data="a:home")]


def _back_home(*, locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[_back_row(locale=locale)])


def _icon(user: AdminUserRow) -> str:
    """Platform dots plus status icons — Xbox login/token status,
    Steam and PSN achievement visibility (public = ✅, private = ⚠️)."""
    if user.is_excluded:
        return "🚫"
    parts = []
    if user.xuid:
        parts.append("🟢" + STATUS_ICON.get(user.token_status or "", "—"))
    if user.steam_id:
        parts.append("⚫" + VISIBILITY_ICON.get(user.steam_achievements_visible, "—"))
    if user.psn_account_id:
        parts.append("🔵" + VISIBILITY_ICON.get(user.psn_achievements_visible, "—"))
    return "".join(parts)


def _note(user: AdminUserRow, *, locale: str) -> str:
    _ = translator("admin", locale)
    if user.is_excluded:
        return _("admin-note-excluded")
    if user.token_status == TokenStatus.INVALID:
        return _("admin-note-invalid")
    if user.token_status == TokenStatus.REVOKED:
        return _("admin-note-revoked")
    return ""


# ---- the screens that ask for one typed value, and the confirmations ----
#
# Each of these used to be built inside its own handler (#63's last
# leftovers). They are one shape: a prompt saying what is set now and what
# is allowed, and a single way back — the flow's state ("who is typing
# what") stays with the handler, because it is not layout.


async def render_limits(repo: Repo, *, locale: str) -> Screen:
    """Every global numeric setting with its current value, each row opening
    its own input — a settings list rather than a menu you have to walk to
    find out what is set."""
    _ = translator("admin", locale)
    # The value is read before the rows are built, not inside the loop that
    # builds them: a label here is a setting *and* what it is currently set
    # to, and only this screen's own rows know how to say that.
    settings = [
        (key, spec, await repo.get_app_setting(key, str(spec.default)))
        for key, spec in NUMERIC_SETTINGS.items()
    ]
    keyboard = InlineListing(
        rows=button_rows(
            settings,
            lambda item: (
                f"{_setting_label(item[1], locale=locale)}: "
                f"{_format_limit(item[0], item[2], locale=locale)} ▸"
            ),
            lambda item: f"a:limit:{item[0]}",
        ),
        tail=_back_row(locale=locale),
    ).markup()
    return Screen(_("admin-limits-screen"), keyboard)


async def render_limit(repo: Repo, key: str, *, locale: str) -> Screen:
    _ = translator("admin", locale)
    spec = NUMERIC_SETTINGS[key]
    current = await repo.get_app_setting(key, str(spec.default))
    # What a 0 means for *this* setting, spelled out only where 0 is allowed
    # at all. This line raised TypeError from 2026-09-11 until #63's own
    # audit found it: the locale ended up inside the f-string instead of in
    # the call, so every limit whose minimum is 0 — the two list caps — blew
    # up the moment the screen was opened.
    zero_hint = f" (0 — {_format_limit(key, '0', locale=locale)})" if spec.min == 0 else ""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=_("admin-back"), callback_data="a:limits"))
    return Screen(
        _(
            "admin-limit-prompt",
            label=_setting_label(spec, locale=locale),
            current=_format_limit(key, current, locale=locale),
            minimum=spec.min,
            maximum=spec.max,
            zero_hint=zero_hint,
        ),
        builder.as_markup(),
    )


def _chat_input_screen(key: str, chat_id: int, *, locale: str, **fields: object) -> Screen:
    _ = translator("admin", locale)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=_("admin-back"), callback_data=f"a:chat:{chat_id}"))
    return Screen(_(key, **fields), builder.as_markup())


def render_rare_prompt(chat: ChatTarget, *, locale: str) -> Screen:
    return _chat_input_screen(
        "admin-chat-threshold-prompt",
        chat.chat_id,
        locale=locale,
        title=chat.title or chat.chat_id,
        value=f"{chat.rare_threshold_percent:g}",
    )


def render_flood_limit_prompt(chat: ChatTarget, *, locale: str) -> Screen:
    return _chat_input_screen(
        "admin-chat-flood-prompt",
        chat.chat_id,
        locale=locale,
        title=chat.title or chat.chat_id,
        value=chat.flood_limit,
        minimum=FLOOD_LIMIT_MIN,
        maximum=FLOOD_LIMIT_MAX,
    )


def render_flood_window_prompt(chat: ChatTarget, *, locale: str) -> Screen:
    return _chat_input_screen(
        "admin-chat-flood-window-prompt",
        chat.chat_id,
        locale=locale,
        title=chat.title or chat.chat_id,
        value=chat.flood_window_minutes,
        minimum=FLOOD_WINDOW_MIN,
        maximum=FLOOD_WINDOW_MAX,
    )


def render_zone_manual_prompt(chat: ChatTarget, *, locale: str) -> Screen:
    """Back goes to the zone grid this was opened from, not to the card."""
    _ = translator("admin", locale)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=_("admin-back"), callback_data=f"a:ctz:{chat.chat_id}"))
    return Screen(
        _(
            "admin-chat-zone-manual-prompt",
            title=chat.title or chat.chat_id,
            offset=format_offset(chat.tz_offset_min),
        ),
        builder.as_markup(),
    )


def render_wipe_prompt(chat: ChatTarget, count: int, hours: int, *, locale: str) -> Screen:
    """The prompt says how many messages it is about to take — a destructive
    action states its own size before it happens."""
    _ = translator("admin", locale)
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=_("admin-confirm-delete"), callback_data=f"a:cwipey:{chat.chat_id}"
        )
    )
    builder.row(
        InlineKeyboardButton(text=_("admin-cancel"), callback_data=f"a:chat:{chat.chat_id}")
    )
    return Screen(
        _("admin-wipe-prompt", count=count, title=chat.title or chat.chat_id, hours=hours),
        builder.as_markup(),
    )


RESET_PLATFORM_NAMES = {"xbox": "XBOX", "steam": "Steam", "psn": "PSN"}


def render_reset_confirm(platform: str, tg_id: str, *, locale: str) -> Screen:
    """ "Сброс базы" is destructive and not undoable (2026-09-08 user
    request) — same one-tap-confirm shape as /disconnect_steam's own
    prompt, not an instant action behind a single tap."""
    _ = translator("admin", locale)
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=_("admin-reset-confirm-yes"), callback_data=f"a:resetok:{platform}:{tg_id}"
        ),
        InlineKeyboardButton(text=_("admin-cancel"), callback_data=f"a:u:{tg_id}"),
    )
    return Screen(
        _("admin-reset-confirm-prompt", platform=RESET_PLATFORM_NAMES[platform]),
        builder.as_markup(),
    )


def render_system_wipe_prompt(
    chat: ChatTarget, count: int, confirm_callback: str, *, locale: str
) -> Screen:
    """Same shape as the 24-hour wipe above, for the "system messages only"
    pair — the confirm target differs, the prompt does not."""
    _ = translator("admin", locale)
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=_("admin-confirm-delete"), callback_data=confirm_callback)
    )
    builder.row(
        InlineKeyboardButton(text=_("admin-cancel"), callback_data=f"a:chat:{chat.chat_id}")
    )
    return Screen(
        _("admin-system-wipe-prompt", count=count, title=chat.title or chat.chat_id),
        builder.as_markup(),
    )


def render_admin_user_delete_confirm_1(name: str, tg_id: int, *, locale: str) -> Screen:
    _ = translator("admin", locale)
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=_("admin-delete-confirm-1-yes"), callback_data=f"a:udel1:{tg_id}"
        ),
        InlineKeyboardButton(text=_("admin-cancel"), callback_data=f"a:u:{tg_id}"),
    )
    return Screen(
        _("admin-delete-confirm-1", name=name, tg_id=tg_id),
        builder.as_markup(),
    )


def render_admin_user_delete_confirm_2(name: str, tg_id: int, *, locale: str) -> Screen:
    _ = translator("admin", locale)
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=_("admin-delete-confirm-2-yes"), callback_data=f"a:udel2:{tg_id}"
        ),
        InlineKeyboardButton(text=_("admin-cancel"), callback_data=f"a:u:{tg_id}"),
    )
    return Screen(
        _("admin-delete-confirm-2", name=name, tg_id=tg_id),
        builder.as_markup(),
    )
