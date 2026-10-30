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

from collections.abc import Callable
from html import escape as html_escape
from typing import Literal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import Settings
from bot.constants import (
    AccountPlatform,
    Platform,
    PresenceState,
    RarityMode,
    TokenStatus,
)
from bot.db.repo import AdminUserRow, ChatTarget, PlatformLink, Repo, User
from bot.i18n import translator
from bot.services import roles
from bot.services.admin_actions import ActionView, AdminContext, Confirm, Target
from bot.services.admin_actions import available as available_actions
from bot.services.admin_credentials import AdminCredentials, CredentialState
from bot.services.admin_registry import GROUPS, group_label
from bot.services.admin_registry import values as registry_values
from bot.services.admin_settings import (
    PAGE_SIZE,
    STATUS_ICON,
    VISIBILITY_ICON,
)
from bot.services.admin_status import admin_status
from bot.services.logins import Login, logins_of
from bot.services.naming import (
    account_nickname,
    person_name,
    person_name_of,
    subscriber_names,
    xbox_nickname,
)
from bot.services.roles import FULL, Access
from bot.services.stats import month_cutoff_utc, today_cutoff_utc
from bot.util import humanize_ago, real_game_name
from bot.views import Screen
from bot.views.admin_home import usage_by_credential
from bot.views.admin_settings import action_rows, setting_rows
from bot.views.inline_lists import InlineListing, button_rows, page_nav, paginate
from bot.views.keyboards import (
    format_offset,
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


def key_icon(state: CredentialState) -> str:
    """A credential's state at a glance (#233): set and working, set and
    refused, or not set at all."""
    if not state.configured:
        return "⚪️"
    return "⚠️" if state.status == TokenStatus.INVALID else "✅"


async def render_keys(
    credentials: AdminCredentials, repo: Repo, *, locale: str
) -> tuple[str, InlineKeyboardMarkup]:
    """One button per credential with its state (#233; agreed on a mockup,
    2026-10-29), from the registry the Mini App walks too (#176); inside each
    its state, load and actions. Beside them, the players' own PSN tokens."""
    _ = translator("admin", locale)
    states = await credentials.states()
    buttons = [
        InlineKeyboardButton(
            text=key_icon(state) + " " + _("admin-keys-" + state.name + "-label"),
            callback_data="a:key:" + state.name,
        )
        for state in states
    ]
    builder = InlineKeyboardBuilder()
    for i in range(0, len(buttons), 2):
        builder.row(*buttons[i : i + 2])
    alive, dead = await repo.psn_token_counts()
    builder.row(
        InlineKeyboardButton(
            text=_("admin-keys-personal-button", alive=alive, dead=dead),
            callback_data="a:psntok",
        )
    )
    builder.row(InlineKeyboardButton(text=_("admin-back"), callback_data="a:home"))
    return "\n".join([_("admin-keys-title"), "", _("admin-keys-tap")]), builder.as_markup()


async def render_key(
    credentials: AdminCredentials, repo: Repo, name: str, *, locale: str
) -> tuple[str, InlineKeyboardMarkup]:
    """One credential (#233): its state, when it was last checked, its load,
    where to get it, and what can be done with it. The value is never shown."""
    _ = translator("admin", locale)
    state = await credentials.state(name)
    if not state.configured:
        status = _("admin-key-status-unset")
    elif state.status == TokenStatus.INVALID:
        status = _("admin-key-status-dead")
    else:
        status = _("admin-key-status-alive")
    lines = [_("admin-key-title", label=_("admin-keys-" + name + "-label")), "", status]
    if state.configured and state.checked_at:
        lines.append(_("admin-key-checked", ago=humanize_ago(state.checked_at, locale)))
    usage = usage_by_credential(await admin_status(repo, credentials=credentials), locale=locale)
    if name in usage:
        lines.append(_("admin-key-usage", usage=usage[name]))
    if name == "psn":
        alive, dead = await repo.psn_token_counts()
        lines.append(
            _(
                "admin-key-psn-reads",
                shared=await repo.psn_accounts_without_token(),
                alive=alive,
                dead=dead,
            )
        )
    lines += ["", _("admin-keys-" + name + "-hint")]
    builder = InlineKeyboardBuilder()
    action = "change" if state.configured else "add"
    builder.row(
        InlineKeyboardButton(
            text=_("admin-keys-" + name + "-" + action), callback_data="a:keyset:" + name
        )
    )
    if state.configured:
        builder.row(
            InlineKeyboardButton(
                text=_("admin-keys-" + name + "-clear"), callback_data="a:keyclr:" + name
            )
        )
    builder.row(InlineKeyboardButton(text=_("admin-keys-back"), callback_data="a:keys"))
    return "\n".join(lines), builder.as_markup()


async def render_psn_tokens(repo: Repo, *, locale: str) -> tuple[str, InlineKeyboardMarkup]:
    """The players' own PSN tokens (#233): whose, which account, working or
    not — never a token itself."""
    _ = translator("admin", locale)
    rows = await repo.psn_token_overview()
    lines = [_("admin-psntok-title"), ""]
    builder = InlineKeyboardBuilder()
    for row in rows:
        name = html_escape(row["display_name"] or row["account_id"])
        who = html_escape(person_name(person_id=row["person_id"], handle=row["handle"]))
        if row["status"] == "active":
            ago = humanize_ago(row["checked_at"], locale)
            lines.append(_("admin-psntok-alive", name=name, who=who, ago=ago))
        else:
            ago = humanize_ago(row["dead_at"], locale)
            lines.append(_("admin-psntok-dead", name=name, who=who, ago=ago))
        builder.row(
            InlineKeyboardButton(text="👤 " + who, callback_data="a:u:p" + str(row["person_id"]))
        )
    if not rows:
        lines.append(_("admin-psntok-none"))
    lines += ["", _("admin-psntok-note", shared=await repo.psn_accounts_without_token())]
    builder.row(InlineKeyboardButton(text=_("admin-keys-back"), callback_data="a:keys"))
    return "\n".join(lines), builder.as_markup()


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
    today = await repo.achievement_counts_by_person(today_cutoff_utc())
    # This aggregate spans every user, with no single person's timezone to
    # key the calendar-month boundary off (#14) — the project default
    # (Europe/Moscow, +180) is the reference, same as admin_view.py's own
    # "updated HH:MM".
    month = await repo.achievement_counts_by_person(month_cutoff_utc(180))

    shown = paginate(users, page, PAGE_SIZE)

    rows = []
    buttons = []
    for user in shown.items:
        # The person chain (#51), not "whichever platform answered first" —
        # this list is a roster of people, and its rows are how the operator
        # finds one. The bare id stays reachable as the last step, which on
        # this screen is diagnostic rather than a bad label.
        name = person_name(person_id=user.person_id, handle=user.handle)
        if mark := roles.badge(user.role):
            name = f"{name} {mark}"
        rows.append(
            _(
                "admin-users-row",
                icon=_icon(user),
                name=truncate_name(name, 14),
                ago=humanize_ago(user.last_online_at, locale),
                today=today.get(user.person_id, (0, 0))[0],
                month=month.get(user.person_id, (0, 0))[0],
                note=_note(user, locale=locale),
            )
        )
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{_icon(user)} {name}", callback_data=f"a:u:p{user.person_id}"
                )
            ]
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


