"""/admin — the operator's screen (SPEC 6.4). UI only: all data comes from services.

One message that redraws itself, like the user panel. Access is the
ADMIN_TG_IDS list from the config, checked on the router so that no single
handler can forget it.
"""

from __future__ import annotations

import contextlib
import logging
from datetime import timedelta

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.filters import BaseFilter, Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    Message,
    TelegramObject,
)
from aiogram_i18n import I18nContext

from bot.config import Settings
from bot.constants import (
    Platform,
    account_platform_of,
)
from bot.db.repo import Repo
from bot.i18n import translator
from bot.poller.fetcher import Fetcher
from bot.poller.psn_fetcher import PsnFetcher
from bot.poller.service_health import (
    DEFAULT_KEY_CHECK_INTERVAL_MIN,
    KEY_CHECK_INTERVAL_KEY,
)
from bot.poller.steam_fetcher import SteamFetcher
from bot.services.admin_settings import (
    CHAT_SCOPED_KEYS,
    DEFAULT_RARITY_MODE_DEFAULT,
    DEFAULT_RARITY_MODE_KEY,
    DEFAULT_SHOW_LINKS_DEFAULT,
    DEFAULT_SHOW_LINKS_KEY,
    FLOOD_LIMIT_DEFAULT,
    FLOOD_LIMIT_MAX,
    FLOOD_LIMIT_MIN,
    FLOOD_WINDOW_MAX,
    FLOOD_WINDOW_MIN,
    NUMERIC_SETTINGS,
    RARE_THRESHOLD_MAX,
    RARE_THRESHOLD_MIN,
)
from bot.services.naming import link_nickname, person_name, xbox_nickname
from bot.services.psn.auth import PsnAuth
from bot.services.psn.client import (
    PsnClientSetupError,
    PsnTokenDeadError,
)
from bot.services.steam.auth import (
    SteamAuth,
    SteamKeyInvalidError,
)
from bot.services.translate.auth import (
    AnthropicAuth,
    AnthropicKeyInvalidError,
)
from bot.util import parse_iso, parse_utc_offset, utcnow
from bot.views.admin import (
    _cancel_input_keyboard,
    _format_limit,
    _hour_grid_markup,
    _setting_label,
    _toast_preview,
    _tz_grid_markup,
    find_chat,
    render_admin_user_delete_confirm_1,
    render_admin_user_delete_confirm_2,
    render_chat_card,
    render_chat_list,
    render_flood_limit_prompt,
    render_flood_window_prompt,
    render_keys,
    render_limit,
    render_limits,
    render_new_user_defaults,
    render_rare_prompt,
    render_reset_confirm,
    render_system_wipe_prompt,
    render_user_card,
    render_user_list,
    render_wipe_prompt,
    render_zone_manual_prompt,
)
from bot.views.admin_home import render_admin_home
from bot.views.keyboards import (
    format_offset,
    next_locale,
    next_rarity_mode,
)

log = logging.getLogger(__name__)

router = Router(name="admin")


class IsAdmin(BaseFilter):
    async def __call__(self, event: TelegramObject, settings: Settings) -> bool:
        user = getattr(event, "from_user", None)
        return user is not None and settings.is_admin(user.id)


router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


async def _replace_admin_home(
    bot: Bot,
    repo: Repo,
    fetcher: Fetcher,
    steam_fetcher: SteamFetcher,
    psn_auth: PsnAuth,
    steam_auth: SteamAuth,
    admin_id: int,
    prefix: str = "",
) -> None:
    """Sends a fresh /admin home screen as a brand-new message, replacing
    whatever this admin had open before, and (re)arms the auto-refresh job
    for it (Follow-up 2026-09-06) — shared by the bare /admin command and
    every flow that confirms a change and redraws home as a new message
    rather than editing the current one in place (a:home's own callback
    does the latter, so it never needs this)."""
    # This one knows whose panel it is rebuilding, so it reads the locale
    # itself rather than making every caller carry it (#48).
    locale = await repo.user_locale(admin_id)
    text, markup = await render_admin_home(
        repo, fetcher, steam_fetcher, psn_auth, steam_auth, locale=locale
    )
    if prefix:
        text = f"{prefix}\n\n{text}"
    previous = await repo.get_admin_panel_refresh(admin_id)
    if previous is not None:
        with contextlib.suppress(Exception):
            await bot.delete_message(admin_id, previous.message_id)
    sent = await bot.send_message(admin_id, text, reply_markup=markup)
    interval = await repo.get_int_setting(KEY_CHECK_INTERVAL_KEY, DEFAULT_KEY_CHECK_INTERVAL_MIN)
    if interval > 0:
        await repo.start_admin_panel_refresh(admin_id, sent.message_id)


@router.message(Command("admin"), F.chat.type == ChatType.PRIVATE)
async def admin_command(
    message: Message,
    repo: Repo,
    fetcher: Fetcher,
    steam_fetcher: SteamFetcher,
    psn_auth: PsnAuth,
    steam_auth: SteamAuth,
    bot: Bot,
) -> None:
    _awaiting_input.pop(message.from_user.id, None)  # a fresh /admin cancels any pending flow
    await _replace_admin_home(
        bot, repo, fetcher, steam_fetcher, psn_auth, steam_auth, message.chat.id
    )


@router.callback_query(F.data == "a:noop")
async def admin_noop(callback: CallbackQuery) -> None:
    """The page counter between a paginated list's arrows. It is a button
    only because a keyboard row has nowhere else to put a label — answering
    the callback is all it does, which stops Telegram's spinner."""
    await callback.answer()


@router.callback_query(F.data == "a:home")
async def admin_home(
    callback: CallbackQuery,
    repo: Repo,
    fetcher: Fetcher,
    steam_fetcher: SteamFetcher,
    psn_auth: PsnAuth,
    steam_auth: SteamAuth,
    i18n: I18nContext,
) -> None:
    _awaiting_input.pop(callback.from_user.id, None)
    await _redraw(
        callback,
        *await render_admin_home(
            repo, fetcher, steam_fetcher, psn_auth, steam_auth, locale=i18n.locale
        ),
    )


