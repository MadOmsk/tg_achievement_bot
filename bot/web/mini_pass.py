"""The season pass in the Mini App (owner, 2026-10-27): where the month's
points stand, its levels — themes and the super-admin's prizes — and
claiming one, checked here, so nothing is opened by editing the page.

The super-admin edits the levels here (from the Mini App only, owner,
2026-10-27): adds, changes, takes down any level nobody has claimed, as a
draft only they see, and publishes it with one tap. A pass a month (owner,
2026-10-28): this month's and the next's are edited, earlier ones only looked
back on, with one's own codes."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import time
from typing import Any

from aiohttp import web

from bot.config import Settings
from bot.db.repo import Repo
from bot.services import game_page, manual_games, pass_pictures, roles, season_pass
from bot.services.naming import person_name
from bot.util import utcnow
from bot.web.mini_chat import _person_month

log = logging.getLogger(__name__)

TITLE_MAX = 80
SEASON_TITLE_MAX = 40
DESCRIPTION_MAX = 500
CODES_MAX = 500
CODE_MAX = 200
PLATFORM_MAX = 40
POINTS_MAX = 100_000
# A pass may be built this many months ahead, this one included.
EDIT_MONTHS = 12

# The month's scores the editor shows, counted again at most this often.
SCORES_TTL = 600
_scores: tuple[float, dict[str, Any]] | None = None

# Notices to everybody, kept so they are not collected mid-run.
_BACKGROUND: set[asyncio.Task] = set()

ITEM = r"/api/mini/pass/items/{item_id:\d+}"

# Signs the editor's picture addresses: a draft's picture (or one waiting
# for the publish) is the super-admin's to see, and an <img> carries no Init
# Data, so the address itself is the permission.
_key: bytes | None = None


def setup_pass_routes(app: web.Application) -> None:
    global _key
    settings: Settings | None = app.get("mini_settings")
    if settings is not None:
        _key = hashlib.sha256(
            b"pass-draft:" + settings.fernet_key.get_secret_value().encode()
        ).digest()
    app.router.add_get("/api/mini/pass", handle_pass)
    app.router.add_post("/api/mini/pass/seen", handle_seen)
    app.router.add_post("/api/mini/pass/claim", handle_claim)
    app.router.add_post(ITEM + "/claim", handle_item_claim)
    app.router.add_get(ITEM + "/takers", handle_item_takers)
    app.router.add_post("/api/mini/pass/items", handle_item_add)
    app.router.add_get("/api/mini/pass/game-search", handle_game_search)
    app.router.add_post("/api/mini/pass/games", handle_game_add)
    app.router.add_patch(ITEM, handle_item_edit)
    app.router.add_delete(ITEM, handle_item_remove)
    app.router.add_post(ITEM + "/revert", handle_item_revert)
    app.router.add_put(ITEM + "/image", handle_item_image_put)
    # A level's picture is no secret: an <img> asks for it with no header.
    app.router.add_get(ITEM + "/image", handle_item_image)
    app.router.add_put("/api/mini/pass/season", handle_season_title)
    app.router.add_put("/api/mini/pass/season/image", handle_season_image_put)
    app.router.add_delete("/api/mini/pass/season/image", handle_season_image_delete)
    # A cover is no secret either: an <img> asks for it with no header.
    app.router.add_get("/api/mini/pass/season/image", handle_season_image)
    app.router.add_post("/api/mini/pass/publish", handle_publish)
    app.router.add_post("/api/mini/pass/discard", handle_discard)


def _picture(item_id: int, path: str | None, *, draft: bool = False) -> str | None:
    # The path's hash names the version, so a new picture is never one a
    # browser keeps from before.
    if not path:
        return None
    version = path.rsplit("-", 1)[-1].split(".")[0]
    url = f"/api/mini/pass/items/{item_id}/image?v={version}"
    return url + f"&draft=1&s={_sign(item_id, version)}" if draft else url


def _sign(item_id: int | str, version: str) -> str:
    if _key is None:
        return ""
    return hmac.new(_key, f"{item_id}:{version}".encode(), hashlib.sha256).hexdigest()[:32]


def _signed(request: web.Request, item_id: int | str) -> bool:
    given = request.query.get("s", "")
    return bool(given) and hmac.compare_digest(given, _sign(item_id, request.query.get("v", "")))


def _cover(month: str, path: str | None, *, draft: bool = False) -> str | None:
    if not path:
        return None
    version = path.rsplit("-", 1)[-1].split(".")[0]
    url = f"/api/mini/pass/season/image?month={month}&v={version}"
    # A cover waiting for the publish is the editor's, as a level's picture is.
    return url + f"&draft=1&s={_sign('season:' + month, version)}" if draft else url


async def _cards(repo: Repo, rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """A game's prize shows the game: its card from the catalog — the game it
    is now, when the one a prize was made for (a game added by hand) has been
    joined to a real one since."""
    ids = {int(r["game_id"]) for r in rows if r.get("game_id")}
    live = {gid: await repo.live_game_id(gid) or gid for gid in ids}
    found = await repo.game_cards(sorted(set(live.values())))
    return {gid: game_page.card_of(found[now]) for gid, now in live.items() if now in found}


def _next_month(key: str) -> str:
    year, month = (int(x) for x in key.split("-"))
    return f"{year + 1}-01" if month == 12 else f"{year:04d}-{month + 1:02d}"


def _editable(current: str) -> list[str]:
    """The months whose pass may be edited: this one and the ones ahead."""
    months = [current]
    while len(months) < EDIT_MONTHS:
        months.append(_next_month(months[-1]))
    return months


async def _edit_month(repo: Repo, person_id: int, request: web.Request) -> str:
    """The month the super-admin edits (`?edit=`): this one or one ahead."""
    current = (await _person_month(repo, person_id, None))[3]
    wanted = request.query.get("edit")
    return wanted if wanted in _editable(current) else current


async def _state(
    repo: Repo,
    person_id: int,
    *,
    admin: bool,
    month: str | None = None,
    edit: str | None = None,
) -> dict[str, Any]:
    """A month's pass for this person — this month by default, an earlier one
    to look back (its codes, what was claimed); never one still to come."""
    current = (await _person_month(repo, person_id, None))[3]
    await repo.ensure_pass_seeded(season_pass.DEFAULT_THEMES, current)
    try:
        month, since, until, current, _n = await _person_month(
            repo, person_id, month if month and month <= current else None
        )
    except ValueError:
        month, since, until, current, _n = await _person_month(repo, person_id, None)
    points = await repo.points_for_person(person_id, since, until)
    claimed = await repo.pass_claims(person_id)
    items = await repo.pass_live_items(person_id, month)
    cards = await _cards(repo, items)
    themes = [i for i in items if i["kind"] == "theme" and i["state"] == "live"]
    state: dict[str, Any] = {
        "ok": True,
        "month": month,
        "points": points,
        "days_left": max(1, -(-int((until - utcnow()).total_seconds()) // 86400)),
        "tiers": [
            {
                "id": t["item_id"],
                "level": n,
                "points": t["points"],
                "tier": t["tier"] or "common",
                "palette": t["palette"],
                "claimed": t["palette"] in claimed,
            }
            for n, t in enumerate(themes, start=1)
        ],
        # Codes never leave but to the one who took them.
        "rewards": [
            {
                "id": r["item_id"],
                "title": r["title"],
                "description": r["description"],
                "points": r["points"],
                "kind": r["kind"],
                "tier": r["tier"],
                "game": cards.get(int(r["game_id"])) if r["game_id"] else None,
                "platform": r["platform"],
                "image": _picture(r["item_id"], r["image_path"]),
                "total": r["total"],
                "left": r["left_count"],
                "code": r["mine"],
                "removed": r["state"] == "removed",
            }
            for r in items
            if r["kind"] != "theme"
        ],
        "admin": admin,
        "current": month == current,
        # The month's theme and cover, as published.
        "title": (season := await repo.pass_season(month))["title"],
        "image": _cover(month, season["image_path"]),
        "months": sorted({current, *await repo.pass_months(current)}, reverse=True),
    }
    if admin:
        edit = edit if edit in _editable(current) else current
        state["editor"] = await _editor(repo, edit, _editable(current))
    return state


async def _editor(repo: Repo, month: str, months: list[str]) -> dict[str, Any]:
    """A month's pass as the super-admin edits it: every level with its draft
    laid over it, whether anybody has it (then it is locked), and its codes."""
    rows = await repo.pass_editor_items(month)
    cards = await _cards(repo, rows)
    counts = await repo.pass_month_counts(months)
    season = await repo.pass_season(month)
    return {
        "month": month,
        "title": season["draft_title"],
        "image": _cover(month, season["draft_image_path"], draft=True),
        "title_changed": season["changed"],
        # Each month to pick, with how many levels it has and how many wait.
        "months": [
            {"title": None, **counts.get(m, {"levels": 0, "dirty": 0}), "month": m} for m in months
        ],
        "scores": await _month_scores(repo),
        "dirty": sum(1 for r in rows if r["state"] == "draft" or r["changed"] or r["remove"])
        + int(season["changed"]),
        "palettes": list(season_pass.PALETTES),
        "items": [
            {
                "id": r["item_id"],
                "kind": r["kind"],
                "palette": r["palette"],
                "tier": r["tier"],
                "title": r["title"],
                "description": r["description"],
                "points": r["points"],
                "game": cards.get(int(r["game_id"])) if r["game_id"] else None,
                "platform": r["platform"],
                "image": _picture(r["item_id"], r["image_path"], draft=True),
                "codes": r["codes"],
                "draft": r["state"] == "draft",
                "changed": r["changed"],
                "remove": r["remove"],
                "taken": r["taken"],
            }
            for r in rows
        ],
    }


async def _month_scores(repo: Repo) -> dict[str, Any]:
    """What people score in a month, for the super-admin to set a level's
    points by (owner, 2026-10-28): this month's best so far, and last
    month's best and middle among those who scored. Each person's month is
    their own calendar month."""
    global _scores
    now = time.monotonic()
    if _scores is not None and now - _scores[0] < SCORES_TTL:
        return _scores[1]
    this: list[int] = []
    last: list[int] = []
    for person_id in await repo.all_person_ids():
        _key, since, until, _current, _n = await _person_month(repo, person_id, None)
        _key, before, _until, _current, _n = await _person_month(
            repo, person_id, _previous_month(_key)
        )
        this.append(await repo.points_for_person(person_id, since, until))
        last.append(await repo.points_for_person(person_id, before, since))
    scored = sorted(n for n in last if n > 0)
    result = {
        "top": max(this, default=0),
        "last_top": scored[-1] if scored else 0,
        "last_median": scored[len(scored) // 2] if scored else 0,
    }
    _scores = (now, result)
    return result


def _previous_month(key: str) -> str:
    year, month = (int(x) for x in key.split("-"))
    return f"{year - 1}-12" if month == 1 else f"{year:04d}-{month - 1:02d}"


async def _person(request: web.Request) -> tuple[Repo, int, bool]:
    from bot.web.mini_api import _require_user

    user = await _require_user(request)
    if user.person_id is None:
        raise web.HTTPForbidden(text="no person")
    repo: Repo = request.app["mini_repo"]
    # The pass's editor: a super-admin or an admin (owner, 2026-10-28).
    admin = request.app["mini_settings"].is_superadmin(user.tg_id) or roles.runs_the_app(
        await repo.person_role(user.person_id)
    )
    return repo, user.person_id, admin


async def _admin(request: web.Request) -> tuple[Repo, int]:
    repo, person_id, admin = await _person(request)
    if not admin:
        raise web.HTTPForbidden(text="superadmin only")
    return repo, person_id


async def _body(request: web.Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except ValueError:
        raise web.HTTPBadRequest(text="bad json") from None
    if not isinstance(body, dict):
        raise web.HTTPBadRequest(text="bad json")
    return body


def _refuse(error: str, status: int = 400) -> web.Response:
    return web.json_response({"ok": False, "error": error}, status=status)


async def _fields(
    repo: Repo, body: dict[str, Any], *, item_id: int | None, month: str
) -> tuple[dict[str, Any], list[str] | None] | str:
    """A level as the editor sends it, checked: its fields and its codes (None
    when the codes are not sent), or the word for what is wrong."""
    kind = str(body.get("kind") or "")
    if kind not in season_pass.KINDS:
        return "invalid"
    try:
        points = int(body.get("points") or 0)
    except (TypeError, ValueError):
        return "invalid"
    if not 0 <= points <= POINTS_MAX:
        return "invalid"
    fields: dict[str, Any] = {
        "kind": kind,
        "points": points,
        "palette": None,
        "tier": None,
        "title": None,
        "description": None,
        "game_id": None,
        "platform": None,
    }
    if kind == "theme":
        palette = str(body.get("palette") or "")
        tier = str(body.get("tier") or "common")
        if palette not in season_pass.PALETTES or tier not in season_pass.LOOKS:
            return "invalid"
        # One level a theme in a month's pass: two would be one claim.
        for other in await repo.pass_editor_items(month):
            if other["item_id"] != item_id and other["kind"] == "theme" and not other["remove"]:
                if other["palette"] == palette:
                    return "palette_taken"
        fields.update(palette=palette, tier=tier)
        return fields, None
    title = str(body.get("title") or "").strip()
    description = str(body.get("description") or "").strip() or None
    if not title or len(title) > TITLE_MAX or (description and len(description) > DESCRIPTION_MAX):
        return "invalid"
    # Free text: Xbox, PlayStation, Steam, or whatever the prize is for.
    platform = str(body.get("platform") or "").strip() or None
    if platform and len(platform) > PLATFORM_MAX:
        return "invalid"
    fields["platform"] = platform
    codes: list[str] | None = None
    if "codes" in body:
        raw = body.get("codes")
        codes = [str(c).strip() for c in raw if str(c).strip()] if isinstance(raw, list) else []
        if not codes or len(codes) > CODES_MAX or any(len(c) > CODE_MAX for c in codes):
            return "invalid"
    # A game of the catalog, or one it lacks named by its title alone
    # (owner, 2026-10-28); a code is for anything that is no game.
    if kind == "game" and body.get("game_id") is not None:
        try:
            game_id = await repo.live_game_id(int(body.get("game_id")))
        except (TypeError, ValueError):
            game_id = None
        if game_id is None:
            return "no_game"
        fields["game_id"] = game_id
    # A prize's look is a tier as a theme's is (owner, 2026-10-28).
    look = str(body.get("tier") or "common")
    if look not in season_pass.LOOKS:
        return "invalid"
    fields.update(title=title, description=description, tier=look)
    return fields, codes


GAME_NAME_MAX = 120


async def handle_game_search(request: web.Request) -> web.Response:
    """The prize picker's search of the stores' own catalogs (Steam, Xbox),
    for a game ours lacks (owner, 2026-10-30): `?q=` -> `{name, image,
    stores}`. **A game the catalog already has is left out** — it is picked
    from the catalog's own search, and a hand-added game must never be a
    duplicate."""
    repo, _person = await _admin(request)
    term = request.query.get("q", "").strip()
    if len(term) < 2 or len(term) > GAME_NAME_MAX:
        return web.json_response({"ok": True, "games": []})
    index = await repo.game_name_index()
    new = [
        hit
        for hit in await manual_games.search_stores(term)
        if await manual_games.existing_game(repo, hit["name"], hit["stores"], index) is None
    ]
    return web.json_response({"ok": True, "games": new})


async def handle_game_add(request: web.Request) -> web.Response:
    """A game the picker found in the stores, as a prize's game: the one our
    catalog already has (by a store id, or by name), else added by hand and
    queued for the octopus to fill in (`Repo.add_manual_game`). Body: `{name,
    stores: [{store, id}]}` -> `{game: card, made}`."""
    repo, _person = await _admin(request)
    body = await _body(request)
    name = str(body.get("name") or "").strip()
    stores = body.get("stores")
    if not 2 <= len(name) <= GAME_NAME_MAX or not isinstance(stores, list) or not stores:
        return _refuse("invalid")
    refs: list[dict[str, str]] = []
    for ref in stores[:4]:
        store, store_id = str(ref.get("store") or ""), str(ref.get("id") or "")
        if manual_games.queue_key(store, store_id) is None:
            return _refuse("invalid")
        refs.append({"store": store, "id": store_id})

    game_id = await manual_games.existing_game(repo, name, refs)
    made = False
    if game_id is None:
        game_id, made = await repo.add_manual_game(
            name, None, manual_games.queue_key(refs[0]["store"], refs[0]["id"])
        )
        for ref in refs[1:]:
            await repo.octopus_enqueue(
                manual_games.queue_key(ref["store"], ref["id"]) or "", "manual"
            )
    card = (await repo.game_cards([game_id])).get(game_id)
    if card is None:
        return _refuse("no_game", 404)
    return web.json_response({"ok": True, "made": made, "game": game_page.card_of(card)})


async def _unclaimed(repo: Repo, item_id: int, month: str) -> dict[str, Any] | web.Response:
    item = await repo.pass_item(item_id)
    # Only the month being edited: a past month's pass stays as it was.
    if item is None or item["state"] == "removed" or item["month"] != month:
        raise web.HTTPNotFound(text="no level")
    if item["taken"]:
        return _refuse("taken", 409)
    return item


async def handle_pass(request: web.Request) -> web.Response:
    """`?month=` an earlier month's pass to look back on; `?edit=` the month
    the super-admin's editor shows."""
    repo, person_id, admin = await _person(request)
    return web.json_response(
        await _state(
            repo,
            person_id,
            admin=admin,
            month=request.query.get("month"),
            edit=request.query.get("edit"),
        )
    )


