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
    return web.HTTPFound(to + ("&" if "?" in to else "?") + urlencode({"msg": message}))


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


def _store_href(row: sqlite3.Row) -> str:
    """The version on its store: a product page, or a search for a stand-in."""
    store, product, name = row["store"], str(row["product_id"]), quote(str(row["name"] or ""))
    stand_in = "stand_in" in row.keys() and row["stand_in"]
    if store == "xbox":
        if stand_in:
            return f"https://www.xbox.com/en-US/search?q={name}"
        return f"https://www.xbox.com/en-US/games/store/x/{product}"
    if store == "steam":
        return f"https://store.steampowered.com/app/{product}"
    if store == "psn":
        if stand_in:
            return f"https://store.playstation.com/en-us/search/{name}"
        return f"https://store.playstation.com/en-us/concept/{product}"
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
    "version_games": "/review",
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
                "version_games",
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
            "SELECT version_id, store, product_id, stand_in, console, name, platform, title_id,"
            " kind, release_date, origin FROM versions"
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
        demo_of = conn.execute(
            "SELECT of_version_id FROM version_links WHERE version_id = ? AND kind = 'demo_of'",
            (version_id,),
        ).fetchone()
        games = conn.execute(
            "SELECT vg.game_id, g.name, vg.kind, vg.state, vg.source, vg.score, vg.reasons"
            " FROM version_games vg JOIN games g ON g.game_id = vg.game_id"
            " WHERE vg.version_id = ? ORDER BY vg.state, vg.game_id",
            (version_id,),
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
        + controls
        + (
            f'<p><a href="{escape(_store_href(row))}">on the store</a>'
            + (
                f' · <a href="{escape(_list_href(row))}">its achievements</a>'
                if row["title_id"]
                else ""
            )
            + (
                f' · demo of <a href="/version/{demo_of["of_version_id"]}">version'
                f" {demo_of['of_version_id']}</a>"
                if demo_of
                else ""
            )
            + "</p>"
            if row is not None
            else ""
        )
        + _record(row, {"title_id": _title_href})
        + "<h2>Games</h2>"
        + _table(games, {"game_id": _game_href, "name": _game_href})
        + "".join(
            _decisions(version_id, g["game_id"], here) for g in games if g["state"] == "review"
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


_DECISIONS = (
    ("version", "same game: a version"),
    ("remaster", "remaster"),
    ("edition", "edition"),
    ("demo", "demo"),
    ("compilation", "part of a compilation"),
    ("remake", "remake: another game"),
    ("different", "a different game"),
)


def _decisions(version_id: int, game_id: int, back: str) -> str:
    """The operator's answers to one review row."""
    return (
        f"<p>version {version_id} → game {game_id}: "
        + "".join(
            _button(
                "/decide",
                label,
                {"version_id": version_id, "game_id": game_id, "decision": key, "back": back},
            )
            for key, label in _DECISIONS
        )
        + "</p>"
    )


async def rules(request: web.Request) -> web.Response:
    """How the matcher decides, with the numbers it decides by now."""
    from bot.services import game_match as m

    rows = [
        (
            "1",
            "A demo whose name the game's opens, nothing numbered after it, released within",
            f"{m.NEAR_YEARS} year → linked (demo)",
        ),
        (
            "2",
            "Same store group (Xbox ProductGroup / PSN concept), same HLTB entry,"
            " Steam's parent app",
            "linked — unless the numbers in the names differ",
        ),
        ("3", "Cut names alike below", f"{m.NAME_FLOOR} → apart"),
        (
            "3",
            'One cut name inside the other ("Modern Warfare 2" ⊂ "Call of Duty: …")',
            f"name = {m.CONTAINED_NAME}",
        ),
        ("3", "Different numbers (Halo / Halo 2, Battlefront / Battlefront II)", "apart"),
        (
            "4",
            f"Achievements' names agree ≥ {m.ACHIEVEMENTS_SAME:.0%}"
            f" (both lists ≥ {m.ACHIEVEMENTS_MIN})",
            "score ≥ 0.95, and that is proof",
        ),
        (
            "4",
            f"Achievements' names agree ≤ {m.ACHIEVEMENTS_OTHER:.0%}",
            "review (two lists of their own)",
        ),
        ("5", "Same developer / same publisher", "+0.05 / +0.02"),
        ("6", f"Years {m.FAR_YEARS}+ apart, no achievements proof", "review"),
        ("6", f"Years more than {m.NEAR_YEARS} apart", "−0.05 a year past the first"),
        ("6", f"Years within {m.NEAR_YEARS}", "proof"),
        ("6", "A year unknown", "no proof from years"),
        ("7", f"Score ≥ {m.LINK_SCORE} with a proof (achievements or close years)", "linked"),
        ("7", f"Score ≥ {m.REVIEW_SCORE}", "review"),
        ("7", "Otherwise", "apart"),
    ]
    body = (
        "<p>Each pair of versions sharing a telling word is compared; linked pairs make one game, "
        "a review pair is filed once per version, on the side less is known about. "
        "Manual decisions are never rewritten.</p><table border=1 cellpadding=3>"
        "<tr><th>step</th><th>when</th><th>then</th></tr>"
        + "".join(
            f"<tr><td>{a}</td><td>{escape(b)}</td><td>{escape(c)}</td></tr>" for a, b, c in rows
        )
        + "</table><p>Kinds from the name: demo / trial / beta / prologue → demo; remaster(ed) /"
        " definitive / reloaded / anniversary / redux / HD / enhanced / director's cut → remaster;"
        " GOTY / complete / deluxe / ultimate / gold / premium / legendary → edition.</p>"
    )
    return _page("How versions are matched", body)


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
            "SELECT g.game_id, g.name, g.year, g.name_source,"
            "  (SELECT COUNT(*) FROM version_games vg WHERE vg.game_id = g.game_id"
            "   AND vg.state = 'linked') AS versions,"
            "  (SELECT COUNT(*) FROM version_games vg WHERE vg.game_id = g.game_id"
            "   AND vg.state = 'review') AS review,"
            "  (SELECT GROUP_CONCAT(DISTINCT v.console) FROM version_games vg"
            "   JOIN versions v ON v.version_id = vg.version_id"
            "   WHERE vg.game_id = g.game_id AND vg.state = 'linked') AS consoles"
            " FROM games g WHERE g.merged_into IS NULL AND (? = '' OR g.name LIKE ?)"
            " ORDER BY versions DESC, g.game_id DESC LIMIT ?",
            (q, f"%{q}%", PAGE_SIZE * 3),
        ).fetchall()
    return _page(
        "Games",
        _flash(request)
        + _search_form("/games", q)
        + _table(rows, {"game_id": _game_href, "name": _game_href}),
    )


async def game(request: web.Request) -> web.Response:
    game_id = int(request.match_info["game_id"])
    with _db(request) as conn:
        row = conn.execute("SELECT * FROM games WHERE game_id = ?", (game_id,)).fetchone()
        members = conn.execute(
            "SELECT vg.version_id, v.store, v.product_id, v.stand_in, v.console, v.name,"
            " v.release_date, v.developer, v.platform, v.title_id,"
            " CASE WHEN v.title_id IS NULL THEN NULL ELSE 'achievements' END AS achievements,"
            " vl.of_version_id AS demo_of, vg.kind, vg.state, vg.source, vg.score, vg.reasons"
            " FROM version_games vg JOIN versions v ON v.version_id = vg.version_id"
            " LEFT JOIN version_links vl ON vl.version_id = v.version_id AND vl.kind = 'demo_of'"
            " WHERE vg.game_id = ? ORDER BY vg.state, v.release_date, v.console",
            (game_id,),
        ).fetchall()
        relations = conn.execute(
            "SELECT r.kind, r.related_id AS game_id, g.name, r.source FROM game_relations r"
            " JOIN games g ON g.game_id = r.related_id WHERE r.game_id = ?"
            " UNION ALL SELECT r.kind || ' (of this)', r.game_id, g.name, r.source"
            " FROM game_relations r JOIN games g ON g.game_id = r.game_id WHERE r.related_id = ?",
            (game_id, game_id),
        ).fetchall()
        dlcs = conn.execute(
            "SELECT d.version_id, v.store, v.console, v.name AS version, v.product_id,"
            " v.stand_in, d.dlc_id, d.name, d.kind, d.release_date, d.store_id,"
            " d.trophy_group_id FROM dlcs d"
            " JOIN version_games vg ON vg.version_id = d.version_id AND vg.state = 'linked'"
            " JOIN versions v ON v.version_id = d.version_id WHERE vg.game_id = ?"
            " ORDER BY v.store, v.console, d.version_id, d.release_date, d.name",
            (game_id,),
        ).fetchall()
        hltb = conn.execute(
            "SELECT DISTINCT h.hltb_id, h.name, h.game_type FROM version_hltb vh"
            " JOIN hltb_games h ON h.hltb_id = vh.hltb_id"
            " JOIN version_games vg ON vg.version_id = vh.version_id AND vg.state = 'linked'"
            " WHERE vg.game_id = ?",
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
            f'<form method=post action="{here}/relate">this game is a remake of game id: '
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
        if m["state"] == "linked"
    )
    reviews = "".join(
        _decisions(m["version_id"], game_id, here) for m in members if m["state"] == "review"
    )
    body = (
        _flash(request)
        + controls
        + _record(row, {"merged_into": lambda r: f"/game/{r['merged_into']}"})
        + "<h2>Versions</h2>"
        + _table([m for m in members if m["state"] == "linked"], _VERSION_LINKS)
        + (
            "<h2>To review: may be this game</h2>"
            + _table([m for m in members if m["state"] == "review"], _VERSION_LINKS)
            + reviews
            if reviews
            else ""
        )
        + (
            "<h2>Decided: not this game</h2>"
            + _table([m for m in members if m["state"] == "rejected"], _VERSION_LINKS)
            if any(m["state"] == "rejected" for m in members)
            else ""
        )
        + "<h2>Related games</h2>"
        + _table(relations, {"game_id": _game_href, "name": _game_href})
        + "<h2>DLC, by version</h2>"
        + _dlcs_by_version(dlcs)
        + "<h2>HLTB</h2>"
        + _table(hltb, {"hltb_id": _hltb_href, "name": _hltb_href})
        + "<h2>Detach</h2>"
        + detach
    )
    return _page(row["name"] if row else f"Game {game_id}", body)


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
            f' · <a href="{escape(_store_href(head))}">store</a> · {len(items)} DLC</h3>'
            + _table(
                [
                    {
                        k: r[k]
                        for k in ("name", "kind", "release_date", "store_id", "trophy_group_id")
                    }
                    for r in items
                ]
            )
        )
    return "".join(parts)


