"""Nothing the bot sends may fail for being too long (#68).

The point of these is less "it cuts" than "what comes out still parses":
truncating HTML at a byte count is how a `message is too long` becomes a
`can't parse entities`, which is the same dead command wearing a different
error.
"""

from __future__ import annotations

import re

from aiogram.methods import AnswerCallbackQuery, SendMediaGroup, SendMessage, SendPhoto
from aiogram.types import InputMediaPhoto

from bot.services.message_limits import (
    CALLBACK_ANSWER_LIMIT,
    CAPTION_LIMIT,
    TEXT_LIMIT,
    clamp,
    truncate_html,
)

_TAG = re.compile(r"<(/?)([a-zA-Z][-a-zA-Z0-9]*)(?:\s[^>]*?)?>")


def _unbalanced(html: str) -> list[str]:
    """Whatever is left open, in the order Telegram would choke on it."""
    stack: list[str] = []
    for closing, name in _TAG.findall(html):
        if closing:
            if stack and stack[-1] == name.lower():
                stack.pop()
            else:
                stack.append(f"stray </{name}>")
        else:
            stack.append(name.lower())
    return stack


def test_a_message_within_the_limit_is_untouched() -> None:
    text = "<b>Short</b> and fine"
    assert truncate_html(text, TEXT_LIMIT) == text


def test_truncation_closes_what_it_cut_through() -> None:
    text = "<blockquote expandable>" + "слово " * 400 + "</blockquote>"
    cut = truncate_html(text, 200)

    assert len(cut) <= 200
    assert cut.endswith("</blockquote>")
    assert _unbalanced(cut) == []


def test_truncation_closes_nested_tags_innermost_first() -> None:
    text = "<blockquote><b><i>" + "x" * 500 + "</i></b></blockquote>"
    cut = truncate_html(text, 120)

    assert len(cut) <= 120
    assert cut.endswith("</i></b></blockquote>")
    assert _unbalanced(cut) == []


def test_the_cut_never_lands_inside_a_tag() -> None:
    """The failure this guards: a limit falling in the middle of
    `<blockquote expandable>` leaves half a tag, and Telegram rejects the
    whole message."""
    opening = "<blockquote expandable>"
    text = "a" * 50 + opening + "b" * 200 + "</blockquote>"
    for limit in range(55, 90):
        cut = truncate_html(text, limit)
        assert len(cut) <= limit
        assert "<blockquote" not in cut or opening in cut
        assert _unbalanced(cut) == []


def test_the_cut_never_lands_inside_an_entity() -> None:
    text = "Marvel&#x27;s Spider-Man " * 40
    for limit in range(20, 60):
        cut = truncate_html(text, limit)
        assert len(cut) <= limit
        assert not re.search(r"&[#a-zA-Z0-9]*$", cut.removesuffix("…"))


def test_truncation_prefers_a_word_boundary() -> None:
    text = "<b>" + "слово " * 200 + "</b>"
    cut = truncate_html(text, 100)
    assert "…</b>" in cut
    assert "слов…" not in cut  # not mid-word


def test_a_long_unbroken_run_is_still_cut() -> None:
    """No space to fall back to — the cut has to happen anyway rather than
    give up and send the whole thing."""
    cut = truncate_html("<b>" + "x" * 5000 + "</b>", 100)
    assert len(cut) <= 100
    assert _unbalanced(cut) == []


def test_send_message_is_clamped_to_the_text_limit() -> None:
    method = SendMessage(chat_id=1, text="<b>" + "я" * 6000 + "</b>", parse_mode="HTML")
    clamp(method)

    assert method.text is not None
    assert len(method.text) <= TEXT_LIMIT
    assert _unbalanced(method.text) == []


def test_a_photo_caption_gets_the_smaller_limit() -> None:
    """A caption is capped at 1024, not 4096 — the achievement card is a
    photo message, so this is the limit that actually binds it."""
    method = SendPhoto(chat_id=1, photo="file-id", caption="a" * 2000, parse_mode="HTML")
    clamp(method)

    assert method.caption is not None
    assert len(method.caption) <= CAPTION_LIMIT


def test_a_callback_answer_gets_its_own_much_smaller_limit() -> None:
    method = AnswerCallbackQuery(callback_query_id="1", text="a" * 500)
    clamp(method)

    assert method.text is not None
    assert len(method.text) <= CALLBACK_ANSWER_LIMIT


def test_an_album_caption_is_clamped_too() -> None:
    """A digest is a sendMediaGroup with the caption on the first image, and
    an album's items are frozen — so this one is replaced, not edited."""
    method = SendMediaGroup(
        chat_id=1,
        media=[
            InputMediaPhoto(media="a", caption="<b>" + "я" * 2000 + "</b>", parse_mode="HTML"),
            InputMediaPhoto(media="b"),
        ],
    )
    clamp(method)

    first = method.media[0]
    assert first.caption is not None
    assert len(first.caption) <= CAPTION_LIMIT
    assert _unbalanced(first.caption) == []
    assert method.media[1].caption is None


def test_plain_text_is_cut_without_any_html_handling() -> None:
    """No parse_mode means the angle brackets are literal text, and closing
    a "tag" that was never markup would corrupt the message."""
    method = SendMessage(chat_id=1, text="1 < 2 and " + "x" * 6000)
    clamp(method)

    assert method.text is not None
    assert len(method.text) <= TEXT_LIMIT
    assert method.text.endswith("…")
    assert "</" not in method.text


#: Shaped like a real /summary: a header, a bold total, a collapsible quote
#: of rows, one of them spoilered, an entity in a game's name and a link.
REAL_MESSAGE = (
    "🏆 <b>Итоги за 16 сентября</b>\n\n"
    "<b>Всего:</b> 201 достижение, +1 100 G\n"
    "<blockquote expandable>"
    + "".join(
        f"{place}. 🟢 Marvel&#x27;s Spider-Man — {place} достижений (+{place}0 G · 💎{place})\n"
        f'{place}. ⚫ <span class="tg-spoiler">Секретное</span> — ещё строка\n'
        for place in range(1, 40)
    )
    + "</blockquote>\n"
    '<a href="https://howlongtobeat.com/game/1234">HowLongToBeat</a>'
)


def test_a_real_message_stays_valid_html_wherever_it_is_cut() -> None:
    """The exhaustive version of the three cases above: every limit from a
    handful of characters up past the whole message, each one asserting the
    two things Telegram actually checks — length, and that the entities
    parse."""
    for limit in range(20, len(REAL_MESSAGE) + 40, 7):
        cut = truncate_html(REAL_MESSAGE, limit)
        assert len(cut) <= limit
        assert _unbalanced(cut) == [], f"limit={limit}: {cut[-80:]!r}"
        assert "<blockquote" not in cut or "<blockquote expandable>" in cut


def test_a_short_message_passes_through_unchanged() -> None:
    method = SendMessage(chat_id=1, text="fine", parse_mode="HTML")
    clamp(method)
    assert method.text == "fine"