async def _edited(repo: Repo, person_id: int, request: web.Request) -> web.Response:
    """The pass again after an edit, the editor on the month edited."""
    edit = await _edit_month(repo, person_id, request)
    return web.json_response(await _state(repo, person_id, admin=True, edit=edit))


async def handle_seen(request: web.Request) -> web.Response:
    """The pass's own page was opened: who has looked is not told the season started
    (`poller/season_start.py`). Not `GET /pass`: Home and Settings read that too."""
    repo, person_id, _admin = await _person(request)
    await repo.mark_pass_seen(person_id, (await _person_month(repo, person_id, None))[3])
    return web.json_response({"ok": True})


async def handle_claim(request: web.Request) -> web.Response:
    """A theme: by its palette, from the published levels."""
    repo, person_id, admin = await _person(request)
    palette = str((await _body(request)).get("palette") or "")
    state = await _state(repo, person_id, admin=admin)
    tier = next((t for t in state["tiers"] if t["palette"] == palette), None)
    if tier is None:
        raise web.HTTPBadRequest(text="unknown palette")
    if state["points"] < tier["points"]:
        return _refuse("not_reached", 403)
    await repo.set_pass_claim(person_id, palette, state["month"], True)
    return web.json_response(await _state(repo, person_id, admin=admin))


