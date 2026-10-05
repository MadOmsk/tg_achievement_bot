"""/panel — the person's own screen, and the per-chat cards behind it (#63).

Reads the database only (SPEC 1.5): the one panel button that reaches a
platform API is the manual sync, which is the handler's job, not this
file's.
"""

from __future__ import annotations

from html import escape as html_escape

from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram_i18n import I18nContext

from bot.constants import (
    MAX_PSN_ACCOUNTS,
    AccountPlatform,
    Platform,
    PresenceState,
    RarityMode,
    TokenStatus,
)
from bot.db.repo import PlatformLink, PsnPresenceRow, Repo, User, UserChatRow
from bot.i18n import gettext, i18n_for
from bot.services.naming import link_nickname, person_name_of, xbox_nickname
from bot.services.presence_view import pick_presence
from bot.services.profile_links import (
    STEAM_PRIVACY_URL,
    platform_profile_url,
    xbox_profile_url,
)
from bot.util import humanize_ago
from bot.views import Screen
from bot.views.inline_lists import InlineListing, button_rows
from bot.views.keyboards import (
    panel_keyboard,
)
from bot.views.parts import (
    PLATFORM_ICON,
    family_tag,
    link_value_parts,
    platform_header_lines,
    visibility_status_text,
    xbox_value_parts,
)

LOGIN_STATUS_KEYS = {
    TokenStatus.ACTIVE: "panel-login-active",
    TokenStatus.INVALID: "panel-login-invalid",
    TokenStatus.REVOKED: "panel-login-revoked",
}


async def render_chat_list(repo: Repo, tg_id: int, *, locale: str) -> Screen:
    """ "Мои чаты" — every chat the bot and this person share, subscribed or
    not, each a button into its own card below."""
    i18n = await i18n_for(locale)
    chats = await repo.user_chats(tg_id)
    text = i18n.get("panel-my-chats-title")
    if not chats:
        text += i18n.get("panel-my-chats-empty")
    listing = InlineListing(
        rows=button_rows(chats, _my_chat_label, lambda chat: f"panel:chat:{chat.chat_id}"),
        tail=[InlineKeyboardButton(text=i18n.get("panel-back"), callback_data="panel:refresh")],
    )
    return Screen(text, listing.markup())


def _my_chat_label(chat: UserChatRow) -> str:
    # The mark is the whole point of the row: this list shows chats this
    # person is *not* subscribed to as well, and subscribing is what the
    # screen is for.
    return f"{'✅' if chat.is_subscribed else '⚪'} {chat.title or chat.chat_id}"


async def find_user_chat(repo: Repo, tg_id: int, chat_id: int) -> UserChatRow | None:
    return next((c for c in await repo.user_chats(tg_id) if c.chat_id == chat_id), None)


async def render_chat_card(repo: Repo, tg_id: int, chat_id: int, *, locale: str) -> Screen | None:
    chat = await find_user_chat(repo, tg_id, chat_id)
    if chat is None:
        return None
    i18n = await i18n_for(locale)
    title = chat.title or chat.chat_id
    builder = InlineKeyboardBuilder()
    if chat.is_subscribed:
        text = (
            i18n.get("panel-chat-card-title", title=html_escape(str(title)))
            + "\n\n"
            + i18n.get("panel-publication-enabled")
        )
        # Nothing to tune per chat any more (#126): which achievements go out
        # is the person's, how many make a digest is the chat's admin's.
        builder.row(
            InlineKeyboardButton(
                text=i18n.get("panel-unsubscribe"), callback_data=f"panel:chatunsub:{chat_id}"
            )
        )
    else:
        text = (
            i18n.get("panel-chat-card-title", title=html_escape(str(title)))
            + "\n\n"
            + i18n.get("panel-publication-disabled")
        )
        builder.row(
            InlineKeyboardButton(
                text=i18n.get("panel-subscribe"), callback_data=f"panel:chatsub:{chat_id}"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=i18n.get("panel-remove-from-list"), callback_data=f"panel:chatdel:{chat_id}"
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=i18n.get("panel-back-to-chat-list"), callback_data="panel:chatlist"
        )
    )
    return Screen(text, builder.as_markup())


