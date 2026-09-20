"""/panel — the person's own screen, and the per-chat cards behind it (#63).

Reads the database only (SPEC 1.5): the one panel button that reaches a
platform API is the manual sync, which is the handler's job, not this
file's.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram_i18n import I18nContext

from bot.constants import Platform, RarityMode, TokenStatus
from bot.db.repo import PlatformLink, Repo, User, UserChatRow
from bot.i18n import gettext, i18n_for
from bot.services.naming import link_nickname, person_name_of
from bot.services.presence_view import pick_presence
from bot.util import humanize_ago
from bot.views import Screen
from bot.views.inline_lists import InlineListing, button_rows
from bot.views.keyboards import (
    format_digest,
    format_offset,
    format_rarity,
    panel_keyboard,
)
from bot.views.parts import platform_header_lines, platform_tag, visibility_status_text

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
            i18n.get("panel-chat-card-title", title=title)
            + "\n\n"
            + i18n.get("panel-publication-enabled")
        )
        # Per-chat, not one shared value any more (SPEC 9, M-Steam-2e's
        # follow-up) — only shown while actually publishing here, same as
        # min_gamerscore/muted_title_ids having nothing to apply to
        # otherwise.
        builder.row(
            InlineKeyboardButton(
                text=i18n.get(
                    "panel-achievements-mode",
                    mode=format_rarity(chat.rarity_mode or RarityMode.ALL, i18n),
                ),
                callback_data=f"panel:chatrarity:{chat_id}",
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=i18n.get(
                    "panel-digest-row",
                    threshold=format_digest(chat.digest_threshold or 3, i18n),
                ),
                callback_data=f"panel:chatdigest:{chat_id}",
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=i18n.get("panel-unsubscribe"), callback_data=f"panel:chatunsub:{chat_id}"
            )
        )
    else:
        text = (
            i18n.get("panel-chat-card-title", title=title)
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
        "panel", "panel-header-identity", locale=locale, name=person_name_of(user, links)
    )


async def _panel_header_lines(
    repo: Repo,
    user: User,
    steam_link: PlatformLink | None,
    psn_link: PlatformLink | None,
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
    platform_links = [link for link in (psn_link, steam_link) if link is not None]
    return [_panel_identity(user, platform_links, i18n.locale)] + await platform_header_lines(
        repo,
        tg_id=user.tg_id,
        xuid=user.xuid,
        gamertag=user.gamertag,
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
    psn_link = await repo.get_platform_link(tg_id, Platform.PSN)

    token = await repo.get_token(tg_id) if connected else None
    needs_reconnect = token is not None and token.status == TokenStatus.INVALID
    tz_offset = settings_row.tz_offset_min if settings_row else None
    keyboard = panel_keyboard(
        tz_offset,
        i18n,
        connected=connected,
        needs_reconnect=needs_reconnect,
        steam_connected=steam_link is not None,
        psn_connected=psn_link is not None,
        gamertag=user.gamertag if user else None,
        steam_id=steam_link.external_id if steam_link else None,
        psn_id=psn_link.display_name if psn_link else None,
        show_profile_links=bool(settings_row and settings_row.show_profile_links),
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
    lines = await _panel_header_lines(repo, user, steam_link, psn_link, i18n)
    lines += ["", i18n.get("panel-login-xbox-row", status=login)]
    if steam_link is not None:
        lines.append(
            i18n.get(
                "panel-login-steam-row",
                name=link_nickname(steam_link),
                status=visibility_status_text(steam_link, i18n.locale),
            )
        )
    if psn_link is not None:
        lines.append(
            i18n.get(
                "panel-login-psn-row",
                name=link_nickname(psn_link),
                status=visibility_status_text(psn_link, i18n.locale),
            )
        )
    lines.append(
        i18n.get(
            "panel-publication-row",
            status=await _publication_status(repo, user.tg_id, user.is_excluded, i18n),
        )
    )
    if user.xuid or steam_link is not None or psn_link is not None:
        # Every connected platform competes for this row now (issue #1's own
        # tail, closed 2026-09-15) — it used to be gated on `user.xuid` and so
        # was missing entirely from a Steam/PSN-only person's panel, the last
        # row here that still assumed Xbox.
        playing = await _now_playing(repo, user, steam_link, psn_link, i18n)
        lines.append(i18n.get("panel-now-playing-row", playing=playing))
    lines += [
        "",
        # Kept as a text line too (#18): the person should see which
        # timezone is selected, not just have it on the button label.
        i18n.get("panel-timezone-row", offset=format_offset(tz_offset, i18n)),
    ]
    if needs_reconnect:
        lines += ["", i18n.get("panel-reconnect-hint")]
    return Screen("\n".join(lines), keyboard)


async def _now_playing(
    repo: Repo,
    user: User,
    steam_link: PlatformLink | None,
    psn_link: PlatformLink | None,
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
    presence = pick_presence(
        xbox=await repo.presence_of(user.xuid) if user.xuid else None,
        steam=await repo.steam_presence_of(steam_link.external_id) if steam_link else None,
        psn=await repo.psn_presence_of(psn_link.external_id) if psn_link else None,
    )
    if presence is None:
        return i18n.get("panel-no-presence-data")
    if not presence.online:
        return i18n.get("panel-offline", ago=humanize_ago(presence.updated_at, i18n.locale))
    tag = platform_tag(presence.platform, i18n.locale)
    if not presence.title_id:
        return f"{tag}  ·  " + i18n.get("panel-online-idle")
    # Presence gives no name for PC titles — fall back to the cache the
    # poller fills (SPEC 4), same as the admin card.
    game = presence.game or await repo.title_name(presence.title_id) or presence.title_id
    return f"{tag}  ·  " + i18n.get("panel-playing", game=game)


async def _publication_status(repo: Repo, tg_id: int, is_excluded: bool, i18n: I18nContext) -> str:
    if is_excluded:
        # An exclusion is never silent: the person sees it here (SPEC 6.4).
        return i18n.get("panel-excluded")
    chats = await repo.chats_of_user(tg_id)
    if not chats:
        return i18n.get("panel-not-subscribed-anywhere")
    return i18n.get("panel-subscribed-in", chats=", ".join(f"«{title}»" for title in chats))


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
    return Screen(i18n.get(prompt, title=chat.title or chat.chat_id), builder.as_markup())