async def handle_item_takers(request: web.Request) -> web.Response:
    """Who took a prize's codes: the race made visible (owner, 2026-10-28)."""
    repo, _person_id, _admin = await _person(request)
    item = await repo.pass_item(int(request.match_info["item_id"]))
    if item is None or item["state"] == "draft" or item["kind"] == "theme":
        raise web.HTTPNotFound(text="no prize")
    takers = await repo.pass_item_takers(item["item_id"])
    return web.json_response(
        {
            "ok": True,
            "takers": [
                {
                    "person_id": t["person_id"],
                    "name": person_name(person_id=t["person_id"], handle=t["handle"]),
                    "claimed_at": t["claimed_at"],
                }
                for t in takers
            ],
        }
    )


async def handle_item_claim(request: web.Request) -> web.Response:
    """A prize: one of its codes."""
    repo, person_id, admin = await _person(request)
    item = await repo.pass_item(int(request.match_info["item_id"]))
    if item is None or item["state"] != "live" or item["kind"] == "theme":
        raise web.HTTPNotFound(text="no prize")
    state = await _state(repo, person_id, admin=admin)
    # Only this month's pass gives: an earlier one is to look back on.
    if item["month"] != state["month"]:
        return _refuse("not_reached", 403)
    if state["points"] < item["points"]:
        return _refuse("not_reached", 403)
    if await repo.claim_pass_code(item["item_id"], person_id) is None:
        return _refuse("gone", 409)
    return web.json_response(await _state(repo, person_id, admin=admin))


