"""`/hltb` — HowLongToBeat search, works in both DM and group chat (SPEC 6.6).

A session lives on the single message it edits through end to end (prompt →
results → card), keyed by (chat_id, message_id) — not by the asker, so
pagination and picking work for whoever taps the buttons, but a *typed*
reply only ever counts as that session's query from the person who actually
ran /hltb. In-memory only, like every other "must not survive a restart"
flow in this project (admin's rare-threshold input, ConnectService._pending).

Busy-chat safety: a typed query is accepted only as an explicit Telegram
reply to the live prompt message, checked by message id — not "whatever this
person types next". A group chat can have hundreds of unrelated messages
between /hltb and an answer; a reply is the only way to point at the right
one unambiguously.
"""

from __future__ import annotations

import contextlib
import html
import logging
import time
from dataclasses import dataclass, field

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram_i18n import I18nContext

from bot.db.repo import Repo
from bot.services.hltb import HltbError, HltbResult, resolve, search
from bot.services.message_log import stats_category

log = logging.getLogger(__name__)

router = Router(name="hltb")

RESULTS_LIMIT_KEY = "hltb_results_limit"
PAGE_SIZE_KEY = "hltb_page_size"
DEFAULT_RESULTS_LIMIT = 20
DEFAULT_PAGE_SIZE = 5
# Generous — the reply-to-message check is the real guard against a stray
# match, this is just a backstop against sessions piling up forever.
SESSION_TTL_SECONDS = 1800


@dataclass
class _Session:
    asker_tg_id: int
    started_at: float
    page_size: int
    results_limit: int
    prompt_text: str = ""
    recent_games: list[str] = field(default_factory=list)
    recent_page: int = 0
    results: list[HltbResult] = field(default_factory=list)
    page: int = 0


_sessions: dict[tuple[int, int], _Session] = {}


def _alive(session: _Session) -> bool:
    return time.monotonic() - session.started_at < SESSION_TTL_SECONDS


@router.message(Command("hltb"))
async def hltb_command(message: Message, repo: Repo, i18n: I18nContext) -> None:
    if message.from_user is None:
        return
    # Only meaningful in a group: a DM's chat_id is the asker's own tg_id,
    # which never has subscriptions/chat_seen rows of its own.
    limit = await repo.get_int_setting(RESULTS_LIMIT_KEY, DEFAULT_RESULTS_LIMIT)
    page_size = await repo.get_int_setting(PAGE_SIZE_KEY, DEFAULT_PAGE_SIZE)
    recent = await repo.chat_recent_games(message.chat.id, limit)

    text = i18n.get("hltb-prompt-title")
    text += "\n" + (
        i18n.get("hltb-prompt-with-recent") if recent else i18n.get("hltb-prompt-reply-only")
    )

    prompt = await message.answer(text, reply_markup=_recent_keyboard(recent, 0, page_size, i18n))
    _sessions[(message.chat.id, prompt.message_id)] = _Session(
        asker_tg_id=message.from_user.id,
        started_at=time.monotonic(),
        page_size=page_size,
        results_limit=limit,
        prompt_text=text,
        recent_games=recent,
    )


def _nav_row(page: int, pages: int, page_prefix: str) -> list[InlineKeyboardButton]:
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"{page_prefix}{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data="hltb:noop"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"{page_prefix}{page + 1}"))
    return nav


def _cancel_row(i18n: I18nContext) -> list[InlineKeyboardButton]:
    # Every stage of the flow gets this — a person who changed his mind
    # should not have to just leave the prompt hanging (SPEC 6.6).
    return [InlineKeyboardButton(text=i18n.get("hltb-cancel-button"), callback_data="hltb:cancel")]


def _recent_keyboard(
    names: list[str], page: int, page_size: int, i18n: I18nContext
) -> InlineKeyboardMarkup:
    start = page * page_size
    chunk = names[start : start + page_size]
    rows = [
        [InlineKeyboardButton(text=name, callback_data=f"hltb:qr:{start + i}")]
        for i, name in enumerate(chunk)
    ]
    pages = -(-len(names) // page_size)
    if pages > 1:
        rows.append(_nav_row(page, pages, "hltb:rpage:"))
    rows.append(_cancel_row(i18n))
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("hltb:rpage:"))
async def hltb_recent_page(callback: CallbackQuery, bot: Bot, i18n: I18nContext) -> None:
    if not isinstance(callback.message, Message):
        return
    key = (callback.message.chat.id, callback.message.message_id)
    session = _sessions.get(key)
    if session is None or not _alive(session):
        await callback.answer(i18n.get("hltb-session-stale"), show_alert=True)
        return
    assert callback.data is not None
    session.recent_page = int(callback.data.rsplit(":", 1)[1])
    await callback.answer()
    markup = _recent_keyboard(session.recent_games, session.recent_page, session.page_size, i18n)
    await _edit(bot, key[0], key[1], session.prompt_text, markup)


