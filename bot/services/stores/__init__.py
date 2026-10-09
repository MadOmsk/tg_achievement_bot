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
    description_en: str | None = None
    description_ru: str | None = None
    media: dict[str, object] = field(default_factory=dict)
    live_service: bool = False
    # Every id that names this version: (kind, id), e.g. ("psn_title", "CUSA00527_00").
    store_ids: list[tuple[str, str]] = field(default_factory=list)
    # The ids of its add-ons, as the store lists them; named separately.
    dlc_ids: list[str] = field(default_factory=list)
    dlcs: list[StoreDlc] = field(default_factory=list)