def _panel_identity(user: User, links: list[PlatformLink], locale: str) -> str:
    """The person's own name for the /panel header (#18) — the one shared
    person chain (#51). This used to be the third hand-written copy of it,
    and the only one whose last resort was a bare `tg_id` with no `id`
    prefix at all."""
    return gettext(
        "panel",
        "panel-header-identity",
        locale=locale,
        name=html_escape(person_name_of(user, links)),
    )


async def _panel_header_lines(
    repo: Repo,
    user: User,
    steam_link: PlatformLink | None,
    psn_links: list[PlatformLink],
    i18n: I18nContext,
) -> list[str]:
    """Identity + one line per connected platform with its lifetime count
    (#18) — now built by the exact same function /stats' own header uses
    (services/achievements.py::platform_header_lines, 2026-09-08 user
    request: "пусть одни одинаково формируются" — this used to be a
    hand-duplicated, HTML-identical copy of that same logic).

    `show_links=False`: unlike /stats, this header's names were never
    inline hyperlinks — /panel's own "Profile" buttons already cover that
    (CLAUDE.md: "always visible regardless of the privacy toggle" is about
    those buttons, not a second, redundant link inside the header text)."""
    platform_links = [*psn_links, *([steam_link] if steam_link else [])]
    return [_panel_identity(user, platform_links, i18n.locale)] + await platform_header_lines(
        repo,
        tg_id=user.tg_id,
        xuid=user.xuid,
        gamertag=user.gamertag,
        gamertag_modern=user.gamertag_modern,
        gamerscore=user.gamerscore,
        platform_links=platform_links,
        show_links=False,
        locale=i18n.locale,
    )


async def render_panel(repo: Repo, tg_id: int, *, locale: str | None = None) -> Screen:
    # No locale given (an internal caller with no aiogram update behind it,
    # e.g. main.py's post-login screen) — read the person's own rather than
    # falling back to Russian (#48). This screen is always about exactly one
    # person, whose tg_id we already have.
    i18n = await i18n_for(locale or await repo.user_locale(tg_id))
    user = await repo.get_user(tg_id)
    settings_row = await repo.get_user_settings(tg_id)
    connected = user is not None and bool(user.xuid)
    steam_link = await repo.get_platform_link(tg_id, Platform.STEAM)
    psn_links = await repo.platform_links_for(tg_id, Platform.PSN)
    psn_link = psn_links[0] if psn_links else None
    xbox_link = await repo.get_platform_link(tg_id, AccountPlatform.XBOX) if connected else None

    token = await repo.get_token(tg_id) if connected else None
    needs_reconnect = token is not None and token.status == TokenStatus.INVALID
    tz_offset = settings_row.tz_offset_min if settings_row else None
    keyboard = panel_keyboard(
        tz_offset,
        i18n,
        connected=connected,
        needs_reconnect=needs_reconnect,
        steam_connected=steam_link is not None,
        psn_connected=bool(psn_links),
        psn_accounts=len(psn_links),
        rarity_mode=settings_row.rarity_mode if settings_row else RarityMode.ALL,
        xbox_publishes=xbox_link.publishes if xbox_link else True,
        psn_publishes=platform_publishes(psn_links),
        steam_publishes=steam_link.publishes if steam_link else True,
        # ❗ on a platform whose achievements the bot cannot see (owner,
        # 2026-09-30) — for PSN, any one of its accounts.
        steam_hidden=bool(steam_link and steam_link.achievements_visible is False),
        psn_hidden=any(link.achievements_visible is False for link in psn_links),
    )

    if user is None:
        # Defensive only — every real call site ensures the user row first
        # (panel_command's own repo.ensure_user, or a callback that can only
        # fire from an already-rendered panel in the first place).
        return Screen(i18n.get("panel-header-not-connected"), keyboard)

    # The body is the same shape regardless of which platforms are
    # connected (2026-09-09, confirmed live: a Steam/PSN-only person used to
    # get an entirely different, stripped-down body here — no header/
    # achievement counts, no publication/presence/timezone rows at all —
    # because this whole branch used to hard-gate on Xbox specifically,
    # a leftover from before Steam/PSN existed. Every row below now
    # degrades per-platform (shown/omitted on its own) instead of the
    # whole body switching on whether *Xbox* is connected.
    login = (
        i18n.get(LOGIN_STATUS_KEYS.get(token.status, "panel-login-revoked"))
        if token
        else i18n.get("panel-login-not-connected")
    )

    # Header: identity + per-platform lifetime counts (#18). The 24h/30d
    # counters and "последние достижения" list this body used to carry are
    # gone — the header covers achievements now.
    lines = await _panel_header_lines(repo, user, steam_link, psn_links, i18n)
    # One login row per platform, connected or not, and one per PSN account
    # (PSN1, PSN2… when there are several): only whether all is well — the
    # nicknames are in the header, when it was checked is not needed here
    # (owner, 2026-09-30).
    not_connected = i18n.get("panel-login-not-connected")
    lines += ["", i18n.get("panel-login-row", platform="XBOX", status=login)]
    lines.append(
        i18n.get(
            "panel-login-row",
            platform="Steam",
            status=(
                visibility_status_text(steam_link, i18n.locale, with_time=False)
                if steam_link is not None
                else not_connected
            ),
        )
    )
    if not psn_links:
        lines.append(i18n.get("panel-login-row", platform="PSN", status=not_connected))
    for number, link in enumerate(psn_links, start=1):
        lines.append(
            i18n.get(
                "panel-login-row",
                platform=f"PSN{number}" if len(psn_links) > 1 else "PSN",
                status=visibility_status_text(link, i18n.locale, with_time=False),
            )
        )
    lines.append(
        i18n.get(
            "panel-publication-row",
            status=await _publication_status(
                repo,
                user.tg_id,
                user.is_excluded,
                i18n,
                muted=_muted_accounts(xbox_link, psn_links, steam_link),
            ),
        )
    )
    if user.xuid or steam_link is not None or psn_link is not None:
        # Every connected platform competes for this row now (issue #1's own
        # tail, closed 2026-09-15) — it used to be gated on `user.xuid` and so
        # was missing entirely from a Steam/PSN-only person's panel, the last
        # row here that still assumed Xbox.
        playing = await _now_playing(repo, user, steam_link, psn_links, i18n)
        lines.append(i18n.get("panel-now-playing-row", playing=playing))
    if needs_reconnect:
        lines += ["", i18n.get("panel-reconnect-hint")]
    return Screen("\n".join(lines), keyboard)


