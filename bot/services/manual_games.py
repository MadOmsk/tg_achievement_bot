"""A game the super-admin adds by hand, found in the stores (owner,
2026-10-30): the prize picker searches Steam's and Xbox's catalogs directly,
not ours — a game the catalog lacks is the usual reason to add one. One row a
game: the same name in both stores is one hit carrying both ids. Picking a hit
finds the game in our catalog by those ids, or adds it
(`Repo.add_manual_game`) and queues its store pages for the octopus, which
fills it in (`octopus.entry_key`'s keys)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from bot.services.game_match import _EXTRA, name_key
from bot.services.stores import steam_store, xbox_catalog

log = logging.getLogger(__name__)

HITS_MAX = 10
STORES = ("steam", "xbox")


def queue_key(store: str, store_id: str) -> str | None:
    """What the octopus reaches a store page by (`octopus.entry_key`)."""
    if store == "steam" and store_id.isdigit():
        return f"product:steam:{store_id}"
    if store == "xbox" and store_id.isalnum() and len(store_id) == 12:
        return f"storeid:xbox_product:{store_id.upper()}"
    return None


async def search_stores(term: str) -> list[dict[str, Any]]:
    """Games the two stores list for a name, `{name, image, stores: [{store,
    id}]}`, Steam's and Xbox's alternating, one row for a name both have. A
    store that cannot be asked leaves the other's."""
    steam, xbox = await asyncio.gather(
        steam_store.search(term), xbox_catalog.search(term), return_exceptions=True
    )
    found: list[tuple[str, str, str, str | None]] = []  # (store, id, name, image)
    if isinstance(steam, list):
        apps = [i for i in steam if i.get("type") == "app" and i.get("id") and i.get("name")]
        # The poster of now, as a game's poster is drawn (one request for all):
        # the search's own picture is a thin banner, kept for an app with none.
        try:
            art = await steam_store.library_art([str(i["id"]) for i in apps])
        except Exception as exc:
            log.info("steam posters for %r not read: %r", term, exc)
            art = {}
        found += [
            (
                "steam",
                str(i["id"]),
                str(i["name"]),
                art.get(str(i["id"]), {}).get("poster") or i.get("tiny_image"),
            )
            for i in apps
        ]
    else:
        log.info("steam search for %r failed: %r", term, steam)
    if isinstance(xbox, list):
        for p in xbox:
            if p.get("Type") != "Game" or not p.get("ProductId") or not p.get("Title"):
                continue
            icon = str(p.get("Icon") or "")
            image = f"https:{icon}" if icon.startswith("//") else (icon or None)
            found.append(("xbox", str(p["ProductId"]).upper(), str(p["Title"]), image))
    else:
        log.info("xbox search for %r failed: %r", term, xbox)

    # Alternate the stores, then fold a name both have into one row.
    by_store = {s: [f for f in found if f[0] == s] for s in STORES}
    order: list[tuple[str, str, str, str | None]] = []
    for i in range(max((len(v) for v in by_store.values()), default=0)):
        for s in STORES:
            if i < len(by_store[s]):
                order.append(by_store[s][i])
    hits: dict[str, dict[str, Any]] = {}
    for store, store_id, name, image in order:
        # A soundtrack or an artbook is a part of its game, not a game to give.
        if _EXTRA.search(name):
            continue
        key = name_key(name) or name.lower()
        hit = hits.setdefault(key, {"name": name, "image": image, "stores": []})
        hit["image"] = hit["image"] or image
        if not any(s["store"] == store for s in hit["stores"]):
            hit["stores"].append({"store": store, "id": store_id})
    return list(hits.values())[:HITS_MAX]


async def existing_game(
    repo: Any, name: str, stores: list[dict[str, str]], index: dict[str, int] | None = None
) -> int | None:
    """The catalog's game for a store's hit — by the store ids it has them
    under, else by name as the matcher reads names — so a game the catalog
    already has is picked, never added again (owner, 2026-10-30: a pile of
    duplicates is what a hand-added game must not make)."""
    for ref in stores:
        store, store_id = ref["store"], ref["id"]
        if store == "steam" and store_id.isdigit():
            game_id = await repo.game_of_steam_app(int(store_id))
            if game_id is not None:
                return game_id
        elif store == "xbox":
            for version in await repo.versions_of_product("xbox", store_id.upper()):
                if version.get("game_id") is not None:
                    return await repo.live_game_id(int(version["game_id"]))
    if index is None:
        index = await repo.game_name_index()
    game_id = index.get(name_key(name))
    return await repo.live_game_id(game_id) if game_id is not None else None
