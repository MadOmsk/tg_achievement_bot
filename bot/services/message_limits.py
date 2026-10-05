"""Nothing this bot sends may fail for being too long (owner, 2026-09-17).

Telegram rejects an oversized message outright — `Bad Request: message is
too long` — and the handler that built it has already done all its work, so
the command simply looks dead. That is #68: `/summary` pressed three times
on production, nothing in the chat, the reason visible only in the log.

Capping each screen at its own call site was the obvious fix and the wrong
one: the limit is in characters, every list is capped by *rows*, and the
same screen fits or does not depending on how long the game titles happen
to be that month. So the guarantee lives here instead, once, on the Bot's
own request pipeline — the same seam `services/message_log.py` already uses
for the same reason, and for the same reason: a dozen handlers, two pollers
and the OAuth callback all send things, and the next one added would have
to remember.

**Truncating HTML naively only trades one Telegram error for another.**
Cutting at 4096 lands inside `<blockquote expandable>` or leaves `<b>`
unclosed, and Telegram answers `can't parse entities` instead. So the cut
lands only where it is safe — never inside a tag or an `&entity;` — and
whatever was open at that point is closed again afterwards.

A truncation is always logged as a warning: the net exists so a screen never
dies, not so an overlong screen goes unnoticed.
"""

from __future__ import annotations

import logging
import re

from aiogram import Bot
from aiogram.client.session.middlewares.base import (
    BaseRequestMiddleware,
    NextRequestMiddlewareType,
)
from aiogram.enums import ParseMode
from aiogram.methods import TelegramMethod
from aiogram.methods.base import TelegramType

log = logging.getLogger(__name__)

#: Telegram's own documented maxima.
TEXT_LIMIT = 4096
CAPTION_LIMIT = 1024
CALLBACK_ANSWER_LIMIT = 200

ELLIPSIS = "…"

#: How far back the cut may walk to land on a space instead of mid-word.
#: Past this it is not worth losing content over, and a hard cut it is.
WORD_BOUNDARY_SEARCH = 120

_TAG = re.compile(r"<(/?)([a-zA-Z][-a-zA-Z0-9]*)((?:\s[^>]*?)?)/?>")

#: Tags that never need closing. Telegram's own HTML subset has none of
#: these, but a stray one must not push a phantom `</br>` onto the stack.
_VOID = frozenset({"br", "hr", "img"})


def _closing_cost(name: str) -> int:
    return len(name) + 3  # </name>


def truncate_html(text: str, limit: int, *, ellipsis: str = ELLIPSIS) -> str:
    """`text` cut to at most `limit` characters, still valid Telegram HTML.

    The cut may land only between tokens — never inside a `<tag>` or an
    `&entity;` — and every tag still open there is closed after the
    ellipsis, so the result parses. Prefers the last space within
    `WORD_BOUNDARY_SEARCH` characters of that point, which costs a few
    characters and reads far better than a word sliced in half.
    """
    if len(text) <= limit:
        return text

    stack: list[str] = []
    closing = 0  # characters the closing tags for `stack` would take
    # The best cut found so far: any safe one, and the best that follows a
    # space. Kept apart so a long unbroken run cannot lose the whole tail.
    best = (0, 0)  # (position, closing cost there)
    best_space = (0, 0)
    best_stack: list[str] = []
    best_space_stack: list[str] = []

    def fits(pos: int, cost: int) -> bool:
        return pos + len(ellipsis) + cost <= limit

    position = 0
    length = len(text)
    while position < length:
        if fits(position, closing):
            best = (position, closing)
            best_stack = list(stack)
            if position and text[position - 1].isspace():
                best_space = (position, closing)
                best_space_stack = list(stack)
        elif position > limit:
            break

        char = text[position]
        if char == "<":
            match = _TAG.match(text, position)
            if match is not None:
                name = match.group(2).lower()
                if match.group(1):
                    if name in stack:
                        # Close back to it: Telegram's own HTML never
                        # interleaves, but a stack that drifts would leak a
                        # bogus closing tag into every later cut.
                        while stack and stack[-1] != name:
                            closing -= _closing_cost(stack.pop())
                        if stack:
                            closing -= _closing_cost(stack.pop())
                elif name not in _VOID and not match.group(0).endswith("/>"):
                    stack.append(name)
                    closing += _closing_cost(name)
                position = match.end()
                continue
        elif char == "&":
            semicolon = text.find(";", position, position + 12)
            if semicolon != -1:
                position = semicolon + 1
                continue
        position += 1

    cut, _cost = best
    tags = best_stack
    space_cut, _space_cost = best_space
    if space_cut and cut - space_cut <= WORD_BOUNDARY_SEARCH:
        cut, tags = space_cut, best_space_stack

    head = text[:cut].rstrip()
    return head + ellipsis + "".join(f"</{name}>" for name in reversed(tags))


def truncate(text: str, limit: int, *, html: bool) -> str:
    if len(text) <= limit:
        return text
    if html:
        return truncate_html(text, limit)
    head = text[: limit - len(ELLIPSIS)].rstrip()
    return head + ELLIPSIS


def _is_html(parse_mode: str | None) -> bool:
    return parse_mode == ParseMode.HTML


def _limit_for(method_name: str, field: str) -> int:
    if field == "caption":
        return CAPTION_LIMIT
    # A callback answer is a toast, not a message, and has its own much
    # smaller maximum — one Telegram rejects just as hard.
    return CALLBACK_ANSWER_LIMIT if method_name == "AnswerCallbackQuery" else TEXT_LIMIT


def clamp(method: TelegramMethod[TelegramType]) -> TelegramMethod[TelegramType]:
    """Cut whatever text this outgoing call carries down to its own limit.

    Driven by which fields the method actually has rather than by a list of
    method names, so a send this bot does not make yet is covered the day it
    is added — which is the whole point of doing it here.
    """
    name = type(method).__name__
    fields = type(method).model_fields
    parse_mode = getattr(method, "parse_mode", None)

    for field in ("text", "caption"):
        if field not in fields:
            continue
        value = getattr(method, field, None)
        if not isinstance(value, str):
            continue
        limit = _limit_for(name, field)
        if len(value) <= limit:
            continue
        cut = truncate(value, limit, html=_is_html(parse_mode))
        setattr(method, field, cut)
        log.warning(
            "%s.%s was %s characters, over the %s limit — truncated to %s",
            name,
            field,
            len(value),
            limit,
            len(cut),
        )

    if "media" in fields:
        media = getattr(method, "media", None)
        if isinstance(media, list):
            # An album's items are frozen, unlike the method itself, so a
            # copy replaces the one that is too long.
            method.media = [_clamp_media(name, item) for item in media]
    return method


def _clamp_media(method_name: str, item: object) -> object:
    caption = getattr(item, "caption", None)
    if not isinstance(caption, str) or len(caption) <= CAPTION_LIMIT:
        return item
    cut = truncate(caption, CAPTION_LIMIT, html=_is_html(getattr(item, "parse_mode", None)))
    log.warning(
        "%s: an album caption was %s characters, over the %s limit — truncated to %s",
        method_name,
        len(caption),
        CAPTION_LIMIT,
        len(cut),
    )
    return item.model_copy(update={"caption": cut})  # type: ignore[attr-defined]


class MessageLimitMiddleware(BaseRequestMiddleware):
    """Applies `clamp` to every outgoing call, before it is made."""

    async def __call__(
        self,
        make_request: NextRequestMiddlewareType[TelegramType],
        bot: Bot,
        method: TelegramMethod[TelegramType],
    ) -> TelegramType:
        return await make_request(bot, clamp(method))