async def _now_playing(
    repo: Repo,
    user: User,
    steam_link: PlatformLink | None,
    psn_links: list[PlatformLink],
    i18n: I18nContext,
) -> str:
    """One row for every platform at once, not one row each: the question
    ("where is this person right now") has a single answer, and two of the
    three platforms would only ever be able to say "offline" alongside it.
    Which platform wins is `services/presence_view.pick_presence`, the same
    playing > online > offline rule /online settled on.

    The platform is named only while the person is actually online — an
    offline row has no "where" left to answer, so naming the platform there
    just picks one arbitrarily (the same call `/online`'s own rows make,
    #51)."""
    # Several PSN accounts (#10): the one with the most to say — the same
    # playing > online > offline rule, applied among them first.
    psn = None
    for link in psn_links:
        candidate = await repo.psn_presence_of(link.external_id)
        if candidate is not None:
            psn = candidate if psn is None else _livelier(psn, candidate)
    presence = pick_presence(
        xbox=await repo.presence_of(user.xuid) if user.xuid else None,
        steam=await repo.steam_presence_of(steam_link.external_id) if steam_link else None,
        psn=psn,
    )
    if presence is None:
        return i18n.get("panel-no-presence-data")
    if not presence.online:
        return i18n.get("panel-offline", ago=humanize_ago(presence.updated_at, i18n.locale))
    tag = family_tag(presence.platform, i18n.locale)
    if not presence.title_id:
        return f"{tag}  ·  " + i18n.get("panel-online-idle")
    # Presence gives no name for PC titles — fall back to the cache the
    # poller fills (SPEC 4), same as the admin card.
    game = presence.game or await repo.title_name(presence.title_id) or presence.title_id
    return f"{tag}  ·  " + i18n.get("panel-playing", game=html_escape(str(game)))


def _livelier(a: PsnPresenceRow, b: PsnPresenceRow) -> PsnPresenceRow:
    def rank(p: PsnPresenceRow) -> tuple[int, str]:
        online = p.state == PresenceState.ONLINE
        return (2 if online and p.title_id else 1 if online else 0, p.updated_at or "")

    return b if rank(b) > rank(a) else a