async def handle_item_add(request: web.Request) -> web.Response:
    repo, person_id = await _admin(request)
    edit = await _edit_month(repo, person_id, request)
    checked = await _fields(repo, await _body(request), item_id=None, month=edit)
    if isinstance(checked, str):
        return _refuse(checked)
    fields, codes = checked
    if fields["kind"] != "theme" and not codes:
        return _refuse("invalid")
    item_id = await repo.add_pass_item(fields, codes or [], person_id, edit)
    # The new level's id: its picture is sent next.
    state = await _state(repo, person_id, admin=True, edit=edit)
    return web.json_response({**state, "added": item_id})


async def handle_item_edit(request: web.Request) -> web.Response:
    repo, person_id = await _admin(request)
    edit = await _edit_month(repo, person_id, request)
    item_id = int(request.match_info["item_id"])
    item = await _unclaimed(repo, item_id, edit)
    if isinstance(item, web.Response):
        return item
    checked = await _fields(repo, await _body(request), item_id=item_id, month=edit)
    if isinstance(checked, str):
        return _refuse(checked)
    fields, codes = checked
    await repo.edit_pass_item(item_id, fields, codes)
    return await _edited(repo, person_id, request)


async def handle_item_remove(request: web.Request) -> web.Response:
    repo, person_id = await _admin(request)
    item_id = int(request.match_info["item_id"])
    item = await _unclaimed(repo, item_id, await _edit_month(repo, person_id, request))
    if isinstance(item, web.Response):
        return item
    pass_pictures.remove(await repo.remove_pass_item(item_id))
    return await _edited(repo, person_id, request)


