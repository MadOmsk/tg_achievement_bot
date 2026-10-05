"""Flushes buffered achievement notifications once an anti-flood window
closes (2026-09-09 user request) — the read side of
publisher.py::Publisher._apply_flood_filter's own write side. Ticks every
minute like every other poller here, plus two forced sweeps that don't wait
for a window to expire on its own: right after the bot starts, and five
minutes before each chat's own daily summary — a window left mid-count (or
a bug in the window math) must never be able to silently swallow someone's
achievements forever; the person should get them either way, eventually.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from bot.db.repo import ChatTarget, FloodState, Repo
from bot.poller.publisher import Publisher
from bot.services.achievements import passes_filters
from bot.services.stats import local_now
from bot.util import utcnow

log = logging.getLogger(__name__)


class FloodFlush:
    def __init__(self, repo: Repo, publisher: Publisher) -> None:
        self._repo = repo
        self._publisher = publisher

    async def tick(self) -> None:
        chats = {chat.chat_id: chat for chat in await self._repo.admin_chats()}
        now = utcnow()
        for state in await self._repo.throttled_flood_states():
            chat = chats.get(state.chat_id)
            if chat is None:
                # The chat is gone (deactivated/deleted) — nothing left to
                # flush into, and admin_chats() will never mention it again.
                await self._repo.clear_flood_state(state.tg_id, state.chat_id)
                continue
            window_expired = now >= state.window_started_at + timedelta(
                minutes=chat.flood_window_minutes
            )
            if window_expired or _five_minutes_before_summary(chat):
                await self._flush_one(state)

    async def flush_all(self) -> None:
        """Force-exit every throttled window regardless of whether it has
        actually expired — called once at startup (main.py). A window that
        was mid-count when the bot last stopped, or one flood_flush.py
        itself somehow never got back to, must not leave its buffered
        achievements stuck forever; better to deliver them a little early
        than not at all."""
        for state in await self._repo.throttled_flood_states():
            await self._flush_one(state)

    async def _flush_one(self, state: FloodState) -> None:
        try:
            targets = await self._repo.publication_targets(state.tg_id)
            chat = next((t for t in targets if t.chat_id == state.chat_id), None)
            if chat is not None:
                pending = await self._repo.unpublished_achievements(state.tg_id, state.chat_id)
                allowed = [
                    item
                    for item in pending
                    if passes_filters(item, chat, chat.rare_threshold_percent)
                ]
                if allowed:
                    await self._publisher.publish_flood_digest(state.tg_id, state.chat_id, allowed)
            # No subscription any more (unsubscribed mid-window) — nothing to
            # flush into, just clear the stale throttle row below.
        except Exception:
            log.exception("flood flush failed for tg_id=%s chat_id=%s", state.tg_id, state.chat_id)
        finally:
            await self._repo.clear_flood_state(state.tg_id, state.chat_id)


def _five_minutes_before_summary(chat: ChatTarget) -> bool:
    """True right at T-5 of a chat's own scheduled daily summary — so the
    summary describes achievements that have actually been announced by the
    time it runs, not ones still sitting in someone's buffer. Skipped
    entirely for a chat with the daily summary off or inactive: nothing is
    about to read the buffer's absence anyway."""
    if not chat.is_active or not chat.daily_summary:
        return False
    now_local = local_now(chat.tz_offset_min)
    return (now_local + timedelta(minutes=5)).strftime("%H:%M") == chat.daily_summary_time
