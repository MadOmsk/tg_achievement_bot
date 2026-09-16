"""The /hltb card and the screens around it (#63).

The card is a photo caption whenever the game has cover art, so Telegram's
1024-character cap is what binds its length — see `_shorten` and
`DESCRIPTION_LIMIT` below.
"""

from __future__ import annotations

import html

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram_i18n import I18nContext

from bot.services.hltb import HltbResult
from bot.views.inline_lists import InlineListing, button_rows, counted_nav, paginate
from bot.views.lists import blockquote

# The rest of the card runs to roughly 300 characters at its longest (a
# long title, every platform HLTB lists, three genres, the link), so this
# leaves comfortable room under Telegram's own 1024-character caption cap
# — see _shorten() below for why the cap is what binds here.
DESCRIPTION_LIMIT = 600


def _cancel_row(i18n: I18nContext) -> list[InlineKeyboardButton]:
    # Every stage of the flow gets this — a person who changed his mind
    # should not have to just leave the prompt hanging (SPEC 6.6).
    return [InlineKeyboardButton(text=i18n.get("hltb-cancel-button"), callback_data="hltb:cancel")]


def _recent_keyboard(
    names: list[str], page: int, page_size: int, i18n: I18nContext
) -> InlineKeyboardMarkup:
    # Paginated over `enumerate(names)`, not the names alone: the callback
    # carries each suggestion's index in the *whole* list, which is what the
    # handler looks it up by, so a page's own 0..N offsets would pick wrong.
    shown = paginate(list(enumerate(names)), page, page_size)
    return InlineListing(
        rows=button_rows(shown.items, lambda item: item[1], lambda item: f"hltb:qr:{item[0]}"),
        nav=counted_nav(shown, "hltb:rpage:"),
        tail=_cancel_row(i18n),
    ).markup()


def _results_keyboard(
    results: list[HltbResult], page: int, page_size: int, i18n: I18nContext
) -> InlineKeyboardMarkup:
    shown = paginate(results, page, page_size)
    return InlineListing(
        rows=button_rows(shown.items, _label, lambda r: f"hltb:pick:{r.hltb_id}"),
        nav=counted_nav(shown, "hltb:page:"),
        tail=_cancel_row(i18n),
    ).markup()


def _label(result: HltbResult) -> str:
    return f"{result.name} ({result.release_year})" if result.release_year else result.name


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
    description = result.description(i18n.locale)
    if description:
        # Collapsed by default (#2, user request): the card's own numbers are
        # what /hltb is for, the summary is there for whoever wants it and
        # must not push the rest off a phone screen.
        lines += ["", blockquote([html.escape(_shorten(description))])]
    if result.game_url:
        url = html.escape(result.game_url, quote=True)
        lines += ["", i18n.get("hltb-card-link", url=url)]
    return "\n".join(lines)


def _shorten(description: str) -> str:
    """A card carrying a cover image is a photo *caption*, and Telegram caps
    those at 1024 characters — a long summary would cost the whole card, not
    just its own tail. Cut on a word boundary well inside that budget; the
    blockquote is collapsed anyway, so nobody is reading a 600-character
    summary in place."""
    if len(description) <= DESCRIPTION_LIMIT:
        return description
    cut = description[:DESCRIPTION_LIMIT]
    head, _, _ = cut.rpartition(" ")
    return (head or cut).rstrip(" ,;:") + "…"