async def _is_awaited_reply(message: Message) -> bool:
    if message.from_user is None or not message.text or message.reply_to_message is None:
        return False
    session = _sessions.get((message.chat.id, message.reply_to_message.message_id))
    # Only while still waiting for a first query — once results are shown the
    # interaction is button-driven, a further reply to that message is noise.
    return (
        session is not None
        and session.asker_tg_id == message.from_user.id
        and not session.results
        and _alive(session)
    )


@router.message(_is_awaited_reply)
async def hltb_query(message: Message, repo: Repo, bot: Bot, i18n: I18nContext) -> None:
    assert message.text is not None and message.reply_to_message is not None
    prompt_id = message.reply_to_message.message_id
    session = _sessions.get((message.chat.id, prompt_id))
    if session is None:  # pragma: no cover — filter already checked this
        return
    await _run_search(bot, repo, message.chat.id, prompt_id, session, message.text, i18n)


@router.callback_query(F.data.startswith("hltb:qr:"))
async def hltb_recent_pick(
    callback: CallbackQuery, repo: Repo, bot: Bot, i18n: I18nContext
) -> None:
    if not isinstance(callback.message, Message):
        return
    key = (callback.message.chat.id, callback.message.message_id)
    session = _sessions.get(key)
    if session is None or not _alive(session):
        await callback.answer(i18n.get("hltb-session-stale"), show_alert=True)
        return
    assert callback.data is not None
    idx = int(callback.data.rsplit(":", 1)[1])
    if idx >= len(session.recent_games):
        await callback.answer()
        return
    await callback.answer()
    await _run_search(bot, repo, key[0], key[1], session, session.recent_games[idx], i18n)


async def _run_search(
    bot: Bot,
    repo: Repo,
    chat_id: int,
    message_id: int,
    session: _Session,
    query: str,
    i18n: I18nContext,
) -> None:
    try:
        results = await search(query, limit=session.results_limit)
    except HltbError:
        log.info("HLTB search failed for %r", query)
        await _edit(bot, chat_id, message_id, i18n.get("hltb-unavailable"), None)
        _sessions.pop((chat_id, message_id), None)
        return

    if not results:
        text = i18n.get("hltb-no-results", query=query)
        await _edit(bot, chat_id, message_id, text, None)
        return  # keep the session alive — the same reply target still works

    if len(results) == 1:
        # One match — asking "which of these?" over a single button is a
        # pointless extra tap, just show the card straight away.
        if not await _show_card(bot, repo, chat_id, message_id, results[0].hltb_id, i18n):
            await _edit(bot, chat_id, message_id, i18n.get("hltb-unavailable"), None)
        _sessions.pop((chat_id, message_id), None)
        return

    session.results = results
    session.page = 0
    markup = _results_keyboard(results, 0, session.page_size, i18n)
    await _edit(bot, chat_id, message_id, i18n.get("hltb-results-prompt"), markup)


def _results_keyboard(
    results: list[HltbResult], page: int, page_size: int, i18n: I18nContext
) -> InlineKeyboardMarkup:
    start = page * page_size
    chunk = results[start : start + page_size]
    rows = [
        [InlineKeyboardButton(text=_label(r), callback_data=f"hltb:pick:{r.hltb_id}")]
        for r in chunk
    ]

    pages = -(-len(results) // page_size)
    if pages > 1:
        rows.append(_nav_row(page, pages, "hltb:page:"))
    rows.append(_cancel_row(i18n))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _label(result: HltbResult) -> str:
    return f"{result.name} ({result.release_year})" if result.release_year else result.name


@router.callback_query(F.data == "hltb:noop")
async def hltb_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data == "hltb:cancel")
async def hltb_cancel(callback: CallbackQuery, bot: Bot) -> None:
    # Delete rather than edit to "Отменено" — a cancelled flow shouldn't
    # leave a message behind for no reason (same call as unsubscribe's and
    # disconnect's cancel, SPEC 6.3). Open to anyone on the message, not just
    # the asker: same reasoning as picking a result or paging — no side
    # effect beyond ending a shared, harmless search session.
    if not isinstance(callback.message, Message):
        return
    chat_id, message_id = callback.message.chat.id, callback.message.message_id
    _sessions.pop((chat_id, message_id), None)
    await callback.answer()
    with contextlib.suppress(Exception):
        await bot.delete_message(chat_id, message_id)


