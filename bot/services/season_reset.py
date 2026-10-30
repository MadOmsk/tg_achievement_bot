"""TEMPORARY (owner, 2026-10-30) — delete this file, its poller
(`poller/season_reset.py`), the repo's `wipe_pass_before` and their wiring in
`main.py` / `scheduler.py` once the second season has started and this has run.

The first season (October 2026) was a trial: its themes, its prizes and what
each person got of them go, once, as the second season starts — the pass
begins empty and is built again by the super-admin (`ensure_pass_seeded` has
already run, so the five themes are not written again). Only a pass of an
earlier month goes; the second season's own levels, built ahead as drafts, and
whatever was claimed in it, stay.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from bot.util import utcnow

if TYPE_CHECKING:
    from bot.db.repo import Repo

log = logging.getLogger(__name__)

SECOND_SEASON = "2026-11"
MARKER = "season2_reset_done"


async def reset_for_second_season(repo: Repo, *, now_month: str | None = None) -> bool:
    """Wipe the first season's passes once the second season has started;
    True when it did."""
    if await repo.get_app_setting(MARKER):
        return False
    month = now_month or utcnow().strftime("%Y-%m")
    if month < SECOND_SEASON:
        return False
    gone = await repo.wipe_pass_before(SECOND_SEASON, MARKER)
    log.warning("second season began: the first season's pass wiped %s", gone)
    return True
