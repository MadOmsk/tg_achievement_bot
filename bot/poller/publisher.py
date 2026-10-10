"""Publishing to Telegram: filtering, digest, queue (SPEC 5.5).

Telegram tolerates about 20 messages per minute into one group, so everything
goes through a queue with a delay. Nothing here talks to Xbox Live.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InputMediaPhoto

from bot.config import Settings
from bot.constants import account_platform_of
from bot.db.repo import AchievementRow, ChatTarget, Repo, TitleProgress
from bot.i18n import gettext
from bot.services import achievement_icons, covers, images, post_picture
from bot.services.achievements import passes_filters
from bot.services.chat_gone import chat_is_gone
from bot.services.descriptions_view import localize_descriptions
from bot.services.message_log import achievement_category
from bot.services.mini_app import mini_app_open_markup
from bot.services.naming import (
    link_nickname,
    person_name,
    person_name_of,
)
from bot.util import parse_iso, utcnow
from bot.version import is_test
from bot.views.notification import format_digest, format_single
from bot.views.parts import platform_label

log = logging.getLogger(__name__)

SEND_INTERVAL_SECONDS = 3.0  # ~20 messages a minute

# Telegram's own cap on one media group (sendMediaGroup) — a digest with more
# achievements than this still lists every one of them in the text (SPEC
# 7.2), the gallery is just illustrative, not required to be exhaustive.
MEDIA_GROUP_MAX = 10

# Told when a person has new achievements in one game, for the people following
# them (#164): (person_id, platform, title_id, game, count).
PostNotice = Callable[..., Awaitable[None]]


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
    reply_markup: InlineKeyboardMarkup | None = None
    # Pictures to try when the gallery's first one does not go through, or
    # there is none: the achievement's icon cached on disk, then the game's
    # cover (its file, its URL) — `Picture`s.
    backups: list[Picture] = field(default_factory=list)
    # Where each gallery picture can be read from, to enlarge a low-resolution
    # one on a square (`services/post_picture.py`): one `Art` per gallery
    # entry, same order.
    art: list[Art] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Picture:
    """One way to give a post its picture: a URL Telegram fetches (`url`), a
    URL the bot fetches and uploads (`fetch`), or a file on disk (`file`)."""

    how: str
    where: str
    spoiler: bool = False
    # `bytes`: a picture drawn here, sent as it is.
    data: bytes | None = None


@dataclass(frozen=True, slots=True)
class Art:
    """One post picture's originals: the icon (its cached file, its URL) and
    the game's cover (its file, its URL), first that loads wins."""

    icon: tuple[str, ...]
    cover: tuple[str, ...] = ()


