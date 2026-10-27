"""The season pass (owner, 2026-10-27): a month's points climb its levels, and
each level reached gives one of the Mini App's themes to claim. Violet is
everybody's. The server is the judge: a claim needs the points, and only the
themes claimed are given back as open. Every month runs the same levels."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_PALETTE = "violet"


@dataclass(frozen=True)
class Tier:
    level: int
    points: int
    tier: str
    palette: str


# The calmest first, the most colourful last.
TIERS: tuple[Tier, ...] = (
    Tier(1, 150, "common", "graphite"),
    Tier(2, 400, "rare", "ocean"),
    Tier(3, 700, "rare", "mint"),
    Tier(4, 1100, "legendary", "ember"),
    Tier(5, 1600, "mythic", "rose"),
)


def tier_of(palette: str) -> Tier | None:
    return next((t for t in TIERS if t.palette == palette), None)
