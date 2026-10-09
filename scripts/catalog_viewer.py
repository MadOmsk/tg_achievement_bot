"""A bare local viewer of the games' store side (#147): achievement lists
(`titles`), their versions, DLC, HLTB entries, the sources' raw answers and
the fetch schedule, every link clickable. Read-only — the database is opened
`mode=ro`. Meant to grow into the operator's table of the games one day.

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

PAGE_SIZE = 100


def _db(request: web.Request) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{request.app['db_path']}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _page(title: str, body: str) -> web.Response:
    nav = (
        '<a href="/">home</a> · <a href="/titles">titles</a> · <a href="/versions">versions</a>'
        ' · <a href="/dlcs">dlcs</a> · <a href="/hltb">hltb</a> · <a href="/fetch">fetch state</a>'
        ' · <a href="/payloads">payloads</a>'
    )
    html = (
        f"<!doctype html><meta charset=utf-8><title>{escape(title)}</title>"
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
            if href is not None and row[column] is not None:
                text = f'<a href="{escape(href(row))}">{text}</a>'  # type: ignore[operator]
            cells.append(f"<td>{text}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table border=1 cellpadding=3><tr>{head}</tr>{''.join(body)}</table>"


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
    return f"<table border=1 cellpadding=3>{''.join(lines)}</table>"


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
        _search_form("/titles", "") + f"<table border=1 cellpadding=3>{rows}</table>",
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
    body = (
        _record(row, {"hltb_id": _hltb_href})
        + "<h2>Versions (store products on one console)</h2>"
        + _table(versions, {"version_id": _version_href, "name": _version_href})
        + "<h2>PSN trophy groups</h2>"
        + _table(groups)
        + "<h2>Fetch state</h2>"
        + _table(state, {"subject": _payload_href})
    )
    return _page(f"{platform} {title_id}", body)


async def versions(request: web.Request) -> web.Response:
    q = request.query.get("q", "")
    with _db(request) as conn:
        rows = conn.execute(
            "SELECT version_id, store, product_id, console, name, platform, title_id, kind,"
            " release_date, origin FROM versions"
            " WHERE ? = '' OR name LIKE ? OR product_id = ? OR store_group = ?"
            " ORDER BY updated_at DESC LIMIT ?",
            (q, f"%{q}%", q, q, PAGE_SIZE),
        ).fetchall()
    return _page(
        "Versions",
        _search_form("/versions", q)
        + _table(
            rows, {"version_id": _version_href, "name": _version_href, "title_id": _title_href}
        ),
    )


async def version(request: web.Request) -> web.Response:
    version_id = int(request.match_info["version_id"])
    with _db(request) as conn:
        row = conn.execute("SELECT * FROM versions WHERE version_id = ?", (version_id,)).fetchone()
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
        payloads = (
            conn.execute(
                "SELECT subject, source, fetched_at, length(payload) AS bytes FROM source_payloads"
                " WHERE subject LIKE ?",
                (f"%{row['product_id']}%",),
            ).fetchall()
            if row is not None
            else []
        )
    body = (
        _record(row, {"title_id": _title_href})
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
    return _page("Fetch state", _table(rows, {"subject": _payload_href}))


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


def build(db_path: Path) -> web.Application:
    app = web.Application()
    app["db_path"] = db_path.resolve().as_posix()
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
    args = parser.parse_args()
    if args.db:
        db_path = Path(args.db)
    else:
        from bot.config import get_settings

        db_path = Path(get_settings().db_path)
    print(f"reading {db_path} — http://127.0.0.1:{args.port}/")
    web.run_app(build(db_path), host="127.0.0.1", port=args.port, print=None)


if __name__ == "__main__":
    main()
