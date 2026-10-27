"""Which guide videos show an achievement — matched on reading, so a game or
an achievement added later finds the videos already stored."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote_plus

from bot.db.repo import GuideMoment, Repo
from bot.services.youtube.guides import (
    CHANNELS,
    JOINED,
    LOOSE,
    game_keys,
    key_of,
    title_mark,
    video_url,
)

# More than this per achievement is noise: the newest first, and from different
# channels before the same one twice.
VIDEOS_PER_ACHIEVEMENT = 3


@dataclass(frozen=True, slots=True)
class AchievementVideo:
    video_id: str
    title: str
    channel: str
    start_seconds: int
    part: int


# A whole game's guide, by its title: the best first.
_WHOLE_GAME = [
    re.compile(r"\b(full game|all (trophies|achievements)|100\s?%)", re.IGNORECASE),
    re.compile(
        r"\b(full walkthrough|walkthrough|trophy guide|achievement guide|roadmap)\b", re.IGNORECASE
    ),
]


@dataclass(frozen=True, slots=True)
class GameGuide:
    """Where the game's guides are: its whole-game video, or the channel's
    videos about it."""

    url: str
    channel: str
    count: int
    video_id: str | None = None
    title: str | None = None


async def game_guide(repo: Repo, platform: str, title_id: str) -> GameGuide | None:
    """The game's guide on a guide channel, when a channel has videos of it:
    a whole-game video when one is titled so, else the channel with most
    videos of it, as a search — what is matched to one achievement rarely
    covers them all."""
    names = await repo.title_names_of(platform, title_id)
    videos = await repo.guide_videos_of(game_keys(*names))
    if not videos:
        return None
    for pattern in _WHOLE_GAME:
        for video in videos:
            # The game's own whole guide, not a video of one achievement
            # ("<name> Trophy Guide"): those name one.
            if title_mark(video.title) is None and "🏆" not in video.title:
                if pattern.search(video.title):
                    return GameGuide(
                        url=video_url(video.video_id),
                        channel=CHANNELS.get(video.channel_id, ""),
                        count=len(videos),
                        video_id=video.video_id,
                        title=video.title,
                    )
    per_channel: dict[str, int] = {}
    for video in videos:
        per_channel[video.channel_id] = per_channel.get(video.channel_id, 0) + 1
    channel_id = max(per_channel, key=lambda c: per_channel[c])
    query = quote_plus(names[0])
    return GameGuide(
        url=f"https://www.youtube.com/channel/{channel_id}/search?query={query}",
        channel=CHANNELS.get(channel_id, ""),
        count=len(videos),
    )


def _spread(moments: list[GuideMoment]) -> list[GuideMoment]:
    """The moments with one from each channel first, then the rest, each
    group in the order it came (the part, then the newest)."""
    seen: dict[str, int] = {}
    keyed = []
    for index, moment in enumerate(moments):
        turn = seen.get(moment.channel_id, 0)
        seen[moment.channel_id] = turn + 1
        keyed.append((turn, index, moment))
    keyed.sort(key=lambda item: (item[0], item[1]))
    return [moment for _turn, _index, moment in keyed]


async def achievement_videos(
    repo: Repo, platform: str, title_id: str
) -> dict[str, list[AchievementVideo]]:
    """`{achievement_id: videos}` for a game's achievements that a guide video
    names exactly — in a video whose title starts with the game's name, or
    (a title with no separators) one that carries the game's name in front of
    the achievement's."""
    by_label: dict[str, list[str]] = {}
    for row in await repo.title_achievement_names(platform, title_id):
        # Guide videos are English: the English name, the Russian one only
        # where there is no other.
        label = key_of(row.name_en or row.name_ru or "")
        if label:
            by_label.setdefault(label, []).append(row.achievement_id)
    if not by_label:
        return {}
    keys = game_keys(*await repo.title_names_of(platform, title_id))
    # Which achievements a stored label stands for, by the way it was marked.
    standing: dict[str, list[str]] = dict(by_label)
    joined: dict[str, list[str]] = {}
    for key in keys:
        if " | " in key:
            continue
        for label, ids in by_label.items():
            joined[f"{JOINED}{key} {label}"] = ids
    moments = await repo.guide_moments(keys, list(by_label))
    moments += await repo.guide_joined_moments(list(joined))
    standing.update(joined)
    loose = {f"{LOOSE}{label}": ids for label, ids in by_label.items()}
    moments += await repo.guide_loose_moments(
        [key for key in keys if " | " not in key], list(loose)
    )
    standing.update(loose)

    # The three queries each came ordered; together they are put in one order:
    # the part, then the newest, then the moment in a video.
    moments.sort(key=lambda m: m.start_seconds)
    moments.sort(key=lambda m: m.published_at or "", reverse=True)
    moments.sort(key=lambda m: m.part)

    found: dict[str, list[AchievementVideo]] = {}
    for moment in _spread(moments):
        video = AchievementVideo(
            video_id=moment.video_id,
            title=moment.title,
            channel=CHANNELS.get(moment.channel_id, ""),
            start_seconds=moment.start_seconds,
            part=moment.part,
        )
        for achievement_id in standing.get(moment.label, []):
            shown = found.setdefault(achievement_id, [])
            if len(shown) < VIDEOS_PER_ACHIEVEMENT and all(
                (v.video_id, v.start_seconds) != (video.video_id, video.start_seconds)
                for v in shown
            ):
                shown.append(video)
    return found
