"""What each store says about a game (#147, stage 2): one module per source,
network and parsing only — nothing here touches the database
(`services/store_collect.py` stores what they return).

A version is a store product on one console (owner, 2026-10-08): PS4 and PS5,
One and Series are two versions even when they share one achievement list;
Xbox Play Anywhere's PC is a platform of the console version (`also_on`),
never a version of its own. Consoles are `services/platform_format.py`'s
canonical names, plus `steam` for a Steam app.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class StoreDlc:
    store_id: str
    name: str | None = None
    kind: str | None = None  # dlc / expansion / season_pass / soundtrack / other
    release_date: str | None = None
    description_en: str | None = None
    image_url: str | None = None
    # Whether its store offers it now (see `StoreVersion.on_sale`).
    on_sale: bool | None = None


@dataclass(slots=True)
class StoreVersion:
    store: str  # steam / xbox / psn
    product_id: str
    console: str
    name: str | None = None
    name_ru: str | None = None
    kind: str | None = None  # game / demo / dlc / bundle / app
    developer: str | None = None
    publisher: str | None = None
    release_date: str | None = None  # ISO day
    genres: list[str] = field(default_factory=list)
    also_on: list[str] = field(default_factory=list)
    store_group: str | None = None
    # Xbox's cross-gen set: the same game on One and Series.
    cross_gen_set: str | None = None
    description_en: str | None = None
    description_ru: str | None = None
    media: dict[str, object] = field(default_factory=dict)
    live_service: bool = False
    # Made from our own list when no store described it (the store is the platform's).
    stand_in: bool = False
    # Whether its store offers the full product now, to buy or to download
    # free (owner, 2026-10-12): True available, False off sale (the store
    # knows it and offers nothing but a trial, or nothing), None unknown (not
    # asked, no store page: a stand-in). Pre-orders count as available. Each
    # store module's own rule; prices take no part.
    on_sale: bool | None = None
    # Every id that names this version: (kind, id), e.g. ("psn_title", "CUSA00527_00").
    store_ids: list[tuple[str, str]] = field(default_factory=list)
    # The ids of its add-ons, as the store lists them; named separately.
    dlc_ids: list[str] = field(default_factory=list)
    dlcs: list[StoreDlc] = field(default_factory=list)


# How a console is said wherever a version is shown (owner, 2026-10-12): the
# Microsoft Store's PC is "xbox pc", never to be taken for Steam. The stored
# value (`versions.console = 'pc'`) and the matcher's maps keep "pc".
CONSOLE_LABELS = {"pc": "xbox pc"}


def console_label(console: str | None) -> str:
    """A version's console as shown: `pc` (only ever the Microsoft Store's —
    a Steam app's console is `steam`) reads "xbox pc"."""
    text = str(console or "")
    return CONSOLE_LABELS.get(text, text)


_EDITION_KINDS = (
    ("preorder", ("pre-order", "preorder", "pre order")),
    ("goty", ("game of the year", "goty", "g.o.t.y")),
    ("anniversary", ("anniversary",)),
    ("ultimate", ("ultimate",)),
    ("premium", ("premium",)),
    ("deluxe", ("deluxe",)),
    ("gold", ("gold",)),
    ("legendary", ("legendary",)),
    ("complete", ("complete",)),
    ("definitive", ("definitive",)),
    # A pack of the game and its add-ons sold under its own name ("Cyberpunk
    # 2077 & Phantom Liberty Bundle"), or several games ("… Collection").
    ("bundle", ("bundle", " & ", " + ")),
    ("collection", ("collection", "trilogy", "anthology")),
)


def without_keys(payload: object, keys: frozenset[str]) -> object:
    """The payload with these keys dropped wherever they are, a copy.

    Prices are not ours to keep (owner, 2026-10-12): they change daily and by
    region, and kept in a raw answer a price change reads as "the game
    changed", which sets its source's schedule back to a week. Each store
    module drops its own price fields before an answer is parsed or stored,
    so a collection and a re-reading of what is stored see the same thing."""
    if isinstance(payload, dict):
        return {k: without_keys(v, keys) for k, v in payload.items() if k not in keys}
    if isinstance(payload, list):
        return [without_keys(v, keys) for v in payload]
    return payload


def edition_kind(name: str | None) -> str:
    """What kind of edition a store's name says it is (`standard` when it says
    none); a pre-order says so first, as it is the one that vanishes."""
    lowered = (name or "").lower()
    for kind, words in _EDITION_KINDS:
        if any(word in lowered for word in words):
            return kind
    return "standard"
