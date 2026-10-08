"""/admin — the operator's screen (SPEC 6.4). UI only: all data comes from services.

One message that redraws itself, like the user panel. Access is the
SUPERADMIN_TG_IDS list from the config, checked on the router so that no single
handler can forget it.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable
from typing import Any

from aiogram import Bot, F, Router
from aiogram.enums import ChatType, ParseMode
from aiogram.filters import BaseFilter, Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    Message,
    TelegramObject,
)
from aiogram_i18n import I18nContext

from bot.config import Settings
from bot.db.repo import Repo
from bot.i18n import translator
from bot.poller.fetcher import Fetcher
from bot.poller.psn_fetcher import PsnFetcher
from bot.poller.service_health import (
    DEFAULT_KEY_CHECK_INTERVAL_MIN,
    KEY_CHECK_INTERVAL_KEY,
)
from bot.poller.steam_fetcher import SteamFetcher
from bot.services import admin_cleanup, custom_avatars
from bot.services.admin_accounts import AdminAccounts
from bot.services.admin_cleanup import WIPE_WINDOW_HOURS, Wipe
from bot.services.admin_credentials import (
    AdminCredentials,
    CredentialInvalid,
    CredentialSetupError,
)
from bot.services.admin_registry import GROUPS, Kind, Scope, Setting, value_label
from bot.services.admin_registry import find as find_setting
from bot.services.admin_registry import label as registry_label
from bot.services.admin_registry import set_value as set_setting
from bot.services.admin_registry import values as registry_values
from bot.services.admin_settings import (
    SettingValueError,
)
from bot.services.message_log import stats_category
from bot.services.naming import link_nickname, person_name
from bot.views.admin import (
    _cancel_input_keyboard,
    _toast_preview,
    find_chat,
    render_admin_user_delete_confirm_1,
    render_admin_user_delete_confirm_2,
    render_chat_card,
    render_chat_list,
    render_keys,
    render_reset_confirm,
    render_system_wipe_prompt,
    render_user_card,
    render_user_list,
    render_wipe_prompt,
)
from bot.views.admin_home import render_admin_home
from bot.views.admin_settings import (
    back_to_group,
    render_setting_choices,
    render_setting_prompt,
    render_settings_group,
    render_settings_home,
)
from bot.views.promo import promo_keyboard, promo_text

log = logging.getLogger(__name__)

router = Router(name="admin")


class IsSuperadmin(BaseFilter):
    async def __call__(self, event: TelegramObject, settings: Settings) -> bool:
        user = getattr(event, "from_user", None)
        return user is not None and settings.is_superadmin(user.id)


router.message.filter(IsSuperadmin())
router.callback_query.filter(IsSuperadmin())


async def _replace_admin_home(
    bot: Bot,
    repo: Repo,
    fetcher: Fetcher,
    steam_fetcher: SteamFetcher,
    admin_credentials: AdminCredentials,
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
    locale = await repo.user_locale(await repo.person_id(admin_id))
    text, markup = await render_admin_home(
        repo, fetcher, steam_fetcher, admin_credentials, locale=locale
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
    admin_credentials: AdminCredentials,
    bot: Bot,
) -> None:
    _awaiting_input.pop(message.from_user.id, None)  # a fresh /admin cancels any pending flow
    await _replace_admin_home(bot, repo, fetcher, steam_fetcher, admin_credentials, message.chat.id)


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
    admin_credentials: AdminCredentials,
    i18n: I18nContext,
) -> None:
    _awaiting_input.pop(callback.from_user.id, None)
    await _redraw(
        callback,
        *await render_admin_home(
            repo, fetcher, steam_fetcher, admin_credentials, locale=i18n.locale
        ),
    )


# --------------------------------------------------------- Platform keys (#17)

# The "Ключи платформ" screen: every shared credential from one registry
# (services/admin_credentials.py, #176), the Mini App's keys screen walks the
# same one. Its text answer is claimed by AwaitingAdminTextInput, registered
# before the free-text numeric/timezone handlers below on purpose: aiogram
# tries message handlers in registration order and stops at the first whose
# filter matches, so a key that happens to be all digits is never taken for
# a number.

_KEY_PENDING = "key:"


class AwaitingAdminTextInput(BaseFilter):
    async def __call__(self, event: TelegramObject) -> bool:
        user = getattr(event, "from_user", None)
        if user is None:
            return False
        pending = _awaiting_input.get(user.id)
        return pending is not None and pending[0].startswith(_KEY_PENDING)


@router.callback_query(F.data == "a:keys")
async def keys_menu(
    callback: CallbackQuery, admin_credentials: AdminCredentials, i18n: I18nContext
) -> None:
    _awaiting_input.pop(callback.from_user.id, None)
    await _redraw(callback, *await render_keys(admin_credentials, locale=i18n.locale))


@router.callback_query(F.data.startswith("a:keyset:"))
async def keys_set(
    callback: CallbackQuery, admin_credentials: AdminCredentials, i18n: I18nContext
) -> None:
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    name = callback.data.rsplit(":", 1)[1]
    if name not in admin_credentials:
        await callback.answer()
        return
    _awaiting_input[callback.from_user.id] = (f"{_KEY_PENDING}{name}", None)
    await _redraw(
        callback, _(f"admin-keys-{name}-prompt"), _cancel_input_keyboard(locale=i18n.locale)
    )


@router.callback_query(F.data.startswith("a:keyclr:"))
async def keys_clear(
    callback: CallbackQuery, admin_credentials: AdminCredentials, i18n: I18nContext
) -> None:
    assert callback.data is not None
    name = callback.data.rsplit(":", 1)[1]
    if name in admin_credentials:
        await admin_credentials.clear(name, callback.from_user.id)
    _awaiting_input.pop(callback.from_user.id, None)
    await _redraw(callback, *await render_keys(admin_credentials, locale=i18n.locale))


@router.callback_query(F.data == "a:psncancel")
async def admin_text_input_cancel(
    callback: CallbackQuery,
    repo: Repo,
    fetcher: Fetcher,
    steam_fetcher: SteamFetcher,
    admin_credentials: AdminCredentials,
    i18n: I18nContext,
) -> None:
    """The way out of a still-armed key/NPSSO retry (Follow-up 2026-09-06,
    found live: a stray later message got misread as the next answer once
    nobody explicitly cancelled) — drops back to the admin home screen."""
    _awaiting_input.pop(callback.from_user.id, None)
    await _redraw(
        callback,
        *await render_admin_home(
            repo, fetcher, steam_fetcher, admin_credentials, locale=i18n.locale
        ),
    )


@router.message(F.chat.type == ChatType.PRIVATE, AwaitingAdminTextInput())
async def admin_text_input(
    message: Message, admin_credentials: AdminCredentials, i18n: I18nContext
) -> None:
    _ = translator("admin", i18n.locale)
    assert message.from_user is not None and message.text is not None
    pending = _awaiting_input.get(message.from_user.id)
    assert pending is not None
    name = pending[0].removeprefix(_KEY_PENDING)
    try:
        await admin_credentials.set(name, message.text, message.from_user.id)
    except CredentialInvalid:
        # Stays armed — a typo is worth just retrying — with an explicit way
        # out: a stray later message (found live 2026-09-06) must not be
        # taken for the next answer.
        await message.answer(
            _(f"admin-keys-{name}-invalid"),
            reply_markup=_cancel_input_keyboard(locale=i18n.locale),
        )
        return
    except CredentialSetupError as exc:
        # psnawp could not even build its client (found live 2026-09-06): a
        # fault on our side, worded so it is not blamed on the value.
        log.exception("admin_text_input: could not set up the %s client", name)
        await message.answer(
            _("admin-keys-setup-error", error=str(exc)),
            reply_markup=_cancel_input_keyboard(locale=i18n.locale),
        )
        return
    _awaiting_input.pop(message.from_user.id, None)
    text, markup = await render_keys(admin_credentials, locale=i18n.locale)
    await message.answer(_(f"admin-keys-{name}-saved", text=text), reply_markup=markup)


# ----------------------------------------------------------------- settings

# Every setting the super-admin changes comes from one registry (#176,
# services/admin_registry.py), which the Mini App draws too. A setting's
# button: on/off flips at once, a pick-one opens its values, a number waits
# for one typed — `_awaiting_input` remembers which, keyed by the admin.

_awaiting_input: dict[int, tuple[str, int | None]] = {}
_SETTING_PENDING = "set:"


@router.callback_query(F.data == "a:set")
async def settings_home(callback: CallbackQuery, i18n: I18nContext) -> None:
    _awaiting_input.pop(callback.from_user.id, None)
    await _redraw(callback, *render_settings_home(locale=i18n.locale).as_pair())


@router.callback_query(F.data.startswith("a:sg:"))
async def settings_group(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    assert callback.data is not None
    group = callback.data.split(":", 2)[2]
    if group not in GROUPS["global"]:
        await callback.answer()
        return
    _awaiting_input.pop(callback.from_user.id, None)
    current = await registry_values(repo, "global")
    await _redraw(callback, *render_settings_group(group, current, locale=i18n.locale).as_pair())


@router.callback_query(F.data.startswith("a:cg:"))
async def chat_settings_group(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    assert callback.data is not None
    _prefix, _action, chat_raw, group = callback.data.split(":")
    _awaiting_input.pop(callback.from_user.id, None)
    await _redraw(
        callback, *await render_chat_card(repo, int(chat_raw), locale=i18n.locale, section=group)
    )


@router.callback_query(F.data.startswith("a:s:"))
async def setting_open(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    assert callback.data is not None
    await _open_setting(callback, repo, "global", callback.data.split(":", 2)[2], None, i18n)


@router.callback_query(F.data.startswith("a:cs:"))
async def chat_setting_open(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    assert callback.data is not None
    _prefix, _action, chat_raw, key = callback.data.split(":")
    await _open_setting(callback, repo, "chat", key, int(chat_raw), i18n)


async def _current(repo: Repo, scope: Scope, chat_id: int | None) -> dict[str, Any] | None:
    if scope == "global":
        return await registry_values(repo, "global")
    chat = await find_chat(repo, chat_id)  # type: ignore[arg-type]
    return None if chat is None else await registry_values(repo, "chat", chat)


async def _open_setting(
    callback: CallbackQuery,
    repo: Repo,
    scope: Scope,
    key: str,
    chat_id: int | None,
    i18n: I18nContext,
) -> None:
    _ = translator("admin", i18n.locale)
    try:
        setting = find_setting(scope, key)
    except KeyError:
        await callback.answer()
        return
    current = await _current(repo, scope, chat_id)
    if current is None:
        await callback.answer(_("admin-chat-not-found"), show_alert=True)
        return
    back = back_to_group(setting, chat_id)
    if setting.kind is Kind.BOOL:
        await set_setting(
            repo, scope, key, not current[key], callback.from_user.id, chat_id=chat_id
        )
        await _show_group(callback, repo, setting, chat_id, i18n.locale)
        return
    if setting.options():
        screen = render_setting_choices(
            setting, current[key], locale=i18n.locale, back=back, chat_id=chat_id
        )
        await _redraw(callback, *screen.as_pair())
        return
    _awaiting_input[callback.from_user.id] = (f"{_SETTING_PENDING}{scope}:{key}", chat_id)
    screen = render_setting_prompt(setting, current[key], locale=i18n.locale, back=back)
    await _redraw(callback, *screen.as_pair())


@router.callback_query(F.data.startswith("a:sv:"))
async def setting_pick(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    assert callback.data is not None
    _prefix, _action, key, index = callback.data.split(":")
    await _pick(callback, repo, "global", key, int(index), None, i18n)


@router.callback_query(F.data.startswith("a:csv:"))
async def chat_setting_pick(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    assert callback.data is not None
    _prefix, _action, chat_raw, key, index = callback.data.split(":")
    await _pick(callback, repo, "chat", key, int(index), int(chat_raw), i18n)


async def _pick(
    callback: CallbackQuery,
    repo: Repo,
    scope: Scope,
    key: str,
    index: int,
    chat_id: int | None,
    i18n: I18nContext,
) -> None:
    _ = translator("admin", i18n.locale)
    try:
        setting = find_setting(scope, key)
        option = setting.options()[index]
    except (KeyError, IndexError):
        await callback.answer(_("admin-settings-choice-retry"), show_alert=True)
        return
    await set_setting(repo, scope, key, option, callback.from_user.id, chat_id=chat_id)
    await _show_group(callback, repo, setting, chat_id, i18n.locale)


async def _show_group(
    callback: CallbackQuery, repo: Repo, setting: Setting, chat_id: int | None, locale: str
) -> None:
    if setting.scope == "global":
        current = await registry_values(repo, "global")
        await _redraw(
            callback, *render_settings_group(setting.group, current, locale=locale).as_pair()
        )
        return
    assert chat_id is not None
    await _redraw(
        callback, *await render_chat_card(repo, chat_id, locale=locale, section=setting.group)
    )


@router.message(F.chat.type == ChatType.PRIVATE, F.text.regexp(r"^\d+([.,]\d+)?$"))
async def setting_number_input(message: Message, repo: Repo, i18n: I18nContext) -> None:
    """A number typed for the setting opened last; anything else stays the
    business of whatever is waiting for it."""
    _ = translator("admin", i18n.locale)
    assert message.from_user is not None and message.text is not None
    pending = _awaiting_input.get(message.from_user.id)
    if pending is None or not pending[0].startswith(_SETTING_PENDING):
        return  # a plain number from an admin who isn't in this flow — ignore
    scope_raw, _sep, key = pending[0].removeprefix(_SETTING_PENDING).partition(":")
    scope: Scope = "chat" if scope_raw == "chat" else "global"
    chat_id = pending[1]
    setting = find_setting(scope, key)
    try:
        value = await set_setting(
            repo, scope, key, message.text, message.from_user.id, chat_id=chat_id
        )
    except SettingValueError as exc:
        await message.answer(_retry_text(exc, _))
        return
    del _awaiting_input[message.from_user.id]
    saved = _(
        "admin-settings-saved",
        label=registry_label(setting, locale=i18n.locale),
        value=value_label(setting, value, locale=i18n.locale),
    )
    if scope == "global":
        current = await registry_values(repo, "global")
        text, markup = render_settings_group(
            setting.group, current, locale=i18n.locale, prefix=saved
        ).as_pair()
    else:
        assert chat_id is not None
        card, markup = await render_chat_card(
            repo, chat_id, locale=i18n.locale, section=setting.group
        )
        text = f"{saved}\n\n{card}"
    await message.answer(text, reply_markup=markup)


def _retry_text(exc: SettingValueError, _: Callable[..., str]) -> str:
    if exc.reason == "integer":
        return _("admin-integer-retry")
    if exc.reason == "choice":
        return _("admin-settings-choice-retry")
    return _("admin-number-range-retry", minimum=f"{exc.minimum:g}", maximum=f"{exc.maximum:g}")


@router.callback_query(F.data.startswith("a:mdel:"))
async def chat_messages_menu(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    assert callback.data is not None
    chat_id = int(callback.data.split(":")[2])
    await _redraw(
        callback, *await render_chat_card(repo, chat_id, locale=i18n.locale, section="messages")
    )


# --------------------------------------------------------------------- users


@router.callback_query(F.data.startswith("a:users:"))
async def users_page(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    assert callback.data is not None
    page = int(callback.data.rsplit(":", 1)[1])
    await _redraw(callback, *await render_user_list(repo, page, locale=i18n.locale))


async def _subject(repo: Repo, raw: str) -> int | None:
    """The person a user-card button is about: `p<person id>` (#156) — somebody
    who signed in by email has no Telegram id. A button drawn before that carries
    a bare Telegram id, and still works."""
    if raw.startswith("p"):
        return int(raw[1:])
    return await repo.person_id(int(raw))


async def _not_found(callback: CallbackQuery, locale: str) -> None:
    await callback.answer(translator("admin", locale)("admin-user-not-found"), show_alert=True)


@router.callback_query(F.data.startswith("a:u:"))
async def user_card(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    assert callback.data is not None
    person = await _subject(repo, callback.data.rsplit(":", 1)[1])
    if person is None:
        await _not_found(callback, i18n.locale)
        return
    await _redraw(callback, *await render_user_card(repo, person, locale=i18n.locale))


@router.callback_query(F.data.startswith("a:excl:"))
async def user_exclude(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    _, _, raw_id, raw_flag = callback.data.split(":")
    person, excluded = await _subject(repo, raw_id), raw_flag == "1"
    if person is None:
        await _not_found(callback, i18n.locale)
        return
    await repo.set_excluded(person, excluded, callback.from_user.id)
    await callback.answer(_("admin-user-excluded") if excluded else _("admin-user-restored"))
    await _redraw(callback, *await render_user_card(repo, person, locale=i18n.locale))


@router.callback_query(F.data.startswith("a:avclr:"))
async def user_avatar_reset(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    """Take down a picture somebody chose in the Mini App (#157)."""
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    person = await _subject(repo, callback.data.rsplit(":", 1)[1])
    if person is None:
        await _not_found(callback, i18n.locale)
        return
    await custom_avatars.clear(repo, person)
    await callback.answer(_("admin-avatar-reset"))
    await _redraw(callback, *await render_user_card(repo, person, locale=i18n.locale))


_SYNC_NOT_CONNECTED_KEY = {
    "xbox": "admin-user-not-connected",
    "steam": "admin-steam-not-connected",
    "psn": "admin-psn-not-connected",
}


async def _parse_account(repo: Repo, data: str) -> tuple[str, int | None, str | None]:
    """`a:<action>:<platform>:<person>[:<account_id>]` → the platform, the person
    (`_subject`) and the account."""
    parts = data.split(":")
    return parts[2], await _subject(repo, parts[3]), parts[4] if len(parts) > 4 else None


def _accounts(
    repo: Repo,
    settings: Settings,
    fetcher: Fetcher,
    steam_fetcher: SteamFetcher,
    psn_fetcher: PsnFetcher,
) -> AdminAccounts:
    return AdminAccounts(repo, settings, xbox=fetcher, steam=steam_fetcher, psn=psn_fetcher)


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
    """ "🔄 Обновить" — the one place in the bot that calls a platform on
    demand (SPEC 1.5); the work is `services/admin_accounts.py`'s, shared with
    the Mini App's admin card."""
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    platform, person, account_id = await _parse_account(repo, callback.data)
    if person is None:
        await _not_found(callback, i18n.locale)
        return
    accounts = _accounts(repo, settings, fetcher, steam_fetcher, psn_fetcher)
    if await accounts.target(platform, person, locale=i18n.locale, account_id=account_id) is None:
        await callback.answer(_(_SYNC_NOT_CONNECTED_KEY[platform]), show_alert=True)
        return
    await callback.answer(_("admin-refreshing"))
    try:
        summary = await accounts.refresh(
            platform, person, locale=i18n.locale, account_id=account_id
        )
    except Exception:
        log.exception("admin %s refresh of person_id=%s failed", platform, person)
        await callback.answer(_("admin-refresh-failed"), show_alert=True)
        return
    text, markup = await render_user_card(repo, person, locale=i18n.locale)
    await _redraw(callback, f"{text}\n\n{summary}" if summary else text, markup)


# --------------------------------------------------------------------- chats


@router.callback_query(F.data == "a:chats")
async def chats_list(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    await _redraw(callback, *await render_chat_list(repo, locale=i18n.locale))


@router.callback_query(F.data.startswith("a:chat:"))
async def chat_card(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    await _redraw(callback, *await render_chat_card(repo, chat_id, locale=i18n.locale))


@router.callback_query(F.data.startswith("a:cpromo:"))
async def chat_send_promo(
    callback: CallbackQuery,
    repo: Repo,
    bot: Bot,
    i18n: I18nContext,
    settings: Settings,
) -> None:
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    chat = await find_chat(repo, chat_id)
    if chat is None:
        await callback.answer(_("admin-chat-not-found"), show_alert=True)
        return
    me = await bot.me()
    bot_username = me.username or ""
    markup = promo_keyboard(
        bot_username,
        chat_id,
        mini_app_url=settings.mini_app_url or "",
        is_group=True,
        locale=chat.locale,
    )
    try:
        with stats_category():
            await bot.send_message(
                chat_id,
                promo_text(locale=chat.locale),
                parse_mode=ParseMode.HTML,
                reply_markup=markup,
            )
        await callback.answer(_("admin-promo-sent"))
    except Exception as exc:
        await callback.answer(f"Failed: {exc}", show_alert=True)


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
    result = await admin_cleanup.delete_last(bot, repo, chat_id)
    if result is None:
        await callback.answer(_("admin-no-bot-messages"), show_alert=True)
        return
    if not result.deleted:
        await callback.answer(_("admin-delete-old-failed"), show_alert=True)
        return
    feedback = (
        _("admin-deleted-last-preview", preview=_toast_preview(result.preview))
        if result.preview
        else _("admin-deleted-last")
    )
    await callback.answer(feedback)
    await _redraw(
        callback, *await render_chat_card(repo, chat_id, locale=i18n.locale, section="messages")
    )


@router.callback_query(F.data.startswith("a:cwipe:"))
async def chat_wipe_prompt(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    chat = await find_chat(repo, chat_id)
    if chat is None:
        await callback.answer(_("admin-chat-not-found"), show_alert=True)
        return
    ids = await admin_cleanup.messages_to_wipe(repo, chat_id, Wipe.ALL_24H)
    if not ids:
        await callback.answer(_("admin-no-bot-messages-24h"), show_alert=True)
        return
    screen = render_wipe_prompt(chat, len(ids), WIPE_WINDOW_HOURS, locale=i18n.locale)
    await _redraw(callback, *screen.as_pair())


@router.callback_query(F.data.startswith("a:cwipey:"))
async def chat_wipe_confirm(
    callback: CallbackQuery, repo: Repo, bot: Bot, i18n: I18nContext
) -> None:
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    ids = await admin_cleanup.messages_to_wipe(repo, chat_id, Wipe.ALL_24H)
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
    ids = await admin_cleanup.messages_to_wipe(repo, chat_id, Wipe.SYSTEM_24H)
    await _system_wipe_prompt(
        callback, repo, chat_id, ids, f"a:cswipey:{chat_id}", locale=i18n.locale
    )


@router.callback_query(F.data.startswith("a:cswipey:"))
async def chat_system_wipe_confirm(
    callback: CallbackQuery, repo: Repo, bot: Bot, i18n: I18nContext
) -> None:
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    ids = await admin_cleanup.messages_to_wipe(repo, chat_id, Wipe.SYSTEM_24H)
    await _wipe_confirm(callback, repo, bot, chat_id, ids, locale=i18n.locale)


@router.callback_query(F.data.startswith("a:cswipeall:"))
async def chat_system_wipe_all_prompt(
    callback: CallbackQuery, repo: Repo, i18n: I18nContext
) -> None:
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    ids = await admin_cleanup.messages_to_wipe(repo, chat_id, Wipe.SYSTEM_ALL)
    await _system_wipe_prompt(
        callback, repo, chat_id, ids, f"a:cswipeally:{chat_id}", locale=i18n.locale
    )


@router.callback_query(F.data.startswith("a:cswipeally:"))
async def chat_system_wipe_all_confirm(
    callback: CallbackQuery, repo: Repo, bot: Bot, i18n: I18nContext
) -> None:
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    ids = await admin_cleanup.messages_to_wipe(repo, chat_id, Wipe.SYSTEM_ALL)
    await _wipe_confirm(callback, repo, bot, chat_id, ids, locale=i18n.locale)


# ------------------------------------------------------------------- screens


@router.callback_query(F.data.startswith("a:reset:"))
async def reset_platform_confirm(
    callback: CallbackQuery, repo: Repo, settings: Settings, i18n: I18nContext
) -> None:
    """ "Сброс базы" is destructive and not undoable (user request 2026-09-08)
    — same one-tap-confirm shape as /disconnect_steam's own prompt, not an
    instant action behind a single tap."""
    assert callback.data is not None
    platform, person, account_id = await _parse_account(repo, callback.data)
    if person is None:
        await _not_found(callback, i18n.locale)
        return
    account_name = None
    if account_id is not None:
        link = await AdminAccounts(repo, settings, xbox=None, steam=None, psn=None).link(
            platform, person, account_id
        )
        account_name = link_nickname(link) if link else account_id
    screen = render_reset_confirm(
        platform,
        f"p{person}",
        locale=i18n.locale,
        account_id=account_id,
        account_name=account_name,
    )
    await _redraw(callback, *screen.as_pair())


@router.callback_query(F.data.startswith("a:resetok:"))
async def reset_platform_confirmed(
    callback: CallbackQuery,
    repo: Repo,
    fetcher: Fetcher,
    steam_fetcher: SteamFetcher,
    psn_fetcher: PsnFetcher,
    settings: Settings,
    i18n: I18nContext,
) -> None:
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    platform, person, account_id = await _parse_account(repo, callback.data)
    if person is None:
        await _not_found(callback, i18n.locale)
        return
    await callback.answer(_("admin-refreshing"))
    accounts = _accounts(repo, settings, fetcher, steam_fetcher, psn_fetcher)
    try:
        if not await accounts.reset(platform, person, account_id):
            await callback.answer(_(_SYNC_NOT_CONNECTED_KEY[platform]), show_alert=True)
    except Exception:
        log.exception("admin reset+resync of person_id=%s platform=%s failed", person, platform)
        await callback.answer(_("admin-refresh-failed"), show_alert=True)
    text, markup = await render_user_card(repo, person, locale=i18n.locale)
    await _redraw(callback, text, markup)


@router.callback_query(F.data.startswith("a:udel:"))
async def admin_delete_user_step1(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    _prefix, _action, raw = callback.data.split(":")
    person = await _subject(repo, raw)
    user = await repo.get_user(person) if person is not None else None
    if person is None or user is None:
        _ = translator("admin", i18n.locale)
        await callback.answer(_("admin-user-not-found"), show_alert=True)
        return
    name = person_name(person_id=user.id, handle=user.handle)
    screen = render_admin_user_delete_confirm_1(name, person, user.tg_id, locale=i18n.locale)
    await _redraw(callback, *screen.as_pair())


@router.callback_query(F.data.startswith("a:udel1:"))
async def admin_delete_user_step2(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    _prefix, _action, raw = callback.data.split(":")
    person = await _subject(repo, raw)
    user = await repo.get_user(person) if person is not None else None
    if person is None or user is None:
        _ = translator("admin", i18n.locale)
        await callback.answer(_("admin-user-not-found"), show_alert=True)
        return
    name = person_name(person_id=user.id, handle=user.handle)
    screen = render_admin_user_delete_confirm_2(name, person, user.tg_id, locale=i18n.locale)
    await _redraw(callback, *screen.as_pair())


@router.callback_query(F.data.startswith("a:udel2:"))
async def admin_delete_user_confirmed(
    callback: CallbackQuery, repo: Repo, i18n: I18nContext
) -> None:
    _ = translator("admin", i18n.locale)
    _prefix, _action, raw = callback.data.split(":")
    person = await _subject(repo, raw)
    deleted = person is not None and await repo.delete_person(person, is_superadmin=True)
    if deleted:
        await callback.answer(_("admin-delete-toast"))
    else:
        await callback.answer(_("admin-delete-not-found"), show_alert=True)
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
    ok = await admin_cleanup.wipe(bot, repo, chat_id, ids)
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