def platform_publishes(links: list[PlatformLink]) -> bool | None:
    """The panel's switch for a whole platform (#10): on, off, or `None` when
    some of its accounts post and some do not."""
    states = {link.publishes for link in links}
    return None if len(states) > 1 else (states.pop() if states else True)


def _muted_accounts(
    xbox_link: PlatformLink | None, psn_links: list[PlatformLink], steam_link: PlatformLink | None
) -> list[str]:
    """Which accounts the person switched off (#20), named as briefly as
    still says which: a platform, or PSN's muted accounts by nickname when
    only some of several are off (#10)."""
    muted = []
    if xbox_link is not None and not xbox_link.publishes:
        muted.append("XBOX")
    psn_muted = [link for link in psn_links if not link.publishes]
    if psn_muted and len(psn_muted) == len(psn_links):
        muted.append("PSN")
    elif psn_muted:
        muted.append("PSN: " + ", ".join(link_nickname(link) for link in psn_muted))
    if steam_link is not None and not steam_link.publishes:
        muted.append("Steam")
    return muted


async def _publication_status(
    repo: Repo,
    tg_id: int,
    is_excluded: bool,
    i18n: I18nContext,
    *,
    muted: list[str] | None = None,
) -> str:
    if is_excluded:
        # An exclusion is never silent: the person sees it here (SPEC 6.4).
        return i18n.get("panel-excluded")
    chats = await repo.chats_of_user(tg_id)
    if not chats:
        return i18n.get("panel-not-subscribed-anywhere")
    status = i18n.get(
        "panel-subscribed-in", chats=", ".join(f"«{html_escape(str(title))}»" for title in chats)
    )
    if muted:
        # Which accounts the person switched off (#20), said where the
        # question "where does it post" is answered.
        status += i18n.get("panel-publishing-without", platforms=html_escape(", ".join(muted)))
    return status


async def render_unsub_prompt(
    repo: Repo, tg_id: int, chat_id: int, *, locale: str
) -> Screen | None:
    """Same weight as the standalone /unsubscribe — a confirm, not an instant
    action (SPEC 6.3): losing a feed in a chat deserves a second tap."""
    return await _chat_confirm(
        repo,
        tg_id,
        chat_id,
        locale=locale,
        prompt="panel-unsub-prompt",
        confirm="panel-unsub-yes",
        callback=f"panel:chatunsuby:{chat_id}",
    )


async def render_chat_delete_prompt(
    repo: Repo, tg_id: int, chat_id: int, *, locale: str
) -> Screen | None:
    """Leaving a chat's card behind entirely — same shape as the unsubscribe
    confirmation above, which is the point: two destructive taps that look
    alike are two taps nobody misreads."""
    return await _chat_confirm(
        repo,
        tg_id,
        chat_id,
        locale=locale,
        prompt="panel-delete-prompt",
        confirm="panel-delete-yes",
        callback=f"panel:chatdely:{chat_id}",
    )


async def _chat_confirm(
    repo: Repo,
    tg_id: int,
    chat_id: int,
    *,
    locale: str,
    prompt: str,
    confirm: str,
    callback: str,
) -> Screen | None:
    """Both keys are passed whole rather than assembled from pieces: a key
    built with an f-string is one `tests/test_locale_parity.py` cannot see
    and one nobody can grep for."""
    chat = await find_user_chat(repo, tg_id, chat_id)
    if chat is None:
        return None
    i18n = await i18n_for(locale)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=i18n.get(confirm), callback_data=callback))
    builder.row(
        InlineKeyboardButton(
            text=i18n.get("panel-unsub-cancel"), callback_data=f"panel:chat:{chat_id}"
        )
    )
    return Screen(
        i18n.get(prompt, title=html_escape(str(chat.title or chat.chat_id))),
        builder.as_markup(),
    )


async def render_panel_delete_confirm_1(*, locale: str) -> Screen:
    i18n = await i18n_for(locale)
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=i18n.get("panel-delete-confirm-1-yes"),
            callback_data="panel:delete:step1",
        )
    )
    builder.row(InlineKeyboardButton(text=i18n.get("kb-cancel"), callback_data="panel:refresh"))
    return Screen(i18n.get("panel-delete-confirm-1"), builder.as_markup())


