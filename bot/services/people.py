"""Who may see whom (#157): the one rule behind every screen that shows a person's
activity. Pure — `db/repo/_follows.py` feeds it the facts."""

from __future__ import annotations

from dataclasses import dataclass

ACTIVITY_ALL = "all"
ACTIVITY_FRIENDS = "friends"
ACTIVITY_NOBODY = "nobody"
ACTIVITY_CHOICES = (ACTIVITY_ALL, ACTIVITY_FRIENDS, ACTIVITY_NOBODY)

SEARCH_MIN = 3
SEARCH_LIMIT = 20


@dataclass(frozen=True, slots=True)
class Relation:
    """What one person is to another, from the first one's side."""

    following: bool = False  # I follow them
    followed_by: bool = False  # they follow me
    blocked: bool = False  # I blocked them
    blocked_by: bool = False  # they blocked me

    @property
    def friends(self) -> bool:
        return self.following and self.followed_by


def can_view(setting: str, relation: Relation, *, self_view: bool = False) -> bool:
    """May the viewer see the target's activity? A block cuts it either way, then
    the target's own setting decides. Looking at oneself is always allowed. The
    nickname and avatar are not activity: they stay visible whatever this says."""
    if self_view:
        return True
    if relation.blocked or relation.blocked_by:
        return False
    if setting == ACTIVITY_ALL:
        return True
    if setting == ACTIVITY_FRIENDS:
        return relation.friends
    return False