async def handle_item_revert(request: web.Request) -> web.Response:
    repo, person_id = await _admin(request)
    item_id = int(request.match_info["item_id"])
    # The same bounds as any edit: the month edited, nobody holding it yet.
    item = await _unclaimed(repo, item_id, await _edit_month(repo, person_id, request))
    if isinstance(item, web.Response):
        return item
    pass_pictures.remove(await repo.revert_pass_item(item_id))
    return await _edited(repo, person_id, request)


async def handle_item_image_put(request: web.Request) -> web.Response:
    """A level's picture: the body is the image's bytes, saved again by the
    server (`services/pass_pictures.py`) — on a draft at once, on a
    published level with its other waiting changes."""
    from bot.web.mini_api import _read_capped

    repo, person_id = await _admin(request)
    item_id = int(request.match_info["item_id"])
    item = await _unclaimed(repo, item_id, await _edit_month(repo, person_id, request))
    if isinstance(item, web.Response):
        return item
    body = await _read_capped(request, pass_pictures.MAX_UPLOAD_BYTES)
    path = await pass_pictures.store(item_id, body) if body else None
    if path is None:
        return _refuse("invalid")
    await repo.edit_pass_item(item_id, {"image_path": path}, None)
    if item["state"] == "draft" and item["image_path"] and item["image_path"] != path:
        pass_pictures.remove(item["image_path"])
    return await _edited(repo, person_id, request)