# --------------------------------------------------------- Platform keys (#17)

# The "Ключи платформ" screen, where an admin sets/changes/clears the shared
# Steam key and PSN NPSSO — both take free-text answers, and the message
# handler for them is registered before the free-text numeric/timezone
# handlers below on purpose: aiogram tries message handlers in registration
# order and stops at the first whose filter matches, so an admin's answer
# here (a key or an NPSSO) must be claimed by this filter before the generic
# ones get a chance at it.
#
# This used to also host a PSN trophy-lookup test screen (a live, uncached
# carve-out of SPEC 1.5's cache-only rule, from before any of this was wired
# into /stats) — removed once this Keys screen covered NPSSO management on
# its own and the test screen had nothing left to justify a live API call
# outside a background job.

STEAM_KEY_KEY = "steam_api_key"
PSN_NPSSO_KEY = "psn_npsso"
# Anthropic (2026-09-09 user request) — achievement-description translation
# only, same admin-settable-shared-credential shape as the two above (#17).
ANTHROPIC_KEY_KEY = "anthropic_api_key"


class AwaitingAdminTextInput(BaseFilter):
    async def __call__(self, event: TelegramObject) -> bool:
        user = getattr(event, "from_user", None)
        if user is None:
            return False
        pending = _awaiting_input.get(user.id)
        return pending is not None and pending[0] in (
            STEAM_KEY_KEY,
            PSN_NPSSO_KEY,
            ANTHROPIC_KEY_KEY,
        )


@router.callback_query(F.data == "a:keys")
async def keys_menu(
    callback: CallbackQuery,
    steam_auth: SteamAuth,
    psn_auth: PsnAuth,
    anthropic_auth: AnthropicAuth,
    i18n: I18nContext,
) -> None:
    _awaiting_input.pop(callback.from_user.id, None)
    await _redraw(
        callback, *await render_keys(steam_auth, psn_auth, anthropic_auth, locale=i18n.locale)
    )


# One parameterized handler per action instead of a Steam/PSN pair each
# (2026-09-09 refactor, same shape reset_platform_confirm/_confirmed below
# already used for all three platforms) — callback_data's own trailing
# segment says which key, same "()" wiring on either platform's button.
# Anthropic (2026-09-09) slotted into the same dicts rather than a third
# handler pair — exactly the duplication this refactor exists to avoid.

_KEYSET_APP_SETTING_KEY = {
    "steam": STEAM_KEY_KEY,
    "psn": PSN_NPSSO_KEY,
    "anthropic": ANTHROPIC_KEY_KEY,
}
_KEYSET_PROMPT = {
    STEAM_KEY_KEY: "admin-keys-steam-prompt",
    PSN_NPSSO_KEY: "admin-keys-psn-prompt",
    ANTHROPIC_KEY_KEY: "admin-keys-anthropic-prompt",
}


@router.callback_query(F.data.startswith("a:keyset:"))
async def keys_set(callback: CallbackQuery, i18n: I18nContext) -> None:
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    platform = callback.data.rsplit(":", 1)[1]
    key = _KEYSET_APP_SETTING_KEY[platform]
    _awaiting_input[callback.from_user.id] = (key, None)
    await _redraw(callback, _(_KEYSET_PROMPT[key]), _cancel_input_keyboard(locale=i18n.locale))


@router.callback_query(F.data.startswith("a:keyclr:"))
async def keys_clear(
    callback: CallbackQuery,
    steam_auth: SteamAuth,
    psn_auth: PsnAuth,
    anthropic_auth: AnthropicAuth,
    i18n: I18nContext,
) -> None:
    assert callback.data is not None
    platform = callback.data.rsplit(":", 1)[1]
    auth: SteamAuth | PsnAuth | AnthropicAuth = {
        "steam": steam_auth,
        "psn": psn_auth,
        "anthropic": anthropic_auth,
    }[platform]
    await auth.clear(callback.from_user.id)
    _awaiting_input.pop(callback.from_user.id, None)
    await _redraw(
        callback, *await render_keys(steam_auth, psn_auth, anthropic_auth, locale=i18n.locale)
    )


@router.callback_query(F.data == "a:psncancel")
async def admin_text_input_cancel(
    callback: CallbackQuery,
    repo: Repo,
    fetcher: Fetcher,
    steam_fetcher: SteamFetcher,
    psn_auth: PsnAuth,
    steam_auth: SteamAuth,
    i18n: I18nContext,
) -> None:
    """The way out of a still-armed key/NPSSO retry (Follow-up 2026-09-06,
    found live: a stray later message got misread as the next answer once
    nobody explicitly cancelled) — drops back to the admin home screen."""
    _awaiting_input.pop(callback.from_user.id, None)
    await _redraw(
        callback,
        *await render_admin_home(
            repo, fetcher, steam_fetcher, psn_auth, steam_auth, locale=i18n.locale
        ),
    )


