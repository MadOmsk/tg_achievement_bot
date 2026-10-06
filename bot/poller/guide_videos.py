"""Video guides read from YouTube channels (services/youtube/guides.py).

A channel's whole history is read once, a few pages of 50 videos a tick
(TrophyTom has ~11 000 videos: ~220 pages, under half an hour of ticks); after that
its newest page is read every few hours, which also catches a description
edited since — a timeline is often added after upload. Each page costs one
unit of the key's 10 000 a day. No key: nothing is read.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timedelta

from bot.db.repo import GuideChannel, GuideVideoRow, Repo
from bot.services.youtube import client as youtube
from bot.services.youtube.auth import YouTubeAuth
from bot.services.youtube.guides import CHANNELS, marks_of, title_key
from bot.util import utcnow

log = logging.getLogger(__name__)

BACKFILL_PAGES_PER_TICK = 8
REFRESH_HOURS = 6


def _rows(channel_id: str, videos: list[youtube.Video]) -> list[GuideVideoRow]:
    return [
        GuideVideoRow(
            video_id=video.video_id,
            channel_id=channel_id,
            title=video.title,
            title_key=title_key(video.title),
            published_at=video.published_at,
            marks=tuple(
                (mark.label, mark.start_seconds, mark.part)
                for mark in marks_of(video.title, video.description)
            ),
        )
        for video in videos
    ]


class GuideVideos:
    def __init__(
        self,
        repo: Repo,
        auth: YouTubeAuth,
        *,
        channels: dict[str, str] | None = None,
        pages_per_tick: int = BACKFILL_PAGES_PER_TICK,
    ) -> None:
        self._repo = repo
        self._auth = auth
        self._channels = CHANNELS if channels is None else channels
        self._pages_per_tick = pages_per_tick

    async def tick(self) -> None:
        key = await self._auth.get_key()
        if key is None:
            return
        for channel_id in self._channels:
            try:
                await self._channel(key, channel_id)
            except youtube.YouTubeError as exc:
                log.warning("guide videos of channel %s: %s", channel_id, exc)
            except Exception:
                log.exception("guide videos of channel %s failed", channel_id)

    async def _channel(self, key: str, channel_id: str) -> None:
        state = await self._repo.guide_channel(channel_id) or GuideChannel(
            channel_id, None, None, False, None
        )
        if state.uploads_id is None:
            uploads = await youtube.uploads_playlist(key, channel_id)
            if uploads is None:
                log.warning("guide channel %s has no uploads playlist", channel_id)
                return
            state = replace(state, uploads_id=uploads)
            await self._repo.save_guide_channel(state)
        assert state.uploads_id is not None

        if not state.backfill_done:
            token = state.backfill_token
            for _ in range(self._pages_per_tick):
                videos, token = await youtube.playlist_page(key, state.uploads_id, token)
                await self._repo.save_guide_videos(_rows(channel_id, videos))
                # Saved page by page: a failure later resumes where it stopped.
                state = replace(
                    state,
                    backfill_token=token,
                    backfill_done=token is None,
                    checked_at=state.checked_at or utcnow().isoformat(timespec="seconds"),
                )
                await self._repo.save_guide_channel(state)
                if token is None:
                    log.info("guide channel %s read through", channel_id)
                    break
            return

        if state.checked_at and utcnow() - datetime.fromisoformat(state.checked_at) < timedelta(
            hours=REFRESH_HOURS
        ):
            return
        videos, _next = await youtube.playlist_page(key, state.uploads_id)
        await self._repo.save_guide_videos(_rows(channel_id, videos))
        await self._repo.save_guide_channel(
            replace(state, checked_at=utcnow().isoformat(timespec="seconds"))
        )