async def _photo_input(picture: Picture) -> str | BufferedInputFile | None:
    """What `send_photo` takes for one picture, or None when there is nothing
    to send (a fetch that failed, a file gone)."""
    if picture.how == "url":
        return picture.where
    if picture.how == "bytes":
        return BufferedInputFile(picture.data, filename="post.jpg") if picture.data else None
    if picture.how == "fetch":
        payload = await images.fetch(picture.where)
    else:
        try:
            payload = await asyncio.to_thread(Path(picture.where).read_bytes)
        except OSError:
            return None
    return BufferedInputFile(payload, filename="picture.jpg") if payload else None


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
    def __init__(
        self,
        bot: Bot | None,
        repo: Repo,
        settings: Settings | None = None,
        *,
        bot_username: str | None = None,
    ) -> None:
        self._bot = bot
        self._repo = repo
        self._settings = settings
        self._bot_username = bot_username.lstrip("@") if bot_username else None
        self._queue: asyncio.Queue[PublishJob] = asyncio.Queue()
        # Chats a *test* bot cannot reach (it is not a member of them): skipped for
        # the life of the process instead of deactivated, see `_send`.
        self._unreachable: set[int] = set()
        self._worker: asyncio.Task[None] | None = None
        # Set once the app's notifications exist (bot/main.py).
        self.on_new_post: PostNotice | None = None
        self._notices: set[asyncio.Task[None]] = set()

    async def _get_bot_username(self) -> str:
        if self._bot_username:
            return self._bot_username
        if self._bot is None:
            return ""
        try:
            me = await self._bot.me()
            self._bot_username = (me.username or "").lstrip("@")
            return self._bot_username
        except Exception:
            return ""

    async def _markup_for(
        self,
        chat_id: int,
        locale: str,
        *,
        person_id: int | None = None,
        game: tuple[str, str] | None = None,
    ) -> InlineKeyboardMarkup | None:
        if not self._settings or not (self._settings.mini_app_url or "").strip():
            return None
        in_group = chat_id < 0
        bot_username = await self._get_bot_username()
        if in_group and not bot_username:
            return None
        button_text = gettext("chat", "chat-open-mini-app", locale=locale)
        return mini_app_open_markup(
            button_text,
            https_url=self._settings.mini_app_url,
            bot_username=bot_username,
            chat_id=chat_id,
            person_id=person_id,
            game=game,
            in_group=in_group,
        )

    async def _person_label(self, person_id: int) -> str:
        """The person as the app names them: their nickname, else their id
        (owner, 2026-10-07) — never a platform's nickname."""
        user = await self._repo.get_user(person_id)
        return person_name_of(user) if user else person_name(person_id=person_id, handle=None)

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
        person_id: int,
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
        # The person's own switch for this account (#20): muted, it stays
        # stored and counted, and posts nowhere.
        if not await self._repo.account_publishes(
            person_id, account_platform_of(achievements[0].platform), xuid
        ):
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
        self._tell_followers(person_id, achievements, title_name)
        # A post names the person as the app does everywhere (owner,
        # 2026-10-07): the nickname, else the id — not the platform's own
        # nickname `gamertag` carries.
        name = await self._person_label(person_id)

        for chat in await self._repo.publication_targets(person_id):
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
                allowed = await self._apply_flood_filter(person_id, chat, allowed)
                if not allowed:
                    continue  # every item this call was buffered, not sent

            # The description is the one piece of an achievement message that
            # is not built from a .ftl: it comes from the platform, and the
            # bilingual cache is what actually holds both languages (#48).
            # Swapped in per chat, after filtering — the same `achievements`
            # list is rendered again for the next chat, possibly in another
            # language, so this must not mutate it.
            allowed = await localize_descriptions(self._repo, allowed, chat.locale)

            # The digest decision happens per chat, after filtering: what one
            # chat sees as five achievements may be one in another. The size
            # itself is one for every chat (owner, 2026-10-08).
            progress = await self._progress_for(allowed, xuid)
            missing = [a.title_id for a in allowed if not getattr(a, "game_platforms", None)]
            if missing:
                plat_map = await self._repo.title_platforms(missing)
                for a in allowed:
                    if not getattr(a, "game_platforms", None) and a.title_id in plat_map:
                        a.game_platforms = plat_map[a.title_id]
            # One `publish()` call is always one game (title_name/xuid are
            # singular above), so every item in `allowed` shares it.
            game_ref = (allowed[0].platform, allowed[0].title_id) if allowed else None
            markup = await self._markup_for(
                chat.chat_id, chat.locale, person_id=person_id, game=game_ref
            )
            if len(allowed) >= chat.digest_threshold:
                await self._queue.put(
                    PublishJob(
                        chat_id=chat.chat_id,
                        text=format_digest(
                            name, title_name, allowed, locale=chat.locale, progress=progress
                        ),
                        gallery=_gallery(allowed),
                        items=[(xuid, a.title_id, a.achievement_id) for a in allowed],
                        reply_markup=markup,
                        backups=await self._backups(allowed[0]),
                        art=await self._art(allowed),
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
                            name,
                            item,
                            # The row's own name wins when it has one: the
                            # localization pass above put the chat's language
                            # there (#61), while `title_name` is whatever the
                            # caller resolved once, in one language, for every
                            # chat at once.
                            item.title_name or title_name,
                            locale=chat.locale,
                            progress=progress.get(
                                (item.platform, item.title_id, item.trophy_group_id)
                            ),
                        ),
                        gallery=_gallery([item]),
                        items=[(xuid, item.title_id, item.achievement_id)],
                        reply_markup=markup,
                        backups=await self._backups(item),
                        art=await self._art([item]),
                    )
                )

    def _tell_followers(
        self, person_id: int, achievements: list[AchievementRow], title_name: str | None
    ) -> None:
        """The followers' notice is about the post itself, not any chat: it goes
        whatever the chats filter, in the background, so pushes to many devices
        never hold up publishing."""
        if self.on_new_post is None:
            return
        first = achievements[0]
        game = first.title_name or title_name or first.title_id
        # The notice names an achievement and shows its picture — never a secret one.
        shown = next((item for item in achievements if not item.is_secret), None)
        notice = self.on_new_post

        async def tell() -> None:
            try:
                await notice(
                    person_id,
                    first.platform,
                    first.title_id,
                    game,
                    len(achievements),
                    achievement=shown.name if shown else None,
                    icon=shown.icon_url if shown else None,
                )
            except Exception:
                log.exception("post notices for person_id=%s failed", person_id)

        task = asyncio.create_task(tell())
        self._notices.add(task)
        task.add_done_callback(self._notices.discard)

    async def _backups(self, item: AchievementRow) -> list[Picture]:
        """Pictures for a post whose own icon cannot be sent: that icon from
        the disk cache, then the game's cover — its file, its URL. A cover
        reveals nothing, so it is never behind a spoiler."""
        backups: list[Picture] = []
        cached = achievement_icons.find_cached_icon(
            item.platform, item.title_id, item.achievement_id
        )
        if cached is not None:
            backups.append(Picture("file", str(cached), item.is_secret))
        cover_path, cover_url = await self._repo.title_cover(item.title_id)
        if cover_path:
            backups.append(Picture("file", str(covers.cover_dir() / cover_path)))
        if cover_url:
            backups += [Picture("url", cover_url), Picture("fetch", cover_url)]
        return backups

    async def _art(self, achievements: list[AchievementRow]) -> list[Art]:
        """Each gallery picture's originals, in `_gallery`'s order."""
        art: list[Art] = []
        seen: set[str] = set()
        for item in achievements:
            if not item.icon_url or item.icon_url in seen:
                continue
            seen.add(item.icon_url)
            icon, cover = await post_picture.sources(self._repo, item)
            art.append(Art(icon, cover))
        return art

    async def _framed(self, job: PublishJob, count: int) -> list[bytes | None]:
        """The gallery's first `count` pictures, a low-resolution one enlarged
        on a square per the admin's style — None for one that goes as it is
        (high resolution, or nothing could be drawn), and nothing at all while
        the style is off."""
        style, scale = await post_picture.style_of(self._repo)
        if style == post_picture.STYLE_OFF or not job.art:
            return []
        return [
            await post_picture.build(art.icon, art.cover, style, scale) for art in job.art[:count]
        ]

    async def _apply_flood_filter(
        self, person_id: int, chat: ChatTarget, allowed: list[AchievementRow]
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
        state = await self._repo.get_flood_state(person_id, chat.chat_id)
        if (
            state is not None
            and not state.throttled
            and now >= state.window_started_at + timedelta(minutes=chat.flood_window_minutes)
        ):
            # This window is over: a fresh one starts below, same as if
            # nothing had ever run yet. A *throttled* one that is over stays
            # as it is until flood_flush.py sweeps it (within the minute):
            # starting afresh here wrote over the state the sweep looks for,
            # and what the window held back was never sent (#167). Whatever
            # arrives meanwhile is held too and goes out in the same digest.
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
            person_id,
            chat.chat_id,
            window_started_at=window_started_at,
            count_in_window=count,
            throttled=throttled,
        )
        return to_send

    async def _progress_for(
        self, achievements: list[AchievementRow], account_id: str | None = None
    ) -> dict[tuple, TitleProgress]:
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

        `account_id` is whose achievements these are, for the ordinary path
        where every row in the batch belongs to the one account `publish()`
        was called for. Rows only carry an `xuid` of their own on the
        anti-flood path, which reads them back out of the database precisely
        because it can mix accounts — and relying on that field alone is why
        the counter never appeared in a real message at all: the poller
        builds its rows from the platform response (`to_achievement_row`),
        which has no `xuid` to put there, so every lookup was skipped.

        Each answer is also filed under `(platform, title_id, group,
        account)`: the anti-flood digest can carry two PSN accounts of one
        person in the same game, and each block shows its own account's
        progress (#10). The three-part key keeps the first account's.
        """
        result: dict[tuple, TitleProgress] = {}
        for item in achievements:
            external_id = item.xuid or account_id
            if not external_id:
                continue
            for group_id in {item.trophy_group_id, None}:
                key = (item.platform, item.title_id, group_id)
                account_key = (*key, item.xuid)
                if account_key in result:
                    continue
                found = await self._repo.title_progress(
                    account_platform_of(item.platform), external_id, item.title_id, group_id
                )
                if found is not None:
                    result[account_key] = found
                    result.setdefault(key, found)
        return result

    async def publish_flood_digest(
        self, person_id: int, chat_id: int, achievements: list[AchievementRow]
    ) -> None:
        """The flush side of `_apply_flood_filter` above — called by
        poller/flood_flush.py once a throttled window closes. Unlike every
        other digest in the codebase, this one can genuinely mix platforms
        (that's the whole point: the filter counts across all of a person's
        platforms together); its header names the person as every post does.
        """
        if not achievements:
            return
        # Read here rather than carried in from flood_flush.py: this path has
        # no ChatTarget in hand (it is driven by the throttle table, not by a
        # subscription walk), and one lookup per flushed window is nothing.
        locale = await self._repo.chat_locale(chat_id)
        achievements = await localize_descriptions(self._repo, achievements, locale)
        links = await self._repo.platform_links_of(person_id)
        platforms = {account_platform_of(item.platform) for item in achievements}
        accounts = {(account_platform_of(item.platform), item.xuid) for item in achievements}
        # Two PSN accounts are one platform but not one account (#10): every
        # block names its account. The header names the person, by their
        # nickname in the app, as every post does.
        account_names: dict[str, str] = {}
        if len(accounts) > 1 and len(platforms) < len(accounts):
            for link in links:
                if any(link.external_id == xuid for _platform, xuid in accounts):
                    account_names[link.external_id] = (
                        f"{platform_label(link.platform, locale)}: {link_nickname(link)}"
                    )
        name = await self._person_label(person_id)

        missing = [a.title_id for a in achievements if not getattr(a, "game_platforms", None)]
        if missing:
            plat_map = await self._repo.title_platforms(missing)
            for a in achievements:
                if not getattr(a, "game_platforms", None) and a.title_id in plat_map:
                    a.game_platforms = plat_map[a.title_id]

        progress_map = await self._progress_for(achievements)
        game_ref: tuple[str, str] | None = None
        if len(achievements) == 1:
            item = achievements[0]
            text = format_single(
                name,
                item,
                item.title_name,
                locale=locale,
                progress=progress_map.get(
                    (item.platform, item.title_id, item.trophy_group_id, item.xuid)
                )
                or progress_map.get((item.platform, item.title_id, item.trophy_group_id)),
            )
            gallery = _gallery([item])
            game_ref = (item.platform, item.title_id)
        else:
            text = format_digest(
                name,
                None,
                achievements,
                locale=locale,
                progress=progress_map,
                account_names=account_names,
            )
            gallery = _gallery(achievements)
            # The flood digest can mix games — only link straight to one
            # when there was, in fact, only one.
            titles = {(a.platform, a.title_id) for a in achievements}
            if len(titles) == 1:
                game_ref = next(iter(titles))

        markup = await self._markup_for(chat_id, locale, person_id=person_id, game=game_ref)
        await self._queue.put(
            PublishJob(
                chat_id=chat_id,
                text=text,
                gallery=gallery,
                items=[
                    (item.xuid, item.title_id, item.achievement_id)
                    for item in achievements
                    if item.xuid
                ],
                reply_markup=markup,
                backups=await self._backups(achievements[0]),
                # One achievement is the whole gallery, else the gallery is
                # every achievement's: the same list either way.
                art=await self._art(achievements),
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
        if job.chat_id in self._unreachable:
            return
        try:
            message_id = await self._deliver(job)
        except (TelegramForbiddenError, TelegramBadRequest) as exc:
            if not chat_is_gone(exc):
                raise
            if is_test():
                # A test bot usually runs on a copy of production's database
                # and is simply not a member of those chats. Deactivating them
                # would empty the copy's chat list — and the Mini App — so it
                # just stops trying until the next start.
                log.info("chat %s is unreachable for the test bot, skipping it", job.chat_id)
                self._unreachable.add(job.chat_id)
                return
            # Kicked out of the group, or the group is gone — stop trying
            # forever (SPEC 5.5, #116).
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
        if self._bot is None:
            return None
        # The achievement matters more than the picture(s) (SPEC 7.1) — any
        # failure below falls through to plain text rather than losing the
        # achievement, same principle at every step: gallery, then a single
        # photo, then text. Every branch is an achievement notification — never
        # auto-deleted (message_cleanup.py) and never taken by /delete_last (#101).
        with achievement_category():
            # Telegram media groups (albums) do not support inline keyboards.
            # When reply_markup is attached (e.g. Mini App button), send as a single
            # photo card with the full digest text so the button is preserved.
            as_album = len(job.gallery) >= 2 and not job.reply_markup
            framed = await self._framed(job, MEDIA_GROUP_MAX if as_album else 1)
            if as_album:
                try:
                    media = [
                        InputMediaPhoto(
                            media=(
                                BufferedInputFile(framed[index], filename=f"post{index}.jpg")
                                if index < len(framed) and framed[index]
                                else url
                            ),
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
                except Exception as exc:
                    if chat_is_gone(exc):
                        raise
                    log.info(
                        "gallery for chat %s did not go through, sending photo or text",
                        job.chat_id,
                    )

            # A post always goes out, and with a picture whenever one can be
            # found at all (owner, 2026-10-07): the achievement's icon by URL
            # (Telegram fetches it), the same bytes fetched by the bot (Telegram
            # cannot always reach a platform's CDN), the icon cached on disk,
            # then the game's cover; text alone only when there is none.
            candidates: list[Picture] = []
            if job.gallery:
                url, secret = job.gallery[0]
                if framed and framed[0]:
                    candidates.append(Picture("bytes", url, secret, framed[0]))
                candidates += [Picture("url", url, secret), Picture("fetch", url, secret)]
            candidates += job.backups
            for picture in candidates:
                photo = await _photo_input(picture)
                if photo is None:
                    continue
                try:
                    message = await self._bot.send_photo(
                        job.chat_id,
                        photo=photo,
                        caption=job.text,
                        parse_mode=ParseMode.HTML,
                        has_spoiler=picture.spoiler,
                        reply_markup=job.reply_markup,
                    )
                    return message.message_id
                except (TelegramForbiddenError, TelegramRetryAfter):
                    raise
                except Exception as exc:
                    if chat_is_gone(exc):
                        raise
                    log.info(
                        "a picture for chat %s did not go through (%s): %r",
                        job.chat_id,
                        picture.how,
                        exc,
                    )
            if candidates:
                log.info("sending chat %s the text without a picture", job.chat_id)

            message = await self._bot.send_message(
                job.chat_id,
                job.text,
                parse_mode=ParseMode.HTML,
                reply_markup=job.reply_markup,
            )
            return message.message_id