async def review(request: web.Request) -> web.Response:
    with _db(request) as conn:
        rows = conn.execute(
            "SELECT vg.version_id, v.name AS version, v.console, v.release_date,"
            " vg.game_id, g.name AS game, vg.kind, vg.score, vg.reasons"
            " FROM version_games vg JOIN versions v ON v.version_id = vg.version_id"
            " JOIN games g ON g.game_id = vg.game_id WHERE vg.state = 'review'"
            " ORDER BY vg.decided_at DESC LIMIT ?",
            (PAGE_SIZE,),
        ).fetchall()
    parts = []
    for r in rows:
        parts.append(
            f'<hr><p><a href="/version/{r["version_id"]}">{escape(r["version"] or "")}</a>'
            f" [{escape(r['console'])}, {escape(r['release_date'] or '?')}] →"
            f' <a href="/game/{r["game_id"]}">{escape(r["game"])}</a>'
            f" · {escape(r['reasons'] or '')}</p>"
            + _decisions(r["version_id"], r["game_id"], "/review")
        )
    return _page("To review", _flash(request) + ("".join(parts) or "<p>(nothing to review)</p>"))


async def decide(request: web.Request) -> web.Response:
    form = await request.post()
    version_id, game_id = int(str(form["version_id"])), int(str(form["game_id"]))
    decision, back = str(form["decision"]), str(form.get("back") or "/review")
    repo = _repo(request)
    if decision in ("version", "remaster", "edition", "demo", "compilation"):
        await repo.set_link(
            version_id, game_id, kind=decision, state="linked", source="manual", decided_by="viewer"
        )
        if decision != "compilation":
            # It is this game now: out of the one the matcher had put it in.
            await repo.drop_auto_links(version_id, game_id, "linked")
    else:
        await repo.set_link(
            version_id,
            game_id,
            kind="version",
            state="rejected",
            source="manual",
            decided_by="viewer",
        )
        if decision == "remake":
            own = await repo.linked_game_of(version_id)
            if own is None or own == game_id:
                own = await repo.create_game(f"version {version_id}", None)
                await repo.set_link(
                    version_id, own, kind="version", state="linked", source="manual"
                )
            await repo.relate_games(own, game_id, "remake_of", "manual")
    await repo.drop_empty_games()
    raise _back(back, f"version {version_id}: {decision}")