@router.callback_query(F.data.startswith("hltb:page:"))
async def hltb_page(callback: CallbackQuery, bot: Bot, i18n: I18nContext) -> None:
    if not isinstance(callback.message, Message):
        return
    key = (callback.message.chat.id, callback.message.message_id)
    session = _sessions.get(key)
    if session is None or not _alive(session):
        await callback.answer(i18n.get("hltb-session-stale"), show_alert=True)
        return
    assert callback.data is not None
    session.page = int(callback.data.rsplit(":", 1)[1])
    await callback.answer()
    markup = _results_keyboard(session.results, session.page, session.page_size, i18n)
    await _edit(bot, key[0], key[1], i18n.get("hltb-results-prompt"), markup)


@router.callback_query(F.data.startswith("hltb:pick:"))
async def hltb_pick(callback: CallbackQuery, repo: Repo, bot: Bot, i18n: I18nContext) -> None:
    if not isinstance(callback.message, Message):
        return
    assert callback.data is not None
    hltb_id = int(callback.data.rsplit(":", 1)[1])
    chat_id, message_id = callback.message.chat.id, callback.message.message_id
    if not await _show_card(bot, repo, chat_id, message_id, hltb_id, i18n):
        await callback.answer(i18n.get("hltb-unavailable"), show_alert=True)
        return
    await callback.answer()
    _sessions.pop((chat_id, message_id), None)


async def _show_card(
    bot: Bot, repo: Repo, chat_id: int, message_id: int, hltb_id: int, i18n: I18nContext
) -> bool:
    try:
        result = await resolve(repo, hltb_id)
    except HltbError:
        return False
    await _send_card(bot, chat_id, message_id, result, i18n)
    return True


async def _send_card(
    bot: Bot, chat_id: int, message_id: int, result: HltbResult, i18n: I18nContext
) -> None:
    """A cover image can't land on a message that started as plain text —
    Telegram's editMessageMedia only swaps media for media, never text for
    media. So the card becomes a fresh photo message and the old prompt is
    deleted (same "delete rather than leave stale text" call as cancel,
    SPEC 6.6), falling back to the old in-place text edit if there is no
    image or Telegram refuses to fetch it."""
    caption = _card(result, i18n)
    if result.image_url:
        try:
            with stats_category():
                await bot.send_photo(
                    chat_id, photo=result.image_url, caption=caption, parse_mode=ParseMode.HTML
                )
        except Exception:
            log.info("could not send hltb cover for id=%s, falling back to text", result.hltb_id)
        else:
            with contextlib.suppress(Exception):
                await bot.delete_message(chat_id, message_id)
            return
    with stats_category():
        await _edit(bot, chat_id, message_id, caption, None, html=True)


def _card(result: HltbResult, i18n: I18nContext) -> str:
    def fmt(hours: float | None) -> str:
        return i18n.get("hltb-hours", hours=f"{hours:.1f}") if hours else i18n.get("hltb-no-data")

    title = f"⏱ <b>{html.escape(result.name)}</b>"
    if result.release_year:
        title += f" ({result.release_year})"
    lines = [
        f"{title}\n",
        i18n.get("hltb-card-main", hours=fmt(result.main_hours)),
        i18n.get("hltb-card-extra", hours=fmt(result.extra_hours)),
        i18n.get("hltb-card-completionist", hours=fmt(result.completionist_hours)),
    ]
    if result.platforms:
        platforms = html.escape(", ".join(result.platforms))
        lines += ["", i18n.get("hltb-card-platforms", platforms=platforms)]
    if result.genre:
        lines += ["", i18n.get("hltb-card-genres", genre=html.escape(result.genre))]
    if result.game_url:
        url = html.escape(result.game_url, quote=True)
        lines += ["", i18n.get("hltb-card-link", url=url)]
    return "\n".join(lines)


async def _edit(
    bot: Bot,
    chat_id: int,
    message_id: int,
    text: str,
    markup: InlineKeyboardMarkup | None,
    *,
    html: bool = False,
) -> None:
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=markup,
            parse_mode=ParseMode.HTML if html else None,
        )
    except Exception:
        # Telegram rejects an edit that changes nothing, or the message could
        # have been deleted meanwhile — neither is worth crashing over.
        log.info("could not edit hltb message %s/%s", chat_id, message_id)
