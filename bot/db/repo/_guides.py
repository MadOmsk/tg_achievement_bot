"""Video guides from YouTube channels (migration 086): the channels' videos and
the moments their descriptions mark, matched to achievements on reading."""

from __future__ import annotations

from dataclasses import dataclass

from bot.db.repo._sql import platform_is
from bot.util import utcnow_iso


@dataclass(frozen=True, slots=True)
class GuideChannel:
    channel_id: str
    uploads_id: str | None
    backfill_token: str | None
    backfill_done: bool
    checked_at: str | None
    read_through_at: str | None = None


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
    async def guide_channel(self, channel_id: str) -> GuideChannel | None:
        cursor = await self._conn.execute(
            "SELECT channel_id, uploads_id, backfill_token, backfill_done, checked_at,"
            " read_through_at FROM guide_channels WHERE channel_id = ?",
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
            read_through_at=row["read_through_at"],
        )

    async def save_guide_channel(self, channel: GuideChannel) -> None:
        await self._conn.execute(
            "INSERT INTO guide_channels"
            " (channel_id, uploads_id, backfill_token, backfill_done, checked_at,"
            "  read_through_at)"
            " VALUES (?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (channel_id) DO UPDATE SET uploads_id = excluded.uploads_id,"
            " backfill_token = excluded.backfill_token,"
            " backfill_done = excluded.backfill_done, checked_at = excluded.checked_at,"
            " read_through_at = excluded.read_through_at",
            (
                channel.channel_id,
                channel.uploads_id,
                channel.backfill_token,
                int(channel.backfill_done),
                channel.checked_at,
                channel.read_through_at,
            ),
        )
        await self._conn.commit()

    async def save_guide_videos(self, videos: list[GuideVideoRow]) -> None:
        """A page of a channel's videos: each one's title and marks as they are
        now — a description edited since (a timeline added) replaces them."""
        now = utcnow_iso()
        # One page is one transaction (#167's rule): a video's old marks are
        # deleted before its new ones go in, and a page cut short must not
        # leave videos with none until the next pass reaches them.
        async with self.transaction():  # type: ignore[attr-defined]
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
                    "INSERT INTO guide_marks (video_id, label, start_seconds, part)"
                    " VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING",
                    [(video.video_id, label, start, part) for label, start, part in video.marks],
                )

    async def guide_moments(self, game_keys: list[str], labels: list[str]) -> list[GuideMoment]:
        """The moments named `labels` in videos of a game: a video whose title
        is one of `game_keys`, or starts with one and then " | "."""
        if not game_keys or not labels:
            return []
        game_clause = " OR ".join("v.title_key = ? OR v.title_key LIKE ?" for _ in game_keys)
        game_args: list[str] = []
        for key in game_keys:
            game_args += [key, f"{key} | %"]
        return await self._marked(labels, f" AND ({game_clause})", game_args)

    async def guide_joined_moments(self, labels: list[str]) -> list[GuideMoment]:
        """Moments whose label is one of `labels`, in any video: a title with
        no separator carries its game inside the label itself ("= game name"),
        so there is no game to ask the title for."""
        return await self._marked(labels, "", [])

    async def guide_loose_moments(
        self, game_keys: list[str], labels: list[str]
    ) -> list[GuideMoment]:
        """Moments named `labels` in videos whose title is one run of words
        starting with one of `game_keys` — "Control Resonant All Dog & Toy
        Locations (Dog's Best Friend Trophy Guide)", which has no separator
        to tell the game by. Only for marks written as loose ones."""
        if not game_keys or not labels:
            return []
        clause = " OR ".join("v.title_key LIKE ?" for _ in game_keys)
        # A title with its own separators is a game's part, not this form.
        return await self._marked(
            labels,
            f" AND v.title_key NOT LIKE '% | %' AND ({clause})",
            [f"{k} %" for k in game_keys],
        )

    async def _marked(self, labels: list[str], where: str, args: list[str]) -> list[GuideMoment]:
        moments: list[GuideMoment] = []
        # SQLite caps the variables of one statement: a game with hundreds of
        # achievements asks in pieces.
        for start in range(0, len(labels), 400):
            chunk = labels[start : start + 400]
            placeholders = ", ".join("?" * len(chunk))
            cursor = await self._conn.execute(
                "SELECT v.video_id, v.channel_id, v.title, v.published_at,"
                " m.label, m.start_seconds, m.part"
                " FROM guide_marks m JOIN guide_videos v ON v.video_id = m.video_id"
                f" WHERE m.label IN ({placeholders}){where}"
                " ORDER BY m.part, v.published_at DESC NULLS LAST, m.start_seconds",
                [*chunk, *args],
            )
            moments += [
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
        return moments

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
            f" WHERE {clause} ORDER BY published_at DESC NULLS LAST",
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

    async def title_names_of(self, platform: str, title_id: str) -> list[str]:
        """Every name a game goes by here."""
        where, params = platform_is(platform)
        cursor = await self._conn.execute(
            f"SELECT name, name_en, name_ru FROM achievement_list_connectors WHERE {where} AND "
            f"title_id = ?",
            (*params, title_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return []
        return [name for name in (row["name_en"], row["name"], row["name_ru"]) if name]
