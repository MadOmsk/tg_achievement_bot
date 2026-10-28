"""Where the games database's pictures live (owner, 2026-10-28): achievement
icons, list covers, edition and HLTB covers, a game's art. `MEDIA_DIR` points
prod and the test server at one directory, so a picture one of them fetched
the other reads from disk; unset, they stay under `data/` as before. File
names never depend on the server (an achievement's ids, an address's hash)
and every write is a rename, so two bots can share it. People's pictures
(`data/avatars/`) stay each server's own.
"""

from __future__ import annotations

from pathlib import Path

from bot.services import achievement_icons, covers, game_art


def configure(media_dir: Path | None) -> None:
    if media_dir is None:
        return
    root = media_dir.resolve()
    achievement_icons.ACHIEVEMENTS_DIR = root / "achievements"
    covers.COVER_DIR = root / "covers"
    game_art.ART_DIR = root / "covers" / "art"
