"""Parsing of Xbox Live achievement responses (SPEC 4).

Three shapes arrive here and become one:

  contract 4 — a modern title, the only one that carries `rarity`;
  contract 2 — the whole library, used for backfill only (no rarity needed);
  contract 1 — Xbox 360, a completely different payload with no rarity at all.

Every block below is optional on purpose. Microsoft ships achievements without
`rarity`, without `rewards` and with an empty `mediaAssets`, and a missing block
must never cost us the achievement itself.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from bot.constants import (
    Platform,
    XboxApiValue,
)
from bot.services.models import ParsedAchievement

__all__ = [
    "ModernAchievement",
    "ParsedAchievement",
    "Platform",
    "X360Achievement",
    "continuation_token",
    "parse_achievements",
    "parse_rarity",
    "parse_rarity_with_title",
    "parse_timestamp",
    "x360_achievement_icon_url",
]

# "2025-08-30T09:17:58.7770000Z" — seven fractional digits, which
# datetime.fromisoformat refuses. Cut them down to six.
_FRACTION = re.compile(r"\.(\d{1,6})\d*")

# Microsoft has two "no date" markers: the zero date 0001-01-01 and 1753-01-01,
# the old SQL Server minimum (84 of 5239 rows on a live account). Xbox Live did
# not exist before 2005, so anything older than that is a placeholder, not a
# date — statistics must not count it as an unlock in the year 1753.
_EARLIEST_REAL_UNLOCK = datetime(2005, 1, 1, tzinfo=UTC)


class _Rarity(BaseModel):
    model_config = ConfigDict(extra="ignore")
    current_percentage: float | None = Field(default=None, alias="currentPercentage")


class _Progression(BaseModel):
    model_config = ConfigDict(extra="ignore")
    time_unlocked: str | None = Field(default=None, alias="timeUnlocked")


class _MediaAsset(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: str | None = None
    url: str | None = None


class _Reward(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: str | None = None
    value: str | int | None = None


class _TitleAssociation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: int | str | None = None
    name: str | None = None


class ModernAchievement(BaseModel):
    """Contract 4 (and contract 2, which is the same minus `rarity`)."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str | int
    name: str = ""
    description: str | None = None
    progress_state: str | None = Field(default=None, alias="progressState")
    progression: _Progression | None = None
    rarity: _Rarity | None = None
    rewards: list[_Reward] = Field(default_factory=list)
    media_assets: list[_MediaAsset] = Field(default_factory=list, alias="mediaAssets")
    title_associations: list[_TitleAssociation] = Field(
        default_factory=list, alias="titleAssociations"
    )
    is_secret: bool = Field(default=False, alias="isSecret")

    @property
    def is_achieved(self) -> bool:
        """Only 'Achieved' counts (SPEC 5.3).

        Writing an InProgress row into seen_achievements would hide the
        achievement from publication forever.
        """
        return self.progress_state == XboxApiValue.ACHIEVED

    def to_parsed(self, fallback_title_id: str | None = None) -> ParsedAchievement:
        association = self.title_associations[0] if self.title_associations else None
        title_id = str(association.id) if association and association.id else fallback_title_id
        return ParsedAchievement(
            achievement_id=str(self.id),
            title_id=title_id or "",
            title_name=association.name if association else None,
            name=self.name,
            description=self.description,
            icon_url=self._icon_url(),
            unlocked_at=parse_timestamp(
                self.progression.time_unlocked if self.progression else None
            ),
            gamerscore=self._gamerscore(),
            rarity_percent=self.rarity.current_percentage if self.rarity else None,
            platform=Platform.XBOX_MODERN,
            is_secret=self.is_secret,
        )

    def _icon_url(self) -> str | None:
        for asset in self.media_assets:
            if asset.type == XboxApiValue.ICON and asset.url:
                return asset.url
        return None

    def _gamerscore(self) -> int:
        for reward in self.rewards:
            if reward.type == XboxApiValue.GAMERSCORE and reward.value is not None:
                try:
                    return int(reward.value)
                except (TypeError, ValueError):
                    return 0
        return 0


def x360_achievement_icon_url(title_id: str | int | None, image_id: str | int | None) -> str | None:
    """Return the Xbox Live CDN URL for an Xbox 360 achievement icon.

    Xbox 360 games store image assets under Microsoft's Akamai CDN path:
    http://image.xboxlive.com/global/t.{title_hex}/ach/0/{image_hex}
    where title_hex is an 8-character hex string and image_hex is lowercase hex.
    """
    if not title_id or image_id is None:
        return None
    try:
        title_hex = f"{int(title_id):08x}"
        image_hex = f"{int(image_id):x}"
        return f"http://image.xboxlive.com/global/t.{title_hex}/ach/0/{image_hex}"
    except (ValueError, TypeError):
        return None


