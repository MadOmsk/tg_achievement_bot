"""`ParsedAchievement` → `AchievementRow` (2026-09-05 refactor; moved here
from bot/poller/rows.py 2026-09-08).

Was duplicated byte-for-byte in fetcher.py and steam_fetcher.py, then lived
in the poller layer as the one place that turned a parsed platform response
into a database row. It now also has a caller *inside* the service layer:
services/psn/achievements.py persists trophies as it scans them (#26),
rather than handing a list back to the poller to convert and write. Both
pollers and that service need the same pure `ParsedAchievement ->
AchievementRow` map, so it sits in `bot.services` — a layer both the poller
and other services can import from without an upward dependency.
"""

from __future__ import annotations

from bot.db.repo import AchievementRow
from bot.services.models import ParsedAchievement


def to_achievement_row(item: ParsedAchievement) -> AchievementRow:
    return AchievementRow(
        title_id=item.title_id,
        achievement_id=item.achievement_id,
        name=item.name,
        description=item.description,
        icon_url=item.icon_url,
        unlocked_at=item.unlocked_at.isoformat(timespec="seconds") if item.unlocked_at else None,
        gamerscore=item.gamerscore,
        rarity_percent=item.rarity_percent,
        platform=item.platform,
        title_name=item.title_name,
        is_secret=item.is_secret,
        trophy_type=item.trophy_type,
    )
