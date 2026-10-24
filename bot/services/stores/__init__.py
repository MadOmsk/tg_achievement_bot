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

import json
from dataclasses import dataclass, field

# A PC version is told apart by its store (owner, 2026-10-12): Microsoft's
# (`xbox` on console `pc`), Steam's, later the Epic Games Store's (`egs`) or
# GOG's (`gog`) — each one more value of `versions.store`, no schema change.
# A source that says only "PC" gives a PC version whose store is unknown:
# an Xbox list played on `Win32` alone is the Xbox app seeing a PC game
# launched from another store (Steam, Epic) — never a Microsoft product.
UNKNOWN_STORE = "unknown"
WIN32 = "Win32"


def pc_of_unknown_store(platform: str | None, platforms_raw: str | None) -> bool:
    """An Xbox achievement list whose platforms are `Win32` alone: the PC
    game seen by the Xbox app, from a store it does not name."""
    if platform != "xbox_modern" or not platforms_raw:
        return False
    try:
        platforms = json.loads(platforms_raw)
    except ValueError:
        return False
    return platforms == [WIN32]


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
    store: str  # steam / xbox / psn / unknown (a PC game's store not known)
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


# How a PC version is said, by its store (owner, 2026-10-12): PC versions are
# told apart by where they are sold — the Microsoft Store's "xbox pc", Steam's
# "steam" (its console is `steam`), later the Epic Games Store's, GOG's. A new
# store is one line here. A PC version of no known store (an Xbox `Win32`
# list of a game bought elsewhere, HLTB's plain "PC") is "pc (store
# unknown)". The stored value (`versions.console = 'pc'`) and the matcher's
# maps keep "pc".
PC_LABELS = {"xbox": "xbox pc", "egs": "egs pc", "gog": "gog pc"}
PC_UNKNOWN = "pc (store unknown)"


def store_of(platform: str, platforms: str | None = None) -> str:
    """The store a stand-in stands under: its platform's, but a PC list of
    an unknown store (Win32 alone) is no Microsoft product."""
    if pc_of_unknown_store(platform, platforms):
        return UNKNOWN_STORE
    return "xbox" if platform in ("xbox_modern", "xbox_360") else platform


def console_of(platform: str, platforms: str) -> str:
    """The console a list stands for, from the platforms `titles` keeps:
    the newest one it names, as a version is one console."""
    from bot.services.platform_format import ONE, PS4, PS5, SERIES, X360, parse_platforms

    found = parse_platforms(platforms)
    if platform == "xbox_360":
        return X360
    if platform == "steam":
        return "steam"
    if platform == "psn":
        return PS5 if PS5 in found and PS4 not in found else PS4
    if SERIES in found and ONE not in found:
        return SERIES
    if found == {"pc"}:
        return "pc"
    return ONE


def stand_in_for(record: dict[str, object]) -> StoreVersion:
    """An achievement list as a version when no store describes it: the
    list's own row in `titles` (a 360 game, an Xbox card the catalog no
    longer carries, a PSN list not proved). Every list is at least one
    version, so it can be put into a game and carry an HLTB entry."""
    from bot.services.hltb_match import normalize

    platform, platforms = str(record["platform"]), str(record.get("platforms") or "")
    return StoreVersion(
        store=store_of(platform, platforms),
        product_id=str(record["title_id"]),
        console=console_of(platform, platforms),
        # A list whose name was lost ("?" on production's PSN lists) is
        # named by its English name.
        name=next(
            (
                str(n)
                for n in (record.get("name"), record.get("name_en"))
                if n and normalize(str(n))
            ),
            None,
        ),
        name_ru=record.get("name_ru"),  # type: ignore[arg-type]
        kind="game",
        stand_in=True,
    )


def console_label(store: str | None, console: str | None) -> str:
    """A version's platform as shown, from its store and its console: a
    console is its own name ("series", "ps5", "steam"); a PC is its store's
    (`PC_LABELS`), or `PC_UNKNOWN`."""
    text = str(console or "")
    if text != "pc":
        return text
    return PC_LABELS.get(str(store or ""), PC_UNKNOWN)


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


def classify_bundle(
    name: str | None, items: list[tuple[str, bool]]
) -> tuple[str, str, list[str | None]]:
    """What a store's bundle is, read from what it holds (owner, 2026-10-24),
    never from a flag alone: `items` are `(item_kind, is_primary)`. Returns
    `(scope, kind, role of each item)`:

    - one game, maybe with its own add-ons → `edition` of it (`main`), its
      kind from its name (Monster Hunter Rise + Sunbreak: no primary flag, an
      edition all the same);
    - several games, one primary → `edition` of that one; the rest are
      `bonus` (FIFA 16 Super Deluxe holds Plants vs. Zombies Garden Warfare) —
      unless its name says it is a set ("Bundle", "Collection", "Trilogy"):
      the PopCap Bundle flags one game primary and is a bundle;
    - several games, none or many primary → a `bundle` of `part`s (the
      PopCap Bundle, games of different series);
    - no game → an `addon_pack` (add-ons, currency).
    """
    games = [n for n, (kind, _p) in enumerate(items) if kind == "game"]
    roles: list[str | None] = [None] * len(items)
    if not games:
        return "addon_pack", "addon_pack", roles
    primary = [n for n in games if items[n][1]]
    # Several games under a name that says it is a set of them (the PopCap
    # Bundle flags Garden Warfare as its primary game and holds Peggle 2):
    # a bundle, whatever the flag.
    named_a_set = edition_kind(name) in ("bundle", "collection")
    if len(games) == 1 or (len(primary) == 1 and not named_a_set):
        main = games[0] if len(games) == 1 else primary[0]
        for n in games:
            roles[n] = "main" if n == main else "bonus"
        kind = edition_kind(name)
        # "Bundle" is a bundle of games now; one game sold with its add-ons
        # under a "+" or "& … Bundle" name is that game complete.
        return "edition", "complete" if kind == "bundle" else kind, roles
    for n in games:
        roles[n] = "part"
    return "bundle", "bundle", roles


def edition_kind(name: str | None) -> str:
    """What kind of edition a store's name says it is (`standard` when it says
    none); a pre-order says so first, as it is the one that vanishes."""
    lowered = (name or "").lower()
    for kind, words in _EDITION_KINDS:
        if any(word in lowered for word in words):
            return kind
    return "standard"