async def game_rename(request: web.Request) -> web.Response:
    game_id = int(request.match_info["game_id"])
    form = await request.post()
    name = str(form.get("name") or "").strip()
    if name:
        await _repo(request).rename_game(
            game_id, name, str(form.get("name_ru") or "").strip() or None, "manual"
        )
    raise _back(f"/game/{game_id}", "renamed")


async def game_merge(request: web.Request) -> web.Response:
    game_id = int(request.match_info["game_id"])
    form = await request.post()
    into = str(form.get("into") or "").strip()
    if not into.isdigit() or int(into) == game_id:
        raise _back(f"/game/{game_id}", "a game id to merge into, please")
    await _repo(request).merge_games(game_id, int(into))
    raise _back(f"/game/{into}", f"game {game_id} merged here")


async def game_relate(request: web.Request) -> web.Response:
    game_id = int(request.match_info["game_id"])
    form = await request.post()
    related = str(form.get("related") or "").strip()
    if not related.isdigit() or int(related) == game_id:
        raise _back(f"/game/{game_id}", "a game id, please")
    await _repo(request).relate_games(game_id, int(related), "remake_of", "manual")
    raise _back(f"/game/{game_id}", f"a remake of game {related}")


async def game_detach(request: web.Request) -> web.Response:
    game_id = int(request.match_info["game_id"])
    form = await request.post()
    version_id = int(str(form["version_id"]))
    repo = _repo(request)
    await repo.set_link(
        version_id, game_id, kind="version", state="rejected", source="manual", decided_by="viewer"
    )
    own = await repo.create_game(f"version {version_id}", None)
    await repo.set_link(
        version_id, own, kind="version", state="linked", source="manual", decided_by="viewer"
    )
    raise _back(f"/game/{own}", f"version {version_id} detached into its own game: rename it")


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


def build(db_path: Path) -> web.Application:
    app = web.Application()
    app["db_path"] = db_path.resolve().as_posix()
    app.on_startup.append(_open)
    app.on_cleanup.append(_close)
    app.router.add_post("/title/{platform}/{title_id}/collect", collect)
    app.router.add_post("/fetch/due", fetch_due)
    app.router.add_get("/games", games)
    app.router.add_get("/rules", rules)
    app.router.add_get("/list/{platform}/{title_id}", achievement_list)
    app.router.add_get("/game/{game_id:\\d+}", game)
    app.router.add_get("/review", review)
    app.router.add_post("/decide", decide)
    app.router.add_post("/game/{game_id:\\d+}/rename", game_rename)
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
    args = parser.parse_args()
    if args.db:
        db_path = Path(args.db)
    else:
        from bot.config import get_settings

        db_path = Path(get_settings().db_path)
    print(f"{db_path} — http://127.0.0.1:{args.port}/ (no authentication)")
    web.run_app(build(db_path), host="127.0.0.1", port=args.port, print=None)


if __name__ == "__main__":
    main()