async def handle_item_image(request: web.Request) -> web.Response:
    repo: Repo = request.app["mini_repo"]
    item_id = int(request.match_info["item_id"])
    item = await repo.pass_item(item_id)
    if item is None:
        raise web.HTTPNotFound(text="no picture")
    draft = bool(request.query.get("draft"))
    # A level not yet published, and a picture waiting for the publish, show
    # only through the editor's signed address.
    if (draft or item["state"] == "draft") and not _signed(request, item_id):
        raise web.HTTPNotFound(text="no picture")
    path = item["image_path"]
    if draft:
        # The editor's preview of a picture waiting for the publish.
        editing = next((i for i in await repo.pass_editor_items() if i["item_id"] == item_id), None)
        path = editing["image_path"] if editing else path
    if not path:
        raise web.HTTPNotFound(text="no picture")
    try:
        body = pass_pictures.read(path)
    except OSError:
        raise web.HTTPNotFound(text="no picture") from None
    # The address names the version (`?v=`), so a browser may keep it.
    return web.Response(
        body=body,
        content_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=604800, immutable"},
    )


async def handle_season_title(request: web.Request) -> web.Response:
    """The edited month's pass's name, its theme; empty clears it."""
    repo, person_id = await _admin(request)
    title = str((await _body(request)).get("title") or "").strip() or None
    if title and len(title) > SEASON_TITLE_MAX:
        return _refuse("invalid")
    await repo.set_pass_season_title(await _edit_month(repo, person_id, request), title)
    return await _edited(repo, person_id, request)


