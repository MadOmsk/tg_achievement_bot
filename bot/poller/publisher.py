"""Publishing to Telegram: filtering, digest, queue (SPEC 5.5).

Telegram tolerates about 20 messages per minute into one group, so everything
goes through a queue with a delay. Nothing here talks to Xbox Live.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from datetime import timedelta

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InputMediaPhoto

from bot.constants import account_platform_of
from bot.db.repo import AchievementRow, ChatTarget, Repo, TitleProgress
from bot.services.achievements import (
    format_digest,
    format_single,
    passes_filters,
)
from bot.services.descriptions_view import localize_descriptions
from bot.services.message_log import stats_category
from bot.services.naming import person_name_of
from bot.util import parse_iso, utcnow

log = logging.getLogger(__name__)

SEND_INTERVAL_SECONDS = 3.0  # ~20 messages a minute

# Telegram's own cap on one media group (sendMediaGroup) — a digest with more
# achievements than this still lists every one of them in the text (SPEC
# 7.2), the gallery is just illustrative, not required to be exhaustive.
MEDIA_GROUP_MAX = 10


@dataclass(slots=True)
class PublishJob:
    chat_id: int
    text: str
    # (icon_url, is_secret) per achievement, in order — a single achievement
    # is just a one-item gallery here, not a separate field any more
    # (2026-09-05 follow-up, SPEC 7.1/7.2): one delivery path for both
    # instead of two that used to duplicate each other's fallback-to-text
    # handling. Rows with no icon at all are dropped before this point, not
    # here — an empty list means "no photo, plain text".
    gallery: list[tuple[str, bool]] = field(default_factory=list)
    # (xuid, title_id, achievement_id) per achievement — xuid used to live on
    # the job itself, one value for the whole job, until the anti-flood
    # filter's flush digest (2026-09-09) started building jobs that can mix
    # achievements from more than one of a person's platforms at once: each
    # one must record its *own* xuid in `publications`, not whichever
    # platform happened to be first.
    items: list[tuple[str, str, str]] = field(default_factory=list)


def _gallery(achievements: list[AchievementRow]) -> list[tuple[str, bool]]:
    """One gallery entry per *distinct* icon, not per achievement — Xbox 360
    achievements all share the same icon (the game's own box art, no
    per-achievement art exists at all — SPEC 7.1), and a digest of several
    x360 unlocks would otherwise repeat that one picture N times. Order
    follows first appearance; an achievement sharing an already-seen icon
    still forces that icon's spoiler on if it itself is secret, so a
    same-icon secret never rides in unmarked behind an earlier public one.
    """
    order: list[str] = []
    has_spoiler: dict[str, bool] = {}
    for item in achievements:
        if not item.icon_url:
            continue
        if item.icon_url not in has_spoiler:
            order.append(item.icon_url)
            has_spoiler[item.icon_url] = item.is_secret
        elif item.is_secret:
            has_spoiler[item.icon_url] = True
    return [(url, has_spoiler[url]) for url in order]


class Publisher:
    def __init__(self, bot: Bot, repo: Repo) -> None:
        self._bot = bot
        self._repo = repo
        self._queue: asyncio.Queue[PublishJob] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._worker = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker
            self._worker = None

    async def publish(
        self,
        tg_id: int,
        xuid: str,
        gamertag: str,
        achievements: list[AchievementRow],
        title_name: str | None = None,
        *,
        window_hours: int | None = None,
    ) -> None:
        """Decide per chat what to send, then hand it to the queue.

        `window_hours` caps how old an achievement may be and still be
        *announced* (#52, user rule: "only the last day"). Everything is
        recorded either way — the caller already stored these rows; this
        only decides what reaches a chat.

        Passed by the paths that are not live: catching up after downtime,
        and relinking an account whose history the bot already had. Left
        None on the ordinary poll, and that is deliberate — PSN trophies
        sync to Sony only when a player opens trophy data on the console,
        sometimes days after the unlock, so a blanket age cap on the normal
        path would silently swallow genuinely new trophies.
        """
        if not achievements:
            return
        if window_hours is not None:
            cutoff = utcnow() - timedelta(hours=window_hours)
            achievements = [
                item
                for item in achievements
                if item.unlocked_at and parse_iso(item.unlocked_at) >= cutoff
            ]
            if not achievements:
                return

        for chat in await self._repo.publication_targets(tg_id):
            allowed = [
                item
                for item in achievements
                if passes_filters(item, chat, chat.rare_threshold_percent)
            ]
            if not allowed:
                # Nothing here to notify about, so nothing here to count
                # either — the anti-flood filter below only ever reacts to
                # achievements that would actually have been announced
                # (2026-09-09 user request: it "works only on what gets
                # notified"). rarity_mode=hidden, a muted game, a below-
                # threshold rare pull — any of these already means no timer
                # starts and no window advances, for free, just by never
                # calling _apply_flood_filter at all.
                continue

            if chat.flood_limit > 0:
                allowed = await self._apply_flood_filter(tg_id, chat, allowed)
                if not allowed:
                    continue  # every item this call was buffered, not sent

            # The description is the one piece of an achievement message that
            # is not built from a .ftl: it comes from the platform, and the
            # bilingual cache is what actually holds both languages (#48).
            # Swapped in per chat, after filtering — the same `achievements`
            # list is rendered again for the next chat, possibly in another
            # language, so this must not mutate it.
            allowed = await localize_descriptions(self._repo, allowed, chat.locale)

            # The digest decision is per chat and happens after filtering:
            # what one chat sees as five achievements may be one in another
            # (digest_threshold lives on the subscription now, not on
            # user_settings — Follow-up, 2026-09-05, same move as
            # rarity_mode before it).
            progress = await self._progress_for(allowed)
            if len(allowed) >= chat.digest_threshold:
                await self._queue.put(
                    PublishJob(
                        chat_id=chat.chat_id,
                        text=format_digest(
                            gamertag, title_name, allowed, locale=chat.locale, progress=progress
                        ),
                        gallery=_gallery(allowed),
                        items=[(xuid, a.title_id, a.achievement_id) for a in allowed],
                    )
                )
                continue

            for item in allowed:
                if await self._repo.is_published(
                    chat.chat_id, xuid, item.title_id, item.achievement_id
                ):
                    continue
                await self._queue.put(
                    PublishJob(
                        chat_id=chat.chat_id,
                        text=format_single(
                            gamertag,
                            item,
                            title_name,
                            locale=chat.locale,
                            progress=progress.get(
                                (item.platform, item.title_id, item.trophy_group_id)
                            ),
                        ),
                        gallery=_gallery([item]),
                        items=[(xuid, item.title_id, item.achievement_id)],
                    )
                )

    async def _apply_flood_filter(
        self, tg_id: int, chat: ChatTarget, allowed: list[AchievementRow]
    ) -> list[AchievementRow]:
        """Anti-flood filter (2026-09-09 user request): up to
        `chat.flood_limit` individually-notified achievements per rolling
        `chat.flood_window_minutes` window, scoped to the whole person (not
        per platform — flooding a chat with a mix of Xbox/Steam/PSN unlocks
        is still one person spamming it). The (N+1)th achievement to arrive
        inside a window closes it early right then (not at expiry) and
        opens a fresh one in "throttled" mode: everything from here until
        that new window itself closes gets left unpublished instead of
        sent — poller/flood_flush.py finds and flushes it later, as one
        combined digest, once the window actually closes (or a forced sweep
        fires first — see that module).

        Walks `allowed` one item at a time rather than deciding for the
        whole batch at once: a single publish() call can already carry
        several achievements (a PSN multi-trophy tick, a Steam session), and
        the Nth item within *that one call* must still be the one to flip
        into throttled mode, exactly as if it had arrived on its own.
        """
        now = utcnow()
        state = await self._repo.get_flood_state(tg_id, chat.chat_id)
        if state is not None and now >= state.window_started_at + timedelta(
            minutes=chat.flood_window_minutes
        ):
            # This window is over. Whatever it left buffered is
            # flood_flush.py's job to find and send, not this one's —
            # simplest to just treat this as "no window open" and let a
            # fresh one start below, same as if nothing had ever run yet.
            state = None

        window_started_at = state.window_started_at if state is not None else now
        count = state.count_in_window if state is not None else 0
        throttled = state.throttled if state is not None else False

        to_send: list[AchievementRow] = []
        for item in allowed:
            if throttled:
                continue  # buffered: left unpublished, picked up by flood_flush.py
            to_send.append(item)
            count += 1
            if count >= chat.flood_limit:
                throttled = True
                window_started_at = now  # restart right here, not at expiry

        await self._repo.set_flood_state(
            tg_id,
            chat.chat_id,
            window_started_at=window_started_at,
            count_in_window=count,
            throttled=throttled,
        )
        return to_send

    async def _progress_for(
        self, achievements: list[AchievementRow]
    ) -> dict[tuple[str, str, str | None], TitleProgress]:
        """ "47/50" per game, for whichever games have a known total (#46).

        Looked up once per batch rather than per achievement: a digest of
        ten unlocks in one game is one query, not ten. Games whose total the
        bot does not know (a Steam game with no cached schema yet, a PSN
        game last polled before totals were stored) simply have no entry,
        and their line renders without a counter.

        Keyed by group as well as game: a PSN trophy also says which part
        of the game it came from, and the same game can appear twice in one
        batch under two different groups. A `None` group is the game-only
        answer — every Xbox and Steam row, and a digest block whose trophies
        do not share one group.
        """
        result: dict[tuple[str, str, str | None], TitleProgress] = {}
        for item in achievements:
            for group_id in {item.trophy_group_id, None}:
                key = (item.platform, item.title_id, group_id)
                if key in result or not item.xuid:
                    continue
                found = await self._repo.title_progress(
                    account_platform_of(item.platform), item.xuid, item.title_id, group_id
                )
                if found is not None:
                    result[key] = found
        return result

    async def publish_flood_digest(
        self, tg_id: int, chat_id: int, achievements: list[AchievementRow]
    ) -> None:
        """The flush side of `_apply_flood_filter` above — called by
        poller/flood_flush.py once a throttled window closes. Unlike every
        other digest in the codebase, this one can genuinely mix platforms
        (that's the whole point: the filter counts across all of a person's
        platforms together), so the header uses the person's own Telegram
        identity rather than one platform's own nickname — there is no
        single "gamertag" that's obviously right here the way there is for
        format_single/format_digest's other callers, each already scoped to
        one platform by construction.
        """
        if not achievements:
            return
        # Read here rather than carried in from flood_flush.py: this path has
        # no ChatTarget in hand (it is driven by the throttle table, not by a
        # subscription walk), and one lookup per flushed window is nothing.
        locale = await self._repo.chat_locale(chat_id)
        achievements = await localize_descriptions(self._repo, achievements, locale)
        user = await self._repo.get_user(tg_id)
        links = await self._repo.platform_links_of(tg_id)
        name = person_name_of(user, links) if user else f"id{tg_id}"
        await self._queue.put(
            PublishJob(
                chat_id=chat_id,
                text=format_digest(
                    name,
                    None,
                    achievements,
                    locale=locale,
                    # Same counters as every other game line (#46) — a
                    # flushed backlog is still one block per game, and the
                    # figure is as true here as it is live.
                    progress=await self._progress_for(achievements),
                ),
                gallery=_gallery(achievements),
                items=[
                    (item.xuid, item.title_id, item.achievement_id)
                    for item in achievements
                    if item.xuid
                ],
            )
        )

    async def _run(self) -> None:
        while True:
            job = await self._queue.get()
            try:
                await self._send(job)
            except Exception:
                log.exception("failed to publish into chat %s", job.chat_id)
            finally:
                self._queue.task_done()
            await asyncio.sleep(SEND_INTERVAL_SECONDS)

    async def _send(self, job: PublishJob) -> None:
        try:
            message_id = await self._deliver(job)
        except TelegramForbiddenError:
            # Kicked out of the group — stop trying forever (SPEC 5.5).
            log.info("chat %s is not available any more, deactivating", job.chat_id)
            await self._repo.deactivate_chat(job.chat_id)
            return
        except TelegramRetryAfter as exc:
            log.info("Telegram asked to wait %ss", exc.retry_after)
            await asyncio.sleep(exc.retry_after)
            message_id = await self._deliver(job)

        for xuid, title_id, achievement_id in job.items:
            await self._repo.record_publication(
                job.chat_id, xuid, title_id, achievement_id, message_id
            )

    async def _deliver(self, job: PublishJob) -> int | None:
        # The achievement matters more than the picture(s) (SPEC 7.1) — any
        # failure below falls through to plain text rather than losing the
        # achievement, same principle at every step: gallery, then a single
        # photo, then text. Every branch is a "stats" result (2026-09-05
        # follow-up) — never a candidate for message_cleanup.py's auto-delete.
        with stats_category():
            if len(job.gallery) >= 2:
                try:
                    media = [
                        InputMediaPhoto(
                            media=url,
                            has_spoiler=secret,
                            caption=job.text if index == 0 else None,
                            parse_mode=ParseMode.HTML if index == 0 else None,
                        )
                        for index, (url, secret) in enumerate(job.gallery[:MEDIA_GROUP_MAX])
                    ]
                    messages = await self._bot.send_media_group(job.chat_id, media)
                    return messages[0].message_id if messages else None
                except (TelegramForbiddenError, TelegramRetryAfter):
                    raise
                except Exception:
                    log.info("gallery for chat %s did not go through, sending text", job.chat_id)
            elif len(job.gallery) == 1:
                url, secret = job.gallery[0]
                try:
                    message = await self._bot.send_photo(
                        job.chat_id,
                        photo=url,
                        caption=job.text,
                        parse_mode=ParseMode.HTML,
                        has_spoiler=secret,
                    )
                    return message.message_id
                except (TelegramForbiddenError, TelegramRetryAfter):
                    raise
                except Exception:
                    log.info("icon for chat %s did not go through, sending text", job.chat_id)

            message = await self._bot.send_message(job.chat_id, job.text, parse_mode=ParseMode.HTML)
            return message.message_id
