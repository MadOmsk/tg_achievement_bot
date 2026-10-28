"""The season pass (owner, 2026-10-27): a month's points climb its levels, each
a theme of the app or a prize of the super-admin's, claimed by a tap. The
server is the judge: a claim needs the points. The levels are the
super-admin's to edit in the Mini App — a draft, then one publish; nothing
anybody claimed is changed. Violet is everybody's. Every month has a pass of
its own (owner, 2026-10-28): empty until published, the next one built ahead,
the earlier ones kept to look back on; a theme once claimed is kept for good."""

from __future__ import annotations

DEFAULT_PALETTE = "violet"
# The themes a level can give: every palette but the one everybody has.
PALETTES = ("graphite", "ocean", "mint", "ember", "rose", "halloween")
# A theme level's look on the timeline.
LOOKS = ("common", "rare", "legendary", "mythic")
KINDS = ("theme", "game", "code")

# The first pass's levels, written once (`repo.ensure_pass_seeded`): the
# calmest theme first, the most colourful last.
DEFAULT_THEMES: tuple[tuple[str, str, int], ...] = (
    ("graphite", "common", 150),
    ("ocean", "rare", 400),
    ("mint", "rare", 700),
    ("ember", "legendary", 1100),
    ("rose", "mythic", 1600),
)
