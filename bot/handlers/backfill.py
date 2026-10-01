"""The person's own status while an account's history is read (owner,
2026-09-30): one message, redrawn at most every `PROGRESS_INTERVAL` seconds,
that ends as the result — synced, partly private, or failed with a retry.

A backfill runs for minutes on a big library, and a person who saw only
"reading your history…" had no way to tell it apart from a hang. Each
platform's backfill reports `(done, total, found)`; this turns that into the
message, and owns the retry buttons that start it again.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.constants import Platform, TokenStatus
from bot.db.repo import Repo
from bot.i18n import translator
from bot.poller.fetcher import Fetcher
from bot.poller.psn_fetcher import PsnFetcher
from bot.poller.steam_fetcher import SteamFetcher
from bot.services.naming import link_nickname
from bot.services.steam.client import SteamGameDetailsPrivateError
from bot.views.parts import plural_achievements, plural_trophies

log = logging.getLogger(__name__)

router = Router(name="backfill")

PROGRESS_INTERVAL = 5.0
BAR_CELLS = 10
# Where Steam's own "Game details" privacy switch lives.
STEAM_PRIVACY_URL = "https://steamcommunity.com/my/edit/settings"


class _Status:
    """One status message and how often it may be redrawn."""

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        message_id: int,
        *,
        locale: str,
        platform: str,
        count_found: Callable[[int, str], str],
        steps: bool,
    ) -> None:
        self._bot = bot
        self._chat_id = chat_id
        self._message_id = message_id
        self._ = translator("backfill", locale)
        self._locale = locale
        self.platform = platform
        self._count_found = count_found
        self._steps = steps
        self._last = 0.0
        self.total = 0

    def found(self, count: int) -> str:
        return self._count_found(count, self._locale)

    async def progress(self, done: int, total: int, found: int) -> None:
        self.total = total
        now = time.monotonic()
        # The first report and the last one always draw; the rest at most
        # every PROGRESS_INTERVAL — Telegram limits edits, and the person
        # needs a pulse, not a ticker.
        if 0 < done < total and now - self._last < PROGRESS_INTERVAL:
            return
        self._last = now
        filled = BAR_CELLS * done // total if total else 0
        detail = self._(
            "backfill-detail-steps" if self._steps else "backfill-detail-games",
            done=done,
            total=total,
            found=self.found(found),
        )
        await self.show(
            self._(
                "backfill-progress",
                platform=self.platform,
                bar="▰" * filled + "▱" * (BAR_CELLS - filled),
                detail=detail,
            )
        )

    async def show(self, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
        # Telegram refuses an edit that changes nothing, and the message may
        # be gone — neither is worth failing a backfill over.
        with contextlib.suppress(Exception):
            await self._bot.edit_message_text(
                text,
                chat_id=self._chat_id,
                message_id=self._message_id,
                reply_markup=markup,
                disable_web_page_preview=True,
            )

    async def done(self, found: int, *, extra: str | None = None) -> None:
        if self._steps or not self.total:
            text = self._("backfill-done", platform=self.platform, found=self.found(found))
        else:
            text = self._(
                "backfill-done-games",
                platform=self.platform,
                found=self.found(found),
                total=self.total,
            )
        if extra:
            text += "\n\n" + extra
        await self.show(text, _panel_markup(self._))

    async def failed(self, retry: str, text: str | None = None, *, recheck: bool = False) -> None:
        await self.show(
            text or self._("backfill-failed", platform=self.platform),
            _retry_markup(self._, retry, recheck=recheck),
        )


def _panel_markup(_: Callable[..., str]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("backfill-panel"), callback_data="panel:refresh")]
        ]
    )


def _retry_markup(
    _: Callable[..., str], retry: str, *, recheck: bool = False
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_("backfill-recheck" if recheck else "backfill-retry"),
                    callback_data=retry,
                )
            ],
            [InlineKeyboardButton(text=_("backfill-panel"), callback_data="panel:refresh")],
        ]
    )


async def _open(
    bot: Bot,
    repo: Repo,
    tg_id: int,
    platform: str,
    count_found: Callable[[int, str], str],
    *,
    steps: bool = False,
    message: Message | None = None,
) -> _Status:
    """The status message: a fresh one, or — for a retry — the message the
    button was on, so a retry never leaves the failure behind it."""
    locale = await repo.user_locale(tg_id)
    text = translator("backfill", locale)("backfill-starting", platform=platform)
    if message is not None:
        with contextlib.suppress(Exception):
            await message.edit_text(text, reply_markup=None)
        chat_id, message_id = message.chat.id, message.message_id
    else:
        sent = await bot.send_message(tg_id, text)
        chat_id, message_id = sent.chat.id, sent.message_id
    return _Status(
        bot,
        chat_id,
        message_id,
        locale=locale,
        platform=platform,
        count_found=count_found,
        steps=steps,
    )


async def run_xbox(
    bot: Bot, fetcher: Fetcher, repo: Repo, tg_id: int, xuid: str, *, message: Message | None = None
) -> None:
    status = await _open(bot, repo, tg_id, "XBOX", plural_achievements, steps=True, message=message)
    try:
        count = await fetcher.backfill(tg_id, xuid, progress=status.progress)
    except Exception:
        log.exception("xbox backfill for tg_id=%s failed", tg_id)
        await status.failed("bf:xbox")
        return
    await status.done(count)


async def run_steam(
    bot: Bot,
    fetcher: SteamFetcher,
    repo: Repo,
    tg_id: int,
    steam_id: str,
    *,
    message: Message | None = None,
) -> None:
    status = await _open(bot, repo, tg_id, "Steam", plural_achievements, message=message)
    try:
        count = await fetcher.backfill(tg_id, steam_id, progress=status.progress)
    except SteamGameDetailsPrivateError:
        # "My Profile" can be public while "Game details" is not (#39): the
        # library comes back empty and nothing can be read.
        log.info("steam backfill: game details private for tg_id=%s", tg_id)
        _ = translator("backfill", await repo.user_locale(tg_id))
        await status.failed(
            "bf:steam",
            _("backfill-steam-private", privacy_url=STEAM_PRIVACY_URL),
            recheck=True,
        )
        return
    except Exception:
        log.exception("steam backfill for tg_id=%s failed", tg_id)
        await status.failed("bf:steam")
        return
    await status.done(count)


async def run_psn(
    bot: Bot,
    fetcher: PsnFetcher,
    repo: Repo,
    tg_id: int,
    account_id: str,
    name: str,
    *,
    message: Message | None = None,
) -> None:
    status = await _open(bot, repo, tg_id, f"PSN ({name})", plural_trophies, message=message)
    retry = f"bf:psn:{account_id}"
    try:
        result = await fetcher.backfill(tg_id, account_id, progress=status.progress)
    except Exception:
        log.exception("psn backfill for tg_id=%s failed", tg_id)
        await status.failed(retry)
        return
    _ = translator("backfill", await repo.user_locale(tg_id))
    if not result.visible:
        await status.failed(retry, _("backfill-hidden-psn", platform=status.platform), recheck=True)
        return
    extra = None
    if result.private_title_ids:
        # #28: the account is readable, some of its games are not.
        extra = _("backfill-private-games", count=len(result.private_title_ids))
    await status.done(result.stored, extra=extra)


# ------------------------------------------------------------------ retries


def _later(coro: Awaitable[None]) -> None:
    """A retry runs as long as a first backfill does — the callback answers
    first, and the work goes on without holding the update."""
    asyncio.create_task(coro)  # type: ignore[arg-type]  # noqa: RUF006


@router.callback_query(F.data == "bf:xbox")
async def retry_xbox(callback: CallbackQuery, repo: Repo, fetcher: Fetcher, bot: Bot) -> None:
    tg_id = callback.from_user.id
    user = await repo.get_user(tg_id)
    token = await repo.get_token(tg_id) if user and user.xuid else None
    if user is None or not user.xuid or token is None or token.status != TokenStatus.ACTIVE:
        _ = translator("backfill", await repo.user_locale(tg_id))
        await callback.answer(_("backfill-gone"), show_alert=True)
        return
    await callback.answer()
    message = callback.message if isinstance(callback.message, Message) else None
    _later(run_xbox(bot, fetcher, repo, tg_id, user.xuid, message=message))


@router.callback_query(F.data == "bf:steam")
async def retry_steam(
    callback: CallbackQuery, repo: Repo, steam_fetcher: SteamFetcher, bot: Bot
) -> None:
    tg_id = callback.from_user.id
    link = await repo.get_platform_link(tg_id, Platform.STEAM)
    if link is None:
        _ = translator("backfill", await repo.user_locale(tg_id))
        await callback.answer(_("backfill-gone"), show_alert=True)
        return
    await callback.answer()
    message = callback.message if isinstance(callback.message, Message) else None
    _later(run_steam(bot, steam_fetcher, repo, tg_id, link.external_id, message=message))


@router.callback_query(F.data.startswith("bf:psn:"))
async def retry_psn(callback: CallbackQuery, repo: Repo, psn_fetcher: PsnFetcher, bot: Bot) -> None:
    assert callback.data is not None
    tg_id = callback.from_user.id
    account_id = callback.data.split(":", 2)[2]
    links = await repo.platform_links_for(tg_id, Platform.PSN)
    link = next((item for item in links if item.external_id == account_id), None)
    if link is None:
        _ = translator("backfill", await repo.user_locale(tg_id))
        await callback.answer(_("backfill-gone"), show_alert=True)
        return
    await callback.answer()
    message = callback.message if isinstance(callback.message, Message) else None
    _later(run_psn(bot, psn_fetcher, repo, tg_id, account_id, link_nickname(link), message=message))
