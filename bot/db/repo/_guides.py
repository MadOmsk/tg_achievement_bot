"""Video guides from YouTube channels (migration 086): the channels' videos and
the moments their descriptions mark, matched to achievements on reading."""

from __future__ import annotations

from dataclasses import dataclass

import aiosqlite

from bot.util import utcnow_iso


@dataclass(frozen=True, slots=True)
class GuideChannel:
    channel_id: str
    uploads_id: str | None
    backfill_token: str | None
    backfill_done: bool
    checked_at: str | None


@dataclass(frozen=True, slots=True)
class GuideVideoRow:
    video_id: str
    channel_id: str
    title: str
    title_key: str
    published_at: str | None
    # (label, start_seconds, part)
    marks: tuple[tuple[str, int, int], ...]


@dataclass(frozen=True, slots=True)
class GuideMoment:
    video_id: str
    channel_id: str
    title: str
    published_at: str | None
    label: str
    start_seconds: int
    part: int


class _GuidesRepo:
    _conn: aiosqlite.Connection

    async def guide_channel(self, channel_id: str) -> GuideChannel | None:
        cursor = await self._conn.execute(
            "SELECT channel_id, uploads_id, backfill_token, backfill_done, checked_at"
            " FROM guide_channels WHERE channel_id = ?",
            (channel_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return GuideChannel(
            channel_id=row["channel_id"],
            uploads_id=row["uploads_id"],
            backfill_token=row["backfill_token"],
            backfill_done=bool(row["backfill_done"]),
            checked_at=row["checked_at"],
        )

    async def save_guide_channel(self, channel: GuideChannel) -> None:
        await self._conn.execute(
            "INSERT INTO guide_channels"
            " (channel_id, uploads_id, backfill_token, backfill_done, checked_at)"
            " VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT (channel_id) DO UPDATE SET uploads_id = excluded.uploads_id,"
            " backfill_token = excluded.backfill_token,"
            " backfill_done = excluded.backfill_done, checked_at = excluded.checked_at",
            (
                channel.channel_id,
                channel.uploads_id,
                channel.backfill_token,
                int(channel.backfill_done),
                channel.checked_at,
            ),
        )
        await self._conn.commit()

    async def save_guide_videos(self, videos: list[GuideVideoRow]) -> None:
        """A page of a channel's videos: each one's title and marks as they are
        now — a description edited since (a timeline added) replaces them."""
        now = utcnow_iso()
        for video in videos:
            await self._conn.execute(
                "INSERT INTO guide_videos"
                " (video_id, channel_id, title, title_key, published_at, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)"
                " ON CONFLICT (video_id) DO UPDATE SET title = excluded.title,"
                " title_key = excluded.title_key, published_at = excluded.published_at",
                (
                    video.video_id,
                    video.channel_id,
                    video.title,
                    video.title_key,
                    video.published_at,
                    now,
                ),
            )
            await self._conn.execute(
                "DELETE FROM guide_marks WHERE video_id = ?", (video.video_id,)
            )
            await self._conn.executemany(
                "INSERT OR IGNORE INTO guide_marks (video_id, label, start_seconds, part)"
                " VALUES (?, ?, ?, ?)",
                [(video.video_id, label, start, part) for label, start, part in video.marks],
            )
        await self._conn.commit()

    async def guide_moments(self, game_keys: list[str], labels: list[str]) -> list[GuideMoment]:
        """The moments named `labels` in videos of a game: a video whose title
        is one of `game_keys`, or starts with one and then " | "."""
        if not game_keys or not labels:
            return []
        game_clause = " OR ".join("v.title_key = ? OR v.title_key LIKE ?" for _ in game_keys)
        game_args: list[str] = []
        for key in game_keys:
            game_args += [key, f"{key} | %"]
        placeholders = ", ".join("?" * len(labels))
        cursor = await self._conn.execute(
            "SELECT v.video_id, v.channel_id, v.title, v.published_at,"
            " m.label, m.start_seconds, m.part"
            " FROM guide_marks m JOIN guide_videos v ON v.video_id = m.video_id"
            f" WHERE m.label IN ({placeholders}) AND ({game_clause})"
            " ORDER BY m.part, v.published_at DESC, m.start_seconds",
            [*labels, *game_args],
        )
        return [
            GuideMoment(
                video_id=row["video_id"],
                channel_id=row["channel_id"],
                title=row["title"],
                published_at=row["published_at"],
                label=row["label"],
                start_seconds=int(row["start_seconds"]),
                part=int(row["part"]),
            )
            for row in await cursor.fetchall()
        ]

    async def guide_videos_of(self, game_keys: list[str]) -> list[GuideMoment]:
        """Every video of a game (its title starts with one of `game_keys`),
        newest first, as a moment at its start."""
        if not game_keys:
            return []
        clause = " OR ".join("title_key = ? OR title_key LIKE ?" for _ in game_keys)
        args: list[str] = []
        for key in game_keys:
            args += [key, f"{key} | %"]
        cursor = await self._conn.execute(
            "SELECT video_id, channel_id, title, published_at FROM guide_videos"
            f" WHERE {clause} ORDER BY published_at DESC",
            args,
        )
        return [
            GuideMoment(
                video_id=row["video_id"],
                channel_id=row["channel_id"],
                title=row["title"],
                published_at=row["published_at"],
                label="",
                start_seconds=0,
                part=0,
            )
            for row in await cursor.fetchall()
        ]

    async def title_names_of(self, title_id: str) -> list[str]:
        """Every name a game goes by here."""
        cursor = await self._conn.execute(
            "SELECT name, name_en, name_ru FROM titles WHERE title_id = ?", (title_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return []
        return [name for name in (row["name_en"], row["name"], row["name_ru"]) if name]