def _admin_tg_header(user: User, *, locale: str) -> list[str]:
    """Who this is and every way they sign in (owner, 2026-10-07): the
    person's name and id, then one line per kind of login, linked or not —
    the super-admin needs all of it at once for lookups. A bare Telegram id
    is never "@"-prefixed: it is not a username, and a real account could
    later take that numeric string as one."""
    _ = translator("admin", locale)
    lines = [
        _(
            "admin-user-header",
            name=person_name_of(user),
            person_id=str(user.id),
        ),
        "",
        _("admin-logins-title"),
    ]
    for login in logins_of(user):
        lines.append(
            _(
                "admin-logins-row",
                label=_(f"admin-logins-{login.kind}"),
                value=_login_value(login, _) if login.linked else _("admin-logins-none"),
            )
        )
    return lines


def login_value(login: Login, *, locale: str) -> str:
    """One login as the cards show it: `@name, id 123` for Telegram, the
    address for email."""
    return _login_value(login, translator("admin", locale))


def _login_value(login: Login, _: Callable[..., str]) -> str:
    if login.kind == "telegram":
        parts = [f"@{login.username}"] if login.username else []
        parts.append(_("admin-logins-tg-id", tg_id=login.ident or ""))
        return ", ".join(parts)
    return login.ident or ""