class X360Achievement(BaseModel):
    """Contract 1 and Contract 3.

    Contract 1 was the legacy Xbox 360 achievement response (no rarity, no secret).
    Contract 3 (accessed via /titleachievements) brings modern parity to Xbox 360:
    it adds rarity, isSecret, description, and carries imageId.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str | int
    name: str = ""
    description: str | None = None
    gamerscore: int = 0
    unlocked: bool = False
    time_unlocked: str | None = Field(default=None, alias="timeUnlocked")
    title_id: int | str | None = Field(default=None, alias="titleId")
    image_id: int | str | None = Field(default=None, alias="imageId")
    rarity: _Rarity | None = None
    is_secret: bool = Field(default=False, alias="isSecret")

    @property
    def is_achieved(self) -> bool:
        return self.unlocked

    def to_parsed(self, fallback_title_id: str | None = None) -> ParsedAchievement:
        tid = str(self.title_id) if self.title_id else (fallback_title_id or "")
        return ParsedAchievement(
            achievement_id=str(self.id),
            title_id=tid,
            title_name=None,  # x360 payload does not carry title name
            name=self.name,
            description=self.description,
            icon_url=x360_achievement_icon_url(tid, self.image_id),
            unlocked_at=parse_timestamp(self.time_unlocked),
            gamerscore=self.gamerscore,
            rarity_percent=self.rarity.current_percentage if self.rarity else None,
            platform=Platform.XBOX_360,
            is_secret=self.is_secret,
        )


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    text = _FRACTION.sub(lambda m: "." + m.group(1), value.replace("Z", "+00:00"))
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return None if parsed < _EARLIEST_REAL_UNLOCK else parsed


def parse_achievements(
    payload: dict[str, Any],
    platform: Platform,
    title_id: str | None = None,
    *,
    earned_only: bool = True,
) -> list[ParsedAchievement]:
    """Turn a raw response into parsed achievements.
    When earned_only is True (default), keeps unlocked achievements only.

    Anything that fails to parse is skipped rather than raising: one malformed
    record must not cost a user his whole session.
    """
    model = X360Achievement if platform == Platform.XBOX_360 else ModernAchievement
    result: list[ParsedAchievement] = []
    for item in payload.get("achievements") or []:
        try:
            achievement = model.model_validate(item)
        except Exception:
            continue
        if not earned_only or achievement.is_achieved:
            result.append(achievement.to_parsed(title_id))
    return result


def parse_rarity_with_title(payload: dict[str, Any]) -> tuple[dict[str, float], str | None]:
    """Every achievement's rarity and the title's name in one contract-4 or contract-3 response.

    Contract 4 includes titleAssociations on each achievement item, which
    carries the human-readable game title. This allows learning title names
    during rarity caching without extra requests (#77).
    Contract 3 (/titleachievements for Xbox 360) carries rarity without titleAssociations.
    """
    result: dict[str, float] = {}
    title_name: str | None = None
    for item in payload.get("achievements") or []:
        if "titleAssociations" in item:
            try:
                achievement = ModernAchievement.model_validate(item)
                if title_name is None and achievement.title_associations:
                    assoc = achievement.title_associations[0]
                    if assoc and assoc.name:
                        title_name = assoc.name
                if (
                    achievement.rarity is not None
                    and achievement.rarity.current_percentage is not None
                ):
                    result[str(achievement.id)] = float(achievement.rarity.current_percentage)
                continue
            except Exception:
                pass
        try:
            x360_ach = X360Achievement.model_validate(item)
            if x360_ach.rarity is not None and x360_ach.rarity.current_percentage is not None:
                result[str(x360_ach.id)] = float(x360_ach.rarity.current_percentage)
        except Exception:
            continue
    return result, title_name


def parse_rarity(payload: dict[str, Any]) -> dict[str, float]:
    """Every achievement's rarity in one title's response, earned or not.

    The one thing in a contract-4 reply that is about the *achievement*
    rather than about the caller — the share of all players who have it — so
    unlike `parse_achievements` above this keeps the locked ones too. One
    person's request therefore fills the shared cache for everybody who owns
    the game (see db/repo/_descriptions.py::cache_rarity).

    Contract 2 and contract 1 carry no rarity at all, which needs no check
    here: their achievements simply have no `rarity` block and fall out.
    """
    rarity, _ = parse_rarity_with_title(payload)
    return rarity


def continuation_token(payload: dict[str, Any]) -> str | None:
    paging = payload.get("pagingInfo") or {}
    token = paging.get("continuationToken")
    return str(token) if token else None
