"""Entry point: wires the database, Xbox auth, the OAuth callback and aiogram."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
)

from bot.config import Settings, get_settings
from bot.constants import Platform
from bot.db.repo import Database, Repo
from bot.handlers import admin as admin_handlers
from bot.handlers import chat as chat_handlers
from bot.handlers import connect as connect_handlers
from bot.handlers import hltb as hltb_handlers
from bot.handlers import panel as panel_handlers
from bot.handlers import psn as psn_handlers
from bot.handlers import steam as steam_handlers
from bot.handlers.chat import UsernameMiddleware
from bot.handlers.keyboards import timezone_keyboard
from bot.i18n import (
    AVAILABLE_LOCALES,
    DEFAULT_LOCALE,
    build_i18n_context,
    build_i18n_middleware,
    gettext,
    translator,
)
from bot.lock import AlreadyRunningError, single_instance
from bot.poller.admin_refresh import AdminPanelRefresh
from bot.poller.daily import DailySummary
from bot.poller.fetcher import Fetcher
from bot.poller.flood_flush import FloodFlush
from bot.poller.message_cleanup import MessageCleanup
from bot.poller.online_refresh import OnlineAutoRefresh
from bot.poller.presence import PresencePoller
from bot.poller.psn_fetcher import PsnFetcher
from bot.poller.psn_presence import PsnPresencePoller
from bot.poller.publisher import Publisher
from bot.poller.reminders import ReminderJob
from bot.poller.scheduler import PollerScheduler
from bot.poller.service_health import ServiceHealth
from bot.poller.steam_fetcher import SteamFetcher
from bot.poller.steam_presence import SteamPresencePoller
from bot.services.connect import ConnectService
from bot.services.crypto import TokenCipher
from bot.services.message_log import MessageLogMiddleware
from bot.services.notify import AdminNotifier
from bot.services.psn.auth import PsnAuth
from bot.services.steam.auth import SteamAuth
from bot.services.translate.auth import AnthropicAuth
from bot.services.xbox.auth import XboxAuthService, XboxIdentity
from bot.services.xbox.client import XboxClient
from bot.util import parse_iso
from bot.web.oauth import OAuthServer

log = logging.getLogger(__name__)

# Outer backstop for startup_catch_up's per-user call (2026-09-09) — see
# that function's own docstring for why this exists on top of
# title_history()'s own deadline. Generous on purpose: a real account can
# legitimately need ~46s for title_history alone (verified live,
# RideTheSun's 1011-title account) before even starting its own
# catchup_max_titles (20) achievement fetches, each with its own up-to-3-
# attempt retry-with-backoff (services/xbox/client.py's own MAX_ATTEMPTS) —
# a account genuinely on the edge should still get to finish, not be cut
# off just short of succeeding.
STARTUP_CATCH_UP_DEADLINE_SECONDS = 120.0


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        # stdout, not the default stderr: manage.ps1 redirects the two streams
        # to different files, and ordinary progress in the error log is noise
        # that hides real tracebacks.
        stream=sys.stdout,
    )
    # httpx logs "HTTP Request: GET <full url> ..." at INFO for every call —
    # harmless for Xbox (auth goes in a header), but Steam's API puts its key
    # in the URL's own query string (SPEC 1.5's "never in logs" — no
    # exception for something a library does on our behalf). Found live in
    # production: the key had been sitting in plain text in journalctl since
    # M-Steam-1. WARNING still surfaces httpx's own connection/TLS errors.
    logging.getLogger("httpx").setLevel(logging.WARNING)


async def run(settings: Settings) -> None:
    database = await Database(settings.db_path).connect()
    repo = Repo(database)

    # The global timezone is a setting, not a constant: the admin can change it
    # later without touching .env. The value from the environment only seeds it.
    if await repo.get_app_setting("timezone") is None:
        await repo.set_app_setting("timezone", settings.tz)

    cipher = TokenCipher(settings.fernet_key.get_secret_value())
    auth = XboxAuthService(settings, repo, cipher)
    await auth.start()
    connect_service = ConnectService(auth, repo)

    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(link_preview_is_disabled=True),
    )
    # Every group message the bot sends, logged for the admin panel's
    # "стереть сообщения бота" (SPEC 6.4) — see the module docstring for why
    # this is one request middleware and not a call in every handler.
    bot.session.middleware(MessageLogMiddleware(repo))

    notifier = AdminNotifier(bot, repo, settings.admin_tg_ids)
    auth.on_token_dead = notifier.token_dead

    # One service-wide PSN client, not per-user OAuth (SPEC 9, M-PSN-1) —
    # on_dead mirrors XboxAuthService.on_token_dead above, just for the one
    # shared credential rather than one person's own.
    psn_auth = PsnAuth(repo, cipher)
    psn_auth.on_dead = lambda: notifier.service_key_dead(Platform.PSN)

    # The Steam key now lives encrypted in app_settings, admin-settable
    # without a restart (#17); the .env value is only a first-run seed
    # SteamAuth imports once. on_dead mirrors psn_auth's above.
    steam_env_key = settings.steam_api_key.get_secret_value() if settings.steam_api_key else None
    steam_auth = SteamAuth(repo, cipher, env_key=steam_env_key)
    steam_auth.on_dead = lambda: notifier.service_key_dead(Platform.STEAM)

    # Anthropic (2026-09-09) — achievement-description translation only,
    # same admin-panel-managed shared-credential shape as Steam/PSN above.
    anthropic_env_key = (
        settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None
    )
    anthropic_auth = AnthropicAuth(repo, cipher, env_key=anthropic_env_key)
    anthropic_auth.on_dead = notifier.translation_key_dead

    client = XboxClient(auth)
    publisher = Publisher(bot, repo)
    fetcher = Fetcher(
        repo, client, publisher, settings.backfill_concurrency, anthropic_auth=anthropic_auth
    )
    poller = PresencePoller(settings, repo, client, fetcher)

    steam_fetcher = SteamFetcher(
        repo, steam_auth, publisher, settings.backfill_concurrency, anthropic_auth=anthropic_auth
    )
    steam_poller = SteamPresencePoller(settings, repo, steam_fetcher, steam_auth)

    # Trophy sync itself still has no presence poller of its own (SPEC 9,
    # M-PSN-2) — psn_fetcher.tick() scans every linked account directly on
    # its own schedule. psn_presence below is a separate, unrelated poller
    # (issue #1): presence for /online only, never triggers a trophy poll.
    psn_fetcher = PsnFetcher(settings, repo, psn_auth, publisher, anthropic_auth=anthropic_auth)
    psn_presence = PsnPresencePoller(settings, repo, psn_auth)

    flood_flush = FloodFlush(repo, publisher)

    scheduler = PollerScheduler(
        poller,
        fetcher,
        ReminderJob(bot, repo),
        DailySummary(bot, repo),
        repo,
        steam_poller,
        MessageCleanup(bot, repo),
        OnlineAutoRefresh(bot, repo),
        ServiceHealth(repo, psn_auth, steam_auth, anthropic_auth),
        AdminPanelRefresh(bot, repo, fetcher, steam_fetcher, psn_auth, steam_auth),
        psn_fetcher,
        psn_presence,
        flood_flush,
    )

    async def backfill(tg_id: int, xuid: str) -> None:
        """Runs in the background: five people connecting one evening must not
        block the poller (SPEC 5.6)."""
        _ = translator("main", await repo.user_locale(tg_id))
        try:
            count = await fetcher.backfill(tg_id, xuid)
        except Exception:
            log.exception("backfill for tg_id=%s failed", tg_id)
            await bot.send_message(tg_id, _("main-backfill-failed"))
            return
        await bot.send_message(tg_id, _("main-backfill-done", count=count))

    async def refresh_after_reconnect(tg_id: int, xuid: str) -> None:
        """store_identity sets gamerscore = NULL on every connect (it does
        not know the real value yet); without a refresh a person who logs
        back in sees "0" until the next presence event happens to touch
        title_history (bug found live: justdrunkzero showed 0 right after
        reconnecting).

        Runs the *full* backfill, not just a title_history refresh — the
        first fix here did the smaller one on the theory that a reconnect's
        history is already complete, which turned out false: seen_achievements
        only grows through live polling and catch_up (both bounded to
        recently-touched games), so anything not replayed since the initial
        connect silently never lands there, and "Всего"/"За месяц" drift low
        forever (SPEC 5.4). backfill() is idempotent and never publishes, so
        re-running it on every reconnect is safe and fixes both at once."""
        try:
            await fetcher.backfill(tg_id, xuid)
        except Exception:
            log.exception("post-reconnect backfill failed for tg_id=%s", tg_id)

    async def on_linked(tg_id: int, identity: XboxIdentity, origin_chat_id: int | None) -> None:
        """Runs in the web callback, right after the account is stored."""
        # No achievements yet means this account is new to the bot, not someone
        # signing in again after his token expired.
        is_new = not await repo.has_any_achievements(identity.xuid)
        locale = await repo.user_locale(tg_id)
        _ = translator("main", locale)
        await bot.send_message(tg_id, _("main-linked", gamertag=identity.gamertag))
        await notifier.user_connected(tg_id, identity.gamertag, is_new=is_new)

        # Pressed «Подключить XBOX» from inside a specific group: finish the
        # job and subscribe him there too, instead of making him find
        # /subscribe on his own right after he just did the hard part (6.3).
        if origin_chat_id is not None and await repo.chat_exists(origin_chat_id):
            await repo.subscribe(origin_chat_id, tg_id)
            with contextlib.suppress(Exception):
                await bot.send_message(tg_id, _("main-linked-subscribed-origin-chat"))

        settings_row = await repo.get_user_settings(tg_id)
        if settings_row is None or settings_row.tz_offset_min is None:
            link_i18n = await build_i18n_context(locale)
            await bot.send_message(
                tg_id,
                link_i18n.get("connect-timezone-prompt"),
                reply_markup=timezone_keyboard(link_i18n),
            )
        if is_new:
            await bot.send_message(tg_id, _("main-linked-backfill-starting"))
            asyncio.create_task(backfill(tg_id, identity.xuid))  # noqa: RUF006
        else:
            # A silent background refresh would leave the panel showing a
            # stale 0 for a few seconds with nothing telling the user why.
            await bot.send_message(tg_id, _("main-linked-refreshing"))
            asyncio.create_task(refresh_after_reconnect(tg_id, identity.xuid))  # noqa: RUF006

    web_server = OAuthServer(settings, connect_service, on_linked)
    await web_server.start()

    dispatcher = Dispatcher()
    dispatcher["repo"] = repo
    dispatcher["connect"] = connect_service
    dispatcher["fetcher"] = fetcher
    dispatcher["steam_fetcher"] = steam_fetcher
    dispatcher["settings"] = settings
    dispatcher["notifier"] = notifier
    dispatcher["psn_auth"] = psn_auth
    dispatcher["psn_fetcher"] = psn_fetcher
    dispatcher["steam_auth"] = steam_auth
    dispatcher["anthropic_auth"] = anthropic_auth
    dispatcher.message.outer_middleware(UsernameMiddleware(repo))
    build_i18n_middleware().setup(dispatcher=dispatcher)
    dispatcher.include_router(admin_handlers.router)
    dispatcher.include_router(connect_handlers.router)
    dispatcher.include_router(panel_handlers.router)
    dispatcher.include_router(chat_handlers.router)
    dispatcher.include_router(hltb_handlers.router)
    dispatcher.include_router(steam_handlers.router)
    dispatcher.include_router(psn_handlers.router)

    async def startup_catch_up() -> None:
        """Pick up what happened while the bot was down (SPEC 5.8).

        In the background: a restart must not wait for the network before it
        starts answering people.

        Each user's own call is wrapped in a hard deadline (found live,
        2026-09-09): under degraded network conditions, catch_up() can
        legitimately accumulate a lot of time on its own — up to
        catchup_max_titles (20) achievement fetches after title_history,
        each with its own up-to-3-attempt retry-with-backoff
        (services/xbox/client.py's MAX_ATTEMPTS) — and this loop is
        otherwise sequential, so one account having a bad run must never
        delay every account after it by that same amount. This is on top
        of title_history()'s own asyncio.wait_for, not instead of it.
        """
        for target in await repo.pollable_users():
            user = await repo.get_user(target.tg_id)
            try:
                await asyncio.wait_for(
                    fetcher.catch_up(
                        target.tg_id,
                        target.xuid,
                        (user.gamertag if user else None)
                        or gettext("main", "main-default-player-name", locale=DEFAULT_LOCALE),
                        parse_iso(target.updated_at),
                        settings.catchup_publish_window_hours,
                        settings.catchup_max_titles,
                    ),
                    timeout=STARTUP_CATCH_UP_DEADLINE_SECONDS,
                )
            except TimeoutError:
                log.error(
                    "catch-up for tg_id=%s exceeded %.0fs overall, moving on",
                    target.tg_id,
                    STARTUP_CATCH_UP_DEADLINE_SECONDS,
                )
            except Exception:
                log.exception("catch-up for tg_id=%s failed", target.tg_id)

    await publisher.start()
    # Force-exit every anti-flood window still open from before this restart
    # (2026-09-09 user request) — a window mid-count when the bot last
    # stopped must not silently swallow its buffered achievements forever;
    # better to deliver them a little early than never. Awaited directly,
    # not backgrounded like startup_catch_up below: it only touches the
    # database and the (already-running) publish queue, no platform API
    # calls, so it can't meaningfully delay startup.
    await flood_flush.flush_all()
    scheduler.start()
    asyncio.create_task(startup_catch_up())  # noqa: RUF006

    await _publish_command_menu(bot)

    me = await bot.me()
    log.info("bot @%s is up", me.username)
    try:
        await dispatcher.start_polling(bot, handle_signals=False)
    finally:
        scheduler.shutdown()
        await publisher.stop()
        await web_server.stop()
        await auth.close()
        await bot.session.close()
        await database.close()


async def _publish_command_menu(bot: Bot) -> None:
    """The command list Telegram shows behind the "/" button.

    Two scopes, because the useful commands differ: in a group nobody needs
    /connect_xbox, and in private nobody needs /online. Most-used first in
    both — subscribe/unsubscribe is one-time setup, not read every time
    (SPEC 6.3).

    The menu is published once per shipped locale (#48). This is the one
    place in the bot that honours Telegram's own `language_code` rather than
    our `user_settings.locale`, and not by choice: Telegram renders this menu
    itself, from whatever it was given, so there is no moment at which we
    could substitute a person's own setting. Everything the bot actually
    *says* still follows the explicit setting; only this hint list follows
    the client's language. A locale Telegram has no entry for falls back to
    the one published with no language_code at all, which stays Russian.
    """

    def menus(locale: str) -> tuple[list[BotCommand], list[BotCommand]]:
        _ = translator("main", locale)
        private = [
            BotCommand(command="panel", description=_("main-cmd-panel")),
            BotCommand(command="stats", description=_("main-cmd-stats-private")),
            BotCommand(command="connect_xbox", description=_("main-cmd-connect-xbox")),
            BotCommand(command="disconnect_xbox", description=_("main-cmd-disconnect-xbox")),
            BotCommand(command="connect_steam", description=_("main-cmd-connect-steam")),
            BotCommand(command="disconnect_steam", description=_("main-cmd-disconnect-steam")),
            BotCommand(command="connect_psn", description=_("main-cmd-connect-psn")),
            BotCommand(command="disconnect_psn", description=_("main-cmd-disconnect-psn")),
            BotCommand(command="hltb", description=_("main-cmd-hltb")),
            BotCommand(command="help", description=_("main-cmd-help")),
        ]
        group = [
            BotCommand(command="stats", description=_("main-cmd-stats-group")),
            BotCommand(command="online", description=_("main-cmd-online")),
            BotCommand(command="who", description=_("main-cmd-who")),
            BotCommand(command="recent", description=_("main-cmd-recent")),
            BotCommand(command="summary", description=_("main-cmd-summary")),
            BotCommand(command="hltb", description=_("main-cmd-hltb")),
            BotCommand(command="subscribe", description=_("main-cmd-subscribe")),
            BotCommand(command="unsubscribe", description=_("main-cmd-unsubscribe")),
            BotCommand(command="help", description=_("main-cmd-help")),
        ]
        return private, group

    try:
        for locale in AVAILABLE_LOCALES:
            private, group = menus(locale)
            # The default locale is published without a language_code as
            # well, so it is what any unlisted client language falls back to.
            language_code = None if locale == DEFAULT_LOCALE else locale
            await bot.set_my_commands(
                private, scope=BotCommandScopeAllPrivateChats(), language_code=language_code
            )
            await bot.set_my_commands(
                group, scope=BotCommandScopeAllGroupChats(), language_code=language_code
            )
    except Exception:
        # A cosmetic menu is not worth failing the whole startup for.
        log.warning("could not publish the command menu", exc_info=True)


def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)

    lock_path = settings.db_path.parent / "bot.lock"
    try:
        with single_instance(lock_path):
            try:
                asyncio.run(run(settings))
            except (KeyboardInterrupt, SystemExit):
                log.info("stopped")
    except AlreadyRunningError:
        # Not a traceback: this is a normal thing to do by mistake.
        print(gettext("main", "main-already-running"), file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