async def _xbox_admin_block(repo: Repo, user: User, today_count: int, *, locale: str) -> list[str]:
    """One block, five fixed lines (2026-09-08 restructure, user request):
    nickname, id, status (+ when last checked), achievements, last online —
    each its own line instead of the old single achievements-and-all header
    line, so a long line no longer buries the id next to the nickname."""
    _ = translator("admin", locale)
    count = await repo.xbox_achievement_count(user.id)
    completed = await repo.xbox_completed_games_count(user.xuid)
    parts = [plural_achievements(count, locale)]
    if completed:
        parts.append(f"{completed} {COMPLETED_BADGE_XBOX}")
    parts.append(_("admin-today-tag", count=today_count))
    parts.append(_("admin-gamerscore-tag", score=user.gamerscore or 0))

    token = await repo.get_token(user.id)
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
        game = real_game_name(presence.title_name) or ""
        if not game and presence.title_id:
            game = real_game_name(await repo.title_name("xbox", presence.title_id)) or ""
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
        *_muted_line(await repo.get_platform_link(user.id, AccountPlatform.XBOX), _),
    ]


def _muted_line(link: PlatformLink | None, _: Callable[..., str]) -> list[str]:
    """One more line only when the owner switched this account's posts off
    (#20) — the answer to "why does nothing of theirs appear in chat"."""
    return [_("admin-muted-row")] if link is not None and not link.publishes else []


async def _steam_admin_block(
    repo: Repo, link: PlatformLink, today_count: int, *, locale: str
) -> list[str]:
    """Steam's counterpart of `_xbox_admin_block` — same five-line shape,
    its "status" line is achievement *visibility* (there is no login/token
    to be active or dead), worded exactly like /panel's own status
    (`visibility_status_text`, shared so the two never drift)."""
    _ = translator("admin", locale)
    count = await repo.platform_achievement_count(link.person_id, Platform.STEAM)
    completed = await repo.steam_completed_games_count(link.person_id)
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
        *_muted_line(link, _),
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
    # This account's own figures (#10): a person may hold several.
    count = await repo.account_achievement_count(Platform.PSN, link.external_id)
    platinum = await repo.account_platinum_count(link.external_id)
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
        await _psn_token_row(repo, link.external_id, _, locale),
        "  ·  ".join(parts),
        _("admin-online-row", online=online),
        *_muted_line(link, _),
    ]


async def _psn_token_row(repo: Repo, account_id: str, _, locale: str) -> str:
    """Which token reads this account (#233) — never the token itself."""
    token = await repo.psn_token(account_id)
    if token is None:
        return _("admin-psn-token-shared")
    if token.status == "active":
        return _("admin-psn-token-alive", ago=humanize_ago(token.checked_at, locale))
    return _("admin-psn-token-dead", ago=humanize_ago(token.dead_at, locale))


async def render_user_card(
    repo: Repo,
    person: int,
    *,
    locale: str,
    access: Access = FULL,
    settings: Settings | None = None,
    admin_id: int | None = None,
) -> tuple[str, InlineKeyboardMarkup]:
    _ = translator("admin", locale)
    user = await repo.get_user(person)
    steam_link = await repo.get_platform_link(person, Platform.STEAM)
    psn_links = await repo.platform_links_for(person, Platform.PSN)
    # Used to bail out on `not user.xuid` alone (2026-09-05 follow-up) — a
    # A Steam-only person got a "user not found" result in the admin panel,
    # same class of gap /stats had before it learned to work without Xbox.
    if user is None or (not user.xuid and steam_link is None and not psn_links):
        return _("admin-user-not-found"), _back_home(locale=locale)

    today = today_cutoff_utc()
    today_xbox, today_steam, _today_psn = await repo.achievement_platform_breakdown(person, today)
    chats = await repo.chats_of_user(person)

    # Telegram identity first (2026-09-08 user request), then one block per
    # connected platform in the one display order — Xbox, PlayStation, Steam
    # (constants.platform_display_rank) — each block grouping everything about
    # that platform together (nickname/id, status, achievements, last online
    # where it applies), five fixed lines each (2026-09-08 restructure)
    # instead of one crowded header line.
    lines = [*_admin_tg_header(user, locale=locale), ""]
    if user.xuid:
        lines += await _xbox_admin_block(repo, user, today_xbox, locale=locale)
        lines.append("")
    # One block per PSN account (#10), each with its own "today".
    for link in psn_links:
        today_psn = await repo.account_count_since(Platform.PSN, link.external_id, today)
        lines += await _psn_admin_block(repo, link, today_psn, locale=locale)
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
        _("admin-rarity", mode=await rarity_label(repo, person, locale=locale)),
        _("admin-role", role=_(f"admin-role-{roles.stored(await repo.person_role(person))}")),
    ]
    text = "\n".join(lines)
    if user.is_excluded:
        text += "\n\n" + _("admin-excluded")

    # The actions come from the registry (#176), the Mini App's card lists the
    # same ones.
    builder = InlineKeyboardBuilder()
    views = await _actions(
        repo, "user", Target(person=person), locale, access, settings=settings, admin_id=admin_id
    )
    for row in action_rows(views):
        builder.row(*row)
    builder.row(InlineKeyboardButton(text=_("admin-back-to-users"), callback_data="a:users:0"))
    return text, builder.as_markup()


