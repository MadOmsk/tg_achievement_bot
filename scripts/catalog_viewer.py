"""A bare viewer of the games' store side (#147): achievement lists
(`titles`), their versions, DLC, HLTB entries, the sources' raw answers and
the fetch schedule, every link clickable — and the controls an operator needs
(collect a game now, ask a source again, fix a version's links, delete a
version). Pages read through their own read-only connection; the controls
write through `Repo`. Meant to grow into the operator's table of the games.

**No authentication yet** (owner, 2026-10-09: to be added before it is
anything but a dev tool) — whoever has the address can press every button.

Usage:
    .venv/Scripts/python.exe -X utf8 -m scripts.catalog_viewer            # the .env database
    .venv/Scripts/python.exe -X utf8 -m scripts.catalog_viewer --db data/test.db --port 8090
then open http://127.0.0.1:8090/
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import zlib
from html import escape
from pathlib import Path
from urllib.parse import quote, urlencode

from aiohttp import web

from bot.db.repo import Database, Repo

PAGE_SIZE = 100


def _db(request: web.Request) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{request.app['db_path']}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _repo(request: web.Request) -> Repo:
    return request.app["repo"]


def _back(to: str, message: str) -> web.HTTPFound:
    """Back where an answer came from, the message in the query (before any
    #anchor, or the browser would take it for part of the anchor)."""
    path, mark, anchor = to.partition("#")
    query = ("&" if "?" in path else "?") + urlencode({"msg": message})
    return web.HTTPFound(path + query + mark + anchor)


def _flash(request: web.Request) -> str:
    message = request.query.get("msg")
    return f"<p><b>{escape(message)}</b></p>" if message else ""


def _button(
    action: str, label: str, fields: dict[str, object] | None = None, confirm: str | None = None
) -> str:
    """A one-button form posting `fields` to `action`."""
    hidden = "".join(
        f'<input type=hidden name="{escape(k)}" value="{escape(str(v))}">'
        for k, v in (fields or {}).items()
    )
    ask = f' onsubmit="return confirm({escape(json.dumps(confirm))})"' if confirm else ""
    return (
        f'<form method=post action="{escape(action)}" style="display:inline"{ask}>'
        f"{hidden}<button>{escape(label)}</button></form> "
    )


def _page(title: str, body: str) -> web.Response:
    nav = (
        '<a href="/">home</a> · <a href="/games">games</a> · <a href="/review">review</a>'
        ' · <a href="/rules">rules</a> · <a href="/titles">titles</a>'
        ' · <a href="/versions">versions</a>'
        ' · <a href="/dlcs">dlcs</a> · <a href="/hltb">hltb</a> · <a href="/fetch">fetch state</a>'
        ' · <a href="/payloads">payloads</a> · <a href="/proposals">proposals</a>'
    )
    html = (
        "<!doctype html><meta charset=utf-8>"
        '<meta name=viewport content="width=device-width,initial-scale=1">'
        "<style>body{font:14px system-ui,sans-serif;margin:8px}"
        ".scroll{overflow-x:auto}"
        "table{border-collapse:collapse;font-size:13px}"
        "td,th{border:1px solid #ccc;padding:3px 5px;vertical-align:middle;text-align:left}"
        "table.versions td:nth-child(2){min-width:140px}"
        "table.versions img{max-width:64px;height:auto;max-height:40px}</style>"
        f"<title>{escape(title)}</title>"
        f"<p>{nav}</p><h1>{escape(title)}</h1>{body}"
    )
    return web.Response(text=html, content_type="text/html")


def _cell(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    return escape(text if len(text) <= 300 else text[:300] + "…")


def _table(rows: list[sqlite3.Row], links: dict[str, object] | None = None) -> str:
    """Rows as a table; `links[column]` makes that column a link (a function
    of the row giving the href)."""
    if not rows:
        return "<p>(none)</p>"
    links = links or {}
    columns = rows[0].keys()
    head = "".join(f"<th>{escape(c)}</th>" for c in columns)
    body = []
    for row in rows:
        cells = []
        for column in columns:
            text = _cell(row[column])
            href = links.get(column)
            target = href(row) if href is not None and row[column] is not None else ""  # type: ignore[operator]
            if target:
                text = f'<a href="{escape(target)}">{text}</a>'
            cells.append(f"<td>{text}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f"<div class=scroll><table><tr>{head}</tr>{''.join(body)}</table></div>"


def _record(row: sqlite3.Row | None, links: dict[str, object] | None = None) -> str:
    if row is None:
        return "<p>(not found)</p>"
    links = links or {}
    lines = []
    for column in row.keys():
        value = row[column]
        text = _cell(value)
        if isinstance(value, str) and value[:1] in "[{":
            try:
                text = (
                    "<pre>"
                    + escape(json.dumps(json.loads(value), ensure_ascii=False, indent=1))
                    + "</pre>"
                )
            except ValueError:
                pass
        href = links.get(column)
        if href is not None and value is not None:
            text = f'<a href="{escape(href(row))}">{text}</a>'  # type: ignore[operator]
        lines.append(f"<tr><th align=left valign=top>{escape(column)}</th><td>{text}</td></tr>")
    return f"<table>{''.join(lines)}</table>"


def _store_href(row: sqlite3.Row) -> str:
    """The version's own page on its store, or "" when no product is known
    (a stand-in): never a search (owner, 2026-10-11) — a name finds other
    games. A page of a product taken off sale is still its page."""
    if "stand_in" in row.keys() and row["stand_in"]:
        return ""
    store, product = row["store"], str(row["product_id"])
    if store == "xbox":
        return f"https://www.xbox.com/en-US/games/store/x/{product}"
    if store == "steam":
        return f"https://store.steampowered.com/app/{product}"
    if store == "psn":
        return f"https://store.playstation.com/en-us/concept/{product}"
    return ""


def _store_link(row: sqlite3.Row, label: str | None = None) -> str:
    """The store, linked to the version's page, said to be off sale when it
    is; no page known: said so, with no link."""
    label = label if label is not None else str(row["store"])
    href = _store_href(row)
    if not href:
        return f"{escape(label)} <small>(no store page)</small>"
    off = (
        " <small>(off sale)</small>"
        if "on_sale" in row.keys() and row["on_sale"] is not None and not row["on_sale"]
        else ""
    )
    return f'<a href="{escape(href)}" target=_blank>{escape(label)} ↗</a>{off}'


# A version's picture: its store's cover, else its achievement list's, else
# the picture of the HLTB entry it is linked to.
COVER = (
    "COALESCE(json_extract(v.media, '$.cover'), json_extract(v.media, '$.poster'),"
    # The list's cover as the bot keeps it on disk (#55): Xbox's 360 art
    # answers no https, so its address alone is no picture here.
    " (SELECT '/covers/' || t.cover_path FROM titles t WHERE t.platform = v.platform"
    "  AND t.title_id = v.title_id AND t.cover_path IS NOT NULL),"
    " (SELECT t.icon_url FROM titles t WHERE t.platform = v.platform"
    "  AND t.title_id = v.title_id),"
    " (SELECT h.image_url FROM version_hltb vh JOIN hltb_games h ON h.hltb_id = vh.hltb_id"
    "  WHERE vh.version_id = v.version_id AND h.image_url IS NOT NULL LIMIT 1)) AS cover"
)


def _img(url: object, height: int, title: str = "") -> str:
    """A picture by its address (an http one asked over https: the viewer is
    opened through a tunnel, and a browser blocks mixed content)."""
    if not url:
        return ""
    src = str(url)
    if src.startswith("http://"):
        src = "https://" + src[len("http://") :]
    return (
        f'<img src="{escape(src)}" height={height} loading=lazy referrerpolicy=no-referrer'
        f' title="{escape(title)}" style="vertical-align:middle;margin:2px">'
    )


def _dlc_href(row: sqlite3.Row) -> str:
    """A DLC on its store."""
    store, store_id = row["store"], row["store_id"]
    if not store_id:
        return "#"
    if store == "steam":
        return f"https://store.steampowered.com/app/{store_id}"
    if store == "xbox":
        return f"https://www.xbox.com/en-US/games/store/x/{store_id}"
    if store == "psn":
        return f"https://store.playstation.com/en-us/product/{store_id}"
    return "#"


def _edition_href(row: sqlite3.Row) -> str:
    """An edition on its store: an Xbox bundle's page, a Steam package's."""
    if row["store"] == "xbox":
        return f"https://www.xbox.com/en-US/games/store/x/{row['store_id']}"
    if row["store"] == "steam":
        return f"https://store.steampowered.com/sub/{row['store_id']}"
    return "#"


def _list_href(row: sqlite3.Row) -> str:
    return f"/list/{quote(str(row['platform']))}/{quote(str(row['title_id']))}"


def _title_href(row: sqlite3.Row) -> str:
    return f"/title/{quote(str(row['platform']))}/{quote(str(row['title_id']))}"


def _version_href(row: sqlite3.Row) -> str:
    return f"/version/{row['version_id']}"


def _hltb_href(row: sqlite3.Row) -> str:
    return f"/hltb/{row['hltb_id']}"


def _payload_href(row: sqlite3.Row) -> str:
    return "/payload?" + urlencode({"subject": row["subject"], "source": row["source"]})


def _search_form(action: str, q: str) -> str:
    return (
        f'<form action="{action}"><input name=q value="{escape(q)}" size=40>'
        " <button>search</button></form>"
    )


_HOME_LINKS = {
    "games": "/games",
    "game_versions": "/games",
    "match_pairs": "/review",
    "match_decisions": "/decisions",
    "titles": "/titles",
    "versions": "/versions",
    "version_store_ids": "/versions",
    "dlcs": "/dlcs",
    "hltb_games": "/hltb",
    "version_hltb": "/hltb",
    "source_payloads": "/payloads",
    "fetch_state": "/fetch",
}


async def home(request: web.Request) -> web.Response:
    with _db(request) as conn:
        counts = [
            (table, conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in (
                "games",
                "game_versions",
                "match_pairs",
                "match_decisions",
                "titles",
                "versions",
                "version_store_ids",
                "dlcs",
                "hltb_games",
                "version_hltb",
                "source_payloads",
                "fetch_state",
            )
        ]
    rows = "".join(
        f'<tr><td><a href="{_HOME_LINKS[t]}">{t}</a></td><td>{n}</td></tr>' for t, n in counts
    )
    return _page(
        "Games: the store side",
        _search_form("/titles", "") + f"<table>{rows}</table>",
    )


async def titles(request: web.Request) -> web.Response:
    q = request.query.get("q", "")
    with _db(request) as conn:
        rows = conn.execute(
            "SELECT t.platform, t.title_id, t.name, t.name_ru, t.hltb_id, t.steam_appid,"
            "  (SELECT COUNT(*) FROM versions v WHERE v.platform = t.platform"
            "   AND v.title_id = t.title_id) AS versions"
            " FROM titles t WHERE ? = '' OR t.name LIKE ? OR t.name_ru LIKE ? OR t.title_id = ?"
            " ORDER BY versions DESC, t.updated_at DESC LIMIT ?",
            (q, f"%{q}%", f"%{q}%", q, PAGE_SIZE),
        ).fetchall()
    return _page(
        "Achievement lists (titles)",
        _search_form("/titles", q)
        + _table(rows, {"title_id": _title_href, "name": _title_href, "hltb_id": _hltb_href}),
    )


async def title(request: web.Request) -> web.Response:
    platform, title_id = request.match_info["platform"], request.match_info["title_id"]
    with _db(request) as conn:
        row = conn.execute(
            "SELECT * FROM titles WHERE platform = ? AND title_id = ?", (platform, title_id)
        ).fetchone()
        versions = conn.execute(
            "SELECT version_id, store, product_id, console, name, kind, developer, publisher,"
            " release_date, also_on, store_group, origin FROM versions"
            " WHERE platform = ? AND title_id = ? ORDER BY console",
            (platform, title_id),
        ).fetchall()
        groups = conn.execute(
            "SELECT group_id, name, name_ru, total FROM title_groups WHERE title_id = ?",
            (title_id,),
        ).fetchall()
        prefix = {"steam": "steam:", "xbox_modern": "xbox_title:", "psn": "psn_list:"}.get(platform)
        subjects = [f"{prefix}{title_id}"] if prefix else []
        if row is not None and row["hltb_id"]:
            subjects.append(f"hltb:{row['hltb_id']}")
        state = (
            conn.execute(
                f"SELECT * FROM fetch_state WHERE subject IN ({','.join('?' * len(subjects))})",
                subjects,
            ).fetchall()
            if subjects
            else []
        )
    here = f"/title/{quote(platform)}/{quote(title_id)}"
    controls = (
        "<p>"
        + _button(f"{here}/collect", "collect (only what is due)")
        + _button(f"{here}/collect", "collect now (force)", {"force": 1})
        + _button(f"{here}/relink", "re-link into games")
        + "</p>"
    )
    resets = "".join(
        "<p>"
        + _button(
            "/fetch/due",
            f"ask {r['source']} again",
            {"subject": r["subject"], "source": r["source"], "back": here},
        )
        + f"{escape(r['subject'])}</p>"
        for r in state
    )
    body = (
        _flash(request)
        + controls
        + _record(row, {"hltb_id": _hltb_href})
        + "<h2>Versions (store products on one console)</h2>"
        + _table(versions, {"version_id": _version_href, "name": _version_href})
        + "<h2>PSN trophy groups</h2>"
        + _table(groups)
        + "<h2>Fetch state</h2>"
        + _table(state, {"subject": _payload_href})
        + resets
    )
    return _page(f"{platform} {title_id}", body)


async def versions(request: web.Request) -> web.Response:
    q = request.query.get("q", "")
    with _db(request) as conn:
        rows = conn.execute(
            "SELECT v.version_id, v.store, v.product_id, v.stand_in,"
            " v.console, v.name, v.platform, v.title_id, v.kind, v.release_date, v.origin"
            " FROM versions v"
            " WHERE ? = '' OR name LIKE ? OR product_id = ? OR store_group = ?"
            " ORDER BY updated_at DESC LIMIT ?",
            (q, f"%{q}%", q, q, PAGE_SIZE),
        ).fetchall()
    return _page(
        "Versions",
        _search_form("/versions", q) + _table(rows, _VERSION_LINKS),
    )


async def version(request: web.Request) -> web.Response:
    version_id = int(request.match_info["version_id"])
    with _db(request) as conn:
        row = conn.execute(
            "SELECT v.* FROM versions v WHERE v.version_id = ?", (version_id,)
        ).fetchone()
        ids = conn.execute(
            "SELECT store, store_id, source FROM version_store_ids WHERE version_id = ?",
            (version_id,),
        ).fetchall()
        dlcs = conn.execute(
            "SELECT dlc_id, store_id, trophy_group_id, name, kind, release_date FROM dlcs"
            " WHERE version_id = ? ORDER BY release_date, name",
            (version_id,),
        ).fetchall()
        hltb = conn.execute(
            "SELECT h.hltb_id, h.name, h.game_type, vh.source FROM version_hltb vh"
            " JOIN hltb_games h ON h.hltb_id = vh.hltb_id WHERE vh.version_id = ?",
            (version_id,),
        ).fetchall()
        siblings = (
            conn.execute(
                "SELECT version_id, store, console, name, platform, title_id FROM versions"
                " WHERE store_group = ? AND version_id <> ?",
                (row["store_group"], version_id),
            ).fetchall()
            if row is not None and row["store_group"]
            else []
        )
        demo_of = conn.execute(
            "SELECT of_version_id, role FROM game_versions WHERE version_id = ?"
            " AND of_version_id IS NOT NULL",
            (version_id,),
        ).fetchone()
        pictures = conn.execute(
            "SELECT v.media,"
            " (SELECT t.icon_url FROM titles t WHERE t.platform = v.platform"
            "  AND t.title_id = v.title_id) AS list_icon,"
            " (SELECT '/covers/' || t.cover_path FROM titles t WHERE t.platform = v.platform"
            "  AND t.title_id = v.title_id) AS list_cover,"
            " (SELECT h.image_url FROM version_hltb vh JOIN hltb_games h"
            "  ON h.hltb_id = vh.hltb_id WHERE vh.version_id = v.version_id"
            "  AND h.image_url IS NOT NULL LIMIT 1) AS hltb_image"
            " FROM versions v WHERE v.version_id = ?",
            (version_id,),
        ).fetchone()
        games = conn.execute(
            "SELECT gv.game_id, g.name, gv.role, gv.p FROM game_versions gv"
            " JOIN games g ON g.game_id = gv.game_id WHERE gv.version_id = ?",
            (version_id,),
        ).fetchall()
        labels = conn.execute(
            "SELECT d.version_id, d.relation, d.other_id, v.name AS other, d.decided_at"
            " FROM match_decisions d JOIN versions v ON v.version_id ="
            "  CASE WHEN d.version_id = ? THEN d.other_id ELSE d.version_id END"
            " WHERE d.version_id = ? OR d.other_id = ?",
            (version_id, version_id, version_id),
        ).fetchall()
        payloads = (
            conn.execute(
                "SELECT subject, source, fetched_at, length(payload) AS bytes FROM source_payloads"
                " WHERE subject LIKE ?",
                (f"%{row['product_id']}%",),
            ).fetchall()
            if row is not None
            else []
        )
    here = f"/version/{version_id}"
    controls = ""
    if row is not None:
        controls = (
            '<form method=post action="' + here + '/title">achievement list: '
            f'<input name=platform value="{escape(row["platform"] or "")}" size=12> '
            f'<input name=title_id value="{escape(row["title_id"] or "")}" size=16> '
            "<button>set</button> (empty both to clear)</form>"
            + '<form method=post action="'
            + here
            + '/hltb">link HLTB id: '
            "<input name=hltb_id size=10> <button>link</button></form>"
            + "<p>"
            + _button(
                f"{here}/delete",
                "delete this version",
                confirm="Delete this version, its DLC and links?",
            )
            + "</p>"
        )
    unlinks = "".join(
        "<p>"
        + _button(f"{here}/hltb/{h['hltb_id']}/unlink", f"unlink HLTB {h['hltb_id']}")
        + "</p>"
        for h in hltb
    )
    body = (
        _flash(request)
        + _pictures(pictures)
        + controls
        + (
            f"<p>{_store_link(row, 'on the store')}"
            + (
                f' · <a href="{escape(_list_href(row))}">its achievements</a>'
                if row["title_id"]
                else ""
            )
            + (
                f" · {escape(demo_of['role'])} of"
                f' <a href="/version/{demo_of["of_version_id"]}">version'
                f" {demo_of['of_version_id']}</a>"
                if demo_of
                else ""
            )
            + "</p>"
            if row is not None
            else ""
        )
        + _record(row, {"title_id": _title_href})
        + "<h2>Game</h2>"
        + _table(games, {"game_id": _game_href, "name": _game_href})
        + "<h2>The operator's labels</h2>"
        + _table(
            labels,
            {
                "version_id": lambda r: f"/version/{r['version_id']}",
                "other_id": lambda r: f"/version/{r['other_id']}",
            },
        )
        + "<h2>Store ids</h2>"
        + _table(ids)
        + "<h2>Same store group (the store's own grouping)</h2>"
        + _table(
            siblings, {"version_id": _version_href, "name": _version_href, "title_id": _title_href}
        )
        + "<h2>DLC</h2>"
        + _table(dlcs)
        + "<h2>HLTB</h2>"
        + _table(hltb, {"hltb_id": _hltb_href, "name": _hltb_href})
        + unlinks
        + "<h2>Raw answers</h2>"
        + _table(payloads, {"subject": _payload_href})
    )
    return _page(f"Version {version_id}", body)


async def dlcs(request: web.Request) -> web.Response:
    q = request.query.get("q", "")
    with _db(request) as conn:
        rows = conn.execute(
            "SELECT d.dlc_id, d.version_id, v.name AS game, v.console, d.name, d.kind,"
            " d.release_date, d.store_id, d.trophy_group_id FROM dlcs d"
            " JOIN versions v ON v.version_id = d.version_id"
            " WHERE ? = '' OR d.name LIKE ? OR v.name LIKE ? ORDER BY d.updated_at DESC LIMIT ?",
            (q, f"%{q}%", f"%{q}%", PAGE_SIZE),
        ).fetchall()
    return _page(
        "DLC",
        _search_form("/dlcs", q)
        + _table(rows, {"version_id": _version_href, "game": _version_href}),
    )


async def hltb_list(request: web.Request) -> web.Response:
    with _db(request) as conn:
        rows = conn.execute(
            "SELECT hltb_id, name, game_type, parent_hltb_id, developer, release_year, checked_at"
            " FROM hltb_games ORDER BY checked_at DESC LIMIT ?",
            (PAGE_SIZE,),
        ).fetchall()
    return _page("HLTB entries", _table(rows, {"hltb_id": _hltb_href, "name": _hltb_href}))


async def hltb_entry(request: web.Request) -> web.Response:
    hltb_id = int(request.match_info["hltb_id"])
    with _db(request) as conn:
        row = conn.execute("SELECT * FROM hltb_games WHERE hltb_id = ?", (hltb_id,)).fetchone()
        children = conn.execute(
            "SELECT hltb_id, name, game_type, times FROM hltb_games WHERE parent_hltb_id = ?",
            (hltb_id,),
        ).fetchall()
        linked = conn.execute(
            "SELECT v.version_id, v.store, v.console, v.name, v.platform, v.title_id, vh.source"
            " FROM version_hltb vh JOIN versions v ON v.version_id = vh.version_id"
            " WHERE vh.hltb_id = ?",
            (hltb_id,),
        ).fetchall()
        titles_ = conn.execute(
            "SELECT platform, title_id, name FROM titles WHERE hltb_id = ?", (hltb_id,)
        ).fetchall()
    body = (
        _record(row, {"parent_hltb_id": lambda r: f"/hltb/{r['parent_hltb_id']}"})
        + "<h2>DLC and expansions</h2>"
        + _table(children, {"hltb_id": _hltb_href, "name": _hltb_href})
        + "<h2>Versions linked</h2>"
        + _table(
            linked, {"version_id": _version_href, "name": _version_href, "title_id": _title_href}
        )
        + "<h2>Achievement lists matched to it (titles.hltb_id)</h2>"
        + _table(titles_, {"title_id": _title_href, "name": _title_href})
        + f'<p><a href="/payload?subject=hltb:{hltb_id}&source=hltb_page">raw page</a></p>'
    )
    return _page(f"HLTB {hltb_id}", body)


async def fetch(request: web.Request) -> web.Response:
    with _db(request) as conn:
        rows = conn.execute(
            "SELECT subject, source, status, attempts, interval_days, checked_at, next_check_at,"
            " last_error FROM fetch_state ORDER BY checked_at DESC LIMIT ?",
            (PAGE_SIZE * 3,),
        ).fetchall()
    buttons = "".join(
        "<p>"
        + _button(
            "/fetch/due",
            "ask again",
            {"subject": r["subject"], "source": r["source"], "back": "/fetch"},
        )
        + f"{escape(r['subject'])} · {escape(r['source'])}</p>"
        for r in rows
        if r["status"] != "ok" or r["interval_days"] > 7
    )
    return _page(
        "Fetch state",
        _flash(request) + _table(rows, {"subject": _payload_href}) + "<h2>Ask again</h2>" + buttons,
    )


async def payloads(request: web.Request) -> web.Response:
    with _db(request) as conn:
        rows = conn.execute(
            "SELECT subject, source, fetched_at, length(payload) AS bytes FROM source_payloads"
            " ORDER BY fetched_at DESC LIMIT ?",
            (PAGE_SIZE * 3,),
        ).fetchall()
    return _page("Raw answers", _table(rows, {"subject": _payload_href}))


async def payload(request: web.Request) -> web.Response:
    subject, source = request.query.get("subject", ""), request.query.get("source", "")
    with _db(request) as conn:
        row = conn.execute(
            "SELECT payload, fetched_at FROM source_payloads WHERE subject = ? AND source = ?",
            (subject, source),
        ).fetchone()
    if row is None:
        return _page(f"{subject} · {source}", "<p>(no answer kept)</p>")
    data = json.loads(zlib.decompress(row["payload"]).decode("utf-8"))
    text = json.dumps(data, ensure_ascii=False, indent=1)
    return _page(
        f"{subject} · {source}",
        f"<p>fetched {escape(row['fetched_at'])}</p><pre>{escape(text)}</pre>",
    )


async def collect(request: web.Request) -> web.Response:
    platform, title_id = request.match_info["platform"], request.match_info["title_id"]
    form = await request.post()
    collector = request.app["collector"]
    report = await collector.collect(platform, title_id, force=bool(form.get("force")))
    message = (
        f"asked: {', '.join(report.asked) or 'nothing (not due)'}; versions {report.versions};"
        f" dlc named {report.dlcs}; hltb {report.hltb_id}"
        + (f"; errors: {'; '.join(report.errors)}" if report.errors else "")
    )
    raise _back(f"/title/{quote(platform)}/{quote(title_id)}", message)


async def fetch_due(request: web.Request) -> web.Response:
    form = await request.post()
    await _repo(request).make_fetch_due(str(form["subject"]), str(form["source"]))
    raise _back(str(form.get("back") or "/fetch"), f"{form['subject']} will be asked again")


async def version_title(request: web.Request) -> web.Response:
    version_id = int(request.match_info["version_id"])
    form = await request.post()
    platform = str(form.get("platform") or "").strip() or None
    title_id = str(form.get("title_id") or "").strip() or None
    await _repo(request).set_version_title(version_id, platform, title_id)
    raise _back(f"/version/{version_id}", f"achievement list: {platform} {title_id}")


async def version_hltb_link(request: web.Request) -> web.Response:
    version_id = int(request.match_info["version_id"])
    form = await request.post()
    raw = str(form.get("hltb_id") or "").strip()
    if not raw.isdigit():
        raise _back(f"/version/{version_id}", "an HLTB id is a number")
    await _repo(request).link_version_hltb(version_id, int(raw), "manual")
    raise _back(f"/version/{version_id}", f"linked HLTB {raw}")


async def version_hltb_unlink(request: web.Request) -> web.Response:
    version_id = int(request.match_info["version_id"])
    hltb_id = int(request.match_info["hltb_id"])
    await _repo(request).unlink_version_hltb(version_id, hltb_id)
    raise _back(f"/version/{version_id}", f"unlinked HLTB {hltb_id}")


async def version_delete(request: web.Request) -> web.Response:
    version_id = int(request.match_info["version_id"])
    await _repo(request).delete_version(version_id)
    raise _back("/versions", f"version {version_id} deleted")


def _game_href(row: sqlite3.Row) -> str:
    return f"/game/{row['game_id']}"


_VERSION_LINKS = {
    "version_id": _version_href,
    "name": _version_href,
    "store": _store_href,
    "product_id": _store_href,
    "title_id": _title_href,
    "achievements": _list_href,
    "demo_of": lambda r: f"/version/{r['demo_of']}",
}


# The operator's answers, quick ones first (owner, 2026-10-11: the review
# should take a tap; everything else is a step further). About two versions:
_DECISIONS_QUICK = (
    ("same", "same game"),
    ("other", "a different game"),
    ("remaster_of", "a remaster of it"),
    ("remake_of", "a remake of it"),
)
_DECISIONS_MORE = (
    ("remaster_of:flip", "⇄ it is a remaster of this"),
    ("remake_of:flip", "⇄ it is a remake of this"),
    ("demo_of", "a demo of it"),
    ("demo_of:flip", "⇄ it is a demo of this"),
    ("tool_of", "a tool for it"),
    ("tool_of:flip", "⇄ it is a tool for this"),
    ("mode_of", "a mode of it (a launcher of one of its modes)"),
    ("mode_of:flip", "⇄ it is a mode of this"),
    ("series", "another game of its series"),
    ("skip", "skip: ask again later"),
)

# …about two games ("this game … that game"); the quick ones are the model's
# guess, "another of the series" (a label that relates nothing but tells the
# model it mixed up a series) and "skip" (asked again later).
_GAME_DECISIONS = (
    ("remaster_of", "this is a remaster of that"),
    ("remaster_of:flip", "that is a remaster of this"),
    ("remake_of", "this is a remake of that"),
    ("remake_of:flip", "that is a remake of this"),
    ("contains", "this compilation holds that"),
    ("contains:flip", "that compilation holds this"),
    ("vr_of", "this is the VR version of that"),
    ("vr_of:flip", "that is the VR version of this"),
    ("series", "another game of the series"),
    ("other", "not related"),
    ("same", "one game after all"),
)
_GUESS_WORDS = {
    "remaster_of": "this is a remaster of that",
    "remake_of": "this is a remake of that",
    "contains": "this compilation holds that",
    "vr_of": "this is the VR version of that",
}


def _answer_forms(
    action: str,
    hidden: dict[str, object],
    quick: list[tuple[str, str]],
    more: tuple[tuple[str, str], ...],
    back: str,
) -> str:
    """Quick answers as buttons, one a line (owner, 2026-10-12), the rest a
    step further under "more…". A quick label is HTML (its parts in bold);
    the "more…" ones are plain text, as an <option> shows no markup."""
    fields = "".join(
        f'<input type=hidden name={k} value="{escape(str(v))}">'
        for k, v in {**hidden, "back": back}.items()
    )
    buttons = "".join(
        f'<form method=post action="{action}" style="display:block;margin:0 0 4px">{fields}'
        f'<input type=hidden name=decision value="{key}">'
        f'<button style="width:100%;text-align:left">{label}</button></form>'
        for key, label in quick
    )
    options = "".join(f'<option value="{k}">{escape(lbl)}</option>' for k, lbl in more)
    rest = (
        f"<details><summary><small>more…</small></summary>"
        f'<form method=post action="{action}" style="margin:0">{fields}'
        "<select name=decision required><option value='' selected disabled>answer…</option>"
        f"{options}</select> <button>ok</button></form></details>"
    )
    return f"<div>{buttons}</div>{rest}"


def _relation_sentence(decision: str, this: str, that: str, *, html: bool = True) -> str:
    """A decision about two games ("this … that", ":flip" the other way round)
    as a sentence naming both (owner, 2026-10-12: "first/second" was unclear).
    As HTML the names are escaped and only the relation is bold (owner,
    2026-10-12); `html=False` is the plain text an <option> takes."""
    relation, _, flip = decision.partition(":")
    a, b = (f"«{that}»", f"«{this}»") if flip else (f"«{this}»", f"«{that}»")
    if html:
        a, b = escape(a), escape(b)

    def bold(words: str) -> str:
        return f"<b>{escape(words)}</b>" if html else words

    return {
        "same": f"{a} and {b} are {bold('one game')}",
        "series": f"{a} and {b} are {bold('different games of one series')}",
        "other": f"{a} and {b} are {bold('not related')}",
        "remaster_of": f"{a} is a {bold('remaster')} of {b}",
        "remake_of": f"{a} is a {bold('remake')} of {b}",
        "contains": f"{a} is a {bold('compilation that holds')} {b}",
        "vr_of": f"{a} is the {bold('VR version')} of {b}",
    }.get(relation, f"{a} {bold(relation)} {b}")


def _game_name(conn: sqlite3.Connection, game_id: int) -> str:
    row = conn.execute("SELECT name FROM games WHERE game_id = ?", (game_id,)).fetchone()
    return str(row[0]) if row and row[0] else f"game {game_id}"


def _game_picker(
    game_id: int,
    other_game: int,
    back: str,
    guess: str = "",
    names: tuple[str, str] | None = None,
) -> str:
    """The answers about two games: the model's guess, another of the series,
    skip — the rest under "more…". With the games' names every button says
    what it records."""
    this, that = names or ("this game", "that game")
    quick = []
    if guess in _GUESS_WORDS:
        quick.append((guess, f"✓ <b>Model</b>: {_relation_sentence(guess, this, that)}"))
    quick += [("series", "another game of the series"), ("skip", "ask later")]
    return _answer_forms(
        "/decide-games",
        {"game_id": game_id, "other_game": other_game},
        quick,
        tuple(
            (key, _relation_sentence(key, this, that, html=False) if names else label)
            for key, label in _GAME_DECISIONS
        ),
        back,
    )


def _decision_picker(version_id: int, other_id: int, back: str) -> str:
    """The answers about two versions: one game, another game, a remaster, a
    remake — the rest under "more…"."""
    return _answer_forms(
        "/decide",
        {"version_id": version_id, "other_id": other_id},
        [(key, escape(label)) for key, label in _DECISIONS_QUICK],
        _DECISIONS_MORE,
        back,
    )


async def rules(request: web.Request) -> web.Response:
    """The model's signs and each class's weight for each, as it decides now."""
    from bot.services import game_match as m

    signs = list(dict.fromkeys(k for c in m.CLASSES for k in m.WEIGHTS[c]))
    head = "".join(f"<th>{escape(c)}</th>" for c in m.CLASSES)
    rows = "".join(
        f"<tr><td>{escape(k)}</td>"
        + "".join(
            f"<td align=right>{m.WEIGHTS[c][k]:+.1f}</td>" if k in m.WEIGHTS[c] else "<td></td>"
            for c in m.CLASSES
        )
        + "</tr>"
        for k in signs
    )
    body = (
        "<p>Each pair of versions that could be one game (a telling word of the name, a"
        " store's group or cross-gen set, an HLTB entry, one list) is read from its subject's"
        " side — the VR one, the compilation, the later one — and every sign adds its weight"
        " to each class's log-odds against <b>other</b> (0). A softmax gives probabilities."
        f" The likeliest class at {m.LINK_P:.0%} or more, {m.CLOSE_CALL:.0%} ahead of the next,"
        f" is taken; a class from {m.REVIEW_P:.0%} goes to the review list. Versions join"
        f" one game from the surest pair down, never across a pair below {m.VETO_P:.0%}"
        " <i>same</i> or a label saying no; a remaster, remake or VR version relates to the"
        " earliest original, a compilation to each part. The operator's labels come first,"
        f" and are what the weights will be fitted to. Model: {escape(m.MODEL)}.</p>"
        "<p>name = similarity − 0.8; years_gap counts the years past the first (at most 9);"
        f" achievements are compared when both lists have {m.ACHIEVEMENTS_MIN}+ names.</p>"
        f"<div class=scroll><table><tr><th>sign</th>{head}</tr>{rows}</table></div>"
    )
    return _page("How versions are matched", body)


def _achievements_link(v: sqlite3.Row) -> str:
    """A version's achievements: its list, or for a Steam app nobody here
    has, the names its schema gives (what the matcher compares)."""
    if v["title_id"]:
        return f'<a href="{escape(_list_href(v))}">list</a>'
    if v["store"] == "steam":
        return f'<a href="/steam-schema/{quote(str(v["product_id"]))}">schema</a>'
    return ""


async def steam_schema(request: web.Request) -> web.Response:
    """A Steam app's achievement names, as its schema gives them."""
    appid = request.match_info["appid"]
    with _db(request) as conn:
        row = conn.execute(
            "SELECT payload FROM source_payloads WHERE subject = ? AND source = 'steam_schema'",
            (f"steam_schema:{appid}",),
        ).fetchone()
    names = json.loads(zlib.decompress(row["payload"])) if row else []
    body = (
        f'<p><a href="https://store.steampowered.com/app/{escape(appid)}" target=_blank>'
        f"Steam {escape(appid)} ↗</a> · {len(names)} achievements in its schema"
        " (nobody here has played it: names only)</p>"
        + (
            "<ol>" + "".join(f"<li>{escape(str(n))}</li>" for n in names) + "</ol>"
            if names
            else "<p>(no schema read)</p>"
        )
    )
    return _page(f"Steam {appid}: achievements", body)


async def achievement_list(request: web.Request) -> web.Response:
    """Every achievement of one list, as the catalog keeps them."""
    platform, title_id = request.match_info["platform"], request.match_info["title_id"]
    with _db(request) as conn:
        rows = conn.execute(
            "SELECT achievement_id, name_en, name_ru, description_en, rarity_percent, listed"
            " FROM title_achievements WHERE platform = ? AND title_id = ?"
            " ORDER BY listed DESC, name_en",
            (platform, title_id),
        ).fetchall()
        title = conn.execute(
            "SELECT name FROM titles WHERE platform = ? AND title_id = ?", (platform, title_id)
        ).fetchone()
    listed = sum(1 for r in rows if r["listed"])
    name = title["name"] if title else title_id
    body = (
        f'<p><a href="/title/{quote(platform)}/{quote(title_id)}">{escape(platform)} '
        f"{escape(title_id)}</a> · {len(rows)} known, {listed} from the full list"
        " (listed = 1)</p>" + _table(rows)
    )
    return _page(f"Achievements: {name}", body)


async def games(request: web.Request) -> web.Response:
    q = request.query.get("q", "")
    with _db(request) as conn:
        rows = conn.execute(
            "SELECT g.game_id, g.name, g.kind, g.year, g.developer, g.name_source,"
            "  (SELECT COUNT(*) FROM game_versions gv WHERE gv.game_id = g.game_id) AS versions,"
            "  (SELECT COUNT(*) FROM match_pairs mp JOIN game_versions gv"
            "   ON gv.version_id IN (mp.version_id, mp.other_id)"
            "   WHERE gv.game_id = g.game_id) AS review,"
            "  (SELECT GROUP_CONCAT(r.kind || ' ' || r.related_id) FROM game_relations r"
            "   WHERE r.game_id = g.game_id) AS relates,"
            "  (SELECT GROUP_CONCAT(DISTINCT v.console) FROM game_versions gv"
            "   JOIN versions v ON v.version_id = gv.version_id"
            "   WHERE gv.game_id = g.game_id) AS consoles"
            " FROM games g WHERE g.merged_into IS NULL AND (? = '' OR g.name LIKE ?)"
            " ORDER BY versions DESC, g.game_id DESC LIMIT ?",
            (q, f"%{q}%", PAGE_SIZE * 3),
        ).fetchall()
    return _page(
        "Games",
        _flash(request)
        + _search_form("/games", q)
        + _table(
            [{**dict(r), "kind": _KIND_BADGES.get(r["kind"], "")} for r in rows],
            {"game_id": _game_href, "name": _game_href},
        ),
    )


async def game(request: web.Request) -> web.Response:
    game_id = int(request.match_info["game_id"])
    with _db(request) as conn:
        row = conn.execute("SELECT * FROM games WHERE game_id = ?", (game_id,)).fetchone()
        members = conn.execute(
            "SELECT gv.version_id, v.store, v.product_id, v.stand_in, v.on_sale,"
            " v.console, v.name, v.release_date, v.developer, v.platform, v.title_id,"
            " " + COVER + ", gv.role, gv.of_version_id, gv.p"
            " FROM game_versions gv JOIN versions v ON v.version_id = gv.version_id"
            " WHERE gv.game_id = ? ORDER BY v.release_date, v.console",
            (game_id,),
        ).fetchall()
        relations = conn.execute(
            "SELECT 'this ' || r.kind AS relation, r.related_id AS game_id, g.name, g.year,"
            " r.source, ROUND(r.p, 2) AS p FROM game_relations r"
            " JOIN games g ON g.game_id = r.related_id WHERE r.game_id = ?"
            " UNION ALL SELECT r.kind || ' this', r.game_id, g.name, g.year, r.source,"
            " ROUND(r.p, 2)"
            " FROM game_relations r JOIN games g ON g.game_id = r.game_id WHERE r.related_id = ?",
            (game_id, game_id),
        ).fetchall()
        mine = [m["version_id"] for m in members]
        marks = ",".join("?" * len(mine)) or "NULL"
        pairs = conn.execute(
            "SELECT mp.version_id AS subject, mp.other_id AS other, mp.relation, mp.p,"
            " mp.features FROM match_pairs mp"
            f" WHERE mp.version_id IN ({marks}) OR mp.other_id IN ({marks})"
            " ORDER BY mp.p DESC",
            (*mine, *mine),
        ).fetchall()
        labels = conn.execute(
            "SELECT d.version_id, d.relation, d.other_id, d.decided_at FROM match_decisions d"
            f" WHERE d.version_id IN ({marks}) OR d.other_id IN ({marks})",
            (*mine, *mine),
        ).fetchall()
        dlcs = conn.execute(
            "SELECT d.version_id, v.store, v.console, v.name AS version, v.product_id,"
            " v.stand_in, d.dlc_id, d.name, d.kind, d.release_date, d.store_id,"
            " d.trophy_group_id FROM dlcs d"
            " JOIN game_versions gv ON gv.version_id = d.version_id"
            " JOIN versions v ON v.version_id = d.version_id WHERE gv.game_id = ?"
            " ORDER BY v.store, v.console, d.version_id, d.release_date, d.name",
            (game_id,),
        ).fetchall()
        editions = conn.execute(
            "SELECT DISTINCT e.edition_id, e.store, e.store_id, e.name, e.kind, e.on_sale,"
            " e.first_seen_at, e.last_seen_at,"
            " (SELECT GROUP_CONCAT(COALESCE(i2.name, i2.store_id) || ' [' || i2.item_kind || ']',"
            "  '; ') FROM edition_items i2 WHERE i2.edition_id = e.edition_id) AS holds"
            " FROM editions e JOIN edition_items i ON i.edition_id = e.edition_id"
            " JOIN game_versions gv ON gv.version_id = i.version_id"
            " WHERE gv.game_id = ? ORDER BY e.store, e.name",
            (game_id,),
        ).fetchall()
        hltb = conn.execute(
            # HLTB's platforms: where the game also came out, as no store
            # we read says (Nintendo, older consoles, PC outside Steam).
            "SELECT DISTINCT h.hltb_id, h.name, h.game_type, h.release_year,"
            " h.platforms AS also_released_on FROM version_hltb vh"
            " JOIN hltb_games h ON h.hltb_id = vh.hltb_id"
            " JOIN game_versions gv ON gv.version_id = vh.version_id"
            " WHERE gv.game_id = ?",
            (game_id,),
        ).fetchall()
    here = f"/game/{game_id}"
    controls = ""
    if row is not None:
        controls = (
            f'<form method=post action="{here}/rename">name: '
            f'<input name=name value="{escape(row["name"])}" size=40> '
            f'ru: <input name=name_ru value="{escape(row["name_ru"] or "")}" size=30> '
            "<button>rename</button></form>"
            f'<form method=post action="{here}/merge">merge this game into game id: '
            "<input name=into size=8> <button>merge</button></form>"
            f'<form method=post action="{here}/kind">this is '
            + "".join(
                f'<label><input type=radio name=kind value="{k}"'
                + (" checked" if row["kind"] == k else "")
                + f"> {escape(w)}</label> "
                for k, w in _KIND_WORDS.items()
            )
            + "<label><input type=radio name=kind value=''> the linker decides</label> "
            + f"<button>set</button> <small>({escape(row['kind_source'])})</small></form>"
            f'<form method=post action="{here}/relate">this game is a '
            "<select name=kind><option>remaster_of</option><option>remake_of</option>"
            "<option>vr_of</option><option>contains</option></select> game id: "
            "<input name=related size=8> <button>link</button></form>"
        )
    detach = "".join(
        "<p>"
        + _button(
            f"{here}/detach",
            f"detach version {m['version_id']} ({m['console']})",
            {"version_id": m["version_id"]},
        )
        + "</p>"
        for m in members
    )
    parts = ""
    if row is not None and row["kind"] == "compilation":
        held = [r for r in relations if r["relation"] == "this contains"]
        parts = (
            "<h2>Parts</h2>"
            + f"<p>parts found: {len(held)}"
            + (" — <b>⚠ a compilation holds two games or more</b>" if len(held) < 2 else "")
            + "</p>"
            + "".join(
                f'<li><a href="/game/{r["game_id"]}">{escape(r["name"])}</a></li>' for r in held
            )
        )
    with _db(request) as conn:
        identity = _identity(conn, game_id)
        cards = _pair_rows(conn, pairs, here)
    body = (
        _flash(request)
        + f"<p><b>{escape(identity)}</b></p>"
        + "<p>"
        + "".join(_img(m["cover"], 56, m["console"]) for m in members if m["cover"])
        + "</p>"
        + controls
        + _record(row, {"merged_into": lambda r: f"/game/{r['merged_into']}"})
        + "<h2>Versions</h2>"
        + _version_cards(members)
        + parts
        + "<h2>Family: related games</h2>"
        + _table(relations, {"game_id": _game_href, "name": _game_href})
        + "".join(
            "<p>"
            + _button(
                f"{here}/unrelate",
                f"not related to game {r['game_id']}",
                {"other_game": r["game_id"]},
            )
            + "</p>"
            for r in relations
        )
        + ("<h2>To review</h2>" + cards if pairs else "")
        + "<h2>The operator's labels on these versions</h2>"
        + _table(
            labels,
            {
                "version_id": lambda r: f"/version/{r['version_id']}",
                "other_id": lambda r: f"/version/{r['other_id']}",
            },
        )
        + "<h2>Editions (packs the stores sell)</h2>"
        + _table(editions, {"name": _edition_href, "store_id": _edition_href})
        + "<h2>DLC, by version</h2>"
        + _dlcs_by_version(dlcs)
        + "<h2>HLTB</h2>"
        + _table(hltb, {"hltb_id": _hltb_href, "name": _hltb_href})
        + "<h2>Detach</h2>"
        + detach
    )
    return _page(row["name"] if row else f"Game {game_id}", body)


def _identity(conn: sqlite3.Connection, game_id: int) -> str:
    """Which game this is, in one line: its name, year, developer and
    publisher as the game keeps them (`game_match.game_facts`)."""
    row = conn.execute(
        "SELECT name, year, last_year, developer, publisher, more_developers,"
        " more_publishers, kind FROM games WHERE game_id = ?",
        (game_id,),
    ).fetchone()
    if row is None:
        return f"game {game_id}"
    year = str(row["year"] or "year ?")
    if row["year"] and row["last_year"] and row["last_year"] > row["year"]:
        # Its versions came out over years: the first, to the latest.
        year = f"{row['year']}–{row['last_year']}"
    parts = [str(row["name"]), year]
    for field in ("developer", "publisher"):
        if row[field]:
            parts.append(str(row[field]) + (" и другие" if row[f"more_{field}s"] else ""))
    badge = _KIND_BADGES.get(row["kind"], "")
    return f"{' · '.join(parts)} (game {game_id})" + (f" {badge}" if badge else "")


# What a game is (owner, 2026-10-12), as a badge beside its name.
_KIND_BADGES = {"compilation": "📦 compilation", "extra": "🎵 not a game"}
_KIND_WORDS = {"game": "a game", "compilation": "a compilation", "extra": "not a game"}


def _version_cards(rows: list[sqlite3.Row]) -> str:
    """A game's versions as one compact table: the picture, what it is, its
    role (and the version a demo or tool is of), where it is sold."""
    if not rows:
        return "<p>(none)</p>"
    head = ["", "name", "role", "console", "date", "store", "studio", "p", "list"]
    lines = []
    for v in rows:
        role = escape(v["role"])
        if v["of_version_id"]:
            role += (
                f'<br><small>of <a href="/version/{v["of_version_id"]}">'
                f"{v['of_version_id']}</a></small>"
            )

        cells = [
            _img(v["cover"], 36),
            f'<a href="/version/{v["version_id"]}">{escape(v["name"] or "")}</a>',
            role,
            escape(v["console"]),
            escape(v["release_date"] or "?"),
            _store_link(v),
            escape(v["developer"] or ""),
            f"{v['p']:.2f}" if v["p"] is not None else "",
            _achievements_link(v),
        ]
        lines.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
    return (
        "<div class=scroll><table class=versions><tr>"
        + "".join(f"<th>{h}</th>" for h in head)
        + "</tr>"
        + "".join(lines)
        + "</table></div>"
    )


def _pair_rows(conn: sqlite3.Connection, pairs: list[sqlite3.Row], back: str) -> str:
    """Doubtful pairs as one table: the subject and its game, what the model
    thinks and how sure, the other and its game, and the answer."""
    if not pairs:
        return "<p>(nothing to review)</p>"
    ids = sorted({r["subject"] for r in pairs} | {r["other"] for r in pairs})
    marks = ",".join("?" * len(ids))
    info = {
        r["version_id"]: r
        for r in conn.execute(
            "SELECT v.version_id, v.name, v.console, v.release_date, v.store, v.product_id,"
            " v.stand_in, v.on_sale, v.developer, " + COVER + ", gv.game_id, g.name AS game,"
            " g.year"
            " FROM versions v LEFT JOIN game_versions gv ON gv.version_id = v.version_id"
            " LEFT JOIN games g ON g.game_id = gv.game_id"
            f" WHERE v.version_id IN ({marks})",
            ids,
        ).fetchall()
    }

    def side(vid: int) -> str:
        v = info.get(vid)
        if v is None:
            return str(vid)
        game = (
            f'<br><small>in <a href="/game/{v["game_id"]}">{escape(v["game"] or "")}'
            f" ({v['year'] or '?'})</a></small>"
            if v["game_id"]
            else ""
        )

        return (
            f"{_img(v['cover'], 36)} "
            f'<a href="/version/{vid}">{escape(v["name"] or "")}</a>'
            f" <small>[{escape(v['console'])}, {escape((v['release_date'] or '?')[:4])},"
            f" {escape(v['developer'] or '?')}]"
            f" {_store_link(v)}</small>{game}"
        )

    lines = []
    for r in pairs:
        feats = json.loads(r["features"]) if r["features"] else {}
        signs = ", ".join(k for k in feats if k != "bias")
        lines.append(
            f"<tr><td>{side(r['subject'])}</td>"
            f"<td><b>{escape(r['relation'])}</b> {r['p']:.2f}"
            f"<br><small>{escape(signs)}</small></td>"
            f"<td>{side(r['other'])}</td>"
            f"<td>{_decision_picker(r['subject'], r['other'], back)}</td></tr>"
        )
    return (
        "<div class=scroll><table class=versions><tr><th>this version</th><th>the model"
        " thinks</th><th>…that version</th><th>answer</th></tr>" + "".join(lines) + "</table></div>"
    )


def _dlcs_by_version(rows: list[sqlite3.Row]) -> str:
    """A DLC belongs to a version (owner, 2026-10-09): one block per version,
    named with its store and console."""
    if not rows:
        return "<p>(none)</p>"
    blocks: dict[int, list[sqlite3.Row]] = {}
    for row in rows:
        blocks.setdefault(int(row["version_id"]), []).append(row)
    parts = []
    for version_id, items in blocks.items():
        head = items[0]
        parts.append(
            f'<h3><a href="/version/{version_id}">{escape(head["version"] or "")}</a>'
            f" · {escape(head['store'])} {escape(head['console'])}"
            f" · {_store_link(head, 'store')} · {len(items)} DLC</h3>"
            + _table(
                [
                    {
                        k: r[k]
                        for k in (
                            "name",
                            "kind",
                            "release_date",
                            "store_id",
                            "trophy_group_id",
                            "store",
                        )
                    }
                    for r in items
                ],
                {"name": _dlc_href, "store_id": _dlc_href},
            )
        )
    return "".join(parts)


# Which review pairs ask about one game, and which about two related games.
_GAME_RELATIONS = ("remaster_of", "remake_of", "contains", "vr_of")


async def review(request: web.Request) -> web.Response:
    """Two questions, two tabs (owner, 2026-10-11): is this version that game
    (versions), and how do these two games relate (games)."""
    tab = request.query.get("tab", "versions")
    marks = ",".join("?" * len(_GAME_RELATIONS))
    games_tab = tab == "games"
    # A pair is about two games only when its versions are in two games; a
    # doubt inside one game (is this version a remaster after all?) is a
    # version question: keep it here, or move it out as another game.
    two_games = (
        "(SELECT game_id FROM game_versions WHERE version_id = mp.version_id) IS NOT"
        " (SELECT game_id FROM game_versions WHERE version_id = mp.other_id)"
    )
    games_where = f"mp.relation IN ({marks}) AND {two_games}"
    versions_where = f"NOT ({games_where})"
    where = games_where if games_tab else versions_where
    with _db(request) as conn:
        counts = {
            name: conn.execute(
                f"SELECT COUNT(*) FROM match_pairs mp WHERE {clause}", _GAME_RELATIONS
            ).fetchone()[0]
            for name, clause in (("versions", versions_where), ("games", games_where))
        }
        everything = conn.execute(
            "SELECT mp.version_id AS subject, mp.other_id AS other, mp.relation, mp.p,"
            f" mp.features FROM match_pairs mp WHERE {where} ORDER BY mp.p DESC",
            _GAME_RELATIONS,
        ).fetchall()
        # A pair answered "skip" comes back, after the rest (this run of the
        # viewer remembers it; nothing is written).
        skipped = request.app["skipped"]
        pairs = sorted(
            everything,
            key=lambda r: frozenset((r["subject"], r["other"])) in skipped,
        )[:PAGE_SIZE]
        back = f"/review?tab={tab}"
        cards = _game_pair_rows(conn, pairs, back) if games_tab else _pair_rows(conn, pairs, back)
    tabs = " · ".join(
        (
            f"<b>{label} ({counts[name]})</b>"
            if name == tab
            else f'<a href="/review?tab={name}">{label} ({counts[name]})</a>'
        )
        for name, label in (("versions", "version ↔ game"), ("games", "game ↔ game"))
    )
    note = (
        "<p>How two games relate: a remaster, a remake, a compilation, a VR version — or"
        " nothing. Each answer is a label between the two games' anchors.</p>"
        if games_tab
        else "<p>Is this version that game (or its edition, demo, tool) — or another game?</p>"
    )
    return _page("To review", _flash(request) + f"<p>{tabs}</p>" + note + cards)


def _game_card(conn: sqlite3.Connection, game_id: int) -> str:
    """A game in one cell: its covers, name and identity, consoles."""
    row = conn.execute(
        "SELECT (SELECT GROUP_CONCAT(DISTINCT v.console) FROM game_versions gv"
        "  JOIN versions v ON v.version_id = gv.version_id WHERE gv.game_id = ?) AS consoles,"
        " (SELECT " + COVER.replace(" AS cover", "") + " FROM game_versions gv"
        "  JOIN versions v ON v.version_id = gv.version_id WHERE gv.game_id = ?"
        "  AND gv.role IN ('version', 'edition') LIMIT 1) AS cover",
        (game_id, game_id),
    ).fetchone()
    return (
        f"{_img(row['cover'], 40)} "
        f'<a href="/game/{game_id}">{escape(_identity(conn, game_id))}</a>'
        f"<br><small>{escape(row['consoles'] or '')}</small>"
    )


def _game_pair_rows(conn: sqlite3.Connection, pairs: list[sqlite3.Row], back: str) -> str:
    """Doubtful relations between games, game against game."""
    if not pairs:
        return "<p>(nothing to review)</p>"
    lines = []
    seen: set[frozenset[int]] = set()
    for r in pairs:
        ga = conn.execute(
            "SELECT game_id FROM game_versions WHERE version_id = ?", (r["subject"],)
        ).fetchone()
        gb = conn.execute(
            "SELECT game_id FROM game_versions WHERE version_id = ?", (r["other"],)
        ).fetchone()
        if ga is None or gb is None or frozenset((ga[0], gb[0])) in seen:
            continue  # one row per pair of games, the surest
        seen.add(frozenset((ga[0], gb[0])))
        feats = json.loads(r["features"]) if r["features"] else {}
        signs = ", ".join(k for k in feats if k != "bias")
        names = (_game_name(conn, ga[0]), _game_name(conn, gb[0]))
        lines.append(
            f"<tr><td>{_game_card(conn, ga[0])}</td>"
            f"<td><b>{escape(r['relation'])}</b> {r['p']:.2f}"
            f"<br><small>{escape(signs)}</small></td>"
            f"<td>{_game_card(conn, gb[0])}</td>"
            f"<td>{_game_picker(ga[0], gb[0], back, str(r['relation']), names)}</td></tr>"
        )
    return (
        "<div class=scroll><table class=versions><tr><th>this game</th><th>the model"
        " thinks</th><th>…that game</th><th>answer</th></tr>" + "".join(lines) + "</table></div>"
    )


# Who besides the operator may give an answer (`decided_by`): the advisers
# agreeing (owner, 2026-10-12).
ADVISERS = {"claude+gemini"}

_PROPOSAL_WORDS = {
    "same": "one game",
    "series": "another of the series",
    "confirm": "the model is right",
    "not_related": "not related",
    "other_relation": "related, another way",
    "flip": "the other way round",
    "unsure": "unsure",
}


def _proposal_decision(answer: str, model: str) -> str | None:
    """An adviser's answer as the decision the game picker posts."""
    kind, _, rest = answer.partition(":")
    if kind == "same":
        return "same"
    if kind == "series":
        return "series"
    if kind == "not_related":
        return "other"
    if kind == "confirm":
        return model
    if kind == "flip":
        return f"{model}:flip"
    if kind == "other_relation" and rest:
        relation, _, direction = rest.partition(" ")
        return f"{relation}:flip" if direction.startswith("second") else relation
    return None


def load_gemini(directory: Path | None) -> dict[int, dict[str, str]]:
    """Gemini's answers about the proposals (owner, 2026-10-12): `*.txt` files,
    one line per pair, `pair|relation|direction|confidence|why`, the pair being
    the proposal's number. Each becomes the decision the game picker posts:
    `not_related` is "other", a `second` direction the other way round."""
    found: dict[int, dict[str, str]] = {}
    if directory is None or not directory.is_dir():
        return found
    for path in sorted(directory.glob("*.txt")):
        for line in path.read_text(encoding="utf-8").splitlines():
            parts = line.strip().split("|", 4)
            if len(parts) < 4 or not parts[0].strip().isdigit():
                continue
            pair, relation, direction, confidence = (p.strip() for p in parts[:4])
            relation = "other" if relation == "not_related" else relation
            if not relation:
                continue
            flip = direction == "second" and relation not in ("same", "series", "other")
            found[int(pair)] = {
                "decision": f"{relation}:flip" if flip else relation,
                "confidence": confidence,
                "why": parts[4].strip() if len(parts) > 4 else "",
            }
    return found


def _agreeing(decision: str, opinions: list[tuple[str, str | None]]) -> str:
    """Who gave this decision, as a button says it: "Claude, Gemini and the
    model", "Claude and Gemini", "Model"."""
    who = [name for name, said in opinions if said == decision]
    text = who[0] if len(who) == 1 else ", ".join(who[:-1]) + " and " + who[-1]
    return "Model" if text == "the model" else text[:1].upper() + text[1:]


def _current_game(conn: sqlite3.Connection, game_id: int) -> int:
    """The game a game id stands for now: a game merged into another is an
    empty row pointing at it (merged_into), followed to its end."""
    seen = {game_id}
    while True:
        row = conn.execute("SELECT merged_into FROM games WHERE game_id = ?", (game_id,)).fetchone()
        if row is None or row[0] is None or row[0] in seen:
            return game_id
        game_id = row[0]
        seen.add(game_id)


def _game_detail(conn: sqlite3.Connection, game_id: int) -> str:
    """A game in a card: its covers, identity, and every version with its
    store page (or that it has none)."""
    row = conn.execute("SELECT game_id FROM games WHERE game_id = ?", (game_id,)).fetchone()
    if row is None:
        return f"<p>game {game_id} is gone (rebuilt since)</p>"
    now = _current_game(conn, game_id)
    if now != game_id:
        return f"<p><small>game {game_id} was merged into game {now}:</small></p>" + (
            _game_detail(conn, now)
        )
    versions = conn.execute(
        "SELECT v.version_id, v.store, v.product_id, v.stand_in, v.on_sale, v.name,"
        " v.console, v.release_date, v.platform, v.title_id, gv.role, " + COVER + ","
        " (SELECT COUNT(*) FROM title_achievements a WHERE a.platform = v.platform"
        "  AND a.title_id = v.title_id) AS achievements"
        " FROM game_versions gv JOIN versions v ON v.version_id = gv.version_id"
        " WHERE gv.game_id = ? ORDER BY v.release_date, v.console",
        (game_id,),
    ).fetchall()
    covers = list(dict.fromkeys(v["cover"] for v in versions if v["cover"]))[:3]
    lines = "".join(
        f"<li><small>{escape(v['console'])} · {escape((v['release_date'] or '?')[:4])}"
        + (f" · {escape(v['role'])}" if v["role"] != "version" else "")
        + f" · {_store_link(v)}"
        + (f" · {v['achievements']} ach." if v["achievements"] else "")
        + f' · <a href="/version/{v["version_id"]}">«{escape(v["name"] or "")}»</a></small></li>'
        for v in versions
    )
    return (
        "<div>" + "".join(_img(cv, 70) for cv in covers) + "</div>"
        f'<p><a href="/game/{game_id}"><b>{escape(_identity(conn, game_id))}</b></a></p>'
        f"<ul style='margin:0;padding-left:18px'>{lines}</ul>"
    )


async def proposals(request: web.Request) -> web.Response:
    """An adviser's proposals for the game pairs (owner, 2026-10-12): each
    pair whole, covers and store pages, and one tap to take the proposal as
    the operator's answer — or the usual answers when it is wrong."""
    items = [dict(i) for i in request.app["proposals"]]
    if not items:
        return _page("Proposals", "<p>(no proposals file: start the viewer with --proposals)</p>")
    show = request.query.get("answer", "")
    order = {"high": 0, "medium": 1, "low": 2}
    with _db(request) as conn:

        def answered(a: int, b: int) -> bool:
            return (
                conn.execute(
                    "SELECT 1 FROM match_decisions d"
                    " JOIN game_versions x ON x.version_id = d.version_id"
                    " JOIN game_versions y ON y.version_id = d.other_id"
                    " WHERE (x.game_id = ? AND y.game_id = ?) OR (x.game_id = ? AND y.game_id = ?)"
                    " LIMIT 1",
                    (a, b, b, a),
                ).fetchone()
                is not None
            )

        for n, item in enumerate(items, 1):
            item["n"] = n
            # A game merged since (answered "one game", here or elsewhere) is
            # the game it went into; two that became one are answered.
            item["game_a"] = _current_game(conn, item["game_a"])
            item["game_b"] = _current_game(conn, item["game_b"])
        open_items = [
            i
            for i in items
            if i["game_a"] != i["game_b"] and not answered(i["game_a"], i["game_b"])
        ]
        counts: dict[str, int] = {}
        for i in open_items:
            key = i["answer"].split(":")[0]
            counts[key] = counts.get(key, 0) + 1
        chosen = [i for i in open_items if not show or i["answer"].split(":")[0] == show]
        # A pair answered "ask later" goes after the rest (this run of the viewer).
        skipped = request.app["skipped_games"]
        chosen.sort(
            key=lambda i: (
                frozenset((i["game_a"], i["game_b"])) in skipped,
                order.get(i["confidence"], 3),
                -i["p"],
            )
        )
        page = chosen[:40]
        cards = []
        for i in page:
            back = f"/proposals?answer={quote(show)}#p{i['n']}"
            # Every opinion and every button is a sentence naming both games
            # (owner, 2026-10-12: "first/second" and "take the proposal" left
            # it unclear whose answer a button records).
            this, that = _game_name(conn, i["game_a"]), _game_name(conn, i["game_b"])
            model, claude = i["model"], _proposal_decision(i["answer"], i["model"])
            gemini_item = request.app["gemini"].get(i["n"])
            gemini = gemini_item["decision"] if gemini_item else None
            model_says = _relation_sentence(model, this, that)
            claude_says = _relation_sentence(claude, this, that) if claude else ""
            # One button per answer, naming everybody who gave it.
            opinions = [("Claude", claude), ("Gemini", gemini), ("the model", model)]
            quick: list[tuple[str, str]] = []
            for decision in dict.fromkeys(d for _who, d in opinions if d):
                quick.append(
                    (
                        decision,
                        f"✓ <b>{_agreeing(decision, opinions)}</b>: "
                        f"{_relation_sentence(decision, this, that)}",
                    )
                )
            if "series" not in (claude, gemini, model):
                quick.append(("series", "another game of the series"))
            quick.append(("skip", "ask later"))
            more = tuple(
                (key, _relation_sentence(key, this, that, html=False)) for key, _ in _GAME_DECISIONS
            )
            buttons = _answer_forms(
                "/decide-games",
                {"game_id": i["game_a"], "other_game": i["game_b"]},
                quick,
                more,
                back,
            )
            cards.append(
                f"<div id=p{i['n']} style='border:1px solid #ccc;border-radius:8px;"
                "padding:8px;margin:10px 0'>"
                f"<p><b>#{i['n']}</b></p>"
                "<div style='display:flex;flex-wrap:wrap;gap:12px'>"
                f"<div style='flex:1 1 300px'>{_game_detail(conn, i['game_a'])}</div>"
                f"<div style='flex:1 1 300px'>{_game_detail(conn, i['game_b'])}</div></div>"
                f"<p><b>Model</b> ({i['p']:.0%}): {model_says}<br>"
                + (
                    f"<b>Claude</b> ({escape(i['confidence'])}): {claude_says}"
                    if claude
                    else "<b>Claude</b>: not sure"
                )
                + f"<br><small>{escape(i['why'])}</small>"
                + (
                    f"<br><b>Gemini</b> ({escape(gemini_item['confidence'])}): "
                    f"{_relation_sentence(gemini, this, that)}"
                    f"<br><small>{escape(gemini_item['why'])}</small>"
                    if gemini_item and gemini
                    else ""
                )
                + f"</p>{buttons}</div>"
            )
    filters = " · ".join(
        (
            f"<b>{escape(w)} ({counts.get(k, 0)})</b>"
            if k == show
            else f'<a href="/proposals?answer={k}">{escape(w)} ({counts.get(k, 0)})</a>'
        )
        for k, w in _PROPOSAL_WORDS.items()
        if counts.get(k)
    )
    head = (
        f"<p>{len(open_items)} open of {len(items)} · "
        + ('<a href="/proposals">all</a> · ' if show else "<b>all</b> · ")
        + filters
        + "</p><p><small>Each button records the answer it spells out. Answered"
        " pairs leave the list. Showing 40 at a time, Claude's surest first.</small></p>"
    )
    return _page("Proposals: game ↔ game", _flash(request) + head + "".join(cards))


async def decisions(request: web.Request) -> web.Response:
    """Every label the operator gave, newest first."""
    with _db(request) as conn:
        rows = conn.execute(
            "SELECT d.version_id, a.name AS this, d.relation, d.other_id, b.name AS that,"
            " d.model, d.decided_at FROM match_decisions d"
            " JOIN versions a ON a.version_id = d.version_id"
            " JOIN versions b ON b.version_id = d.other_id ORDER BY d.decided_at DESC LIMIT ?",
            (PAGE_SIZE * 3,),
        ).fetchall()
    links = {
        "version_id": lambda r: f"/version/{r['version_id']}",
        "this": lambda r: f"/version/{r['version_id']}",
        "other_id": lambda r: f"/version/{r['other_id']}",
        "that": lambda r: f"/version/{r['other_id']}",
    }
    return _page("The operator's labels", _table(rows, links))


def _version_line(v: sqlite3.Row) -> str:
    """A version in one line: its name, console and year, and its store page."""

    return (
        f'<a href="/version/{v["version_id"]}">{escape(v["name"] or "")}</a>'
        f" [{escape(v['console'])}, {escape(v['release_date'] or '?')}]"
        f" {_store_link(v, str(v['store']) + ' ' + str(v['product_id']))}"
    )


async def _label(
    repo: Repo, version_id: int, other_id: int, relation: str, *, by: str = "viewer"
) -> None:
    """A label, with the signs the model saw for the pair, then the two
    versions linked again around it."""
    from bot.services.game_link import GameLinker
    from bot.services.game_match import MODEL

    features, model = await repo.pair_features(version_id, other_id)
    await repo.save_decision(
        version_id, other_id, relation, features=features, model=model or MODEL, decided_by=by
    )
    await GameLinker(repo).link_versions([version_id, other_id])


async def decide(request: web.Request) -> web.Response:
    form = await request.post()
    version_id, other_id = int(str(form["version_id"])), int(str(form["other_id"]))
    decision, back = str(form["decision"]), str(form.get("back") or "/review")
    relation, _, flip = decision.partition(":")
    if relation == "skip":
        request.app["skipped"].add(frozenset((version_id, other_id)))
        raise _back(back, f"versions {version_id} / {other_id}: asked again later")
    if flip:
        version_id, other_id = other_id, version_id
    await _label(_repo(request), version_id, other_id, relation)
    raise _back(back, f"version {version_id} {relation} version {other_id}")


async def game_rename(request: web.Request) -> web.Response:
    game_id = int(request.match_info["game_id"])
    form = await request.post()
    name = str(form.get("name") or "").strip()
    if name:
        await _repo(request).rename_game(
            game_id, name, str(form.get("name_ru") or "").strip() or None, "manual"
        )
    raise _back(f"/game/{game_id}", "renamed")


async def game_kind(request: web.Request) -> web.Response:
    """The operator says what a game is; a rebuild never overwrites it."""
    game_id = int(request.match_info["game_id"])
    form = await request.post()
    kind = str(form.get("kind") or "")
    await _repo(request).set_game_kind_manual(game_id, kind if kind in _KIND_WORDS else None)
    raise _back(f"/game/{game_id}", f"kind: {kind or 'the linker decides'}")


async def decide_games(request: web.Request) -> web.Response:
    """An answer about two games: a label between their anchors."""
    form = await request.post()
    game_id, other_game = int(str(form["game_id"])), int(str(form["other_game"]))
    decision, back = str(form["decision"]), str(form.get("back") or "/review?tab=games")
    relation, _, flip = decision.partition(":")
    repo = _repo(request)
    if relation == "skip":
        # Every pair of versions between the two games comes back later.
        with _db(request) as conn:
            for row in conn.execute(
                "SELECT mp.version_id, mp.other_id FROM match_pairs mp"
                " JOIN game_versions a ON a.version_id = mp.version_id"
                " JOIN game_versions b ON b.version_id = mp.other_id"
                " WHERE (a.game_id = ? AND b.game_id = ?) OR (a.game_id = ? AND b.game_id = ?)",
                (game_id, other_game, other_game, game_id),
            ):
                request.app["skipped"].add(frozenset((row[0], row[1])))
        request.app["skipped_games"].add(frozenset((game_id, other_game)))
        # Not back to its card: it has gone to the end of the list.
        raise _back(back.split("#")[0], f"games {game_id} / {other_game}: asked again later")
    if game_id == other_game:
        raise _back(back, f"game {game_id} is one game: answer its versions on the other tab")
    a, b = await _game_anchors(repo, game_id, other_game)
    if flip:
        a, b = b, a
    # An answer the advisers agreed on (owner, 2026-10-12: Claude's proposal
    # confirmed by Gemini) is written as theirs, never as the operator's.
    by = str(form.get("by") or "")
    await _label(repo, a, b, relation, by=by if by in ADVISERS else "viewer")
    raise _back(back, f"game {game_id} / game {other_game}: {decision}")


async def game_unrelate(request: web.Request) -> web.Response:
    """Take a relation away: "not related" between the two games."""
    game_id = int(request.match_info["game_id"])
    form = await request.post()
    other = int(str(form["other_game"]))
    repo = _repo(request)
    a, b = await _game_anchors(repo, game_id, other)
    await _label(repo, a, b, "other")
    raise _back(f"/game/{game_id}", f"game {game_id} and game {other}: not related")


async def _game_anchors(repo: Repo, game_id: int, other: int) -> tuple[int, int]:
    a, b = await repo.anchor_of(game_id), await repo.anchor_of(other)
    if a is None or b is None:
        raise _back(f"/game/{game_id}", "no such game, or it has no version")
    return a, b


async def game_merge(request: web.Request) -> web.Response:
    """ "One game": a label `same` between the two games' anchors."""
    game_id = int(request.match_info["game_id"])
    form = await request.post()
    into = str(form.get("into") or "").strip()
    if not into.isdigit() or int(into) == game_id:
        raise _back(f"/game/{game_id}", "a game id to merge into, please")
    repo = _repo(request)
    a, b = await _game_anchors(repo, game_id, int(into))
    await _label(repo, a, b, "same")
    target = await repo.linked_game_of(b) or int(into)
    raise _back(f"/game/{target}", f"game {game_id} is game {into}")


async def game_relate(request: web.Request) -> web.Response:
    """ "This game is a remaster / remake / VR version of that one, or holds
    it": a label between the two games' anchors."""
    game_id = int(request.match_info["game_id"])
    form = await request.post()
    related, kind = str(form.get("related") or "").strip(), str(form.get("kind") or "")
    if not related.isdigit() or int(related) == game_id:
        raise _back(f"/game/{game_id}", "a game id, please")
    if kind not in ("remaster_of", "remake_of", "vr_of", "contains"):
        raise _back(f"/game/{game_id}", "which relation?")
    repo = _repo(request)
    a, b = await _game_anchors(repo, game_id, int(related))
    await _label(repo, a, b, kind)
    raise _back(f"/game/{await repo.linked_game_of(a) or game_id}", f"{kind} game {related}")


async def game_detach(request: web.Request) -> web.Response:
    """ "Not this game": a label `other` against another version of it."""
    game_id = int(request.match_info["game_id"])
    form = await request.post()
    version_id = int(str(form["version_id"]))
    repo = _repo(request)
    with _db(request) as conn:
        row = conn.execute(
            "SELECT version_id FROM game_versions WHERE game_id = ? AND version_id <> ?"
            " ORDER BY version_id = (SELECT anchor_version_id FROM games WHERE game_id = ?) DESC,"
            " version_id LIMIT 1",
            (game_id, version_id, game_id),
        ).fetchone()
    if row is None:
        raise _back(f"/game/{game_id}", "the only version of its game")
    await _label(repo, version_id, int(row[0]), "other")
    raise _back(f"/version/{version_id}", f"version {version_id} is not game {game_id}")


async def relink(request: web.Request) -> web.Response:
    from bot.services.game_link import GameLinker

    platform, title_id = request.match_info["platform"], request.match_info["title_id"]
    report = await GameLinker(_repo(request)).link_title(platform, title_id)
    raise _back(
        f"/title/{quote(platform)}/{quote(title_id)}",
        f"games {sorted(report.games)}; to review {len(report.review)}",
    )


async def _open(app: web.Application) -> None:
    from bot.config import get_settings
    from bot.services.crypto import TokenCipher
    from bot.services.psn.auth import PsnAuth
    from bot.services.steam.auth import SteamAuth
    from bot.services.store_collect import StoreCollector

    database = await Database(Path(app["db_path"])).connect()
    repo = Repo(database)
    app["database"], app["repo"] = database, repo
    settings = get_settings()
    cipher = TokenCipher(settings.fernet_key.get_secret_value())
    steam = SteamAuth(repo, cipher, env_key=_secret(settings.steam_api_key))
    app["collector"] = StoreCollector(repo, PsnAuth(repo, cipher), steam)


def _secret(value: object) -> str | None:
    """A pydantic secret's text, or None."""
    getter = getattr(value, "get_secret_value", None)
    return getter() if getter else (str(value) if value else None)


async def _close(app: web.Application) -> None:
    await app["database"].close()


def _pictures(row: sqlite3.Row | None) -> str:
    """Every picture a version has: the store's (cover, poster, hero…), its
    achievement list's, its HLTB entry's — each once, named by where it came
    from. Screenshots are left to the raw answer."""
    if row is None:
        return ""
    seen: dict[str, str] = {}
    media = json.loads(row["media"]) if row["media"] else {}
    for role, url in media.items():
        if isinstance(url, str) and url.startswith("http") and url not in seen:
            seen[url] = f"store: {role}"
    for url, source in (
        (row["list_cover"], "achievement list (kept)"),
        (row["list_icon"], "achievement list"),
        (row["hltb_image"], "HLTB"),
    ):
        if url and url not in seen:
            seen[str(url)] = source
    if not seen:
        return "<p>(no pictures)</p>"
    return (
        "<p>"
        + "".join(
            f"<figure style='display:inline-block;margin:4px'>{_img(url, 180, source)}"
            f"<figcaption><small>{escape(source)}</small></figcaption></figure>"
            for url, source in seen.items()
        )
        + "</p>"
    )


def build(
    db_path: Path, proposals_path: Path | None = None, gemini_dir: Path | None = None
) -> web.Application:
    app = web.Application()
    app["db_path"] = db_path.resolve().as_posix()
    app["skipped"] = set()  # pairs answered "skip": asked again, after the rest
    app["skipped_games"] = set()  # the same, as pairs of games (the proposals)
    # An adviser's proposals, read once at start (`--proposals`).
    app["proposals"] = (
        json.loads(proposals_path.read_text(encoding="utf-8"))
        if proposals_path and proposals_path.exists()
        else []
    )
    # Gemini's answers about the same pairs, read once at start (`--gemini`).
    app["gemini"] = load_gemini(gemini_dir)
    covers = db_path.resolve().parent / "covers"
    if covers.is_dir():
        # The covers the bot downloaded (#55), beside its database.
        app.router.add_static("/covers/", covers)
    app.on_startup.append(_open)
    app.on_cleanup.append(_close)
    app.router.add_post("/title/{platform}/{title_id}/collect", collect)
    app.router.add_post("/fetch/due", fetch_due)
    app.router.add_get("/games", games)
    app.router.add_get("/rules", rules)
    app.router.add_get("/list/{platform}/{title_id}", achievement_list)
    app.router.add_get("/steam-schema/{appid}", steam_schema)
    app.router.add_get("/game/{game_id:\\d+}", game)
    app.router.add_get("/review", review)
    app.router.add_get("/decisions", decisions)
    app.router.add_get("/proposals", proposals)
    app.router.add_post("/decide-games", decide_games)
    app.router.add_post("/game/{game_id:\\d+}/unrelate", game_unrelate)
    app.router.add_post("/decide", decide)
    app.router.add_post("/game/{game_id:\\d+}/rename", game_rename)
    app.router.add_post("/game/{game_id:\\d+}/kind", game_kind)
    app.router.add_post("/game/{game_id:\\d+}/merge", game_merge)
    app.router.add_post("/game/{game_id:\\d+}/relate", game_relate)
    app.router.add_post("/game/{game_id:\\d+}/detach", game_detach)
    app.router.add_post("/title/{platform}/{title_id}/relink", relink)
    app.router.add_post("/version/{version_id:\\d+}/title", version_title)
    app.router.add_post("/version/{version_id:\\d+}/hltb", version_hltb_link)
    app.router.add_post(
        "/version/{version_id:\\d+}/hltb/{hltb_id:\\d+}/unlink", version_hltb_unlink
    )
    app.router.add_post("/version/{version_id:\\d+}/delete", version_delete)
    app.router.add_get("/", home)
    app.router.add_get("/titles", titles)
    app.router.add_get("/title/{platform}/{title_id}", title)
    app.router.add_get("/versions", versions)
    app.router.add_get("/version/{version_id:\\d+}", version)
    app.router.add_get("/dlcs", dlcs)
    app.router.add_get("/hltb", hltb_list)
    app.router.add_get("/hltb/{hltb_id:\\d+}", hltb_entry)
    app.router.add_get("/fetch", fetch)
    app.router.add_get("/payloads", payloads)
    app.router.add_get("/payload", payload)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--db", help="database file (default: DB_PATH from the env file)")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument(
        "--proposals", help="an adviser's proposals for the game pairs (JSON), shown at /proposals"
    )
    parser.add_argument(
        "--gemini",
        help="a folder of Gemini's answers about the proposals (*.txt, pair|relation|"
        "direction|confidence|why), shown on the /proposals cards",
    )
    args = parser.parse_args()
    if args.db:
        db_path = Path(args.db)
    else:
        from bot.config import get_settings

        db_path = Path(get_settings().db_path)
    print(f"{db_path} — http://127.0.0.1:{args.port}/ (no authentication)")
    proposals = Path(args.proposals) if args.proposals else None
    gemini = Path(args.gemini) if args.gemini else None
    web.run_app(build(db_path, proposals, gemini), host="127.0.0.1", port=args.port, print=None)


if __name__ == "__main__":
    main()
