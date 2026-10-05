"""Every screen's layout, one module per screen (#63, 2026-09-15).

A screen used to be assembled inside the handler that answered the
callback — `handlers/admin.py` alone was 2172 lines with 152 locale lookups
woven through the callback routing. Four screens escaped that only because
something else needed to draw them too (an auto-refresh poller, mostly),
and `docs/ui/` existed to describe by hand what that code was supposed to
produce, kept in sync by hand, wrong often enough that a capture script had
to be written to catch the drift.

So the layout lives here instead, and the rule that makes it worth doing is
this one: **a view renders, it never sends.** It may read the database; it
must never touch `Message`/`CallbackQuery`, never call the Telegram API,
and never decide *when* it is shown. What comes back is a `Screen` — text,
a keyboard, sometimes a picture — and the caller delivers it: a handler
edits it in place, a poller sends it, and `scripts/render_screen.py` puts
it in front of the owner as a real Telegram message on request. That last
one is what replaced the mockups: a picture of a screen stops being a
document you maintain once it can be produced from the code that draws it.

The locale is an explicit argument, never ambient — same rule the rest of
the codebase follows (see bot/i18n.py): one loop renders the same screen
for many chats, and a locale left in module state is exactly how one
chat's message ends up in another chat's language.
"""

from __future__ import annotations

from dataclasses import dataclass

from aiogram.types import InlineKeyboardMarkup


@dataclass(frozen=True)
class Screen:
    """One rendered screen, ready for whoever is going to deliver it.

    `photo` and `media` are how the notification cards fit here: a single
    achievement is a photo whose caption is the whole card, and a digest is
    a media group carrying its caption on the first image. A plain text
    screen leaves both empty, which is every panel and admin screen.
    """

    text: str
    keyboard: InlineKeyboardMarkup | None = None
    photo: str | None = None
    media: tuple[str, ...] = ()

    def as_pair(self) -> tuple[str, InlineKeyboardMarkup | None]:
        """For the handlers still written against the `(text, markup)` tuple
        these functions used to return. Deliberately not the other way
        round: new code takes the Screen."""
        return self.text, self.keyboard


__all__ = ["Screen"]