async def render_panel_delete_confirm_2(*, locale: str) -> Screen:
    i18n = await i18n_for(locale)
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=i18n.get("panel-delete-confirm-2-yes"),
            callback_data="panel:delete:step2",
        )
    )
    builder.row(InlineKeyboardButton(text=i18n.get("kb-cancel"), callback_data="panel:refresh"))
    return Screen(i18n.get("panel-delete-confirm-2"), builder.as_markup())


# ---------------------------------------------------------------- account screens (#10)


def _back(i18n: I18nContext) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=i18n.get("panel-back"), callback_data="panel:refresh")


def _publish_state(publishes: bool, i18n: I18nContext) -> str:
    return i18n.get("panel-account-publishes-on" if publishes else "panel-account-publishes-off")


async def render_account_menu(
    repo: Repo, tg_id: int, platform: str, *, locale: str
) -> Screen | None:
    """One platform's own screen behind its /panel button (#10): what the
    account is, its profile, its publishing switch, unlinking — and for PSN
    every account the person holds, plus adding another. None when the
    platform is not linked any more (the caller falls back to the panel)."""
    i18n = await i18n_for(locale)
    if platform == AccountPlatform.PSN:
        return await _psn_menu(repo, tg_id, i18n)
    if platform == AccountPlatform.XBOX:
        user = await repo.get_user(tg_id)
        link = await repo.get_platform_link(tg_id, AccountPlatform.XBOX)
        if user is None or not user.xuid or link is None:
            return None
        token = await repo.get_token(tg_id)
        login = (
            i18n.get(LOGIN_STATUS_KEYS.get(token.status, "panel-login-revoked"))
            if token
            else i18n.get("panel-login-not-connected")
        )
        name = xbox_nickname(
            gamertag_modern=user.gamertag_modern, gamertag=user.gamertag, xuid=user.xuid
        )
        parts = await xbox_value_parts(
            repo, tg_id=tg_id, xuid=user.xuid, gamerscore=user.gamerscore, locale=i18n.locale
        )
        profile_url = xbox_profile_url(user.gamertag) if user.gamertag else None
        label = "XBOX"
        icon = PLATFORM_ICON[Platform.XBOX_MODERN]
        unlink_cb = "panel:disconnect"
    else:
        link = await repo.get_platform_link(tg_id, AccountPlatform.STEAM)
        if link is None:
            return None
        login = visibility_status_text(link, i18n.locale)
        name = link_nickname(link)
        parts = await link_value_parts(repo, tg_id=tg_id, link=link, locale=i18n.locale)
        profile_url = platform_profile_url(
            link.platform, external_id=link.external_id, display_name=link.display_name
        )
        token = None
        label = "Steam"
        icon = PLATFORM_ICON[Platform.STEAM]
        unlink_cb = "steam:disconnectprompt"

    text = "\n".join(
        [
            i18n.get("panel-account-title", icon=icon, platform=label),
            "",
            f"{html_escape(name)}  ·  " + "  ·  ".join(parts),
            i18n.get("panel-account-login", status=login),
            i18n.get("panel-account-publication", state=_publish_state(link.publishes, i18n)),
        ]
    )
    builder = InlineKeyboardBuilder()
    # Hidden achievements first (#95): what it means, and the way out on top.
    if platform == AccountPlatform.STEAM and link.achievements_visible is False:
        text += "\n\n" + i18n.get("panel-hidden-steam")
        builder.row(
            InlineKeyboardButton(text=i18n.get("kb-howto-steam"), callback_data="panel:howto:steam")
        )
    if (
        platform == AccountPlatform.XBOX
        and token is not None
        and token.status == TokenStatus.INVALID
    ):
        # First: nothing else on this screen works until the login does.
        builder.row(
            InlineKeyboardButton(text=i18n.get("kb-xbox-reconnect"), callback_data="relogin")
        )
    if profile_url:
        builder.row(
            InlineKeyboardButton(
                text=i18n.get("kb-account-profile", platform=label, name=name), url=profile_url
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=i18n.get(
                "kb-account-publication-on" if link.publishes else "kb-account-publication-off"
            ),
            callback_data=f"panel:accpub:{platform}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=i18n.get("kb-account-unlink", platform=label), callback_data=unlink_cb
        )
    )
    if platform == AccountPlatform.STEAM:
        builder.row(
            InlineKeyboardButton(text=i18n.get("kb-account-relink"), callback_data="steam:connect")
        )
    builder.row(_back(i18n))
    return Screen(text, builder.as_markup())


