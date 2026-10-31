"""The Mini App's game page, the games search and favorite games (#147,
stage 5; owner, 2026-10-25). The page is read whole from the catalog; the
old page of one achievement list (`/api/mini/games/{platform}/{title_id}`)
stays as the achievements screen it opens."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from aiohttp import web

from bot.constants import account_platform_of
from bot.db.repo import Repo
from bot.services import game_page, steam_library_art
from bot.services.game_link import GameLinker
from bot.services.naming import person_name_of
from bot.web.mini_chat import news_text, news_title

log = logging.getLogger(__name__)

SEARCH_MIN = 2
SEARCH_LIMIT = 20
# Faces of people who played it, on the page.
PLAYERS_SHOWN = 12
NEWS_SHOWN = game_page.NEWS_SHOWN

# Background reads started from a page, kept so they are not collected mid-run.
_BACKGROUND: set[asyncio.Task] = set()
# A Steam app's first news read is started once in this long, however many
# visits ask (several at once, or Steam failing and every visit retrying).
NEWS_READ_RETRY_SECONDS = 600
_news_read_at: dict[int, float] = {}


def setup_game_routes(app: web.Application) -> None:
    app.router.add_get("/api/mini/game", handle_game_page)
    app.router.add_put(r"/api/mini/game/{game_id:\d+}/favorite", handle_favorite)
    app.router.add_delete(r"/api/mini/game/{game_id:\d+}/favorite", handle_favorite)
    app.router.add_get("/api/mini/game-search", handle_game_search)
    app.router.add_get("/api/mini/game-favorites", handle_favorites)


def _int(raw: str | None, what: str) -> int:
    try:
        return int(raw or "")
    except ValueError as exc:
        raise web.HTTPBadRequest(text=f"bad {what}") from exc


async def _game_id(request: web.Request, repo: Repo) -> int:
    """The game asked for: by its id, or by one of its achievement lists (a
    post, a profile's games, an old link)."""
    if request.query.get("game_id"):
        game = await repo.live_game_id(_int(request.query.get("game_id"), "game_id"))
    else:
        platform = (request.query.get("platform") or "").lower()
        title_id = request.query.get("title_id") or ""
        if not platform or not title_id:
            raise web.HTTPBadRequest(text="game_id or platform and title_id")
        game = await repo.game_of_list(platform, title_id)
        if game is None:
            # A list in no game yet: a game of its own from this visit on,
            # and at once where it belongs — the linker (local, no network)
            # joins it to the same game on another platform.
            game = await repo.adopt_list_as_game(platform, title_id)
            if game is not None:
                await GameLinker(repo).link_title(platform, title_id)
                game = await repo.game_of_list(platform, title_id) or game
    if game is None:
        raise web.HTTPNotFound(text="game not found")
    return game


async def _translating(collector: Any, game_id: int, locale: str) -> bool:
    """Whether the game's description is on its way, starting it when not: the
    page shows the text blurred and asks again."""
    translator = collector.translator if collector is not None else None
    if translator is None:
        return False
    return (await translator.pending(game_id, locale)).description


async def handle_game_page(request: web.Request) -> web.Response:
    from bot.web.mini_api import _may_see_activity, _require_user, _user_locale

    user = await _require_user(request)
    repo: Repo = request.app["mini_repo"]
    game_id = await _game_id(request, repo)
    game = await repo.game_row(game_id)
    if game is None:
        raise web.HTTPNotFound(text="game not found")
    locale = await _user_locale(repo, user.person_id)

    # Whose progress the page leads with: the viewer's own, or the person it
    # was opened from when the viewer may see their activity (#157).
    viewer = user.person_id
    viewed = viewer
    raw_person = request.query.get("person")
    if raw_person:
        other = _int(raw_person, "person")
        if other != viewer and await _may_see_activity(repo, viewer, other):
            viewed = other

    versions = await repo.game_page_versions(game_id)
    # Steam's poster and head of now, for the next look (never awaited).
    steam_library_art.refresh_later(repo, versions)
    lists = await repo.game_page_lists(game_id)
    hltb_found = await repo.game_hltb(game_id)
    hltb_entry = hltb_found["entry"] if hltb_found else None
    art = game_page.art_of(versions, game_page.list_icons(lists))

    # Who here played it: the viewer, whom they follow, and the person it was
    # opened from — each only as far as their privacy lets the viewer see.
    people: list[int] = []
    if viewer is not None:
        people = [viewer, *[row.id for row in await repo.following_of(viewer)]]
    if viewed is not None and viewed not in people:
        people.append(viewed)
    visible = [
        person
        for person in people
        if person == viewer or await _may_see_activity(repo, viewer, person)
    ]
    totals = {(row["platform"], str(row["title_id"])): int(row["total"] or 0) for row in lists}
    # Which version a list is, so two lists of one platform tell apart
    # (Xbox One and Xbox PC): its console and store, the plain version first.
    list_console: dict[tuple[str, str], tuple[str, str]] = {}
    for version in sorted(versions, key=lambda v: v.get("role") != "version"):
        key = (str(version.get("platform") or ""), str(version.get("title_id") or ""))
        if key[1] and key not in list_console:
            list_console[key] = (str(version.get("console") or ""), str(version.get("store") or ""))
    players = []
    progress = None
    for row in await repo.game_players(game_id, visible):
        person = await repo.get_user(int(row["person_id"]))
        if person is None:
            continue
        # One entry per list the person played (a game on Xbox and Steam is
        # two lists, never summed), the most earned first.
        played = []
        for one in row["lists"]:
            # The same count the feed and the posts show (`title_progress`), so a
            # game reads "40/50" everywhere; the list's own size when it knows none.
            known = await repo.title_progress(
                account_platform_of(one["platform"]), str(one["xuid"]), str(one["title_id"])
            )
            console, store = list_console.get((one["platform"], str(one["title_id"])), ("", ""))
            played.append(
                {
                    "count": known.unlocked if known else int(one["n"]),
                    "last": one["last"],
                    "platform": one["platform"],
                    "title_id": str(one["title_id"]),
                    "console": console or None,
                    "store": store or None,
                    "total": (known.total if known else None)
                    or totals.get((one["platform"], str(one["title_id"])))
                    or None,
                }
            )
        item = {
            "person_id": person.id,
            "name": person_name_of(person),
            **played[0],
            "lists": played,
        }
        if person.id == viewed:
            progress = item
        else:
            players.append(item)

    # The newest posts of the game's Steam apps; an app never read is read in
    # the background, and the page shows them from its next visit.
    news: list[dict[str, Any]] = []
    extras = request.app.get("mini_steam_extras")
    for appid in await repo.game_steam_apps(game_id):
        _guides_at, patches_at = await repo.steam_app_checked(appid)
        if patches_at is None:
            now = time.monotonic()
            if extras is not None and now - _news_read_at.get(appid, -1e9) >= (
                NEWS_READ_RETRY_SECONDS
            ):
                _news_read_at[appid] = now
                task = asyncio.create_task(extras.refresh_patches(appid))
                _BACKGROUND.add(task)
                task.add_done_callback(_BACKGROUND.discard)
            continue
        for post in await repo.game_patches(appid, NEWS_SHOWN):
            news.append(
                {
                    "appid": appid,
                    "gid": post.gid,
                    "title": news_title(post, locale),
                    "date": post.published_at,
                    "kind": post.kind,
                    "image": post.image_url,
                    "text": news_text(post, locale),
                    "url": f"https://store.steampowered.com/news/app/{appid}/view/{post.gid}",
                }
            )
    news.sort(key=lambda post: post["date"] or "", reverse=True)

    # What the stores say, asked again in the background when it is due.
    collector = request.app.get("mini_store_collector")
    if collector is not None and lists:
        collector.ensure(str(lists[0]["platform"]), str(lists[0]["title_id"]), reason="page")

    series = []
    for one in await repo.game_page_series(game_id):
        cards = await repo.game_cards(one["game_ids"])
        series.append(
            {
                "series_id": one["series_id"],
                "name": (one["name_ru"] if locale == "ru" and one.get("name_ru") else one["name"]),
                "games": [game_page.card_of(cards[g]) for g in one["game_ids"] if g in cards],
            }
        )
    relations = await repo.game_page_relations(game_id)
    related_cards = await repo.game_cards([int(r["other"]) for r in relations])
    related = [
        {
            "kind": row["kind"],
            "forward": bool(row["forward"]),
            "game": game_page.card_of(related_cards[int(row["other"])]),
        }
        for row in relations
        if int(row["other"]) in related_cards
    ]

    return web.json_response(
        {
            "ok": True,
            "game": {
                "game_id": game_id,
                "name": game["name"],
                "name_ru": game.get("name_ru"),
                "year": game.get("year"),
                "last_year": game.get("last_year"),
                "developer": game.get("developer"),
                "publisher": game.get("publisher"),
                "more_developers": bool(game.get("more_developers")),
                "more_publishers": bool(game.get("more_publishers")),
                "kind": game.get("kind"),
            },
            "art": art,
            "description": game_page.description_of(versions, hltb_entry, locale),
            "translating": await _translating(collector, game_id, locale),
            "genres": game_page.genres_of(versions, hltb_entry),
            "platforms": game_page.platforms_of(versions),
            "screenshots": game_page.screenshots_of(versions),
            "videos": game_page.videos_of(versions),
            "hltb": game_page.hltb_of(hltb_entry),
            "lists": [
                {
                    "platform": row["platform"],
                    "title_id": str(row["title_id"]),
                    "name": row["name"],
                    "total": int(row["total"] or 0) or None,
                    "icon_url": game_page.https(row.get("icon_url")),
                }
                for row in lists
            ],
            "viewed_is_me": viewed == viewer,
            "progress": progress,
            "players": players[:PLAYERS_SHOWN],
            "favorite": viewer is not None and await repo.is_favorite(viewer, game_id),
            "favorites": await repo.favorite_count(game_id),
            "news": news[:NEWS_SHOWN],
            "dlcs": game_page.dlcs_of(await repo.game_page_dlcs(game_id), game["name"]),
            "editions": game_page.editions_of(await repo.game_page_editions(game_id)),
            "series": series,
            "related": related,
        }
    )


async def handle_favorite(request: web.Request) -> web.Response:
    from bot.web.mini_api import _require_user

    user = await _require_user(request)
    if user.person_id is None:
        raise web.HTTPForbidden(text="no person")
    repo: Repo = request.app["mini_repo"]
    game_id = await repo.live_game_id(_int(request.match_info.get("game_id"), "game_id"))
    if game_id is None:
        raise web.HTTPNotFound(text="game not found")
    on = request.method == "PUT"
    await repo.set_favorite(user.person_id, game_id, on)
    return web.json_response(
        {"ok": True, "favorite": on, "favorites": await repo.favorite_count(game_id)}
    )


async def handle_game_search(request: web.Request) -> web.Response:
    """Games of our own catalog by name — never a search on the internet
    (owner, 2026-10-25): every game anybody here played, and every one the
    stores were asked about."""
    from bot.web.mini_api import _require_user

    await _require_user(request)
    repo: Repo = request.app["mini_repo"]
    query = (request.query.get("q") or "").strip()
    if len(query) < SEARCH_MIN:
        raise web.HTTPBadRequest(text="query too short")
    matches = game_page.rank_search(await repo.game_search_names(), query)
    # Among names that match alike, the games people here play come first.
    counts = await repo.game_player_counts([game for game, _rank, _length in matches])
    matches.sort(key=lambda m: (m[1], -counts.get(m[0], 0), m[2]))
    found = [game for game, _rank, _length in matches][:SEARCH_LIMIT]
    cards = await repo.game_cards(found)
    return web.json_response(
        {
            "ok": True,
            "games": [
                {**game_page.card_of(cards[game]), "players": counts.get(game, 0)}
                for game in found
                if game in cards
            ],
        }
    )


async def handle_favorites(request: web.Request) -> web.Response:
    """A person's favorite games, for their profile: the viewer's own, or
    somebody's whose activity the viewer may see."""
    from bot.web.mini_api import _may_see_activity, _require_user

    user = await _require_user(request)
    repo: Repo = request.app["mini_repo"]
    person = user.person_id
    if request.query.get("person"):
        person = _int(request.query.get("person"), "person")
    if person is None:
        return web.json_response({"ok": True, "games": []})
    if person != user.person_id and not await _may_see_activity(repo, user.person_id, person):
        raise web.HTTPForbidden(text="activity hidden")
    ids = await repo.favorite_game_ids(person)
    cards = await repo.game_cards(ids)
    return web.json_response(
        {"ok": True, "games": [game_page.card_of(cards[g]) for g in ids if g in cards]}
    )
