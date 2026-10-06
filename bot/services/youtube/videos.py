"""Which guide videos show an achievement — matched on reading, so a game or
an achievement added later finds the videos already stored."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote_plus

from bot.db.repo import Repo
from bot.services.youtube.guides import CHANNELS, game_keys, key_of, video_url

# More than this per achievement is noise: the newest first.
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
    re.compile(r"\b(full walkthrough|walkthrough|trophy guide|achievement guide)\b", re.IGNORECASE),
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


async def game_guide(repo: Repo, title_id: str) -> GameGuide | None:
    """The game's guide on a guide channel, when the channel has videos of it:
    a whole-game video when one is titled so, else the channel's search for
    the game — what is matched to one achievement rarely covers them all."""
    names = await repo.title_names_of(title_id)
    videos = await repo.guide_videos_of(game_keys(*names))
    if not videos:
        return None
    channel_id = videos[0].channel_id
    channel = CHANNELS.get(channel_id, "")
    ours = [video for video in videos if video.channel_id == channel_id]
    for pattern in _WHOLE_GAME:
        for video in ours:
            # The game's own whole guide, not a one-achievement video ("🏆 Trophy Guide").
            if "🏆" not in video.title and pattern.search(video.title):
                return GameGuide(
                    url=video_url(video.video_id),
                    channel=channel,
                    count=len(ours),
                    video_id=video.video_id,
                    title=video.title,
                )
    query = quote_plus(names[0])
    return GameGuide(
        url=f"https://www.youtube.com/channel/{channel_id}/search?query={query}",
        channel=channel,
        count=len(ours),
    )


async def achievement_videos(
    repo: Repo, platform: str, title_id: str
) -> dict[str, list[AchievementVideo]]:
    """`{achievement_id: videos}` for a game's achievements that a guide video
    names exactly — in a video whose title starts with the game's name."""
    by_label: dict[str, list[str]] = {}
    for row in await repo.title_achievement_names(platform, title_id):
        # Guide videos are English: the English name, the Russian one only
        # where there is no other.
        label = key_of(row.name_en or row.name_ru or "")
        if label:
            by_label.setdefault(label, []).append(row.achievement_id)
    if not by_label:
        return {}
    keys = game_keys(*await repo.title_names_of(title_id))
    moments = await repo.guide_moments(keys, list(by_label))
    found: dict[str, list[AchievementVideo]] = {}
    for moment in moments:
        video = AchievementVideo(
            video_id=moment.video_id,
            title=moment.title,
            channel=CHANNELS.get(moment.channel_id, ""),
            start_seconds=moment.start_seconds,
            part=moment.part,
        )
        for achievement_id in by_label.get(moment.label, []):
            shown = found.setdefault(achievement_id, [])
            if len(shown) < VIDEOS_PER_ACHIEVEMENT and all(
                (v.video_id, v.start_seconds) != (video.video_id, video.start_seconds)
                for v in shown
            ):
                shown.append(video)
    return found