@router.message(F.chat.type == ChatType.PRIVATE, AwaitingAdminTextInput())
async def admin_text_input(
    message: Message,
    psn_auth: PsnAuth,
    steam_auth: SteamAuth,
    anthropic_auth: AnthropicAuth,
    i18n: I18nContext,
) -> None:
    _ = translator("admin", i18n.locale)
    assert message.from_user is not None and message.text is not None
    pending = _awaiting_input.get(message.from_user.id)
    assert pending is not None
    key = pending[0]
    raw = message.text.strip()

    if key == STEAM_KEY_KEY:
        try:
            await steam_auth.set_key(raw, message.from_user.id)
        except SteamKeyInvalidError:
            # Stays armed — a typo is worth just retrying — but the explicit
            # cancel is there for a stray later paste, same as PSN below.
            await message.answer(
                _("admin-keys-steam-invalid"),
                reply_markup=_cancel_input_keyboard(locale=i18n.locale),
            )
            return
        _awaiting_input.pop(message.from_user.id, None)
        text, markup = await render_keys(steam_auth, psn_auth, anthropic_auth, locale=i18n.locale)
        await message.answer(_("admin-keys-steam-saved", text=text), reply_markup=markup)
        return

    if key == PSN_NPSSO_KEY:
        try:
            await psn_auth.set_npsso(raw, message.from_user.id)
        except PsnTokenDeadError:
            # Stays armed on purpose — a typo is worth just retrying,
            # not a trip back through /admin — but a stray later message
            # (found live 2026-09-06: a repeated paste while debugging got
            # misread as a PSN Online ID once the state moved on) needs an
            # explicit way out too, not just "send something else".
            await message.answer(
                _("admin-psn-npsso-invalid"),
                reply_markup=_cancel_input_keyboard(locale=i18n.locale),
            )
            return
        except PsnClientSetupError as exc:
            # Found live 2026-09-06: psnawp couldn't even construct its own
            # client (a sandboxed temp dir) and the admin got no reply at
            # all — this is deliberately a different message from the one
            # above, so a real bug doesn't get blamed on the NPSSO itself.
            log.exception("admin_text_input: could not set up the PSN client")
            await message.answer(
                _("admin-psn-client-error", error=exc),
                reply_markup=_cancel_input_keyboard(locale=i18n.locale),
            )
            return
        _awaiting_input.pop(message.from_user.id, None)
        text, markup = await render_keys(steam_auth, psn_auth, anthropic_auth, locale=i18n.locale)
        await message.answer(_("admin-keys-psn-saved", text=text), reply_markup=markup)
        return

    if key == ANTHROPIC_KEY_KEY:
        try:
            await anthropic_auth.set_key(raw, message.from_user.id)
        except AnthropicKeyInvalidError:
            # Same "stays armed, typo is worth just retrying" shape as
            # Steam/PSN above.
            await message.answer(
                _("admin-keys-anthropic-invalid"),
                reply_markup=_cancel_input_keyboard(locale=i18n.locale),
            )
            return
        _awaiting_input.pop(message.from_user.id, None)
        text, markup = await render_keys(steam_auth, psn_auth, anthropic_auth, locale=i18n.locale)
        await message.answer(_("admin-keys-anthropic-saved", text=text), reply_markup=markup)
        return