async def rarity_label(repo: Repo, person: int, *, locale: str) -> str:
    """The person's rarity mode (all / rare / none) as both cards word it."""
    settings = await repo.get_user_settings(person)
    mode = settings.rarity_mode if settings is not None else RarityMode.ALL
    if mode not in (RarityMode.ALL, RarityMode.RARE, RarityMode.HIDDEN):
        mode = RarityMode.ALL
    return translator("admin", locale)(f"admin-rarity-{mode}")


async def _actions(
    repo: Repo,
    scope: Literal["user", "chat", "global"],
    target: Target,
    locale: str,
    access: Access = FULL,
    *,
    settings: Settings | None = None,
    admin_id: int | None = None,
):
    # Listing needs only the database (and, for the roles, who is asking and
    # who the environment names); running one is the handler's.
    ctx = AdminContext(repo, settings, access=access, admin_id=admin_id)  # type: ignore[arg-type]
    return await available_actions(ctx, scope, target, locale=locale)


# Plain platform names for the confirm prompt's own sentence — distinct
# from the "🔄 Обновить X" / "🗑 Сброс X" button labels, which read wrong
# spliced into "Стереть базу <label> для...".


async def render_chat_list(
    repo: Repo, *, locale: str, access: Access = FULL
) -> tuple[str, InlineKeyboardMarkup]:
    """Unlike the user list above, this one is buttons only — a chat row is
    two facts wide, and both fit on the button, so there is no separate text
    row to write. It used to call `Listing` with an empty row list to look
    like it shared the text machinery; that rendered nothing, and a keyboard
    list now has machinery of its own to share instead."""
    _ = translator("admin", locale)
    # A chat admin sees their own chats, with nothing above them (#232).
    chats = [chat for chat in await repo.admin_chats() if access.chat(chat.chat_id)]
    tail = _back_row(locale=locale) if access.app else []
    if not chats:
        empty = _("admin-chats-empty") if access.app else _("admin-chats-mine-empty")
        return empty, InlineKeyboardMarkup(inline_keyboard=[tail] if tail else [])

    def label(chat: ChatTarget) -> str:
        return _(
            "admin-chat-list-row",
            mark="" if chat.is_active else "⏸ ",
            title=chat.title or chat.chat_id,
            subscribers=chat.subscribers,
        )

    keyboard = InlineListing(
        rows=button_rows(chats, label, lambda chat: f"a:chat:{chat.chat_id}"),
        tail=tail,
    ).markup()
    return _("admin-chats-header"), keyboard


