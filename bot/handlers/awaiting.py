"""Whose next private message is a profile link, and for which platform.

One registry, not one per platform (2026-09-12, found while testing #52):
`/connect_steam` and `/connect_psn` each used to keep their own set of
"waiting for this person's next message". Pressing one and then the other
left both waiting, the typed nickname matched both filters, and whichever
router was registered first — Steam — swallowed it. The person got "Steam
profile not found" after asking to connect PSN.

Asking for one platform therefore cancels any other platform's question:
there is only ever one pending question per person, because a person can
only answer the last thing they were asked.

In-memory on purpose, like every other "must not survive a restart" flow
here (admin.py's own text input, ConnectService._pending): a lost entry
just means running the command again.
"""

from __future__ import annotations

_awaiting: dict[int, str] = {}


def expect(tg_id: int, platform: str) -> None:
    """This person's next private message is a profile link for `platform`.
    Replaces whatever else was expected of them."""
    _awaiting[tg_id] = platform


def is_expecting(tg_id: int, platform: str, text: str | None = None) -> bool:
    """Whether this person's next message answers `platform`'s question.

    A message starting with "/" never does (2026-09-12, user report):
    typing /connect_psn right after /connect_steam was swallowed as a Steam
    nickname and answered with "invalid key". A command is the person
    changing their mind, not answering — and the command's own handler is
    what should see it.
    """
    if text is not None and text.lstrip().startswith("/"):
        return False
    return _awaiting.get(tg_id) == platform


def clear(tg_id: int) -> None:
    _awaiting.pop(tg_id, None)