@router.callback_query(F.data == "a:newusers")
async def new_user_defaults_menu(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    await _redraw(callback, *await render_new_user_defaults(repo, locale=i18n.locale))


@router.callback_query(F.data == "a:defaultrarity")
async def default_rarity_cycle(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    current = await repo.get_app_setting(DEFAULT_RARITY_MODE_KEY, DEFAULT_RARITY_MODE_DEFAULT)
    assert current is not None
    mode = next_rarity_mode(current)
    await repo.set_app_setting(DEFAULT_RARITY_MODE_KEY, mode, callback.from_user.id)
    await _redraw(callback, *await render_new_user_defaults(repo, locale=i18n.locale))


@router.callback_query(F.data == "a:defaultlinks")
async def default_show_links_toggle(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    current = await repo.get_int_setting(DEFAULT_SHOW_LINKS_KEY, int(DEFAULT_SHOW_LINKS_DEFAULT))
    await repo.set_app_setting(
        DEFAULT_SHOW_LINKS_KEY, "0" if current else "1", callback.from_user.id
    )
    await _redraw(callback, *await render_new_user_defaults(repo, locale=i18n.locale))


# ------------------------------------------------------ free-text numeric settings

# Row-cap settings (always global — no per-chat meaning) and the per-chat
# rare threshold share one "type a number, not a button" flow — free values
# a handful of preset buttons could not cover anyway. Keyed by tg_id ->
# (which setting, which chat — None for a global row-cap), so a stray digit
# typed by an admin who isn't in this flow is never mistaken for input, and
# the one regex handler below knows which validation and target apply.

_awaiting_input: dict[int, tuple[str, int | None]] = {}


@router.callback_query(F.data == "a:limits")
async def limits_menu(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    await _redraw(callback, *(await render_limits(repo, locale=i18n.locale)).as_pair())


@router.callback_query(F.data.startswith("a:limit:"))
async def limit_menu(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    assert callback.data is not None
    key = callback.data.rsplit(":", 1)[1]
    _awaiting_input[callback.from_user.id] = (key, None)
    await _redraw(callback, *(await render_limit(repo, key, locale=i18n.locale)).as_pair())


@router.message(F.chat.type == ChatType.PRIVATE, F.text.regexp(r"^\d+([.,]\d+)?$"))
async def numeric_setting_input(
    message: Message,
    repo: Repo,
    fetcher: Fetcher,
    steam_fetcher: SteamFetcher,
    psn_auth: PsnAuth,
    steam_auth: SteamAuth,
    bot: Bot,
    i18n: I18nContext,
) -> None:
    _ = translator("admin", i18n.locale)
    assert message.from_user is not None and message.text is not None
    pending = _awaiting_input.get(message.from_user.id)
    if pending is None:
        return  # a plain number from an admin who isn't in this flow — ignore
    key, chat_id = pending
    if key not in NUMERIC_SETTINGS and key not in CHAT_SCOPED_KEYS:
        # An all-digit PSN Online ID landing here while _awaiting_psn_lookup
        # is pending, say (SPEC 9, M-PSN-1) — not this flow's business, its
        # own handler (below) owns whatever key it registered.
        return

    if key == "rare_threshold_percent":
        assert chat_id is not None  # only ever chat-scoped now (SPEC 5.5)
        value = float(message.text.replace(",", "."))
        if not (RARE_THRESHOLD_MIN <= value <= RARE_THRESHOLD_MAX):
            await message.answer(
                _(
                    "admin-number-range-retry",
                    minimum=RARE_THRESHOLD_MIN,
                    maximum=RARE_THRESHOLD_MAX,
                )
            )
            return
        del _awaiting_input[message.from_user.id]
        await repo.update_chat_settings(chat_id, rare_threshold_percent=value)
        reply_text, markup = await render_chat_card(repo, chat_id, locale=i18n.locale)
        await message.answer(
            _("admin-threshold-saved", value=f"{value:g}", text=reply_text),
            reply_markup=markup,
        )
        return

    if key in ("flood_limit", "flood_window_minutes"):
        assert chat_id is not None  # chat-scoped, same as rare_threshold_percent above
        if "." in message.text or "," in message.text:
            await message.answer(_("admin-integer-retry"))
            return
        value_int = int(message.text)
        minimum, maximum = (
            (FLOOD_LIMIT_MIN, FLOOD_LIMIT_MAX)
            if key == "flood_limit"
            else (FLOOD_WINDOW_MIN, FLOOD_WINDOW_MAX)
        )
        if not (minimum <= value_int <= maximum):
            await message.answer(_("admin-number-range-retry", minimum=minimum, maximum=maximum))
            return
        del _awaiting_input[message.from_user.id]
        await repo.update_chat_settings(chat_id, **{key: value_int})
        reply_text, markup = await render_chat_card(repo, chat_id, locale=i18n.locale)
        saved_key = "admin-flood-saved" if key == "flood_limit" else "admin-flood-window-saved"
        await message.answer(_(saved_key, value=value_int, text=reply_text), reply_markup=markup)
        return

    # The row-cap settings below are always global — chat_id is always None
    # here, there is no per-chat meaning for them.
    if "." in message.text or "," in message.text:
        await message.answer(_("admin-integer-retry"))
        return
    value_int = int(message.text)
    spec = NUMERIC_SETTINGS[key]
    if not (spec.min <= value_int <= spec.max):
        await message.answer(_("admin-number-range-retry", minimum=spec.min, maximum=spec.max))
        return
    stored = str(value_int)
    confirm = (
        f"{_setting_label(spec, locale=i18n.locale)}: "
        f"{_format_limit(key, stored, locale=i18n.locale)}"
    )

    del _awaiting_input[message.from_user.id]
    await repo.set_app_setting(key, stored, message.from_user.id)
    await _replace_admin_home(
        bot,
        repo,
        fetcher,
        steam_fetcher,
        psn_auth,
        steam_auth,
        message.from_user.id,
        prefix=confirm,
    )


# ------------------------------------------------------- per-chat settings

# Rare threshold, daily-summary time and its timezone are always explicit
# per chat (SPEC 5.5, 5.7) — no global screen any more, editing always
# happens from a chat's own card.


@router.callback_query(F.data.startswith("a:crt:"))
async def chat_rare_menu(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    chat = await find_chat(repo, chat_id)
    if chat is None:
        await callback.answer(_("admin-chat-not-found"), show_alert=True)
        return
    _awaiting_input[callback.from_user.id] = ("rare_threshold_percent", chat_id)
    await _redraw(callback, *render_rare_prompt(chat, locale=i18n.locale).as_pair())


@router.callback_query(F.data.startswith("a:cfltoggle:"))
async def chat_flood_toggle(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    """On/off for the whole filter (2026-09-09 user request), next to the
    limit/window buttons below — same one-tap-toggle shape as the daily
    summary switch above. Off is flood_limit = 0 (the schema's own "off"
    convention); back on lands on FLOOD_LIMIT_DEFAULT rather than
    remembering whatever it was set to before — no column exists to
    remember that, and re-tuning it with the limit button right next to
    this one costs one more tap, not a real loss."""
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    chat = await find_chat(repo, chat_id)
    if chat is None:
        await callback.answer(_("admin-chat-not-found"), show_alert=True)
        return
    new_limit = 0 if chat.flood_limit > 0 else FLOOD_LIMIT_DEFAULT
    await repo.update_chat_settings(chat_id, flood_limit=new_limit)
    await callback.answer()
    await _redraw(
        callback, *await render_chat_card(repo, chat_id, locale=i18n.locale, section="flood")
    )


# The chat card's three sub-screens (2026-09-11, user request). Each used to
# be a single row of two to four buttons on the card itself; the card now
# carries one entry per group and these open the group. The card *text* is
# unchanged in all of them — only the keyboard differs — so the chat's state
# stays on screen while its settings are being tuned.


@router.callback_query(F.data.startswith("a:msum:"))
async def chat_summary_menu(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    assert callback.data is not None
    chat_id = int(callback.data.split(":")[2])
    await _redraw(
        callback, *await render_chat_card(repo, chat_id, locale=i18n.locale, section="summary")
    )


@router.callback_query(F.data.startswith("a:mflood:"))
async def chat_flood_menu_screen(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    assert callback.data is not None
    chat_id = int(callback.data.split(":")[2])
    await _redraw(
        callback, *await render_chat_card(repo, chat_id, locale=i18n.locale, section="flood")
    )


@router.callback_query(F.data.startswith("a:mdel:"))
async def chat_messages_menu(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    assert callback.data is not None
    chat_id = int(callback.data.split(":")[2])
    await _redraw(
        callback, *await render_chat_card(repo, chat_id, locale=i18n.locale, section="messages")
    )


@router.callback_query(F.data.startswith("a:cloc:"))
async def chat_locale_toggle(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    """Cycles the chat's own language (#48). One shared value per chat, not
    per viewer: Telegram cannot show two members of the same group different
    text, so somebody has to decide for everyone — the super-admin today,
    a chat admin once #47 exists.

    Only the chat's own broadcasts move; the super-admin's panel keeps
    rendering in the super-admin's own language, which is why this redraws
    with the injected context rather than a rebuilt one (unlike /panel's
    personal toggle, where the two are the same person).
    """
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    chat_id = int(callback.data.split(":")[2])
    chat = await find_chat(repo, chat_id)
    if chat is None:
        await callback.answer(_("admin-chat-not-found"), show_alert=True)
        return
    await repo.update_chat_settings(chat_id, locale=next_locale(chat.locale))
    # No toast of its own: _redraw already acknowledges the press, and the
    # card it redraws shows the new language on its own line anyway.
    await _redraw(callback, *await render_chat_card(repo, chat_id, locale=i18n.locale))


@router.callback_query(F.data.startswith("a:cfl:"))
async def chat_flood_menu(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    chat = await find_chat(repo, chat_id)
    if chat is None:
        await callback.answer(_("admin-chat-not-found"), show_alert=True)
        return
    _awaiting_input[callback.from_user.id] = ("flood_limit", chat_id)
    await _redraw(callback, *render_flood_limit_prompt(chat, locale=i18n.locale).as_pair())


@router.callback_query(F.data.startswith("a:cflw:"))
async def chat_flood_window_menu(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    chat = await find_chat(repo, chat_id)
    if chat is None:
        await callback.answer(_("admin-chat-not-found"), show_alert=True)
        return
    _awaiting_input[callback.from_user.id] = ("flood_window_minutes", chat_id)
    await _redraw(callback, *render_flood_window_prompt(chat, locale=i18n.locale).as_pair())


@router.callback_query(F.data.startswith("a:ctime:"))
async def chat_time_menu(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    chat = await find_chat(repo, chat_id)
    if chat is None:
        await callback.answer(_("admin-chat-not-found"), show_alert=True)
        return
    await _redraw(
        callback,
        _("admin-chat-time-prompt", title=chat.title or chat_id, time=chat.daily_summary_time),
        _hour_grid_markup(
            chat.daily_summary_time,
            f"a:ctimes:{chat_id}:",
            f"a:ctz:{chat_id}",
            f"a:chat:{chat_id}",
            locale=i18n.locale,
        ),
    )


@router.callback_query(F.data.startswith("a:ctimes:"))
async def chat_time_set(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    _, _, chat_id_raw, hour_raw = callback.data.split(":")
    chat_id, hour = int(chat_id_raw), int(hour_raw)
    await repo.update_chat_settings(chat_id, daily_summary_time=f"{hour:02d}:00")
    await callback.answer(_("admin-chat-time-saved", time=f"{hour:02d}:00"))
    await _redraw(
        callback, *await render_chat_card(repo, chat_id, locale=i18n.locale, section="summary")
    )


@router.callback_query(F.data.startswith("a:ctz:"))
async def chat_zone_menu(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    chat = await find_chat(repo, chat_id)
    if chat is None:
        await callback.answer(_("admin-chat-not-found"), show_alert=True)
        return
    await _redraw(
        callback,
        _(
            "admin-chat-zone-prompt",
            title=chat.title or chat_id,
            offset=format_offset(chat.tz_offset_min),
        ),
        _tz_grid_markup(
            chat.tz_offset_min,
            f"a:ctzs:{chat_id}:",
            f"a:ctzm:{chat_id}",
            f"a:ctime:{chat_id}",
            locale=i18n.locale,
        ),
    )


@router.callback_query(F.data.startswith("a:ctzs:"))
async def chat_zone_set(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    assert callback.data is not None
    _, _, chat_id_raw, minutes_raw = callback.data.split(":")
    chat_id, minutes = int(chat_id_raw), int(minutes_raw)
    await repo.update_chat_settings(chat_id, tz_offset_min=minutes)
    await callback.answer(format_offset(minutes))
    await _redraw(
        callback, *await render_chat_card(repo, chat_id, locale=i18n.locale, section="summary")
    )


@router.callback_query(F.data.startswith("a:ctzm:"))
async def chat_zone_manual_prompt(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    chat = await find_chat(repo, chat_id)
    if chat is None:
        await callback.answer(_("admin-chat-not-found"), show_alert=True)
        return
    _awaiting_input[callback.from_user.id] = ("tz_offset_min", chat_id)
    await _redraw(callback, *render_zone_manual_prompt(chat, locale=i18n.locale).as_pair())


@router.message(
    F.chat.type == ChatType.PRIVATE, F.text.regexp(r"(?i)^(?:utc)?\s*[+-]\d{1,2}(?::[0-5]\d)?$")
)
async def chat_timezone_input(message: Message, repo: Repo, i18n: I18nContext) -> None:
    _ = translator("admin", i18n.locale)
    assert message.from_user is not None and message.text is not None
    pending = _awaiting_input.get(message.from_user.id)
    if pending is None or pending[0] != "tz_offset_min":
        return  # a stray signed number from an admin not in this flow — ignore
    _, chat_id = pending
    assert chat_id is not None

    minutes = parse_utc_offset(message.text)
    if minutes is None:  # out of −12..+14 range — the regex alone can't catch that
        await message.answer(_("admin-timezone-invalid"))
        return

    del _awaiting_input[message.from_user.id]
    await repo.update_chat_settings(chat_id, tz_offset_min=minutes)
    reply_text, markup = await render_chat_card(repo, chat_id, locale=i18n.locale)
    await message.answer(
        _("admin-timezone-saved", offset=format_offset(minutes), text=reply_text),
        reply_markup=markup,
    )


# --------------------------------------------------------------------- users


@router.callback_query(F.data.startswith("a:users:"))
async def users_page(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    assert callback.data is not None
    page = int(callback.data.rsplit(":", 1)[1])
    await _redraw(callback, *await render_user_list(repo, page, locale=i18n.locale))


@router.callback_query(F.data.startswith("a:u:"))
async def user_card(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    assert callback.data is not None
    tg_id = int(callback.data.rsplit(":", 1)[1])
    await _redraw(callback, *await render_user_card(repo, tg_id, locale=i18n.locale))


@router.callback_query(F.data.startswith("a:excl:"))
async def user_exclude(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    _, _, raw_id, raw_flag = callback.data.split(":")
    tg_id, excluded = int(raw_id), raw_flag == "1"
    await repo.set_excluded(tg_id, excluded, callback.from_user.id)
    await callback.answer(_("admin-user-excluded") if excluded else _("admin-user-restored"))
    await _redraw(callback, *await render_user_card(repo, tg_id, locale=i18n.locale))


_SYNC_NOT_CONNECTED_KEY = {
    "xbox": "admin-user-not-connected",
    "steam": "admin-steam-not-connected",
    "psn": "admin-psn-not-connected",
}


async def _sync_target(
    repo: Repo, platform: str, tg_id: int, *, locale: str
) -> tuple[str, str] | None:
    """(external_id, display_name) for user_refresh below, or None if this
    platform isn't connected for this person — Xbox resolves through
    `users`, Steam/PSN through `platform_links`, same split every other
    per-platform lookup in this file already has."""
    _ = translator("admin", locale)
    if platform == "xbox":
        user = await repo.get_user(tg_id)
        if user is None or not user.xuid:
            return None
        return user.xuid, user.gamertag or _("admin-default-player")
    link = await repo.get_platform_link(
        tg_id, Platform.STEAM if platform == "steam" else Platform.PSN
    )
    if link is None:
        return None
    return link.external_id, link_nickname(link)


@router.callback_query(F.data.startswith("a:sync:"))
async def user_refresh(
    callback: CallbackQuery,
    repo: Repo,
    fetcher: Fetcher,
    steam_fetcher: SteamFetcher,
    psn_fetcher: PsnFetcher,
    settings: Settings,
    i18n: I18nContext,
) -> None:
    """The only place in the whole interface that may call the API on demand
    (SPEC 1.5) — one handler for all three platforms (2026-09-09 refactor,
    same shape reset_platform_confirm/_confirmed below already used):
    Fetcher/SteamFetcher/PsnFetcher all expose a compatible
    refresh_user(tg_id, external_id, name, locale) -> str."""
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    # Not `_, _prefix, platform, tg_id_s`: that bound `_` — the translator,
    # two lines up — to the string "a", so the next `_("key")` raised
    # TypeError and this button had never once worked (found 2026-09-13 by
    # capturing the real screens; the same slip killed "🗑 Сброс" below).
    _prefix, _action, platform, tg_id_s = callback.data.split(":")
    tg_id = int(tg_id_s)

    target = await _sync_target(repo, platform, tg_id, locale=i18n.locale)
    if target is None:
        await callback.answer(_(_SYNC_NOT_CONNECTED_KEY[platform]), show_alert=True)
        return
    external_id, name = target

    await callback.answer(_("admin-refreshing"))
    fetcher_by_platform: dict[str, Fetcher | SteamFetcher | PsnFetcher] = {
        "xbox": fetcher,
        "steam": steam_fetcher,
        "psn": psn_fetcher,
    }
    try:
        summary = await fetcher_by_platform[platform].refresh_user(
            tg_id, external_id, name, i18n.locale
        )
        delta = await _sync_delta(
            repo,
            fetcher,
            steam_fetcher,
            settings,
            platform=platform,
            tg_id=tg_id,
            external_id=external_id,
            name=name,
            locale=i18n.locale,
        )
    except Exception:
        log.exception("admin %s refresh of tg_id=%s failed", platform, tg_id)
        await callback.answer(_("admin-refresh-failed"), show_alert=True)
        return
    text, markup = await render_user_card(repo, tg_id, locale=i18n.locale)
    if delta:
        summary = f"{summary}\n{delta}"
    await _redraw(callback, f"{text}\n\n{summary}", markup)


async def _sync_delta(
    repo: Repo,
    fetcher: Fetcher,
    steam_fetcher: SteamFetcher,
    settings: Settings,
    *,
    platform: str,
    tg_id: int,
    external_id: str,
    name: str,
    locale: str,
) -> str:
    """Everything earned since the newest unlock already stored — the "pull
    what is new" half of "🔄 Обновить" (user request, 2026-09-13).

    `refresh_user` on its own is a *right now* look: presence, plus the
    achievements of the game being played at this moment. For somebody who is
    offline that finds nothing at all, which is not what the button claims to
    do. PSN needs nothing extra here — its own `refresh_user` already runs the
    ordinary trophy scan, which is a delta by construction: it walks the
    recently-touched titles and fetches detail only where progress grew.

    What it finds is stored in full and *announced* only inside the usual
    catch-up window. A delta reaching back a month is worth storing; it is
    never worth posting to a chat all at once.
    """
    _ = translator("admin", locale)
    since = await repo.account_latest_unlock(account_platform_of(platform), external_id)
    window = settings.catchup_publish_window_hours
    if platform == "xbox":
        titles, published = await fetcher.catch_up(
            tg_id,
            external_id,
            name,
            parse_iso(since) if since else None,
            window,
            settings.catchup_max_titles,
        )
        return _("admin-sync-delta", titles=titles, published=published)
    if platform == "steam" and since is not None:
        published = await steam_fetcher.catch_up(tg_id, external_id, name, since, window)
        return _("admin-sync-delta-steam", published=published)
    return ""


# --------------------------------------------------------------------- chats


@router.callback_query(F.data == "a:chats")
async def chats_list(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    await _redraw(callback, *await render_chat_list(repo, locale=i18n.locale))


@router.callback_query(F.data.startswith("a:chat:"))
async def chat_card(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    await _redraw(callback, *await render_chat_card(repo, chat_id, locale=i18n.locale))


@router.callback_query(F.data.startswith("a:cds:"))
async def chat_daily(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    chat = await find_chat(repo, chat_id)
    if chat is None:
        await callback.answer(_("admin-chat-not-found"), show_alert=True)
        return
    await repo.update_chat_settings(chat_id, daily_summary=0 if chat.daily_summary else 1)
    await callback.answer()
    await _redraw(
        callback, *await render_chat_card(repo, chat_id, locale=i18n.locale, section="summary")
    )


@router.callback_query(F.data.startswith("a:coff:"))
async def chat_toggle_active(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    chat = await find_chat(repo, chat_id)
    if chat is None:
        await callback.answer(_("admin-chat-not-found"), show_alert=True)
        return
    await repo.set_chat_active(chat_id, not chat.is_active)
    await callback.answer(_("admin-chat-disabled") if chat.is_active else _("admin-chat-enabled"))
    await _redraw(callback, *await render_chat_card(repo, chat_id, locale=i18n.locale))


# Telegram caps an answerCallbackQuery's own text at 200 characters total
# (2026-09-09) — `bot_messages.preview` can itself be up to 200 chars, which
# would leave nothing for the "🗑 Удалено: «…»" wrapper around it and get
# silently cut off by Telegram mid-word. Trim further, specifically for the
# toast; the group-chat confirmation (chat.py's own /delete_last, a real
# message with no such cap) uses the stored preview untouched.


@router.callback_query(F.data.startswith("a:cdellast:"))
async def chat_delete_last(
    callback: CallbackQuery, repo: Repo, bot: Bot, i18n: I18nContext
) -> None:
    """The admin panel's own way in to /delete_last's logic (chat.py) —
    found live: an admin looking to undo the bot's last message in a chat
    went looking for it here first, not the group chat itself. Same target
    (the last *non-system* message, 2026-09-05) and same "expected failure,
    forget the row either way" handling, just reached from the chat card
    instead of typed into the chat.

    The toast itself now names what got deleted (2026-09-09 user request,
    `bot_messages.preview`) instead of a bare "Удалил последнее сообщение."
    — the card underneath is redrawn unchanged, the preview lives only in
    the toast (user feedback: baking it into the card body reads as
    permanent clutter, the toast is the right place for something
    transient).
    """
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    target = await repo.last_non_system_bot_message(chat_id)
    if target is None:
        await callback.answer(_("admin-no-bot-messages"), show_alert=True)
        return
    try:
        await bot.delete_message(chat_id, target.message_id)
    except Exception:
        log.info("admin delete_last failed for chat %s message %s", chat_id, target.message_id)
        await repo.forget_bot_messages(chat_id, [target.message_id])
        await callback.answer(_("admin-delete-old-failed"), show_alert=True)
        return
    await repo.forget_bot_messages(chat_id, [target.message_id])
    feedback = (
        _("admin-deleted-last-preview", preview=_toast_preview(target.preview))
        if target.preview
        else _("admin-deleted-last")
    )
    await callback.answer(feedback)
    await _redraw(
        callback, *await render_chat_card(repo, chat_id, locale=i18n.locale, section="messages")
    )


WIPE_WINDOW_HOURS = 24


@router.callback_query(F.data.startswith("a:cwipe:"))
async def chat_wipe_prompt(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    chat = await find_chat(repo, chat_id)
    if chat is None:
        await callback.answer(_("admin-chat-not-found"), show_alert=True)
        return
    ids = await repo.bot_messages_since(chat_id, utcnow() - timedelta(hours=WIPE_WINDOW_HOURS))
    if not ids:
        await callback.answer(_("admin-no-bot-messages-24h"), show_alert=True)
        return
    screen = render_wipe_prompt(chat, len(ids), WIPE_WINDOW_HOURS, locale=i18n.locale)
    await _redraw(callback, *screen.as_pair())


async def _bulk_delete_messages(bot: Bot, chat_id: int, ids: list[int]) -> bool:
    """Deletes in chunks of 100 — the Bot API's own cap on deleteMessages —
    shared by the unconditional wipe and the "system only" pair below
    (2026-09-05 refactor: this loop was duplicated verbatim between them).
    Returns whether every chunk went through; a failed chunk is logged, not
    raised — same "expected failure" tolerance as everywhere else here."""
    ok = True
    for start in range(0, len(ids), 100):
        try:
            await bot.delete_messages(chat_id, ids[start : start + 100])
        except Exception:
            log.info("bulk delete failed for chat %s, chunk at %s", chat_id, start)
            ok = False
    return ok


@router.callback_query(F.data.startswith("a:cwipey:"))
async def chat_wipe_confirm(
    callback: CallbackQuery, repo: Repo, bot: Bot, i18n: I18nContext
) -> None:
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    ids = await repo.bot_messages_since(chat_id, utcnow() - timedelta(hours=WIPE_WINDOW_HOURS))
    await _wipe_confirm(callback, repo, bot, chat_id, ids, locale=i18n.locale)


# A narrower sibling of the unconditional wipe above (2026-09-05 follow-up,
# "system message" auto-delete): these two leave published achievements,
# stats and summaries untouched, so they're safe as a routine cleanup, not
# just a "just in case" tool — one bounded to 24h, one with no time limit
# at all for whenever that isn't enough.


@router.callback_query(F.data.startswith("a:cswipe:"))
async def chat_system_wipe_prompt(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    since = utcnow() - timedelta(hours=WIPE_WINDOW_HOURS)
    ids = await repo.system_bot_messages_since(chat_id, since)
    await _system_wipe_prompt(
        callback, repo, chat_id, ids, f"a:cswipey:{chat_id}", locale=i18n.locale
    )


@router.callback_query(F.data.startswith("a:cswipey:"))
async def chat_system_wipe_confirm(
    callback: CallbackQuery, repo: Repo, bot: Bot, i18n: I18nContext
) -> None:
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    since = utcnow() - timedelta(hours=WIPE_WINDOW_HOURS)
    ids = await repo.system_bot_messages_since(chat_id, since)
    await _wipe_confirm(callback, repo, bot, chat_id, ids, locale=i18n.locale)


@router.callback_query(F.data.startswith("a:cswipeall:"))
async def chat_system_wipe_all_prompt(
    callback: CallbackQuery, repo: Repo, i18n: I18nContext
) -> None:
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    ids = await repo.all_system_bot_messages(chat_id)
    await _system_wipe_prompt(
        callback, repo, chat_id, ids, f"a:cswipeally:{chat_id}", locale=i18n.locale
    )


@router.callback_query(F.data.startswith("a:cswipeally:"))
async def chat_system_wipe_all_confirm(
    callback: CallbackQuery, repo: Repo, bot: Bot, i18n: I18nContext
) -> None:
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    ids = await repo.all_system_bot_messages(chat_id)
    await _wipe_confirm(callback, repo, bot, chat_id, ids, locale=i18n.locale)


# ------------------------------------------------------------------- screens


@router.callback_query(F.data.startswith("a:reset:"))
async def reset_platform_confirm(callback: CallbackQuery, i18n: I18nContext) -> None:
    """ "Сброс базы" is destructive and not undoable (user request 2026-09-08)
    — same one-tap-confirm shape as /disconnect_steam's own prompt, not an
    instant action behind a single tap."""
    assert callback.data is not None
    _prefix, _action, platform, tg_id_s = callback.data.split(":")  # not `_`, see user_refresh
    await _redraw(callback, *render_reset_confirm(platform, tg_id_s, locale=i18n.locale).as_pair())


@router.callback_query(F.data.startswith("a:resetok:"))
async def reset_platform_confirmed(
    callback: CallbackQuery,
    repo: Repo,
    fetcher: Fetcher,
    steam_fetcher: SteamFetcher,
    psn_fetcher: PsnFetcher,
    i18n: I18nContext,
) -> None:
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    # Four parts here too, and `_` stays the translator (see user_refresh):
    # this one unpacked four into three and raised ValueError instead.
    _prefix, _action, platform, tg_id_s = callback.data.split(":")
    tg_id = int(tg_id_s)
    await callback.answer(_("admin-refreshing"))

    try:
        if platform == "xbox":
            user = await repo.get_user(tg_id)
            assert user is not None and user.xuid is not None
            await repo.reset_xbox_data(tg_id, user.xuid)
            await fetcher.backfill(tg_id, user.xuid)
        elif platform == "steam":
            link = await repo.get_platform_link(tg_id, Platform.STEAM)
            assert link is not None
            # The account's own id, not the person's: since #52 the history
            # belongs to the account, and this call used to be handed `tg_id`,
            # which matches no row — so it deleted nothing and "reset" re-ran
            # backfill over data that was still there.
            await repo.reset_steam_data(link.external_id)
            await steam_fetcher.backfill(tg_id, link.external_id)
        else:
            link = await repo.get_platform_link(tg_id, Platform.PSN)
            assert link is not None
            await repo.reset_psn_data(tg_id, link.external_id)
            await psn_fetcher.backfill(tg_id, link.external_id)
    except Exception:
        log.exception("admin reset+resync of tg_id=%s platform=%s failed", tg_id, platform)
        await callback.answer(_("admin-refresh-failed"), show_alert=True)

    text, markup = await render_user_card(repo, tg_id, locale=i18n.locale)
    await _redraw(callback, text, markup)


@router.callback_query(F.data.startswith("a:udel:"))
async def admin_delete_user_step1(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    _prefix, _action, tg_id_s = callback.data.split(":")
    tg_id = int(tg_id_s)
    user = await repo.get_user(tg_id)
    if user is None:
        _ = translator("admin", i18n.locale)
        await callback.answer(_("admin-user-not-found"), show_alert=True)
        return
    name = person_name(
        tg_id=user.tg_id,
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username,
        xbox=xbox_nickname(gamertag_modern=user.gamertag_modern, gamertag=user.gamertag),
    )
    screen = render_admin_user_delete_confirm_1(name, tg_id, locale=i18n.locale)
    await _redraw(callback, *screen.as_pair())


@router.callback_query(F.data.startswith("a:udel1:"))
async def admin_delete_user_step2(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    _prefix, _action, tg_id_s = callback.data.split(":")
    tg_id = int(tg_id_s)
    user = await repo.get_user(tg_id)
    if user is None:
        _ = translator("admin", i18n.locale)
        await callback.answer(_("admin-user-not-found"), show_alert=True)
        return
    name = person_name(
        tg_id=user.tg_id,
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username,
        xbox=xbox_nickname(gamertag_modern=user.gamertag_modern, gamertag=user.gamertag),
    )
    screen = render_admin_user_delete_confirm_2(name, tg_id, locale=i18n.locale)
    await _redraw(callback, *screen.as_pair())


@router.callback_query(F.data.startswith("a:udel2:"))
async def admin_delete_user_confirmed(
    callback: CallbackQuery, repo: Repo, i18n: I18nContext
) -> None:
    _ = translator("admin", i18n.locale)
    _prefix, _action, tg_id_s = callback.data.split(":")
    tg_id = int(tg_id_s)
    await repo.delete_user(tg_id)
    await callback.answer(_("admin-delete-toast"))
    text, markup = await render_user_list(repo, 0, locale=i18n.locale)
    await _redraw(callback, text, markup)


async def _wipe_confirm(
    callback: CallbackQuery, repo: Repo, bot: Bot, chat_id: int, ids: list[int], *, locale: str
) -> None:
    """Shared tail of every wipe variant below: delete what the caller
    already decided on, forget the log rows either way (Telegram silently
    skips ids it can no longer delete — too old, already gone — and
    retrying those later would not help), report, redraw the chat card."""
    _ = translator("admin", locale)
    ok = await _bulk_delete_messages(bot, chat_id, ids)
    await repo.forget_bot_messages(chat_id, ids)
    await callback.answer(_("admin-wipe-done") if ok else _("admin-wipe-partial"))
    await _redraw(
        callback, *await render_chat_card(repo, chat_id, locale=locale, section="messages")
    )


async def _system_wipe_prompt(
    callback: CallbackQuery,
    repo: Repo,
    chat_id: int,
    ids: list[int],
    confirm_callback: str,
    *,
    locale: str,
) -> None:
    _ = translator("admin", locale)
    chat = await find_chat(repo, chat_id)
    if chat is None:
        await callback.answer(_("admin-chat-not-found"), show_alert=True)
        return
    if not ids:
        await callback.answer(_("admin-no-system-messages"), show_alert=True)
        return
    screen = render_system_wipe_prompt(chat, len(ids), confirm_callback, locale=locale)
    await _redraw(callback, *screen.as_pair())


async def _redraw(callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup) -> None:
    """One message that redraws itself, not a new one per press (SPEC 6)."""
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(text, reply_markup=markup)
        except Exception:
            # Telegram refuses an edit that changes nothing — harmless.
            pass
    await callback.answer()
