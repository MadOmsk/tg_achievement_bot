"""A link to share that Telegram (and every other messenger) can draw as a
card (owner, 2026-10-30): the app is one page with no picture or title of a
post's own, so a shared link pointed at it showed nothing. The link points
here instead — a tiny public page carrying the post's Open Graph tags (the
game and the title, the start of the text, the post's picture or its game's
art), which sends a person on to the post in the app at once.

Public, as the post is on Steam: a messenger's crawler carries no sign-in.
The pictures are the stores' own addresses, which any crawler can fetch.
"""

from __future__ import annotations

import html
import re
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from aiohttp import web

from bot.services import game_page

if TYPE_CHECKING:
    from bot.db.repo import Repo

# Where the app lives on this host: a path of our own, never another site.
_APP_PATH = re.compile(r"^/[A-Za-z0-9/_-]*$")
_DESCRIPTION_CHARS = 200


def setup_share_routes(app: web.Application) -> None:
    app.router.add_get("/api/mini/share/news/{appid}/{gid}", handle_news_share)


async def handle_news_share(request: web.Request) -> web.Response:
    """`?g=platform:title_id` the game the post was opened over, `?b=` the
    app's path on this host (`/` on the dev server, `/app/` in production)."""
    from bot.web.mini_chat import _news_excerpt

    repo: Repo = request.app["mini_repo"]
    try:
        appid = int(request.match_info["appid"])
    except ValueError as exc:
        raise web.HTTPNotFound(text="no such post") from exc
    gid = request.match_info["gid"]
    post = await repo.game_patch(appid, gid)
    if post is None:
        raise web.HTTPNotFound(text="no such post")

    game_name: str | None = None
    art: dict[str, str | None] = {}
    platform, _, title_id = (request.query.get("g") or "").partition(":")
    # The game the post was opened over, else the game its Steam app is.
    game_id = await repo.game_of_list(platform, title_id) if platform and title_id else None
    if game_id is None:
        game_id = await repo.game_of_steam_app(appid)
    card = (await repo.game_cards([game_id])).get(game_id) if game_id is not None else None
    if card:
        game_name = card.get("name_ru") or card.get("name")
        art = game_page.store_art(card["media"], card["icons"])
    title = post.title_ru or post.title
    text = post.text_ru if post.title_ru else post.text_en
    image = post.image_url or art.get("hero") or art.get("poster")

    base = request.query.get("b") or "/"
    if not _APP_PATH.match(base) or base.startswith("//"):
        base = "/"
    query = {"n": f"{appid}:{gid}"}
    if platform and title_id:
        query["g"] = f"{platform}:{title_id}"
    target = f"{base}?{urlencode(query)}"

    def tag(prop: str, value: str | None) -> str:
        if not value:
            return ""
        return f'<meta property="{prop}" content="{html.escape(value, quote=True)}">'

    # The game first, unless the post's title already starts with it.
    named = game_name and title.casefold().startswith(game_name.casefold())
    heading = f"{game_name} — {title}" if game_name and not named else title
    page = (
        '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
        f"<title>{html.escape(heading)}</title>"
        f"{tag('og:type', 'article')}"
        f"{tag('og:site_name', 'Unlocked')}"
        f"{tag('og:title', heading)}"
        f"{tag('og:description', _news_excerpt(text)[:_DESCRIPTION_CHARS] if text else None)}"
        f"{tag('og:image', image)}"
        '<meta name="twitter:card" content="summary_large_image">'
        f'<meta http-equiv="refresh" content="0;url={html.escape(target, quote=True)}">'
        f"<script>location.replace({_js_string(target)})</script>"
        "</head><body></body></html>"
    )
    return web.Response(text=page, content_type="text/html")


def _js_string(value: str) -> str:
    """A string for the page's one script, safe inside `<script>`."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("<", "\\u003c")
    return f'"{escaped}"'
