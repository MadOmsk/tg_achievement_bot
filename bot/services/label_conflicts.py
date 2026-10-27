"""Labels that contradict each other (#218 step 5): checked whenever a label
is written, shown to the operator as cards. No database access.

Two kinds:

- **apart in a group**: a label keeping two versions apart (another game, a
  remaster, …) while labels that join versions into one game link them
  anyway, however indirectly;
- **relations disagree**: two labels between the same two groups of joined
  versions that say different things — a remaster and a remake, a relation
  and "another game", or one relation pointing both ways.

A fit learns nothing from two labels that cancel out, and the linker obeys
one of them at random; the operator settles which stands.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from bot.services.game_link import JOINING, NOT_RELATED

Label = tuple[int, int, str]  # (version_id, other_id, relation)


@dataclass(frozen=True, slots=True)
class Conflict:
    kind: str  # "apart_in_group" | "relations_disagree"
    label: Label  # the label that disagrees
    against: tuple[Label, ...]  # what it disagrees with: a chain, or one label

    def versions(self) -> set[int]:
        return {v for lab in (self.label, *self.against) for v in lab[:2]}


def _labels(rows: Iterable[Mapping[str, Any]]) -> list[Label]:
    return [(int(r["version_id"]), int(r["other_id"]), str(r["relation"])) for r in rows]


def conflicts(rows: Iterable[Mapping[str, Any]]) -> list[Conflict]:
    """Every contradiction among these labels (`match_decisions` rows)."""
    labels = _labels(rows)
    joined: dict[int, list[Label]] = {}
    for lab in labels:
        if lab[2] in JOINING:
            joined.setdefault(lab[0], []).append(lab)
            joined.setdefault(lab[1], []).append(lab)

    def path(a: int, b: int) -> tuple[Label, ...] | None:
        """The joining labels from `a` to `b`, shortest first found."""
        came: dict[int, Label | None] = {a: None}
        queue = deque([a])
        while queue:
            v = queue.popleft()
            if v == b:
                chain: list[Label] = []
                while (step := came[v]) is not None:
                    chain.append(step)
                    v = step[0] if step[1] == v else step[1]
                return tuple(reversed(chain))
            for lab in joined.get(v, ()):
                w = lab[1] if lab[0] == v else lab[0]
                if w not in came:
                    came[w] = lab
                    queue.append(w)
        return None

    group: dict[int, int] = {}
    for start in joined:
        if start in group:
            continue
        queue = deque([start])
        group[start] = start
        while queue:
            v = queue.popleft()
            for lab in joined[v]:
                w = lab[1] if lab[0] == v else lab[0]
                if w not in group:
                    group[w] = start
                    queue.append(w)

    found: list[Conflict] = []
    between: dict[frozenset[int], list[tuple[Label, int]]] = {}
    for lab in labels:
        if lab[2] in JOINING:
            continue
        a, b = (group.get(v, -v) for v in lab[:2])
        if a == b:
            chain = path(lab[0], lab[1])
            if chain:
                found.append(Conflict("apart_in_group", lab, chain))
            continue
        between.setdefault(frozenset((a, b)), []).append((lab, a))
    for said in between.values():
        first, first_from = said[0]
        for lab, origin in said[1:]:
            if _disagree(first, first_from, lab, origin):
                found.append(Conflict("relations_disagree", lab, (first,)))
    return found


def _disagree(x: Label, x_from: int, y: Label, y_from: int) -> bool:
    """Two labels between one pair of groups that cannot both hold."""
    if x[2] in NOT_RELATED and y[2] in NOT_RELATED:
        return False
    if x[2] != y[2]:
        return True
    return x_from != y_from  # one relation, pointing both ways


def around(found: Iterable[Conflict], version_ids: Iterable[int]) -> list[Conflict]:
    """The contradictions touching any of these versions."""
    ids = set(version_ids)
    return [c for c in found if c.versions() & ids]