async def render_chat_card(
    repo: Repo,
    chat_id: int,
    *,
    locale: str,
    section: str | None = None,
    access: Access = FULL,
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
    zone_label = format_offset(chat.tz, None)
    flood_label = (
        _("admin-chat-flood-value", limit=chat.flood_limit, window=chat.flood_window_minutes)
        if chat.flood_limit > 0
        else _("admin-chat-flood-off")
    )
    text = _(
        "admin-chat-card",
        title=chat.title or chat_id,
        state=_("admin-active") if chat.is_active else _("admin-inactive"),
        publishing=_("admin-on") if chat.publishing else _("admin-off"),
        admin=await chat_admin_name(repo, chat_id, locale=locale),
        subscribers=chat.subscribers,
        summary=_("admin-yes") if chat.daily_summary else _("admin-no"),
        time=chat.daily_summary_time,
        offset=zone_label,
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

    if section in GROUPS["chat"]:
        # A group of the chat's settings, drawn from the registry (#176) under
        # the card's text, which stays whole.
        current = await registry_values(repo, "chat", chat)
        rows = setting_rows("chat", section, current, locale=locale, chat_id=chat_id)
        for row in rows:
            builder.row(*row)
        builder.row(back_to_card)
        return text, builder.as_markup()

    if section == "messages":
        # One action per row: the wipes are the destructive ones, and a
        # cramped row of four 🗑 buttons made them easy to mistap (2026-09-11).
        views = await _actions(repo, "chat", Target(chat_id=chat_id), locale, access)
        for row in action_rows(views, "messages"):
            builder.row(*row)
        builder.row(back_to_card)
        return text, builder.as_markup()

    # The root card: one entry per group of settings (the registry's), then
    # the actions.
    for group in GROUPS["chat"]:
        builder.row(
            InlineKeyboardButton(
                text=f"{group_label('chat', group, locale=locale)} ▸",
                callback_data=f"a:cg:{chat_id}:{group}",
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=_("admin-chat-messages-menu-button"), callback_data=f"a:mdel:{chat_id}"
        )
    )
    builder.row(
        InlineKeyboardButton(text=_("admin-chat-admin-button"), callback_data=f"a:ca:{chat_id}")
    )
    for row in action_rows(await _actions(repo, "chat", Target(chat_id=chat_id), locale, access)):
        builder.row(*row)
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
    # No game account yet: the panel's own "not connected" mark.
    return "".join(parts) or "🔘"


def _note(user: AdminUserRow, *, locale: str) -> str:
    _ = translator("admin", locale)
    if user.is_excluded:
        return _("admin-note-excluded")
    if user.token_status == TokenStatus.INVALID:
        return _("admin-note-invalid")
    if user.token_status == TokenStatus.REVOKED:
        return _("admin-note-revoked")
    return ""


def render_action_confirm(confirm: Confirm, *, yes: str, back: str, locale: str) -> Screen:
    """One confirmation of a super-admin action (`services/admin_actions.py`):
    its words, its "yes", and the way back."""
    _ = translator("admin", locale)
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=confirm.yes, callback_data=yes),
        InlineKeyboardButton(text=_("admin-cancel"), callback_data=back),
    )
    return Screen(confirm.text, builder.as_markup())


async def global_actions(repo: Repo, *, locale: str, access: Access = FULL) -> list[ActionView]:
    """The app's own actions; a settings group shows those of its section."""
    return await _actions(repo, "global", Target(), locale, access)


# ---------------------------------------------------------------- chat admin


async def chat_admin_name(repo: Repo, chat_id: int, *, locale: str) -> str:
    """The chat admin as the cards name them (#232): their nickname, else
    their Telegram id — a chat admin may never have used the app."""
    tg_id = await repo.chat_admin(chat_id)
    if tg_id is None:
        return translator("admin", locale)("admin-chat-admin-none")
    return await tg_name(repo, tg_id)


async def tg_name(repo: Repo, tg_id: int) -> str:
    user = await repo.get_user_by_tg(tg_id)
    if user is None:
        return f"tg {tg_id}"
    return person_name(person_id=user.id, handle=user.handle)  # type: ignore[arg-type]


async def render_chat_admin_pick(
    repo: Repo, chat_id: int, *, locale: str, access: Access, me: int
) -> Screen:
    """Who the chat admin role goes to: the chat's known members, one a
    button. An app admin appoints (and may remove); the chat admin hands
    their own role on."""
    _ = translator("admin", locale)
    current = await repo.chat_admin(chat_id)
    handing_on = not access.app
    if handing_on:
        text = _("admin-chat-admin-hand-on")
    else:
        text = _("admin-chat-admin-pick", admin=await chat_admin_name(repo, chat_id, locale=locale))
    candidates = [
        (tg_id, person, handle)
        for tg_id, person, handle in await repo.chat_admin_candidates(chat_id)
        if tg_id not in (current, me if handing_on else None)
    ]
    if not candidates:
        text += "\n\n" + _("admin-chat-admin-nobody")
    builder = InlineKeyboardBuilder()
    for tg_id, person, handle in candidates:
        builder.button(
            text=person_name(person_id=person, handle=handle),
            callback_data=f"a:cap:{chat_id}:{tg_id}",
        )
    builder.adjust(2)
    if access.app and current is not None:
        builder.row(
            InlineKeyboardButton(
                text=_("admin-chat-admin-remove"), callback_data=f"a:cax:{chat_id}:0"
            )
        )
    builder.row(InlineKeyboardButton(text=_("admin-back"), callback_data=f"a:chat:{chat_id}"))
    return Screen(text, builder.as_markup())