async def _psn_menu(repo: Repo, tg_id: int, i18n: I18nContext) -> Screen | None:
    links = await repo.platform_links_for(tg_id, Platform.PSN)
    if not links:
        return None
    lines = [
        i18n.get(
            "panel-psn-title",
            icon=PLATFORM_ICON[Platform.PSN],
            count=len(links),
            max=MAX_PSN_ACCOUNTS,
        ),
        "",
    ]
    builder = InlineKeyboardBuilder()
    # Hidden trophies first (#95): one explanation and one way out per account.
    hidden = [link for link in links if link.achievements_visible is False]
    for link in hidden:
        builder.row(
            InlineKeyboardButton(
                text=i18n.get("kb-howto-psn", name=link_nickname(link)),
                callback_data=f"panel:howto:psn:{link.external_id}",
            )
        )
    for link in links:
        name = link_nickname(link)
        parts = await link_value_parts(repo, tg_id=tg_id, link=link, locale=i18n.locale)
        lines.append(f"<b>PSN: {html_escape(name)}</b>  ·  " + "  ·  ".join(parts))
        lines.append(
            i18n.get(
                "panel-psn-account-state",
                login=visibility_status_text(link, i18n.locale),
                state=_publish_state(link.publishes, i18n),
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=i18n.get("kb-account-psn", name=name),
                url=platform_profile_url(
                    link.platform, external_id=link.external_id, display_name=link.display_name
                ),
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=i18n.get("kb-publishes-on" if link.publishes else "kb-publishes-off"),
                callback_data=f"panel:psnpub:{link.external_id}",
            ),
            InlineKeyboardButton(
                text=i18n.get("kb-psn-disconnect"), callback_data=f"psn:unlink:{link.external_id}"
            ),
        )
    if len(links) > 1:
        lines += ["", i18n.get("panel-psn-summed")]
    for link in hidden:
        lines += ["", i18n.get("panel-hidden-psn", name=html_escape(link_nickname(link)))]
    if len(links) < MAX_PSN_ACCOUNTS:
        builder.row(InlineKeyboardButton(text=i18n.get("kb-psn-add"), callback_data="psn:add"))
    builder.row(_back(i18n))
    return Screen("\n".join(lines), builder.as_markup())


async def render_privacy_howto(
    repo: Repo, tg_id: int, platform: str, account_id: str | None, *, locale: str
) -> Screen | None:
    """How to open hidden achievements on one account (#95): the steps, and
    "check again", which reads the account anew in this same message. None
    when the account is not linked any more."""
    i18n = await i18n_for(locale)
    builder = InlineKeyboardBuilder()
    if platform == AccountPlatform.STEAM:
        link = await repo.get_platform_link(tg_id, AccountPlatform.STEAM)
        if link is None:
            return None
        text = i18n.get("panel-howto-steam", privacy_url=STEAM_PRIVACY_URL)
        builder.row(InlineKeyboardButton(text=i18n.get("kb-steam-privacy"), url=STEAM_PRIVACY_URL))
        builder.row(InlineKeyboardButton(text=i18n.get("kb-recheck"), callback_data="bf:steam"))
        builder.row(_back_to(i18n, "panel:acc:steam"))
        return Screen(text, builder.as_markup())
    links = await repo.platform_links_for(tg_id, AccountPlatform.PSN)
    link = next((item for item in links if item.external_id == account_id), None)
    if link is None:
        return None
    text = i18n.get("panel-howto-psn", name=html_escape(link_nickname(link)))
    builder.row(
        InlineKeyboardButton(
            text=i18n.get("kb-recheck"), callback_data=f"bf:psn:{link.external_id}"
        )
    )
    builder.row(_back_to(i18n, "panel:acc:psn"))
    return Screen(text, builder.as_markup())


def _back_to(i18n: I18nContext, callback: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=i18n.get("kb-back"), callback_data=callback)