async def handle_season_image_put(request: web.Request) -> web.Response:
    """The edited month's cover: the body is the image's bytes, saved again by
    the server, waiting for the month's publish."""
    from bot.web.mini_api import _read_capped

    repo, person_id = await _admin(request)
    month = await _edit_month(repo, person_id, request)
    body = await _read_capped(request, pass_pictures.MAX_UPLOAD_BYTES)
    path = await pass_pictures.store(month, body, kind="season") if body else None
    if path is None:
        return _refuse("invalid")
    pass_pictures.remove(await repo.set_pass_season_image(month, path))
    return await _edited(repo, person_id, request)


async def handle_season_image_delete(request: web.Request) -> web.Response:
    repo, person_id = await _admin(request)
    month = await _edit_month(repo, person_id, request)
    pass_pictures.remove(await repo.set_pass_season_image(month, None))
    return await _edited(repo, person_id, request)


async def handle_season_image(request: web.Request) -> web.Response:
    repo: Repo = request.app["mini_repo"]
    month = request.query.get("month", "")
    season = await repo.pass_season(month)
    draft = bool(request.query.get("draft"))
    if draft and not _signed(request, "season:" + month):
        raise web.HTTPNotFound(text="no picture")
    path = season["draft_image_path"] if draft else season["image_path"]
    if not path:
        raise web.HTTPNotFound(text="no picture")
    try:
        body = pass_pictures.read(path)
    except OSError:
        raise web.HTTPNotFound(text="no picture") from None
    return web.Response(
        body=body,
        content_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=604800, immutable"},
    )


async def handle_publish(request: web.Request) -> web.Response:
    """The draft made the pass. «Оповестить всех» tells everybody of the new
    levels; a level somebody claimed meanwhile is left as it was."""
    repo, person_id = await _admin(request)
    notify = bool((await _body(request)).get("notify"))
    edit = await _edit_month(repo, person_id, request)
    result = await repo.publish_pass(edit)
    for path in result.pop("old_pictures"):
        pass_pictures.remove(path)
    notifier = request.app.get("mini_notifications")
    if notify and result["added"] and notifier is not None:
        names = [n for n in result["added"] if n and n not in season_pass.PALETTES]
        title = ", ".join(names[:3]) if names else str(len(result["added"]))
        task = asyncio.create_task(notifier.tell_about_reward(title))
        _BACKGROUND.add(task)
        task.add_done_callback(_BACKGROUND.discard)
    published = {**result, "added": len(result["added"])}
    state = await _state(repo, person_id, admin=True, edit=edit)
    return web.json_response({**state, "published": published})


async def handle_discard(request: web.Request) -> web.Response:
    repo, person_id = await _admin(request)
    for path in await repo.discard_pass_draft(await _edit_month(repo, person_id, request)):
        pass_pictures.remove(path)
    return await _edited(repo, person_id, request)
