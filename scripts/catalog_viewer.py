"""A bare viewer of the games' store side (#147): achievement lists
(`titles`), their versions, DLC, HLTB entries, the sources' raw answers and
the fetch schedule, every link clickable — and the controls an operator needs
(collect a game now, ask a source again, fix a version's links, delete a
version). Pages read through their own read-only connection; the controls
write through `Repo`. Meant to grow into the operator's table of the games.

**No authentication yet** (owner, 2026-10-09: to be added before it is
anything but a dev tool) — whoever has the address can press every button.

Usage:
    .venv/Scripts/python.exe -X utf8 -m scripts.catalog_viewer            # the .env schema
    .venv/Scripts/python.exe -X utf8 -m scripts.catalog_viewer --schema test --port 8090
then open http://127.0.0.1:8090/
"""

from __future__ import annotations

import argparse
import json
import zlib
from collections import Counter
from collections.abc import Callable
from html import escape
from pathlib import Path
from urllib.parse import quote, urlencode

from aiohttp import web

from bot.db import tools
from bot.db.postgres import Row
from bot.db.repo import Repo
from bot.db.repo._sql import BONUS_IN, OWN_EDITION, PART_OF_BUNDLE, STEAM_APP_OF_TITLE
from bot.db.tools import Connection
from bot.services.advice import (
    ADVISER_SOURCES,
    AdviceStore,
    games_pair_id,
    versions_pair_id,
)
from bot.services.game_series import SURE_P
from bot.services.stores import PC_LABELS, PC_UNKNOWN, console_label
from scripts.trial_page import CSS as CARD_CSS

PAGE_SIZE = 100


def _db(request: web.Request) -> Connection:
    return tools.connect(request.app["dsn"], schema=request.app["schema"], readonly=True)


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


def _confirm(request: web.Request, form, question: str, sides: list[str]) -> web.Response:
    """A step before an action whose other side was typed as an id (owner,
    2026-10-24: a merge went through with nothing saying what the id was):
    what each id stands for, then a yes that posts the same form again with
    `confirmed`, or back."""
    fields = {k: v for k, v in form.items() if k != "confirmed"}
    fields["confirmed"] = 1
    back = str(form.get("back") or request.path.rsplit("/", 1)[0])
    body = (
        "".join(f"<p>{side}</p>" for side in sides)
        + "<p>"
        + _button(request.path, "yes, do it", fields)
        + f' <a href="{escape(back)}">cancel</a></p>'
    )
    return _page(question, body)


def _game_said(conn: Connection, game_id: int) -> str:
    """A game as a confirmation names it: id, name, years, its versions."""
    row = conn.execute(
        "SELECT name, year, last_year, merged_into FROM games WHERE game_id = ?", (game_id,)
    ).fetchone()
    if row is None:
        return f"game {game_id}: <b>no such game</b>"
    if row["merged_into"]:
        now = _current_game(conn, game_id)
        return f"game {game_id} was merged into — " + _game_said(conn, now)
    years = row["year"] or "?"
    if row["last_year"] and row["last_year"] != row["year"]:
        years = f"{years}–{row['last_year']}"
    consoles = conn.execute(
        "SELECT string_agg(console, ', ' ORDER BY console) AS c, COUNT(*) AS n FROM versions"
        " WHERE game_id = ?",
        (game_id,),
    ).fetchone()
    return (
        f'<a href="/game/{game_id}" target=_blank>game {game_id}</a>: '
        f"<b>{escape(row['name'])}</b> ({years}) — {consoles['n']} versions"
        + (f": {escape(consoles['c'])}" if consoles["c"] else "")
    )


def _series_said(conn: Connection, series_id: int) -> str:
    row = conn.execute(
        "SELECT name, merged_into, (SELECT COUNT(*) FROM game_series gs"
        " WHERE gs.series_id = s.series_id AND gs.member = 1) AS games"
        " FROM series s WHERE series_id = ?",
        (series_id,),
    ).fetchone()
    if row is None:
        return f"series {series_id}: <b>no such series</b>"
    if row["merged_into"]:
        return f"series {series_id} was merged into — " + _series_said(conn, row["merged_into"])
    return (
        f'<a href="/series/{series_id}" target=_blank>series {series_id}</a>: '
        f"<b>{escape(row['name'])}</b> — {row['games']} games"
    )


# Every page the menu lists, once (owner, 2026-10-14: the menu, the home
# page's table and each page's title say one name): path → name.
PAGES = {
    "/": "Home",
    "/games": "Games",
    # One tab of manual review (owner, 2026-10-23): the advisers' disputes and
    # the model's doubts in one queue; Proposals, Advised and Trial are gone
    # from the menu (their pages stay at their addresses for an old link).
    "/review": "Review",
    "/rules": "Rules",
    "/titles": "Achievement lists",
    "/versions": "Versions",
    "/dlcs": "DLC",
    "/hltb": "HLTB",
    "/fetch": "Fetch state",
    "/payloads": "Payloads",
    "/decisions": "Answer history",
    "/conflicts": "Contradictions",
    "/recheck": "To recheck",
    "/series": "Series",
    "/octopus": "Octopus",
}


def _page(title: str, body: str) -> web.Response:
    nav = " · ".join(f'<a href="{path}">{escape(name)}</a>' for path, name in PAGES.items())
    html = (
        "<!doctype html><meta charset=utf-8>"
        '<meta name=viewport content="width=device-width,initial-scale=1">'
        "<style>body{font:14px system-ui,sans-serif;margin:8px}"
        ".scroll{overflow-x:auto}"
        "table{border-collapse:collapse;font-size:13px}"
        "td,th{border:1px solid #ccc;padding:3px 5px;vertical-align:middle;text-align:left}"
        "table.versions td:nth-child(2){min-width:140px}"
        "table.versions img{max-width:64px;height:auto;max-height:40px}"
        # A press shows at once (owner, 2026-10-15): the button sinks while
        # held, and once its form is sent it turns green and says so, every
        # button of that form locked until the next page comes.
        "button{transition:transform .06s,background .1s}"
        "button:active,button.down{transform:scale(.94);background:#bbb}"
        "button.sent{background:#2e7d32;color:#fff;border-color:#2e7d32}"
        "form.sending button:not(.sent){opacity:.45}</style>"
        # A phone shows :active late or not at all: the press is marked on
        # the touch itself.
        "<script>document.addEventListener('pointerdown',function(e){"
        "var b=e.target.closest('button');if(b)b.classList.add('down')});"
        "['pointerup','pointercancel','pointerleave'].forEach(function(t){"
        "document.addEventListener(t,function(e){var b=e.target.closest&&"
        "e.target.closest('button');if(b)b.classList.remove('down')})});"
        "document.addEventListener('submit',function(e){"
        "if(e.defaultPrevented)return;var f=e.target,b=e.submitter;"
        "if(f.classList.contains('sending')){"
        "e.preventDefault();return}f.classList.add('sending');"
        "if(b){b.classList.add('sent');b.textContent='✓ '+b.textContent}"
        "setTimeout(function(){f.querySelectorAll('button').forEach("
        "function(x){x.disabled=true})},0)})</script>"
        # One look for every question (owner, 2026-10-24): the advisers'
        # cards' styles, on every page.
        f"{CARD_CSS}<title>{escape(title)}</title>"
        f"<p>{nav}</p><h1>{escape(title)}</h1>{body}"
    )
    return web.Response(text=html, content_type="text/html")


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, _Html):
        return str(value)
    text = str(value)
    return escape(text if len(text) <= 300 else text[:300] + "…")


def _table(
    rows: list[Row],
    links: dict[str, object] | None = None,
    extra: dict[str, object] | None = None,
) -> str:
    """Rows as a table; `links[column]` makes that column a link (a function
    of the row giving the href); `extra[title]` adds a last column of HTML of
    its own (a function of the row: a button)."""
    if not rows:
        return "<p>(none)</p>"
    links = links or {}
    extra = extra or {}
    columns = rows[0].keys()
    head = "".join(f"<th>{escape(c)}</th>" for c in [*columns, *extra])
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
        cells += [f"<td>{make(row)}</td>" for make in extra.values()]  # type: ignore[operator]
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f"<div class=scroll><table><tr>{head}</tr>{''.join(body)}</table></div>"


def _record(row: Row | None, links: dict[str, object] | None = None) -> str:
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


def _store_href(row: Row) -> str:
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


def _store_link(row: Row, label: str | None = None, href: str | None = None) -> str:
    """The store page, always its own small "↗" link beside a name that
    opens our page (owner, 2026-10-12), with whether it is on sale; no page
    known: said so, with no link. Never a search."""
    label = label if label is not None else str(row["store"])
    href = _store_href(row) if href is None else href
    sale = f" <small>{_sale_word(row['on_sale'])}</small>" if "on_sale" in row.keys() else ""
    if not href or href == "#":
        return f"{escape(label)} <small>(no store page)</small>{sale}"
    return f'<a href="{escape(href)}" target=_blank>{escape(label)} ↗</a>{sale}'


def _sale_word(on_sale: object) -> str:
    """Whether the store offers it now (`versions.on_sale`; owner, 2026-10-12)."""
    if on_sale is None:
        return "unknown"
    return "on sale" if on_sale else "off sale"


def _console_sql(store: str = "v.store", console: str = "v.console") -> str:
    """A version's platform as shown (`stores.console_label`, the same
    table), for a query's own lists."""
    cases = " ".join(f"WHEN '{k}' THEN '{v}'" for k, v in PC_LABELS.items())
    return (
        f"CASE WHEN {console} = 'pc' THEN CASE {store} {cases} ELSE '{PC_UNKNOWN}' END"
        f" ELSE {console} END"
    )


def _hours(main: object, plus: object = None, hundred: object = None) -> str:
    """An entry's hours (HLTB gives seconds) in one line: main, main + extra,
    completionist."""
    parts = []
    for seconds, word in ((main, "main"), (plus, "+extra"), (hundred, "100%")):
        if isinstance(seconds, int) and seconds > 0:
            parts.append(f"{word} {round(seconds / 3600, 1)}h")
    return " · ".join(parts)


def _entry_hours(row: dict | Row) -> str:
    return _hours(row["comp_main"], row["comp_plus"], row["comp_100"])


def _platform_hours_html(got: dict | None) -> str:
    """What HLTB says of a version or a DLC: its entry, and the row of its
    platform (or the group of platforms that has it)."""
    if got is None:
        return "<p>(no HLTB entry linked)</p>"
    entry = got["entry"]
    html = (
        f'<p>entry <a href="/hltb/{entry["hltb_id"]}">{escape(entry["name"])}</a>'
        f" ({escape(entry['game_type'] or '?')}, {escape(str(entry['link_source']))}):"
        f" {escape(_entry_hours(entry) or 'no hours')}</p>"
    )
    platform = got["platform"]
    if platform is None:
        return html + "<p>HLTB has no platform for this console</p>"
    if got["row"]:
        row = got["row"]
        return html + (
            f"<p><b>{escape(platform)}</b>: {escape(_entry_hours(row) or 'no hours')}"
            f" · {row['count_comp'] or 0} finished it</p>"
        )
    if got["group"]:
        group = got["group"]
        return html + (
            f"<p><b>{escape(platform)}</b> (the group {escape(group['platforms'])}):"
            f" {escape(_entry_hours(group) or 'no hours')}</p>"
        )
    return html + f"<p>no row for {escape(platform)} on this entry</p>"


async def _game_hltb_html(repo: Repo, game_id: int, members: list) -> str:
    """A game's HLTB: its main game's entry, and each version's platform row."""
    found = await repo.game_hltb(game_id)
    if found is None:
        return "<p>(no HLTB entry linked)</p>"
    entry = found["entry"]
    html = (
        f'<p>main game: <a href="/hltb/{entry["hltb_id"]}">{escape(entry["name"])}</a>'
        f" ({escape(entry['game_type'] or '?')}): {escape(_entry_hours(entry) or 'no hours')}</p>"
    )
    if found["others"]:
        html += "<p>other entries: " + ", ".join(
            f'<a href="/hltb/{e["hltb_id"]}">{escape(e["name"])}</a>' for e in found["others"]
        )
        html += "</p>"
    rows = []
    for m in members:
        got = await repo.version_hltb_platform(int(m["version_id"]))
        if got is None:
            continue
        part = got["row"] or got["group"]
        rows.append(
            f'<tr><td><a href="/version/{m["version_id"]}">{m["version_id"]}</a></td>'
            f"<td>{escape(m['console'])}</td><td>{escape(got['platform'] or '—')}</td>"
            f"<td>{escape(_entry_hours(part) if part else '')}</td>"
            f"<td>{escape(got['entry']['name'])}</td></tr>"
        )
    if rows:
        html += (
            "<table><tr><th>version</th><th>console</th><th>HLTB platform</th><th>hours</th>"
            "<th>entry</th></tr>" + "".join(rows) + "</table>"
        )
    return html


# A version's picture: its store's cover, else its achievement list's, else
# the picture of the HLTB entry it is linked to.
COVER = (
    "COALESCE(v.media::jsonb ->> 'cover', v.media::jsonb ->> 'poster',"
    # The list's cover as the bot keeps it on disk (#55): Xbox's 360 art
    # answers no https, so its address alone is no picture here.
    " (SELECT '/covers/' || t.cover_path FROM achievement_list_connectors t WHERE t.platform = "
    "v.platform"
    "  AND t.title_id = v.title_id AND t.cover_path IS NOT NULL),"
    " (SELECT t.icon_url FROM achievement_list_connectors t WHERE t.platform = v.platform"
    "  AND t.title_id = v.title_id),"
    " (SELECT COALESCE('/covers/' || h.image_path, h.image_url) FROM version_hltb vh"
    "  JOIN hltb_entries h ON h.hltb_id = vh.hltb_id"
    "  WHERE vh.version_id = v.version_id AND vh.source <> 'rejected'"
    "  AND h.image_url IS NOT NULL LIMIT 1)) AS cover"
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


def _dlc_href(row: Row) -> str:
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


def _edition_href(row: Row) -> str:
    """An edition on its store: an Xbox bundle's page, a Steam package's."""
    if row["store"] == "xbox":
        return f"https://www.xbox.com/en-US/games/store/x/{row['store_id']}"
    if row["store"] == "steam":
        return f"https://store.steampowered.com/sub/{row['store_id']}"
    return "#"


def _list_href(row: Row) -> str:
    return f"/list/{quote(str(row['platform']))}/{quote(str(row['title_id']))}"


def _title_href(row: Row) -> str:
    return f"/title/{quote(str(row['platform']))}/{quote(str(row['title_id']))}"


def _version_href(row: Row) -> str:
    return f"/version/{row['version_id']}"


def _hltb_href(row: Row) -> str:
    return f"/hltb/{row['hltb_id']}"


def _payload_href(row: Row) -> str:
    return "/payload?" + urlencode({"subject": row["subject"], "source": row["source"]})


def _search_form(action: str, q: str) -> str:
    return (
        f'<form action="{action}"><input name=q value="{escape(q)}" size=40>'
        " <button>search</button></form>"
    )


# The home page: every table of the games database, in the groups the model
# has (owner, 2026-10-15: one row each, the current model only). `count` is
# what is counted when it is not every row.
_HOME_SECTIONS = (
    (
        "Games",
        (
            (
                "games",
                "/games",
                "what the model built over the versions (a game merged into another is not counted)",  # noqa: E501
                "merged_into IS NULL",
            ),
            (
                "versions",
                "/versions",
                "a store product on one console, or a stand-in made from an achievement list; each is in one game",  # noqa: E501
                None,
            ),
            ("dlcs", "/dlcs", "add-ons the stores list for each version", None),
            ("editions", "/games", "bundles and editions the stores sell around a version", None),
            ("edition_items", "/games", "what each edition holds", None),
            (
                "game_relations",
                "/games",
                "remaster, remake, VR version, compilation: how games relate",
                None,
            ),
            (
                "series",
                "/series",
                "series; a game is in several (its franchise's, a local one, LEGO)",
                "merged_into IS NULL",
            ),
            ("game_series", "/series", "which game is in which series, how sure and why", None),
        ),
    ),
    (
        "Answers",
        (
            (
                "match_decisions",
                "/decisions",
                "every answer on a pair of versions: yours and the advisers'",
                None,
            ),
            ("match_pairs", "/review", "the pairs the model is unsure of: its review queue", None),
            ("match_decisions", "/conflicts", "answers that contradict each other", None),
            (
                "game_relations",
                "/recheck",
                "relations the linker set by itself, for the advisers to recheck",
                None,
            ),
        ),
    ),
    (
        "HowLongToBeat (the mirror)",
        (
            (
                "hltb_entries",
                "/hltb",
                "a game or additional content HLTB has a page for, every field the page gives (hours in seconds)",  # noqa: E501
                None,
            ),
            ("hltb_platform_times", "/hltb", "an entry's own row for a platform", None),
            ("hltb_platform_groups", "/hltb", "platforms HLTB gives one set of hours", None),
            ("hltb_entry_platforms", "/hltb", "the platforms an entry is on", None),
            ("hltb_review_scores", "/hltb", "how many of HLTB's users gave each score", None),
            (
                "hltb_related",
                "/hltb",
                "entries a page names that are not its additional content",
                None,
            ),
            (
                "version_hltb",
                "/hltb",
                "which entry each version is (auto, manual or rejected)",
                None,
            ),
            ("dlc_hltb", "/hltb", "which entry each DLC is (auto, manual or rejected)", None),
        ),
    ),
    (
        "Sources",
        (
            ("source_payloads", "/payloads", "each store's last answer, kept as it came", None),
            (
                "fetch_state",
                "/fetch",
                "when each source was asked for each game, and when it is due again",
                None,
            ),
        ),
    ),
    (
        "Achievement lists (the bot's)",
        (
            (
                "achievement_list_connectors",
                "/titles",
                "an achievement list on one platform that somebody here has",
                None,
            ),
            (
                "title_achievements",
                "/titles",
                "every achievement of those lists: names, descriptions, rarity",
                None,
            ),
            (
                "seen_achievements",
                "/titles",
                "what each account earned, achievement by achievement",
                None,
            ),
        ),
    ),
)


async def home(request: web.Request) -> web.Response:
    rows = []
    with _db(request) as conn:
        for section, tables in _HOME_SECTIONS:
            rows.append(f"<tr><th colspan=4 style='background:#eee'>{escape(section)}</th></tr>")
            for table, path, what, where in tables:
                sql = f"SELECT COUNT(*) FROM {table}" + (f" WHERE {where}" if where else "")
                count = conn.execute(sql).fetchone()[0]
                extra = ""
                if table == "hltb_entries":
                    read = conn.execute(
                        "SELECT COUNT(*) FROM hltb_entries WHERE page_read_at IS NOT NULL"
                    ).fetchone()[0]
                    extra = f" · its own page read for {read}"
                rows.append(
                    f"<tr><td>{table}</td><td align=right>{count}</td>"
                    f'<td><a href="{path}">{escape(PAGES[path])}</a></td>'
                    f"<td>{escape(what)}{extra}</td></tr>"
                )
    head = "<tr><th>table</th><th>rows</th><th>page</th><th>what it holds</th></tr>"
    return _page(PAGES["/"], _search_form("/titles", "") + f"<table>{head}{''.join(rows)}</table>")


async def titles(request: web.Request) -> web.Response:
    q = request.query.get("q", "")
    with _db(request) as conn:
        rows = conn.execute(
            "SELECT t.platform, t.title_id, t.name, t.name_ru,"
            "  (SELECT vh.hltb_id FROM versions v JOIN version_hltb vh"
            "   ON vh.version_id = v.version_id WHERE v.platform = t.platform"
            "   AND v.title_id = t.title_id AND vh.source <> 'rejected'"
            "   ORDER BY vh.source = 'manual' DESC, vh.score IS NULL, vh.score DESC, vh.hltb_id"
            "   LIMIT 1) AS hltb_id, " + STEAM_APP_OF_TITLE + " AS steam_appid,"
            "  (SELECT COUNT(*) FROM versions v WHERE v.platform = t.platform"
            "   AND v.title_id = t.title_id) AS versions,"
            "  (SELECT COUNT(*) FROM title_achievements a WHERE a.platform = t.platform"
            "   AND a.title_id = t.title_id AND a.listed = 1) AS achievements"
            " FROM achievement_list_connectors t WHERE ? = '' OR t.name ILIKE ? OR t.name_ru ILIKE "
            "? OR t.title_id = ?"
            " ORDER BY versions DESC, t.updated_at DESC LIMIT ?",
            (q, f"%{q}%", f"%{q}%", q, PAGE_SIZE),
        ).fetchall()
    return _page(
        PAGES["/titles"],
        _search_form("/titles", q)
        + _table(
            rows,
            {
                "title_id": _title_href,
                "name": _title_href,
                "hltb_id": _hltb_href,
                "achievements": _list_href,
            },
        ),
    )


async def title(request: web.Request) -> web.Response:
    platform, title_id = request.match_info["platform"], request.match_info["title_id"]
    with _db(request) as conn:
        row = conn.execute(
            "SELECT * FROM achievement_list_connectors WHERE platform = ? AND title_id = ?",
            (platform, title_id),
        ).fetchone()
        versions = conn.execute(
            "SELECT version_id, name, store, product_id, stand_in, on_sale,"
            f" {_console_sql('store', 'console')} AS console, kind, developer, publisher,"
            " release_date, also_on, store_group, origin, found_how, found_via FROM versions"
            " WHERE platform = ? AND title_id = ? ORDER BY console",
            (platform, title_id),
        ).fetchall()
        groups = conn.execute(
            "SELECT group_id, name, name_ru, total FROM title_groups WHERE title_id = ?",
            (title_id,),
        ).fetchall()
        prefix = {"steam": "steam:", "xbox_modern": "xbox_title:", "psn": "psn_list:"}.get(platform)
        subjects = [f"{prefix}{title_id}"] if prefix else []
        entry = conn.execute(
            "SELECT vh.hltb_id FROM versions v JOIN version_hltb vh ON vh.version_id = v.version_id"
            " WHERE v.platform = ? AND v.title_id = ? AND vh.source <> 'rejected'"
            " ORDER BY vh.source = 'manual' DESC, vh.score IS NULL, vh.score DESC, vh.hltb_id"
            " LIMIT 1",
            (platform, title_id),
        ).fetchone()
        if entry is not None:
            subjects.append(f"hltb:{entry['hltb_id']}")
        listed = conn.execute(
            "SELECT COUNT(*) FROM title_achievements WHERE platform = ? AND title_id = ?"
            " AND listed = 1",
            (platform, title_id),
        ).fetchone()[0]
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
        + _record(row, {})
        + (
            f'<p>HLTB entry: <a href="/hltb/{entry["hltb_id"]}">{entry["hltb_id"]}</a></p>'
            if entry
            else ""
        )
        + f'<p><a href="{here.replace("/title/", "/list/", 1)}">its achievements ({listed})</a></p>'
        + "<h2>Versions (store products on one console)</h2>"
        + _table(_with_store(versions), {"version_id": _version_href, "name": _version_href})
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
            "SELECT v.version_id, v.name, v.store, v.product_id, v.stand_in, v.on_sale,"
            f" {_console_sql()} AS console, v.platform, v.title_id, v.kind, v.release_date,"
            " v.origin, v.found_how, v.found_via FROM versions v"
            " WHERE ? = '' OR v.name ILIKE ? OR product_id = ? OR store_group = ?"
            " ORDER BY updated_at DESC LIMIT ?",
            (q, f"%{q}%", q, q, PAGE_SIZE),
        ).fetchall()
    return _page(
        PAGES["/versions"],
        _search_form("/versions", q) + _table(_with_store(rows), _VERSION_LINKS),
    )


async def version(request: web.Request) -> web.Response:
    version_id = int(request.match_info["version_id"])
    with _db(request) as conn:
        row = conn.execute(
            "SELECT v.* FROM versions v WHERE v.version_id = ?", (version_id,)
        ).fetchone()
        ids = [
            {"kind": kind, "id": store_id}
            for kind, store_id in json.loads((row["store_ids"] if row else None) or "[]")
        ]
        dlcs = conn.execute(
            "SELECT d.dlc_id, d.name, d.kind, d.release_date, d.store_id, d.trophy_group_id,"
            " d.on_sale, v.store, " + _DLC_HLTB + " FROM dlcs d"
            " JOIN versions v ON v.version_id = d.version_id"
            " WHERE d.version_id = ? ORDER BY d.release_date NULLS FIRST, d.name NULLS FIRST",
            (version_id,),
        ).fetchall()
        hltb = conn.execute(
            "SELECT h.hltb_id, h.name, h.game_type, vh.source FROM version_hltb vh"
            " JOIN hltb_entries h ON h.hltb_id = vh.hltb_id WHERE vh.version_id = ?",
            (version_id,),
        ).fetchall()
        siblings = (
            conn.execute(
                "SELECT version_id, store, " + _console_sql("store", "console") + " AS console,"
                " name, platform, title_id FROM versions"
                " WHERE store_group = ? AND version_id <> ?",
                (row["store_group"], version_id),
            ).fetchall()
            if row is not None and row["store_group"]
            else []
        )
        demo_of = conn.execute(
            "SELECT of_version_id, role FROM versions WHERE version_id = ?"
            " AND of_version_id IS NOT NULL",
            (version_id,),
        ).fetchone()
        pictures = conn.execute(
            "SELECT v.media,"
            " (SELECT t.icon_url FROM achievement_list_connectors t WHERE t.platform = v.platform"
            "  AND t.title_id = v.title_id) AS list_icon,"
            " (SELECT '/covers/' || t.cover_path FROM achievement_list_connectors t WHERE "
            "t.platform = v.platform"
            "  AND t.title_id = v.title_id) AS list_cover,"
            " (SELECT COALESCE('/covers/' || h.image_path, h.image_url)"
            "  FROM version_hltb vh JOIN hltb_entries h"
            "  ON h.hltb_id = vh.hltb_id WHERE vh.version_id = v.version_id"
            "  AND vh.source <> 'rejected' AND h.image_url IS NOT NULL LIMIT 1) AS hltb_image"
            " FROM versions v WHERE v.version_id = ?",
            (version_id,),
        ).fetchone()
        games = conn.execute(
            "SELECT v.game_id, g.name, v.role, v.link_p AS p FROM versions v"
            " JOIN games g ON g.game_id = v.game_id WHERE v.version_id = ?",
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
                " WHERE subject ILIKE ?",
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
        + _record(
            {**dict(row), "console": console_label(row["store"], row["console"])} if row else row,  # type: ignore[arg-type]
            {"title_id": _title_href},
        )
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
        + _dlc_table(dlcs)
        + "<h2>HLTB</h2>"
        + _table(hltb, {"hltb_id": _hltb_href, "name": _hltb_href})
        + _platform_hours_html(await _repo(request).version_hltb_platform(version_id))
        + unlinks
        + "<h2>Raw answers</h2>"
        + _table(payloads, {"subject": _payload_href})
    )
    return _page(f"Version {version_id}", body)


async def dlcs(request: web.Request) -> web.Response:
    q = request.query.get("q", "")
    with _db(request) as conn:
        rows = conn.execute(
            "SELECT d.dlc_id, d.name, d.kind, d.release_date, d.store_id, d.trophy_group_id,"
            " d.on_sale, v.store, d.version_id, v.name AS version,"
            f" {_console_sql()} AS console, " + _DLC_HLTB + " FROM dlcs d"
            " JOIN versions v ON v.version_id = d.version_id"
            " WHERE ? = '' OR d.name ILIKE ? OR v.name ILIKE ? ORDER BY d.updated_at DESC LIMIT ?",
            (q, f"%{q}%", f"%{q}%", PAGE_SIZE),
        ).fetchall()
    return _page(PAGES["/dlcs"], _search_form("/dlcs", q) + _dlc_table(rows))


# A DLC's HLTB entry (`dlc_hltb`): its id, name and times, the first if several.
_DLC_HLTB = (
    "(SELECT h.hltb_id FROM dlc_hltb dh JOIN hltb_entries h ON h.hltb_id = dh.hltb_id"
    " WHERE dh.dlc_id = d.dlc_id AND dh.source <> 'rejected' ORDER BY h.hltb_id LIMIT 1)"
    " AS hltb_id,"
    " (SELECT h.comp_main FROM dlc_hltb dh JOIN hltb_entries h ON h.hltb_id = dh.hltb_id"
    " WHERE dh.dlc_id = d.dlc_id AND dh.source <> 'rejected' ORDER BY h.hltb_id LIMIT 1)"
    " AS hltb_times"
)


def _dlc_table(rows: list[Row]) -> str:
    """DLC rows: the name opens our page, the store is its own "↗" with
    whether it is sold, HLTB's entry and times where one is linked."""
    shown = []
    for r in rows:
        item: dict[str, object] = {
            "dlc_id": r["dlc_id"],
            "name": r["name"],
            "kind": r["kind"],
            "release_date": r["release_date"],
        }
        if "version" in r.keys():
            item["version"] = r["version"]
            item["console"] = r["console"]
        item["store page"] = _Html(_store_link(r, str(r["store"]), _dlc_href(r)))
        item["hltb"] = _Html(
            f'<a href="/hltb/{r["hltb_id"]}">{r["hltb_id"]}</a>'
            f" <small>{escape(_hours(r['hltb_times']))}</small>"
            if r["hltb_id"]
            else ""
        )
        if "version_id" in r.keys():
            item["version_id"] = r["version_id"]
        shown.append(item)
    return _table(
        shown,  # type: ignore[arg-type]
        {
            "dlc_id": lambda r: f"/dlc/{r['dlc_id']}",
            "name": lambda r: f"/dlc/{r['dlc_id']}",
            "version": lambda r: f"/version/{r['version_id']}",
            "version_id": lambda r: f"/version/{r['version_id']}",
        },
    )


async def dlc_read(request: web.Request) -> web.Response:
    """A PlayStation add-on's page read now (#215: a long list is kept by
    its ids, each page read when wanted)."""
    from bot.services import psn_products

    dlc_id = int(request.match_info["dlc_id"])
    with _db(request) as conn:
        row = conn.execute("SELECT store_id FROM dlcs WHERE dlc_id = ?", (dlc_id,)).fetchone()
    if row is None or not row["store_id"]:
        raise _back(f"/dlc/{dlc_id}", "no store id")
    read = await psn_products.read_one(_repo(request), str(row["store_id"]))
    raise _back(f"/dlc/{dlc_id}", "page read" if read else "no such page on the store")


async def dlc(request: web.Request) -> web.Response:
    """A DLC's own page (owner, 2026-10-12): its version and game, its store
    page, whether it is sold, its HLTB entry and times."""
    dlc_id = int(request.match_info["dlc_id"])
    with _db(request) as conn:
        row = conn.execute(
            "SELECT d.*, v.store, v.name AS version, " + _console_sql() + " AS console,"
            " v.game_id, g.name AS game FROM dlcs d"
            " JOIN versions v ON v.version_id = d.version_id"
            " LEFT JOIN games g ON g.game_id = v.game_id WHERE d.dlc_id = ?",
            (dlc_id,),
        ).fetchone()
        hltb = conn.execute(
            "SELECT h.hltb_id, h.name, h.game_type, h.parent_hltb_id, h.comp_main, h.comp_plus,"
            " h.comp_100, dh.source"
            " FROM dlc_hltb dh JOIN hltb_entries h ON h.hltb_id = dh.hltb_id WHERE dh.dlc_id = ?",
            (dlc_id,),
        ).fetchall()
        twins = (
            conn.execute(
                "SELECT d.dlc_id, d.name, d.kind, d.release_date, d.store_id, d.trophy_group_id,"
                " d.on_sale, v.store, d.version_id, v.name AS version,"
                f" {_console_sql()} AS console, " + _DLC_HLTB + " FROM dlcs d"
                " JOIN versions v ON v.version_id = d.version_id"
                " WHERE d.store_id = ? AND v.store = ? AND d.dlc_id <> ?",
                (row["store_id"], row["store"], dlc_id),
            ).fetchall()
            if row is not None and row["store_id"]
            else []
        )
    if row is None:
        return _page(f"DLC {dlc_id}", "<p>(no such DLC)</p>")
    head = (
        f"<p>{_img(row['image_url'], 80)}</p>"
        f'<p>of <a href="/version/{row["version_id"]}">{escape(row["version"] or "")}</a>'
        f" [{escape(row['console'])}]"
        + (
            f' · in <a href="/game/{row["game_id"]}">{escape(row["game"] or "")}</a>'
            if row["game_id"]
            else ""
        )
        + f" · {_store_link(row, 'on the store', _dlc_href(row))}</p>"
    )
    if row["store"] == "psn" and row["store_id"] and not row["name"]:
        # One of a long list kept by its id only (#215): its page read when
        # it is wanted.
        head += (
            f'<form method=post action="/dlc/{dlc_id}/read">'
            "<button>read the PSN page</button>"
            " <small>listed by id: the game has over 100 DLC</small></form>"
        )
    body = (
        head
        + _record(row)
        + "<h2>HLTB</h2>"
        + (
            "".join(
                f'<p><a href="/hltb/{h["hltb_id"]}">{escape(h["name"])}</a>'
                f" <small>({escape(h['game_type'] or '?')}, {escape(h['source'])})</small>"
                f" — {escape(_hours(h['comp_main'], h['comp_plus'], h['comp_100']) or '-')}</p>"
                for h in hltb
            )
            or "<p>(no HLTB entry linked)</p>"
        )
        + _platform_hours_html(await _repo(request).dlc_hltb_platform(dlc_id))
        + "<h2>The same add-on on the store's other versions</h2>"
        + _dlc_table(twins)
    )
    return _page(f"DLC: {row['name'] or dlc_id}", body)


def _hours1(seconds: object) -> str:
    return f"{round(seconds / 3600, 1)}" if isinstance(seconds, int) and seconds > 0 else ""


async def hltb_list(request: web.Request) -> web.Response:
    """The mirror's entries: searchable, by type, read or not, a hundred a page."""
    q = request.query.get("q", "").strip()
    kind = request.query.get("type", "")
    read = request.query.get("read", "")
    page = max(0, int(request.query.get("page", "0") or 0))
    where, params = ["1 = 1"], []
    if q:
        where.append("(e.name ILIKE ? OR e.alias ILIKE ? OR CAST(e.hltb_id AS TEXT) = ?)")
        params += [f"%{q}%", f"%{q}%", q]
    if kind:
        where.append("e.game_type = ?")
        params.append(kind)
    if read in ("yes", "no"):
        where.append("e.page_read_at IS " + ("NOT NULL" if read == "yes" else "NULL"))
    clause = " AND ".join(where)
    with _db(request) as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM hltb_entries e WHERE {clause}", params
        ).fetchone()[0]
        rows = conn.execute(
            "SELECT e.hltb_id, e.name, e.game_type AS type, p.name AS main_game, e.release_year AS year,"  # noqa: E501
            " e.comp_main, e.comp_plus, e.comp_100,"
            " (SELECT COUNT(*) FROM hltb_entry_platforms x WHERE x.hltb_id = e.hltb_id) AS platforms,"  # noqa: E501
            " e.count_comp AS finished, e.review_score AS score,"
            " (SELECT COUNT(*) FROM version_hltb vh WHERE vh.hltb_id = e.hltb_id"
            "  AND vh.source <> 'rejected') AS versions,"
            " (SELECT COUNT(*) FROM dlc_hltb dh WHERE dh.hltb_id = e.hltb_id"
            "  AND dh.source <> 'rejected') AS dlcs,"
            " e.page_read_at IS NOT NULL AS page_read"
            f" FROM hltb_entries e LEFT JOIN hltb_entries p ON p.hltb_id = e.parent_hltb_id"
            f" WHERE {clause} ORDER BY e.name LIMIT ? OFFSET ?",
            (*params, PAGE_SIZE, page * PAGE_SIZE),
        ).fetchall()
        types = conn.execute(
            "SELECT game_type, COUNT(*) FROM hltb_entries GROUP BY 1 ORDER BY 2 DESC"
        ).fetchall()
        reads = dict(
            conn.execute(
                "SELECT page_read_at IS NOT NULL, COUNT(*) FROM hltb_entries GROUP BY 1"
            ).fetchall()
        )
    shown = [
        {
            "hltb_id": r["hltb_id"],
            "name": r["name"],
            "type": r["type"],
            "main game": r["main_game"],
            "year": r["year"],
            "main h": _hours1(r["comp_main"]),
            "extra h": _hours1(r["comp_plus"]),
            "100% h": _hours1(r["comp_100"]),
            "platforms": r["platforms"],
            "finished it": r["finished"],
            "score": r["score"],
            "versions": r["versions"],
            "dlc": r["dlcs"],
            "page read": "yes" if r["page_read"] else "no",
        }
        for r in rows
    ]

    def link(label: str, **query: str) -> str:
        merged = {"q": q, "type": kind, "read": read, **query}
        return f'<a href="/hltb?{urlencode({k: v for k, v in merged.items() if v})}">{escape(label)}</a>'  # noqa: E501

    filters = (
        "<p>type: "
        + link("all", type="")
        + " · "
        + " · ".join(link(f"{t or '?'} ({n})", type=t or "") for t, n in types)
        + "</p><p>page read: "
        + link("all", read="")
        + f" · {link(f'yes ({reads.get(1, 0)})', read='yes')}"
        + f" · {link(f'no ({reads.get(0, 0)})', read='no')}</p>"
    )
    pager = (
        f"<p>{total} entries"
        + (f" · {link('‹ previous', page=str(page - 1))}" if page else "")
        + (f" · {link('next ›', page=str(page + 1))}" if (page + 1) * PAGE_SIZE < total else "")
        + "</p>"
    )
    form = (
        f'<form action="/hltb"><input name=q value="{escape(q)}" size=40 placeholder="name, alias or id">'  # noqa: E501
        f'<input type=hidden name=type value="{escape(kind)}">'
        f'<input type=hidden name=read value="{escape(read)}"> <button>search</button></form>'
    )
    table = _table(shown, {"hltb_id": _hltb_href, "name": _hltb_href})  # type: ignore[arg-type]
    return _page(PAGES["/hltb"], form + filters + pager + table)


async def hltb_entry(request: web.Request) -> web.Response:
    hltb_id = int(request.match_info["hltb_id"])
    with _db(request) as conn:
        row = conn.execute("SELECT * FROM hltb_entries WHERE hltb_id = ?", (hltb_id,)).fetchone()
        parent = (
            conn.execute(
                "SELECT hltb_id, name, game_type FROM hltb_entries WHERE hltb_id = ?",
                (row["parent_hltb_id"],),
            ).fetchone()
            if row is not None and row["parent_hltb_id"]
            else None
        )
        children = conn.execute(
            "SELECT hltb_id, name, game_type, comp_main, comp_plus, comp_100, page_read_at"
            " FROM hltb_entries WHERE parent_hltb_id = ? ORDER BY name",
            (hltb_id,),
        ).fetchall()
        platform_rows = conn.execute(
            "SELECT platform, comp_main, comp_plus, comp_100, comp_low, comp_high, count_comp,"
            " count_total FROM hltb_platform_times WHERE hltb_id = ?"
            " ORDER BY count_total DESC NULLS LAST",
            (hltb_id,),
        ).fetchall()
        groups = conn.execute(
            "SELECT platforms, comp_main, comp_plus, comp_100, comp_all, compare, count_comp"
            " FROM hltb_platform_groups WHERE hltb_id = ? ORDER BY count_comp DESC NULLS LAST",
            (hltb_id,),
        ).fetchall()
        platforms = [
            r[0]
            for r in conn.execute(
                "SELECT platform FROM hltb_entry_platforms WHERE hltb_id = ? ORDER BY platform",
                (hltb_id,),
            )
        ]
        reviews = conn.execute(
            "SELECT score, votes FROM hltb_review_scores WHERE hltb_id = ? ORDER BY score",
            (hltb_id,),
        ).fetchall()
        related = conn.execute(
            "SELECT e.hltb_id, e.name, e.game_type FROM hltb_related r"
            " JOIN hltb_entries e ON e.hltb_id = r.related_id WHERE r.hltb_id = ?",
            (hltb_id,),
        ).fetchall()
        linked = conn.execute(
            "SELECT v.version_id, v.name, v.store, v.product_id, v.stand_in, v.on_sale,"
            f" {_console_sql()} AS console, v.platform, v.title_id, vh.source, vh.score"
            " FROM version_hltb vh JOIN versions v ON v.version_id = vh.version_id"
            " WHERE vh.hltb_id = ?",
            (hltb_id,),
        ).fetchall()
        dlcs_ = conn.execute(
            "SELECT d.dlc_id, d.name, d.kind, d.release_date, d.store_id, d.trophy_group_id,"
            " d.on_sale, v.store, d.version_id, v.name AS version,"
            f" {_console_sql()} AS console, " + _DLC_HLTB + " FROM dlc_hltb dh"
            " JOIN dlcs d ON d.dlc_id = dh.dlc_id JOIN versions v ON v.version_id = d.version_id"
            " WHERE dh.hltb_id = ? AND dh.source <> 'rejected'",
            (hltb_id,),
        ).fetchall()
        titles_ = conn.execute(
            "SELECT DISTINCT t.platform, t.title_id, t.name FROM version_hltb vh"
            " JOIN versions v ON v.version_id = vh.version_id"
            " JOIN achievement_list_connectors t ON t.platform = v.platform AND t.title_id = "
            "v.title_id"
            " WHERE vh.hltb_id = ? AND vh.source <> 'rejected'",
            (hltb_id,),
        ).fetchall()
    if row is None:
        return _page(f"HLTB {hltb_id}", "<p>(not found)</p>")

    def hours_table(rows_: list[tuple]) -> str:
        return _table(
            [
                {
                    "kind": name,
                    "headline": _hours1(row[prefix]),
                    "average": _hours1(row[f"{prefix}_avg"])
                    if f"{prefix}_avg" in row.keys()
                    else "",
                    "median": _hours1(row[f"{prefix}_med"])
                    if f"{prefix}_med" in row.keys()
                    else "",
                    "fastest": _hours1(
                        row[f"{prefix}_l"] if f"{prefix}_l" in row.keys() else row[f"{prefix}_min"]
                    ),
                    "slowest": _hours1(
                        row[f"{prefix}_h"] if f"{prefix}_h" in row.keys() else row[f"{prefix}_max"]
                    ),
                    "people": row[f"{prefix}_count"],
                }
                for name, prefix in rows_
                if row[prefix] or row[f"{prefix}_count"]
            ]
        )

    def plat(r: Row) -> dict:
        return {
            "platform": r["platform"],
            "main h": _hours1(r["comp_main"]),
            "extra h": _hours1(r["comp_plus"]),
            "100% h": _hours1(r["comp_100"]),
            "fastest": _hours1(r["comp_low"]),
            "slowest": _hours1(r["comp_high"]),
            "finished": r["count_comp"],
            "all players": r["count_total"],
        }

    def grp(r: Row) -> dict:
        return {
            "platforms": r["platforms"],
            "main h": _hours1(r["comp_main"]),
            "extra h": _hours1(r["comp_plus"]),
            "100% h": _hours1(r["comp_100"]),
            "all h": _hours1(r["comp_all"]),
            "compare": r["compare"],
            "finished": r["count_comp"],
        }

    def kids(r: Row) -> dict:
        return {
            "hltb_id": r["hltb_id"],
            "name": r["name"],
            "type": r["game_type"],
            "main h": _hours1(r["comp_main"]),
            "extra h": _hours1(r["comp_plus"]),
            "100% h": _hours1(r["comp_100"]),
            "page read": "yes" if r["page_read_at"] else "no",
        }

    bar = "".join(
        f"<tr><td align=right>{r['score']}</td><td>{'▇' * max(1, round(40 * r['votes'] / max(x['votes'] for x in reviews)))}"  # noqa: E501
        f" {r['votes']}</td></tr>"
        for r in reviews
    )
    modes = [
        w
        for w, key in (
            ("single", "comp_lvl_sp"),
            ("co-op", "comp_lvl_co"),
            ("multiplayer", "comp_lvl_mp"),
            ("speedrun", "comp_lvl_spd"),
        )
        if row[key]
    ]
    body = (
        _img("/covers/" + row["image_path"] if row["image_path"] else row["image_url"], 160)
        + f"<p><b>{escape(row['name'])}</b> · {escape(row['game_type'] or '?')}"
        + (
            f' · of <a href="/hltb/{parent["hltb_id"]}">{escape(parent["name"])}</a>'
            if parent is not None
            else ""
        )
        + f' · <a href="https://howlongtobeat.com/game/{hltb_id}">on HowLongToBeat</a>'
        + f' · <a href="/payload?subject=hltb:{hltb_id}&source=hltb_page">raw page</a></p>'
        + (
            "<p><i>its own page was never read: only what another page says of it is here</i></p>"
            if not row["page_read_at"]
            else ""
        )
        + f"<p>platforms: {escape(', '.join(platforms) or '—')} · modes: {escape(', '.join(modes) or '—')}"  # noqa: E501
        + f" · score {row['review_score'] or '—'} ({row['review_count'] or 0} votes)</p>"
        + f"<p>released: world {escape(str(row['release_world'] or '—'))}, NA {escape(str(row['release_na'] or '—'))},"  # noqa: E501
        + f" EU {escape(str(row['release_eu'] or '—'))}, JP {escape(str(row['release_jp'] or '—'))}</p>"  # noqa: E501
        + "<h2>Hours (all platforms)</h2>"
        + hours_table(
            [
                ("main story", "comp_main"),
                ("main + extras", "comp_plus"),
                ("completionist", "comp_100"),
                ("all styles", "comp_all"),
                ("speedrun", "comp_speed"),
                ("speedrun 100%", "comp_speed100"),
                ("co-op", "invested_co"),
                ("multiplayer", "invested_mp"),
            ]
        )
        + "<h2>By platform (HLTB's own row)</h2>"
        + _table([plat(r) for r in platform_rows])
        + "<h2>Groups of platforms with one set of hours</h2>"
        + _table([grp(r) for r in groups])
        + "<h2>HLTB's users</h2>"
        + f"<p>finished {row['count_comp'] or 0} · playing {row['count_playing'] or 0} · backlog {row['count_backlog'] or 0}"  # noqa: E501
        + f" · replays {row['count_replay'] or 0} · retired {row['count_retired'] or 0} · total {row['count_total'] or 0}</p>"  # noqa: E501
        + (f"<table>{bar}</table>" if reviews else "<p>(no scores)</p>")
        + "<h2>DLC and additional content</h2>"
        + _table([kids(c) for c in children], {"hltb_id": _hltb_href, "name": _hltb_href})  # type: ignore[arg-type]
        + "<h2>Other entries it names</h2>"
        + _table(related, {"hltb_id": _hltb_href, "name": _hltb_href})
        + "<h2>Versions linked</h2>"
        + _table(
            _with_store(linked),
            {"version_id": _version_href, "name": _version_href, "title_id": _title_href},
        )
        + "<h2>Our DLC it is (its game's DLC, matched)</h2>"
        + _dlc_table(dlcs_)
        + "<h2>Achievement lists of those versions</h2>"
        + _table(titles_, {"title_id": _title_href, "name": _title_href})
        + "<h2>Every field</h2>"
        + _record(row, {"parent_hltb_id": lambda r: f"/hltb/{r['parent_hltb_id']}"})
    )
    return _page(f"HLTB {hltb_id}: {row['name']}", body)


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
        PAGES["/fetch"],
        _flash(request) + _table(rows, {"subject": _payload_href}) + "<h2>Ask again</h2>" + buttons,
    )


async def payloads(request: web.Request) -> web.Response:
    with _db(request) as conn:
        rows = conn.execute(
            "SELECT subject, source, fetched_at, length(payload) AS bytes FROM source_payloads"
            " ORDER BY fetched_at DESC LIMIT ?",
            (PAGE_SIZE * 3,),
        ).fetchall()
    return _page(PAGES["/payloads"], _table(rows, {"subject": _payload_href}))


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


def _with_store(rows: list[Row]) -> list[dict]:
    """Version rows with their store page as a column of its own ("↗" and
    whether it is sold) — the name beside it opens our page."""
    shown = []
    for row in rows:
        item = {k: row[k] for k in row.keys() if k not in ("stand_in", "on_sale")}
        item["store page"] = _Html(_store_link(row, str(row["store"])))
        shown.append(item)
    return shown


class _Html(str):
    """A cell already written as HTML (`_cell` leaves it as it is)."""


def _game_href(row: Row) -> str:
    return f"/game/{row['game_id']}"


_VERSION_LINKS = {
    "version_id": _version_href,
    "name": _version_href,
    "title_id": _title_href,
    "achievements": _list_href,
    "demo_of": lambda r: f"/version/{r['demo_of']}",
}


# The operator's answers, quick ones first (owner, 2026-10-11: the review
# should take a tap; everything else is a step further). About two versions:
# Worded by the sides' numbers, 1 above, 2 below (owner, 2026-10-24: "1 a
# demo of 2, or 2 of 1?" — "it" and "this" did not say which).
_DECISIONS_QUICK = (
    ("same", "1 and 2 are one game"),
    ("other", "1 and 2 are different games"),
    ("remaster_of", "1 is a remaster of 2"),
    ("remake_of", "1 is a remake of 2"),
    ("enhanced_of", "1 is an enhanced edition of 2"),
)
_DECISIONS_MORE = (
    ("enhanced_of:flip", "2 is an enhanced edition of 1"),
    ("remaster_of:flip", "2 is a remaster of 1"),
    ("remake_of:flip", "2 is a remake of 1"),
    ("demo_of", "1 is a demo of 2"),
    ("demo_of:flip", "2 is a demo of 1"),
    ("tool_of", "1 is a tool for 2"),
    ("tool_of:flip", "2 is a tool for 1"),
    ("mode_of", "1 is a mode of 2 (a launcher of one of its modes)"),
    ("mode_of:flip", "2 is a mode of 1"),
    ("extra_of", "1 is the soundtrack / artbook of 2"),
    ("extra_of:flip", "2 is the soundtrack / artbook of 1"),
    ("pass_of", "1 is a friend's pass of 2"),
    ("pass_of:flip", "2 is a friend's pass of 1"),
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
    ("extra_of", "this is a soundtrack / artbook of that"),
    ("extra_of:flip", "that is a soundtrack / artbook of this"),
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
    extra: str = "",
) -> str:
    """Answers as the advisers' cards draw them (owner, 2026-10-24: one look
    for every question): the quick ones a button a line — a quick label is
    HTML, its parts in bold —, the rest under «Own answer…», each a button;
    `extra` (a field to name a series) under the quick ones."""
    fields = "".join(
        f'<input type=hidden name={k} value="{escape(str(v))}">'
        for k, v in {**hidden, "back": back}.items()
    )
    picks = "".join(
        f'<button name=decision value="{escape(key)}">{label}</button>' for key, label in quick
    )
    rest = "".join(
        f'<button name=decision value="{escape(key)}">{escape(label)}</button>'
        for key, label in more
    )
    own = (
        f"<details class=own><summary>Own answer…</summary><div class=more>{rest}</div></details>"
        if rest
        else ""
    )
    return (
        f'<form method=post action="{action}" style="margin:0">{fields}'
        f"<div class=picks>{picks}</div></form>{extra}"
        f'<form method=post action="{action}" style="margin:0">{fields}{own}</form>'
    )


def _card(badge: str, note: str, sides: list[str], answers: str, why: str = "") -> str:
    """One question as a card, the advisers' look: what it is, the model's
    word, the sides with their pictures, the answers, why (folded)."""
    return (
        f"<div class=tq><h3><span class=badge>{escape(badge)}</span><small>{note}</small></h3>"
        + "".join(f"<div class=subj>{side}</div>" for side in sides)
        + answers
        + (
            f"<details class=why><summary>why the model thinks so</summary>{why}</details>"
            if why
            else ""
        )
        + "</div>"
    )


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
        "enhanced_of": f"{a} is an {bold('enhanced edition')} of {b}",
        "remake_of": f"{a} is a {bold('remake')} of {b}",
        "contains": f"{a} is a {bold('compilation that holds')} {b}",
        "vr_of": f"{a} is the {bold('VR version')} of {b}",
        "extra_of": f"{a} is the {bold('soundtrack / artbook')} of {b}",
        "pass_of": f"{a} is a {bold('friend’s pass')} of {b}",
        "demo_of": f"{a} is a {bold('demo / beta')} of {b}",
    }.get(relation, f"{a} {bold(relation)} {b}")


def _game_name(conn: Connection, game_id: int) -> str:
    row = conn.execute("SELECT name FROM games WHERE game_id = ?", (game_id,)).fetchone()
    return str(row[0]) if row and row[0] else f"game {game_id}"


def _game_picker(
    game_id: int,
    other_game: int,
    back: str,
    guess: str = "",
    names: tuple[str, str] | None = None,
    series: list[tuple[int, str]] | None = None,
) -> str:
    """The answers about two games: the model's guess, another of the series
    — which series (owner, 2026-10-24: "one series" with no name chained
    LEGO into Star Wars) —, skip; the rest under "more…". With the games'
    names every button says what it records."""
    this, that = names or ("this game", "that game")
    quick = []
    if guess in _GUESS_WORDS:
        quick.append((guess, f"✓ <b>Model</b>: {_relation_sentence(guess, this, that)}"))
    quick += [
        (f"series#{sid}", f"one series — <b>{escape(name)}</b>") for sid, name in series or []
    ]
    quick.append(("skip", "ask later"))
    named = (
        f'<form method=post action="/decide-games" class=free style="margin:4px 0">'
        f'<input type=hidden name=game_id value="{game_id}">'
        f'<input type=hidden name=other_game value="{other_game}">'
        f'<input type=hidden name=back value="{escape(back)}">'
        '<input type=hidden name=decision value="series#new">'
        "<input class=other name=series_name list=series-names required"
        f" placeholder='{'one series — another' if series else 'one series — which?'}"
        " (several: comma-separated)'>"
        "<button>ok</button></form>"
    )
    return _answer_forms(
        "/decide-games",
        {"game_id": game_id, "other_game": other_game},
        quick,
        tuple(
            (key, _relation_sentence(key, this, that, html=False) if names else label)
            for key, label in _GAME_DECISIONS
        ),
        back,
        named,
    )


PART_DECISIONS = ("demo_of", "tool_of", "mode_of", "extra_of", "pass_of", "enhanced_of")

# The labelling queue's answers (the training audit, 2026-10-24): the rare
# relations are one tap, as one game and another game are.
_LABEL_QUICK = (
    ("same", "1 and 2 are one game"),
    ("other", "1 and 2 are different games"),
    ("remaster_of", "1 is a remaster of 2"),
    ("enhanced_of", "1 is an enhanced edition of 2"),
    ("remake_of", "1 is a remake of 2"),
    ("contains", "1 is a compilation holding 2"),
    ("vr_of", "1 is the VR version of 2"),
)
_LABEL_MORE = (
    ("remaster_of:flip", "2 is a remaster of 1"),
    ("remake_of:flip", "2 is a remake of 1"),
    ("contains:flip", "2 is a compilation holding 1"),
    ("vr_of:flip", "2 is the VR version of 1"),
    # The parts of a game, as the version answers have them (owner,
    # 2026-10-24: «Tiny Bunny: Prologue» is a demo, and there was no way).
    *(item for item in _DECISIONS_MORE if item[0].split(":")[0] in PART_DECISIONS),
    ("skip", "skip: ask again later"),
)
# The relations the queue asks about, rarest among the operator's labels first.
RARE_RELATIONS = ("vr_of", "contains", "remake_of", "remaster_of")
LABEL_FLOOR = 0.1  # a relation the model gives at least this is worth asking
ASKED = "asked"  # a pair put in the labelling queue by hand


def _label_picker(
    version_id: int, other_id: int, back: str, series: list[tuple[int, str]] | None = None
) -> str:
    return _versions_picker(version_id, other_id, back, _LABEL_QUICK, _LABEL_MORE, series)


def _decision_picker(
    version_id: int, other_id: int, back: str, series: list[tuple[int, str]] | None = None
) -> str:
    """The answers about two versions: one game, another game, a remaster, a
    remake, another game of its series — the rest under "more…"."""
    return _versions_picker(version_id, other_id, back, _DECISIONS_QUICK, _DECISIONS_MORE, series)


def _versions_picker(
    version_id: int,
    other_id: int,
    back: str,
    quick: tuple[tuple[str, str], ...],
    more: tuple[tuple[str, str], ...],
    series: list[tuple[int, str]] | None,
) -> str:
    """ "Another game of its series" is a frequent answer (owner, 2026-10-24):
    one button per series either game is in, naming it; with none, a field
    to name it (several by commas)."""
    buttons = [(key, escape(label)) for key, label in quick]
    buttons += [
        (f"series#{sid}", f"1 and 2: another game of the series (<b>{escape(name)}</b>)")
        for sid, name in series or []
    ]
    named = (
        '<form method=post action="/decide" class=free style="margin:4px 0">'
        f'<input type=hidden name=version_id value="{version_id}">'
        f'<input type=hidden name=other_id value="{other_id}">'
        f'<input type=hidden name=back value="{escape(back)}">'
        '<input type=hidden name=decision value="series#new">'
        "<input class=other name=series_name list=series-names required"
        f" placeholder='another game of the series — {'another' if series else 'which'}?"
        " (several: comma-separated)'>"
        "<button>ok</button></form>"
    )
    return _answer_forms(
        "/decide",
        {"version_id": version_id, "other_id": other_id},
        buttons,
        tuple((k, label) for k, label in more if k != "series"),
        back,
        named,
    )


async def rules(request: web.Request) -> web.Response:
    """The model's signs and each class's weight for each, as it decides now."""
    from bot.services import game_match as m

    w = m.current_weights()
    signs = list(dict.fromkeys(k for c in m.CLASSES for k in m.WEIGHTS[c]))
    head = "".join(f"<th>{escape(c)}</th>" for c in m.CLASSES)
    rows = "".join(
        f"<tr><td>{escape(k)}</td>"
        + "".join(
            f"<td align=right>{w[c][k]:+.1f}</td>" if k in w.get(c, {}) else "<td></td>"
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
        f" and are what the weights will be fitted to. Model: {escape(m.model_name())}.</p>"
        "<p>name = similarity − 0.8; years_gap counts the years past the first (at most 9);"
        f" achievements are compared when both lists have {m.ACHIEVEMENTS_MIN}+ names.</p>"
        f"<div class=scroll><table><tr><th>sign</th>{head}</tr>{rows}</table></div>"
    )
    return _page(PAGES["/rules"], body)


def _achievements_link(v: Row) -> str:
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
            " ORDER BY listed DESC, name_en NULLS FIRST",
            (platform, title_id),
        ).fetchall()
        title = conn.execute(
            "SELECT name FROM achievement_list_connectors WHERE platform = ? AND title_id = ?",
            (platform, title_id),
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
            "  (SELECT COUNT(*) FROM versions v WHERE v.game_id = g.game_id) AS versions,"
            "  (SELECT COUNT(*) FROM match_pairs mp JOIN versions v"
            "   ON v.version_id IN (mp.version_id, mp.other_id)"
            "   WHERE v.game_id = g.game_id) AS review,"
            "  (SELECT string_agg(r.kind || ' ' || r.related_id, ',' ORDER BY r.related_id, r.kind)"
            "   FROM game_relations r"
            "   WHERE r.game_id = g.game_id) AS relates,"
            f"  (SELECT string_agg(DISTINCT {_console_sql()}, ',') FROM versions v"
            "   WHERE v.game_id = g.game_id AND v.role <> 'covered') AS consoles"
            " FROM games g WHERE g.merged_into IS NULL AND (? = '' OR g.name ILIKE ?)"
            " ORDER BY versions DESC, g.game_id DESC LIMIT ?",
            (q, f"%{q}%", PAGE_SIZE * 3),
        ).fetchall()
    return _page(
        PAGES["/games"],
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
            "SELECT v.version_id, v.store, v.product_id, v.stand_in, v.on_sale,"
            f" {_console_sql()} AS console, v.name, v.release_date, v.developer, v.platform,"
            " v.title_id, " + COVER + ", v.role, v.of_version_id, v.link_p AS p"
            " FROM versions v WHERE v.game_id = ? ORDER BY v.release_date NULLS FIRST, v.console",
            (game_id,),
        ).fetchall()
        relations = conn.execute(
            "SELECT 'this ' || r.kind AS relation, r.related_id AS game_id, g.name, g.year,"
            " r.source, ROUND(r.p::numeric, 2)::float8 AS p FROM game_relations r"
            " JOIN games g ON g.game_id = r.related_id WHERE r.game_id = ?"
            " UNION ALL SELECT r.kind || ' this', r.game_id, g.name, g.year, r.source,"
            " ROUND(r.p::numeric, 2)::float8"
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
            "SELECT d.version_id, v.store, " + _console_sql() + " AS console,"
            " v.name AS version, v.product_id, v.stand_in, v.on_sale AS version_on_sale,"
            " d.dlc_id, d.name, d.kind, d.release_date, d.store_id, d.trophy_group_id,"
            " d.on_sale, " + _DLC_HLTB + " FROM dlcs d"
            " JOIN versions v ON v.version_id = d.version_id WHERE v.game_id = ?"
            " ORDER BY v.store, v.console, d.version_id, d.release_date NULLS FIRST,"
            " d.name NULLS FIRST",
            (game_id,),
        ).fetchall()
        # What the stores sell around it, by what each holds (owner,
        # 2026-10-24; `stores.classify_bundle`): its editions, the bundles it
        # is one game of, those it is thrown into, and packs of its add-ons.
        held = (
            "SELECT DISTINCT e.edition_id, e.store, e.store_id, e.name, e.kind, e.on_sale,"
            " e.first_seen_at, e.last_seen_at,"
            " (SELECT string_agg(COALESCE(i2.name, i2.store_id) || ' [' || i2.item_kind || ']',"
            "  '; ' ORDER BY i2.seq) FROM edition_items i2"
            "  WHERE i2.edition_id = e.edition_id) AS holds"
            " FROM editions e JOIN edition_items i ON i.edition_id = e.edition_id"
            " JOIN versions v ON v.version_id = i.version_id"
            " WHERE v.game_id = ? AND {} ORDER BY e.store, e.name NULLS FIRST"
        )
        editions = conn.execute(held.format(OWN_EDITION), (game_id,)).fetchall()
        in_bundles = conn.execute(held.format(PART_OF_BUNDLE), (game_id,)).fetchall()
        bonus_in = conn.execute(held.format(BONUS_IN), (game_id,)).fetchall()
        packs = conn.execute(
            "SELECT DISTINCT e.edition_id, e.store, e.store_id, e.name, e.on_sale,"
            " (SELECT string_agg(COALESCE(i2.name, i2.store_id), '; ' ORDER BY i2.seq)"
            "  FROM edition_items i2 WHERE i2.edition_id = e.edition_id) AS holds"
            " FROM editions e JOIN edition_items i ON i.edition_id = e.edition_id"
            " JOIN dlcs d ON d.store_id = i.store_id"
            " JOIN versions v ON v.version_id = d.version_id"
            " WHERE e.scope = 'addon_pack' AND v.game_id = ? ORDER BY e.name NULLS FIRST",
            (game_id,),
        ).fetchall()
        hltb = conn.execute(
            # HLTB's platforms: where the game also came out, as no store
            # we read says (Nintendo, older consoles, PC outside Steam).
            "SELECT DISTINCT h.hltb_id, h.name, h.game_type, h.release_year,"
            " (SELECT string_agg(p.platform, ', ' ORDER BY p.platform) FROM hltb_entry_platforms p"
            "  WHERE p.hltb_id = h.hltb_id) AS also_released_on FROM version_hltb vh"
            " JOIN hltb_entries h ON h.hltb_id = vh.hltb_id"
            " JOIN versions v ON v.version_id = vh.version_id"
            " WHERE v.game_id = ? AND vh.source <> 'rejected'",
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
            + _button("/octopus/add", "assemble with the octopus", {"keys": f"game:{game_id}"})
            + f'<form method=post action="{here}/merge">merge this game into game id: '
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
        series_part = _game_series_section(conn, game_id)
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
        + "<h2>HowLongToBeat</h2>"
        + await _game_hltb_html(_repo(request), game_id, members)
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
        + series_part
        + ("<h2>To review</h2>" + cards if pairs else "")
        + "<h2>The operator's labels on these versions</h2>"
        + _table(
            labels,
            {
                "version_id": lambda r: f"/version/{r['version_id']}",
                "other_id": lambda r: f"/version/{r['other_id']}",
            },
        )
        + "<h2>Editions</h2>"
        + _editions_table(editions)
        + "<h2>In store bundles of several games</h2>"
        + _editions_table(in_bundles)
        + "<h2>Thrown into another game's edition</h2>"
        + _editions_table(bonus_in)
        + "<h2>DLC, by version</h2>"
        + _dlcs_by_version(dlcs)
        + "<h2>Add-on packs</h2>"
        + _editions_table(packs)
        + "<h2>HLTB</h2>"
        + _table(hltb, {"hltb_id": _hltb_href, "name": _hltb_href})
        + "<h2>Detach</h2>"
        + detach
    )
    return _page(row["name"] if row else f"Game {game_id}", body)


def _editions_table(rows: list[Row]) -> str:
    return _table(
        [
            {
                **{k: e[k] for k in e.keys() if k != "on_sale"},
                "store page": _Html(_store_link(e, str(e["store"]), _edition_href(e))),
            }
            for e in rows
        ]  # type: ignore[arg-type]
    )


def _identity(conn: Connection, game_id: int) -> str:
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
            parts.append(str(row[field]) + (" and others" if row[f"more_{field}s"] else ""))
    badge = _KIND_BADGES.get(row["kind"], "")
    return f"{' · '.join(parts)} (game {game_id})" + (f" {badge}" if badge else "")


# What a game is (owner, 2026-10-12), as a badge beside its name.
_KIND_BADGES = {"compilation": "📦 compilation", "extra": "🎵 not a game"}
_KIND_WORDS = {"game": "a game", "compilation": "a compilation", "extra": "not a game"}


def _version_cards(rows: list[Row]) -> str:
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


def _pair_rows(
    conn: Connection,
    pairs: list[Row],
    back: str,
    advice: AdviceStore | None = None,
    picker: Callable[..., str] = _decision_picker,
) -> str:
    """Doubtful pairs as one table: the subject and its game, what the model
    thinks and how sure, the other and its game, and the answer."""
    if not pairs:
        return "<p>(nothing to review)</p>"
    ids = sorted({r["subject"] for r in pairs} | {r["other"] for r in pairs})
    marks = ",".join("?" * len(ids))
    info = {
        r["version_id"]: r
        for r in conn.execute(
            "SELECT v.version_id, v.name, " + _console_sql() + " AS console, v.release_date,"
            " v.store, v.product_id,"
            " v.stand_in, v.on_sale, v.developer, " + COVER + ", v.game_id, g.name AS game,"
            " g.year"
            " FROM versions v LEFT JOIN games g ON g.game_id = v.game_id"
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

    cards = []
    for r in pairs:
        feats = json.loads(r["features"]) if r["features"] else {}
        signs = ", ".join(k for k in feats if k != "bias")
        answers = picker(r["subject"], r["other"], back, _series_of_pair(conn, info, r))
        answers += _advice_badge(
            advice,
            *(
                versions_pair_id(a, g)
                for a, b in ((r["subject"], r["other"]), (r["other"], r["subject"]))
                if (g := (info.get(b) or {"game_id": None})["game_id"]) is not None
            ),
        )
        cards.append(
            _card(
                "Version ↔ version",
                f"the model: <b>{escape(r['relation'])}</b> {r['p']:.2f}",
                [
                    f"<span class=badge>1</span>{side(r['subject'])}",
                    f"<span class=badge>2</span>{side(r['other'])}",
                ],
                answers,
                escape(signs),
            )
        )
    return "".join(cards)


def _series_of_pair(conn: Connection, info: dict, row: Row) -> list[tuple[int, str]]:
    """The series either version's game is in, those of both first."""
    games = [(info.get(v) or {"game_id": None})["game_id"] for v in (row["subject"], row["other"])]
    games = [g for g in games if g is not None]
    if not games:
        return []
    marks = ",".join("?" * len(games))
    return [
        (int(x[0]), str(x[1]))
        for x in conn.execute(
            "SELECT s.series_id, s.name FROM series s JOIN game_series gs"
            " ON gs.series_id = s.series_id AND gs.member = 1"
            f" WHERE gs.game_id IN ({marks}) AND s.merged_into IS NULL"
            " GROUP BY s.series_id ORDER BY COUNT(DISTINCT gs.game_id) DESC, s.name",
            games,
        )
    ]


def _dlcs_by_version(rows: list[Row]) -> str:
    """A DLC belongs to a version (owner, 2026-10-09): one block per version,
    named with its store and console."""
    if not rows:
        return "<p>(none)</p>"
    blocks: dict[int, list[Row]] = {}
    for row in rows:
        blocks.setdefault(int(row["version_id"]), []).append(row)
    parts = []
    for version_id, items in blocks.items():
        head = items[0]
        version_row = {**dict(head), "on_sale": head["version_on_sale"]}
        parts.append(
            f'<h3><a href="/version/{version_id}">{escape(head["version"] or "")}</a>'
            f" · {escape(head['store'])} {escape(head['console'])}"
            f" · {_store_link(version_row, 'store page')} · {len(items)} DLC</h3>"
            + _dlc_table(items)  # type: ignore[arg-type]
        )
    return "".join(parts)


# Which review pairs ask about one game, and which about two related games.
_GAME_RELATIONS = ("remaster_of", "remake_of", "contains", "vr_of")


async def review(request: web.Request) -> web.Response:
    """The one tab of manual review (owner, 2026-10-23): what the advisers
    disagree on (the trial's questions, `scripts/trial_page.py`), then the
    pairs the model is unsure of — is this version that game, how do these two
    games relate (owner, 2026-10-11). Filters, not tabs: `tab` is `all`,
    `advisers`, `versions` or `games`; `kind` narrows the advisers' questions."""
    from scripts import trial_page

    tab = request.query.get("tab", "all")
    trial = request.app.get("trial_dir")
    marks = ",".join("?" * len(_GAME_RELATIONS))
    # A pair is about two games only when its versions are in two games; a
    # doubt inside one game (is this version a remaster after all?) is a
    # version question: keep it here, or move it out as another game.
    two_games = (
        "(SELECT game_id FROM versions WHERE version_id = mp.version_id) IS DISTINCT FROM"
        " (SELECT game_id FROM versions WHERE version_id = mp.other_id)"
    )
    games_where = f"mp.relation IN ({marks}) AND {two_games}"
    if tab == "label":
        return _page(
            PAGES["/review"],
            _flash(request) + _label_queue(request) + _series_datalist(request),
        )
    versions_where = f"NOT ({games_where})"
    query = request.query_string
    advisers_line, advisers_cards, advisers_open = (
        trial_page.cards(request, trial, back_base="/review" + (f"?{query}" if query else ""))
        if trial is not None
        else ("", [], 0)
    )
    sections: list[str] = []
    if tab in ("all", "advisers"):
        if advisers_cards:
            sections.append(advisers_line + "".join(advisers_cards))
        elif tab == "advisers":
            sections.append("<p>(the advisers agree on everything)</p>")
    with _db(request) as conn:
        counts = {
            name: conn.execute(
                f"SELECT COUNT(*) FROM match_pairs mp WHERE {clause}", _GAME_RELATIONS
            ).fetchone()[0]
            for name, clause in (("versions", versions_where), ("games", games_where))
        }
        advice = AdviceStore(request.app["data_dir"] / "advice")
        # A pair answered "skip" comes back, after the rest (this run of the
        # viewer remembers it; nothing is written).
        skipped = request.app["skipped"]
        back = f"/review?tab={tab}"
        for name, where, title in (
            ("versions", versions_where, "Version ↔ game — the model is unsure"),
            ("games", games_where, "Games related — the model is unsure"),
        ):
            if tab not in ("all", name) or (tab == "all" and not counts[name]):
                continue
            everything = conn.execute(
                "SELECT mp.version_id AS subject, mp.other_id AS other, mp.relation, mp.p,"
                f" mp.features FROM match_pairs mp WHERE {where} ORDER BY mp.p DESC",
                _GAME_RELATIONS,
            ).fetchall()
            pairs = sorted(
                everything,
                key=lambda r: frozenset((r["subject"], r["other"])) in skipped,
            )[:PAGE_SIZE]
            rows = (
                _game_pair_rows(conn, pairs, back, advice)
                if name == "games"
                else _pair_rows(conn, pairs, back, advice)
            )
            sections.append(f"<h2>{title} ({counts[name]})</h2>{rows}")
    total = advisers_open + counts["versions"] + counts["games"]

    def chip(label: str, href: str, on: bool) -> str:
        return f"<b>{escape(label)}</b>" if on else f'<a href="{href}">{escape(label)}</a>'

    kind = request.query.get("kind", "")
    later = request.query.get("later") == "1"
    chips = [
        chip(f"All ({total})", "/review", tab == "all" and not kind and not later),
        chip(
            f"Advisers disagree ({advisers_open})",
            "/review?tab=advisers",
            tab == "advisers" and not kind and not later,
        ),
        chip(f"Version ↔ game ({counts['versions']})", "/review?tab=versions", tab == "versions"),
        chip(f"Games related, model ({counts['games']})", "/review?tab=games", tab == "games"),
        chip("Labelling", "/review?tab=label", False),
    ]
    if trial is not None:
        chips += [
            chip(name, f"/review?tab=advisers&kind={k}", tab == "advisers" and kind == k)
            for k, name in trial_page.kinds()
        ]
        chips.append(chip("Postponed", "/review?tab=advisers&later=1&done=1", later))
    head = (
        f"<p>{' · '.join(chips)}</p>"
        "<p><small>One tap records the answer. «Own answer…» has the rest.</small></p>"
    )
    return _page(
        PAGES["/review"], _flash(request) + head + "".join(sections) + _series_datalist(request)
    )


def _series_datalist(request: web.Request) -> str:
    """Every series' name, offered as one types a series."""
    with _db(request) as conn:
        names = [
            str(r[0])
            for r in conn.execute("SELECT name FROM series WHERE merged_into IS NULL ORDER BY name")
        ]
    return (
        "<datalist id=series-names>"
        + "".join(f'<option value="{escape(n)}">' for n in names)
        + "</datalist>"
    )


def label_queue(
    conn: Connection,
    skipped: set | frozenset = frozenset(),
    requested: list[dict] | tuple = (),
) -> tuple[list[tuple[Row, str]], dict[str, int], list[str]]:
    """Pairs to label for the model's sake (the training audit, 2026-10-24):
    the doubtful pairs in which the model gives a rare relation — a VR
    version, a compilation, a remake, a remaster — at least `LABEL_FLOOR`,
    not yet answered by the operator. The relation the operator has answered
    least comes first, then the pairs the model is least sure of. Returns
    (row, its rare relation) in that order, the operator's counts, and the
    relations' order. `requested`: pairs asked for by hand
    (`AdviceStore.label_requests`), first of all, as `ASKED`."""
    answered = {
        str(r[0]): int(r[1])
        for r in conn.execute(
            "SELECT relation, COUNT(*) FROM match_decisions WHERE decided_by = 'viewer'"
            " GROUP BY relation"
        )
    }
    order = sorted(RARE_RELATIONS, key=lambda c: (answered.get(c, 0), RARE_RELATIONS.index(c)))
    labelled = {
        frozenset((int(r[0]), int(r[1])))
        for r in conn.execute(
            "SELECT version_id, other_id FROM match_decisions WHERE decided_by = 'viewer'"
        )
    }
    found: list[tuple[tuple[int, float], Row, str]] = []
    for r in conn.execute(
        "SELECT version_id AS subject, other_id AS other, relation, p, probs, features"
        " FROM match_pairs"
    ):
        pair = frozenset((int(r["subject"]), int(r["other"])))
        if pair in labelled:
            continue
        probs = json.loads(r["probs"] or "{}")
        rare = max(RARE_RELATIONS, key=lambda c: probs.get(c, 0.0))
        if probs.get(rare, 0.0) < LABEL_FLOOR:
            continue
        # Least sure first: the rare relation nearest to even odds.
        found.append(((order.index(rare), abs(probs[rare] - 0.5) + (pair in skipped)), r, rare))
    found.sort(key=lambda t: t[0])
    asked: list[tuple[Row, str]] = []
    queued: set[frozenset[int]] = set()
    for r in requested:
        pair = frozenset((int(r["subject"]), int(r["other"])))
        if pair not in labelled and pair not in queued:
            queued.add(pair)
            asked.append((r, ASKED))
    return asked + [(r, rare) for _, r, rare in found], answered, order


def _label_queue(request: web.Request) -> str:
    """The labelling queue (`label_queue`) as a page."""
    with _db(request) as conn:
        advice = AdviceStore(request.app["data_dir"] / "advice")
        queue, answered, order = label_queue(conn, request.app["skipped"], advice.label_requests())
        asked = sum(1 for _, x in queue if x == ASKED)
        tally = " · ".join(
            ([f"asked for by hand: {asked}"] if asked else [])
            + [
                f"{escape(c)}: {answered.get(c, 0)} answered,"
                f" {sum(1 for _, x in queue if x == c)} to ask"
                for c in order
            ]
        )
        rows = _pair_rows(
            conn, [r for r, _ in queue[:PAGE_SIZE]], "/review?tab=label", advice, _label_picker
        )
    return (
        "<h2>Labelling — rare relations</h2>"
        f"<p><small>{tally}</small></p>"
        "<p><small>Pairs where the model allows a VR version, a compilation, a remake"
        " or a remaster;"
        " first what you have answered least. Every answer goes into training."
        "</small></p>" + rows
    )


def _game_card(conn: Connection, game_id: int) -> str:
    """A game in one cell: its covers, name and identity, consoles."""
    row = conn.execute(
        f"SELECT (SELECT string_agg(DISTINCT {_console_sql()}, ',') FROM versions v"
        "  WHERE v.game_id = ? AND v.role <> 'covered') AS consoles,"
        " (SELECT " + COVER.replace(" AS cover", "") + " FROM versions v"
        "  WHERE v.game_id = ? AND v.role IN ('version', 'edition', 'enhanced') LIMIT 1) AS cover",
        (game_id, game_id),
    ).fetchone()
    return (
        f"{_img(row['cover'], 40)} "
        f'<a href="/game/{game_id}">{escape(_identity(conn, game_id))}</a>'
        f"<br><small>{escape(row['consoles'] or '')}</small>"
    )


def _game_pair_rows(
    conn: Connection,
    pairs: list[Row],
    back: str,
    advice: AdviceStore | None = None,
) -> str:
    """Doubtful relations between games, game against game."""
    if not pairs:
        return "<p>(nothing to review)</p>"
    lines = []
    seen: set[frozenset[int]] = set()
    for r in pairs:
        ga = conn.execute(
            "SELECT game_id FROM versions WHERE version_id = ? AND game_id IS NOT NULL",
            (r["subject"],),
        ).fetchone()
        gb = conn.execute(
            "SELECT game_id FROM versions WHERE version_id = ? AND game_id IS NOT NULL",
            (r["other"],),
        ).fetchone()
        if ga is None or gb is None or frozenset((ga[0], gb[0])) in seen:
            continue  # one row per pair of games, the surest
        seen.add(frozenset((ga[0], gb[0])))
        feats = json.loads(r["features"]) if r["features"] else {}
        signs = ", ".join(k for k in feats if k != "bias")
        names = (_game_name(conn, ga[0]), _game_name(conn, gb[0]))
        shared = [
            (int(x[0]), str(x[1]))
            for x in conn.execute(
                "SELECT s.series_id, s.name FROM series s"
                " JOIN game_series a ON a.series_id = s.series_id"
                "  AND a.game_id = ? AND a.member = 1"
                " JOIN game_series b ON b.series_id = s.series_id"
                "  AND b.game_id = ? AND b.member = 1"
                " WHERE s.merged_into IS NULL ORDER BY s.name",
                (ga[0], gb[0]),
            )
        ]
        lines.append(
            _card(
                "Games related",
                f"the model: <b>{escape(r['relation'])}</b> {r['p']:.2f}",
                [_game_card(conn, ga[0]), _game_card(conn, gb[0])],
                _game_picker(ga[0], gb[0], back, str(r["relation"]), names, shared)
                + _advice_badge(advice, games_pair_id(ga[0], gb[0]), games_pair_id(gb[0], ga[0])),
                escape(signs),
            )
        )
    return "".join(lines)


# Who besides the operator may give an answer (`decided_by`): the advisers
# agreeing, with or without the model (owner, 2026-10-12).
ADVISERS = set(ADVISER_SOURCES)

# Where a pair stands with the advisers, worded for the review tabs.
_ADVICE_WORDS = {
    "unknown": "not asked yet",
    "waiting_both": "waits for Claude and Gemini",
    "waiting_claude": "waits for Claude",
    "waiting_gemini": "waits for Gemini",
    "conflict": "Claude and Gemini disagree — yours",
    "agreed": "advisers agree — not written yet",
    "applied": "answered by the advisers",
    "operator": "answered by you",
    "recorded": "advisers agree — kept aside (no way to write it yet)",
}


def _advice_badge(advice: AdviceStore | None, *pair_ids: str) -> str:
    """The advisers' state of a pair (either way round), a small line under
    its answer buttons; nothing when the pair was never exported."""
    if advice is None:
        return ""
    for pair_id in pair_ids:
        state = advice.state(pair_id)
        if state.state != "unknown":
            word = _ADVICE_WORDS.get(state.state, state.state)
            said = ""
            if state.state == "conflict":
                # Who said what (owner, 2026-10-24): the operator decides
                # between them.
                said = " · ".join(
                    f"{name}: {escape(str(a['relation']))}"
                    + (f" ({escape(str(a['direction']))})" if a.get("direction") else "")
                    + f", {escape(str(a['confidence']))}"
                    for name, a in (("Claude", state.claude), ("Gemini", state.gemini))
                    if a
                )
                said = f"<br><small>{said}</small>" if said else ""
            return f"<br><small>advisers: <b>{escape(word)}</b></small>{said}"
    return "<br><small>advisers: not asked yet</small>"


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


def _current_game(conn: Connection, game_id: int) -> int:
    """The game a game id stands for now: a game merged into another is an
    empty row pointing at it (merged_into), followed to its end."""
    seen = {game_id}
    while True:
        row = conn.execute("SELECT merged_into FROM games WHERE game_id = ?", (game_id,)).fetchone()
        if row is None or row[0] is None or row[0] in seen:
            return game_id
        game_id = row[0]
        seen.add(game_id)


def _game_detail(conn: Connection, game_id: int) -> str:
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
        " "
        + _console_sql()
        + " AS console, v.release_date, v.platform, v.title_id, v.role, "
        + COVER
        + ","
        " (SELECT COUNT(*) FROM title_achievements a WHERE a.platform = v.platform"
        "  AND a.title_id = v.title_id) AS achievements"
        " FROM versions v"
        " WHERE v.game_id = ? AND v.role <> 'covered'"
        " ORDER BY v.release_date NULLS FIRST, v.console",
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


_ADVISED_WHY = {
    "overruled": "Claude and Gemini against the model",
    "conflict": "Claude and Gemini disagree",
}


def _opinion(who: str, answer: dict | None, this: str, that: str, kind: str) -> str:
    """One adviser's (or the model's) answer as a line: for two games a
    sentence naming them, else the relation and its direction."""
    if not answer:
        return f"<b>{who}</b>: —"
    relation = str(answer.get("relation") or "?")
    direction = answer.get("direction")
    decision = _adviser_decision(answer)
    if kind in ("games", "versions") and decision:
        said = _relation_sentence(decision, this, that)
        if relation == "extra":
            said += " (<b>not a game</b>)"
    else:
        arrow = ""
        if direction == "first":
            arrow = " (FIRST → SECOND)"
        elif direction == "second":
            arrow = " (SECOND → FIRST)"
        said = f"<b>{escape(relation)}</b>{arrow}"
    extra = []
    if answer.get("p") is not None:
        extra.append(f"{float(answer['p']):.0%}")
    if answer.get("confidence"):
        extra.append(str(answer["confidence"]))
    why = f"<br><small>{escape(str(answer['why']))}</small>" if answer.get("why") else ""
    return f"<b>{who}</b> ({escape(', '.join(extra))}): {said}{why}"


def _adviser_decision(answer: dict | None) -> str | None:
    """An adviser's (or the model's) answer as the decision a button posts:
    the relation, ":flip" when SECOND is the remaster / demo / … of FIRST,
    "other" for not related or not a game; None for unsure."""
    if not answer:
        return None
    relation = str(answer.get("relation") or "")
    if relation in ("", "unsure"):
        return None
    if relation in ("not_related", "extra"):
        return "other"
    if answer.get("direction") == "second":
        return f"{relation}:flip"
    return relation


def _advised_buttons(
    action: str,
    hidden: dict[str, object],
    i: dict,
    this: str,
    that: str,
    more: tuple[tuple[str, str], ...],
    back: str,
) -> str:
    """A button for each opinion — the model's, Claude's, Gemini's — saying
    whose it is ("✓ Claude and Gemini: …" where they agree), then another of
    the series and ask later; the rest under "more…"."""
    who: dict[str, list[str]] = {}
    for name, key in (("Claude", "claude"), ("Gemini", "gemini"), ("the model", "model")):
        decision = _adviser_decision(i.get(key))
        if decision:
            who.setdefault(decision, []).append(name)
    quick = [
        (decision, f"✓ <b>{' and '.join(names)}</b>: {_relation_sentence(decision, this, that)}")
        for decision, names in who.items()
    ]
    if "series" not in who:
        quick.append(("series", "another game of the series"))
    quick.append(("skip", "ask later"))
    return _answer_forms(action, hidden, quick, more, back)


def _advised_sides(conn: Connection, i: dict, back: str) -> tuple[str, str, str, str]:
    """A re-check card's two sides, the names its sentences use, and its
    answer buttons."""
    t = i["type"]
    if t == "games":
        this, that = _game_name(conn, i["game_a"]), _game_name(conn, i["game_b"])
        sides = (
            f"<div style='flex:1 1 300px'>{_game_detail(conn, i['game_a'])}</div>"
            f"<div style='flex:1 1 300px'>{_game_detail(conn, i['game_b'])}</div>"
        )
        label = i.get("label")
        if label and i["game_a"] == i["game_b"]:
            # Written "one game": the two games are one by now, so each side
            # is the version the answer is on, as the question showed it.
            flipped = (i.get("claude") or {}).get("direction") == "second"
            first, second = (label[1], label[0]) if flipped else (label[0], label[1])
            rows = {
                r["version_id"]: r
                for r in conn.execute(
                    "SELECT v.*, " + COVER + " FROM versions v WHERE v.version_id IN (?, ?)",
                    (first, second),
                )
            }
            this = str(rows[first]["name"]) if first in rows else this
            that = str(rows[second]["name"]) if second in rows else that
            sides = "".join(
                f"<div style='flex:1 1 300px'><small>{side}</small> "
                f"<small>(now game <a href='/game/{i['game_a']}'>{i['game_a']}</a>)</small><br>"
                + (f"{_img(rows[v]['cover'], 70)}<br>" if v in rows else "")
                + (_version_line(rows[v]) if v in rows else f"v{v}")
                + f"<br><small>{escape(str(i[key]))}</small></div>"
                for side, v, key in (("FIRST", first, "first"), ("SECOND", second, "second"))
            )
        more = tuple(
            (key, _relation_sentence(key, this, that, html=False)) for key, _ in _GAME_DECISIONS
        )
        label = i.get("label")
        if label:
            # Already written (the two games may be one by now): the answer
            # goes on the very pair of versions the advisers' label is on, so
            # agreeing confirms it and anything else replaces it. The label's
            # first version is FIRST's unless the written answer was flipped.
            flipped = (i.get("claude") or {}).get("direction") == "second"
            first, second = (label[1], label[0]) if flipped else (label[0], label[1])
            action, hidden = "/decide", {"version_id": first, "other_id": second}
        else:
            action, hidden = "/decide-games", {"game_id": i["game_a"], "other_game": i["game_b"]}
        buttons = _advised_buttons(action, hidden, i, this, that, more, back)
        return sides, this, that, buttons
    sides = (
        "<div style='flex:1 1 300px'><small>FIRST</small><br>"
        f"{escape(str(i['first']))}</div>"
        "<div style='flex:1 1 300px'><small>SECOND</small><br>"
        f"{escape(str(i['second']))}</div>"
    )
    if t == "versions":
        version = int(i["version_id"])
        label = i.get("label")
        other = None
        if label and version in label[:2]:
            other = label[1] if label[0] == version else label[0]
        else:
            row = conn.execute(
                "SELECT anchor_version_id FROM games WHERE game_id = ?", (i["game_id"],)
            ).fetchone()
            other = row[0] if row else None
        v = conn.execute("SELECT * FROM versions WHERE version_id = ?", (version,)).fetchone()
        sides = (
            "<div style='flex:1 1 300px'><small>this version</small><br>"
            + (_version_line(v) if v else str(version))
            + "</div><div style='flex:1 1 300px'><small>that game</small>"
            + _game_detail(conn, int(i["game_id"]))
            + "</div>"
        )
        this = str(v["name"]) if v else f"version {version}"
        that = _game_name(conn, int(i["game_id"]))
        answers = (
            _advised_buttons(
                "/decide",
                {"version_id": version, "other_id": int(other)},
                i,
                this,
                that,
                tuple(_DECISIONS_QUICK) + tuple(_DECISIONS_MORE),
                back,
            )
            if other is not None
            else "<p>(that game is gone)</p>"
        )
        return sides, this, that, answers
    answers = "<p><small>(rejecting or linking it is not here yet)</small></p>"
    if i.get("hltb_id"):
        answers = (
            f'<p><a href="/hltb/{int(i["hltb_id"])}">the HLTB entry</a> · '
            "<small>(rejecting or linking it is not here yet)</small></p>"
        )
    return sides, "FIRST", "SECOND", answers


async def advised(request: web.Request) -> web.Response:
    """The operator's second look at the advisers' work (owner, 2026-10-13):
    every pair Claude and Gemini decided against the model (already written)
    and every pair they disagreed on, of every kind, with the three opinions.
    Games and versions are answered here (the operator's word replaces the
    advisers'); an HLTB or DLC pair can only be looked at for now."""
    items = request.app["advised"]
    if not items:
        return _page("Advised", "<p>(no file: start the viewer with --advised)</p>")
    kind, why = request.query.get("type", ""), request.query.get("why", "")
    with _db(request) as conn:
        marks = ",".join("?" * len(ADVISERS))
        operator = {
            frozenset((r[0], r[1]))
            for r in conn.execute(
                "SELECT version_id, other_id FROM match_decisions"
                f" WHERE decided_by NOT IN ({marks})",
                tuple(ADVISERS),
            )
        }

        def anchor(game_id: int) -> int | None:
            row = conn.execute(
                "SELECT anchor_version_id FROM games WHERE game_id = ?", (game_id,)
            ).fetchone()
            return row[0] if row else None

        def answered(i: dict) -> bool:
            label = i.get("label")
            if label and frozenset(label[:2]) in operator:
                return True
            if i["type"] == "games":
                a, b = anchor(i["game_a"]), anchor(i["game_b"])
                return bool(a and b and frozenset((a, b)) in operator)
            return False

        open_items = [(n, i) for n, i in enumerate(items, 1) if not answered(i)]
        counts: dict[tuple[str, str], int] = {}
        for _, i in open_items:
            counts[(i["type"], i["why"])] = counts.get((i["type"], i["why"]), 0) + 1
        shown = [
            (n, i)
            for n, i in open_items
            if (not kind or i["type"] == kind) and (not why or i["why"] == why)
        ][:40]
        cards = []
        for n, i in shown:
            back = f"/advised?type={quote(kind)}&why={quote(why)}#a{n}"
            sides, this, that, answers = _advised_sides(conn, i, back)
            t = i["type"]
            written = ""
            if i.get("label"):
                written = f" · written: <b>{escape(str(i['label'][2]))}</b>"
            cards.append(
                f"<div id=a{n} style='border:1px solid #ccc;border-radius:8px;"
                "padding:8px;margin:10px 0'>"
                f"<p><b>#{n}</b> · {escape(t)} · {escape(_ADVISED_WHY.get(i['why'], i['why']))}"
                + (" · audit" if i.get("audit") else "")
                + f"{written}</p>"
                f"<div style='display:flex;flex-wrap:wrap;gap:12px'>{sides}</div>"
                f"<p>{_opinion('Model', i.get('model'), this, that, t)}<br>"
                f"{_opinion('Claude', i.get('claude'), this, that, t)}<br>"
                f"{_opinion('Gemini', i.get('gemini'), this, that, t)}</p>"
                f"{answers}</div>"
            )
    filters = " · ".join(
        f'<a href="/advised?type={k}&why={w}">{k}: {escape(_ADVISED_WHY[w])} ({c})</a>'
        for (k, w), c in sorted(counts.items())
    )
    head = (
        f"<p>{len(open_items)} open of {len(items)} · <a href='/advised'>all</a> · {filters}</p>"
        "<p><small>Your answer replaces the advisers' and leaves this list.</small></p>"
    )
    return _page("Advised", _flash(request) + head + "".join(cards))


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
                    " JOIN versions x ON x.version_id = d.version_id"
                    " JOIN versions y ON y.version_id = d.other_id"
                    " WHERE ((x.game_id = ? AND y.game_id = ?)"
                    "  OR (x.game_id = ? AND y.game_id = ?))"
                    # Claude and Gemini without the model are no answer (owner,
                    # 2026-10-15: all three must agree), the operator's is.
                    "  AND d.decided_by <> 'claude+gemini' LIMIT 1",
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

        def unanimous(i: dict) -> bool:
            # The model, Claude and Gemini saying the same is an answer
            # (owner, 2026-10-15): such a pair is not the operator's.
            gemini = (request.app["gemini"].get(i["n"]) or {}).get("decision")
            return _proposal_decision(i["answer"], i["model"]) == gemini == i["model"]

        open_items = [
            i
            for i in items
            if i["game_a"] != i["game_b"]
            and not answered(i["game_a"], i["game_b"])
            and not unanimous(i)
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
    return _page("Proposals", _flash(request) + head + "".join(cards))


async def decisions(request: web.Request) -> web.Response:
    """The latest answers, newest first — the operator's and the advisers'
    (owner, 2026-10-13: a mistaken tap is found and fixed here): each with
    whose it is, a way to answer it again and to take it back."""
    who = request.query.get("by", "")
    with _db(request) as conn:
        rows = conn.execute(
            "SELECT d.version_id, a.name AS this, "
            + _console_sql("a.store", "a.console")
            + " AS this_console,"
            " a.game_id AS this_game, d.relation, d.other_id, b.name AS that,"
            " " + _console_sql("b.store", "b.console") + " AS that_console, b.game_id AS that_game,"
            " d.decided_by, d.decided_at FROM match_decisions d"
            " JOIN versions a ON a.version_id = d.version_id"
            " JOIN versions b ON b.version_id = d.other_id"
            " WHERE (? = '' OR (? = 'operator' AND d.decided_by = 'viewer')"
            "  OR (? = 'advisers' AND d.decided_by <> 'viewer'))"
            " ORDER BY d.decided_at DESC LIMIT ?",
            (who, who, who, PAGE_SIZE * 3),
        ).fetchall()
        cards = []
        for r in rows:
            back = f"/decisions?by={quote(who)}"
            this = f"{r['this']} ({r['this_console']})"
            that = f"{r['that']} ({r['that_console']})"
            whose = "you" if r["decided_by"] == "viewer" else r["decided_by"]
            games = ""
            if r["this_game"] and r["that_game"]:
                games = (
                    f" · games <a href='/game/{r['this_game']}'>{r['this_game']}</a>"
                    f" / <a href='/game/{r['that_game']}'>{r['that_game']}</a>"
                )
            cards.append(
                "<div style='border:1px solid #ccc;border-radius:8px;padding:8px;margin:8px 0'>"
                f"<p><small>{escape(r['decided_at'][:16].replace('T', ' '))} · "
                f"<b>{escape(whose)}</b>{games}</small><br>"
                f"<a href='/version/{r['version_id']}'>v{r['version_id']}</a> → "
                f"<a href='/version/{r['other_id']}'>v{r['other_id']}</a>: "
                f"{_relation_sentence(r['relation'], this, that)}</p>"
                f"{_undo_form(r['version_id'], r['other_id'], back)}"
                "<details><summary><small>answer again…</small></summary>"
                f"{_decision_picker(r['version_id'], r['other_id'], back)}</details></div>"
            )
    tabs = " · ".join(
        (f"<b>{label}</b>" if key == who else f'<a href="/decisions?by={key}">{label}</a>')
        for key, label in (("", "all"), ("operator", "yours"), ("advisers", "the advisers'"))
    )
    return _page(
        PAGES["/decisions"],
        _flash(request) + f"<p>{tabs}</p>" + ("".join(cards) or "<p>(none)</p>"),
    )


def _undo_form(version_id: int, other_id: int, back: str) -> str:
    return (
        '<form method=post action="/decision/undo" style="margin:0 0 4px">'
        f'<input type=hidden name=version_id value="{version_id}">'
        f'<input type=hidden name=other_id value="{other_id}">'
        f'<input type=hidden name=back value="{escape(back)}">'
        "<button>✕ take this answer back</button></form>"
    )


async def decision_undo(request: web.Request) -> web.Response:
    """An answer taken back: the pair is the model's again, and the two
    versions are linked anew."""
    from bot.services.game_link import GameLinker

    form = await request.post()
    a, b = int(str(form["version_id"])), int(str(form["other_id"]))
    repo = _repo(request)
    await repo.delete_decision(a, b)
    await GameLinker(repo).link_versions([a, b])
    raise _back(str(form.get("back") or "/decisions"), f"v{a} / v{b}: answer taken back")


def _version_line(v: Row) -> str:
    """A version in one line: its name, console and year, and its store page."""

    return (
        f'<a href="/version/{v["version_id"]}">{escape(v["name"] or "")}</a>'
        f" [{escape(console_label(v['store'], v['console']))}, {escape(v['release_date'] or '?')}]"
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
    relation, _, which = relation.partition("#")
    if relation == "skip":
        request.app["skipped"].add(frozenset((version_id, other_id)))
        # "Unsure" is an answer too (the training audit): kept in the log.
        await _repo(request).log_label(
            "pair", "skip", "viewer", version_id=version_id, other_id=other_id
        )
        raise _back(back, f"versions {version_id} / {other_id}: asked again later")
    if flip:
        version_id, other_id = other_id, version_id
    repo = _repo(request)
    named = await _series_named(repo, relation, which, form)
    if named is None:
        raise _back(back, "a series name, please")
    await _label(repo, version_id, other_id, relation)
    await _put_in_series(repo, which, named, (version_id, other_id))
    message = f"version {version_id} {relation} version {other_id}"
    raise _back(back, message + await _contradicted(repo, (version_id, other_id)))


async def _contradicted(repo: Repo, version_ids: tuple[int, ...]) -> str:
    """What a label just written contradicts, in a word for the message
    (#218 step 5): the cards are on /conflicts."""
    from bot.services.label_conflicts import around, conflicts

    n = len(around(conflicts(await repo.all_decisions()), version_ids))
    return f" — ⚠ contradicts {n} answer(s): see Contradictions" if n else ""


async def conflicts_page(request: web.Request) -> web.Response:
    """Answers that contradict each other (#218 step 5): a label keeping
    two versions apart that answers joining them link anyway, or two
    answers between the same two groups saying different things. Each
    card shows both sides; taking one back settles it."""
    from bot.services.label_conflicts import conflicts

    rows = await _repo(request).all_decisions()
    whose = {(r["version_id"], r["other_id"]): r["decided_by"] for r in rows}
    found = conflicts(rows)
    ids = sorted({v for c in found for v in c.versions()})
    with _db(request) as conn:
        names = {
            r["version_id"]: f"{r['name']} ({r['console_name']})"
            for r in conn.execute(
                "SELECT version_id, name, "
                + _console_sql("store", "console")
                + " AS console_name FROM versions WHERE version_id IN ("
                + (",".join("?" * len(ids)) or "NULL")
                + ")",
                ids,
            )
        }

    def line(lab: tuple[int, int, str]) -> str:
        a, b, relation = lab
        by = whose.get((a, b)) or whose.get((b, a)) or "?"
        return (
            f"<li><a href='/version/{a}'>v{a}</a> → <a href='/version/{b}'>v{b}</a>: "
            f"{_relation_sentence(relation, names.get(a, f'v{a}'), names.get(b, f'v{b}'))}"
            f" <small>({escape('you' if by == 'viewer' else by)})</small>"
            f"{_undo_form(a, b, '/conflicts')}</li>"
        )

    heads = {
        "apart_in_group": "kept apart, yet joined by",
        "relations_disagree": "says otherwise than",
    }
    cards = [
        "<div style='border:1px solid #ccc;border-radius:8px;padding:8px;margin:8px 0'>"
        f"<ul>{line(c.label)}</ul><p><small>{heads[c.kind]}</small></p>"
        f"<ul>{''.join(line(lab) for lab in c.against)}</ul></div>"
        for c in found
    ]
    return _page(
        PAGES["/conflicts"],
        _flash(request)
        + f"<p>{len(found)} contradiction(s)</p>"
        + ("".join(cards) or "<p>(none)</p>"),
    )


async def recheck_page(request: web.Request) -> web.Response:
    """The relations the linker set by itself (owner, 2026-10-27): its first
    guess, until an adviser's or the operator's label settles each.
    `scripts.review_questions --recheck` asks them all."""
    from scripts.review_questions import to_recheck

    with _db(request) as conn:
        found = to_recheck(conn)
        ids = sorted({v for a, b, _r in found for v in (a, b)})
        names = {
            r["version_id"]: f"{r['name']} ({r['console_name']})"
            for r in conn.execute(
                "SELECT version_id, name, "
                + _console_sql("store", "console")
                + " AS console_name FROM versions WHERE version_id IN ("
                + (",".join("?" * len(ids)) or "NULL")
                + ")",
                ids,
            )
        }
    counts = Counter(r for _a, _b, r in found)
    rows = [
        f"<li><a href='/version/{a}'>v{a}</a> → <a href='/version/{b}'>v{b}</a>: "
        f"{_relation_sentence(r, names.get(a, f'v{a}'), names.get(b, f'v{b}'))}</li>"
        for a, b, r in found
    ]
    return _page(
        PAGES["/recheck"],
        f"<p>{len(found)} to recheck: "
        + escape(", ".join(f"{r} {n}" for r, n in counts.most_common()))
        + "</p><ul>"
        + "".join(rows)
        + "</ul>",
    )


async def _series_named(repo: Repo, relation: str, which: str, form) -> list[str] | None:
    """The series an answer "another of the series" names: by id, or typed
    (several by commas, owner, 2026-10-24); [] for any other answer, None
    when a series was meant and none is named."""
    if relation != "series" or not which:
        return []
    from scripts.trial_page import series_names

    named = series_names(str(form.get("series_name") or ""))
    if which.isdigit():
        named = [await repo.series_name(int(which)) or ""]
    return named if any(named) else None


async def _put_in_series(repo: Repo, which: str, named: list[str], versions) -> None:
    """After the label, which relinks and proposes the series again: the
    games are found again by their versions, the series by its id or its
    name (owner, 2026-10-24: "one series" says which)."""
    for name in named:
        series_id = (
            int(which)
            if which.isdigit() and await repo.series_exists(int(which))
            else await repo.series_by_name(name) or await repo.create_series(name)
        )
        for version in versions:
            game = await repo.game_of_version(version)
            if game is not None:
                await repo.set_series_member(game, series_id, True)


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
    # "series#<id>" or "series#new" with its name: which series (owner,
    # 2026-10-24) — both games are put in it by hand as well.
    relation, _, which = relation.partition("#")
    repo = _repo(request)
    if relation == "skip":
        # Every pair of versions between the two games comes back later.
        with _db(request) as conn:
            for row in conn.execute(
                "SELECT mp.version_id, mp.other_id FROM match_pairs mp"
                " JOIN versions a ON a.version_id = mp.version_id"
                " JOIN versions b ON b.version_id = mp.other_id"
                " WHERE (a.game_id = ? AND b.game_id = ?) OR (a.game_id = ? AND b.game_id = ?)",
                (game_id, other_game, other_game, game_id),
            ):
                request.app["skipped"].add(frozenset((row[0], row[1])))
                await repo.log_label("pair", "skip", "viewer", version_id=row[0], other_id=row[1])
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
    named = await _series_named(repo, relation, which, form)
    if named is None:
        raise _back(back, "a series name, please")
    await _label(repo, a, b, relation, by=by if by in ADVISERS else "viewer")
    await _put_in_series(repo, which, named, (a, b))
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
    if not form.get("confirmed"):
        with _db(request) as conn:
            sides = [_game_said(conn, game_id), "→ into →", _game_said(conn, int(into))]
        return _confirm(request, form, "Merge the games?", sides)
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
    if not form.get("confirmed"):
        with _db(request) as conn:
            sides = [_game_said(conn, game_id), f"is {kind}", _game_said(conn, int(related))]
        return _confirm(request, form, "Relate the games?", sides)
    repo = _repo(request)
    a, b = await _game_anchors(repo, game_id, int(related))
    await _label(repo, a, b, kind)
    raise _back(f"/game/{await repo.linked_game_of(a) or game_id}", f"{kind} game {related}")


async def game_detach(request: web.Request) -> web.Response:
    """ "Not this game": a label `other` against the version that pulled it
    in — the one the model thinks likeliest the same game (the training
    audit, 2026-10-24: labelling the anchor taught nothing about the pair
    that was wrong)."""
    game_id = int(request.match_info["game_id"])
    form = await request.post()
    version_id = int(str(form["version_id"]))
    repo = _repo(request)
    with _db(request) as conn:
        others = [
            int(r[0])
            for r in conn.execute(
                "SELECT version_id FROM versions WHERE game_id = ? AND version_id <> ?"
                " ORDER BY version_id",
                (game_id, version_id),
            )
        ]
    if not others:
        raise _back(f"/game/{game_id}", "the only version of its game")
    await _label(repo, version_id, await _puller(repo, version_id, others), "other")
    raise _back(f"/version/{version_id}", f"version {version_id} is not game {game_id}")


async def _puller(repo: Repo, version_id: int, others: list[int]) -> int:
    """Of `others`, the version the model would most readily call one game
    with `version_id`: the link a detach says was wrong."""
    from bot.services.game_link import load_candidates
    from bot.services.game_match import features, probabilities

    candidates = await load_candidates(repo, [version_id, *others])
    me = candidates.get(version_id)
    if me is None:
        return others[0]

    def same(other: int) -> float:
        them = candidates.get(other)
        return probabilities(features(me, them))["same"] if them is not None else -1.0

    return max(others, key=lambda o: (same(o), -o))


# ---------------------------------------------------------------- series


def _series_href(row: Row) -> str:
    return f"/series/{row['series_id']}"


def _series_members(conn: Connection, series_id: int) -> list[Row]:
    """A series' games by year, with how each got there; the ones said not
    to be in it last."""
    return conn.execute(
        "SELECT gs.game_id, g.name, g.year, g.developer, gs.member, gs.source,"
        " ROUND(gs.p::numeric, 2)::float8 AS p, gs.reason, gs.decided_by FROM game_series gs"
        " JOIN games g ON g.game_id = gs.game_id WHERE gs.series_id = ?"
        " ORDER BY gs.member DESC, COALESCE(g.year, 9999), g.game_id",
        (series_id,),
    ).fetchall()


def _member_toggle(
    series_id: int, game_id: int, name: str, member: bool, back: str, *, short: bool = False
) -> str:
    """The operator's "not in this series" / "in it after all"; `short` on a
    row that already names the game."""
    if short:
        label = "exclude" if member else "restore"
    else:
        label = f"not in «{name}»" if member else f"in «{name}» after all"
    return _button(
        f"/series/{series_id}/member",
        label,
        {"game_id": game_id, "member": 0 if member else 1, "back": back},
    )


def _game_series_section(conn: Connection, game_id: int) -> str:
    """The series a game is in (a crossover in several), how it got into
    each, and the operator's add / remove."""
    rows = conn.execute(
        "SELECT gs.series_id, s.name, gs.member, gs.source,"
        " ROUND(gs.p::numeric, 2)::float8 AS p, gs.reason,"
        " (SELECT COUNT(*) FROM game_series o WHERE o.series_id = gs.series_id"
        "  AND o.member = 1) AS games FROM game_series gs"
        " JOIN series s ON s.series_id = gs.series_id"
        " WHERE gs.game_id = ? AND s.merged_into IS NULL ORDER BY gs.member DESC, s.name",
        (game_id,),
    ).fetchall()
    here = f"/game/{game_id}"
    toggles = "".join(
        "<p>" + _member_toggle(r["series_id"], game_id, r["name"], bool(r["member"]), here) + "</p>"
        for r in rows
    )
    add = (
        f'<form method=post action="{here}/series">add to series id: '
        "<input name=series_id size=8> or a new series named: <input name=name size=30> "
        "<button>add</button></form>"
    )
    return (
        "<h2>Series</h2>"
        + _table(
            [{**dict(r), "member": "yes" if r["member"] else "no (said so)"} for r in rows],  # type: ignore[arg-type]
            {"series_id": _series_href, "name": _series_href},
        )
        + toggles
        + add
    )


async def series_list(request: web.Request) -> web.Response:
    q = request.query.get("q", "")
    with _db(request) as conn:
        rows = conn.execute(
            "SELECT s.series_id, s.name, s.name_source, s.rule_key AS named_by_rule,"
            " (SELECT COUNT(*) FROM game_series gs WHERE gs.series_id = s.series_id"
            "  AND gs.member = 1) AS games,"
            " (SELECT COUNT(*) FROM game_series gs WHERE gs.series_id = s.series_id"
            "  AND gs.member = 1 AND gs.source = 'auto' AND COALESCE(gs.p, 0) < ?) AS unsure,"
            " (SELECT COUNT(*) FROM game_series gs WHERE gs.series_id = s.series_id"
            "  AND gs.source <> 'auto') AS answered,"
            " (SELECT MIN(g.year) FROM game_series gs JOIN games g ON g.game_id = gs.game_id"
            "  WHERE gs.series_id = s.series_id AND gs.member = 1) AS since"
            " FROM series s WHERE s.merged_into IS NULL AND (? = '' OR s.name ILIKE ?"
            "  OR EXISTS (SELECT 1 FROM game_series gs JOIN games g ON g.game_id = gs.game_id"
            "   WHERE gs.series_id = s.series_id AND g.name ILIKE ?))"
            " ORDER BY games DESC, s.name LIMIT ?",
            (SURE_P, q, f"%{q}%", f"%{q}%", PAGE_SIZE * 3),
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*), (SELECT COUNT(*) FROM game_series WHERE member = 1)"
            " FROM series WHERE merged_into IS NULL"
        ).fetchone()
    body = (
        _flash(request)
        + f"<p>{total[0]} series, {total[1]} memberships. A game may be in several (a"
        " crossover, LEGO, a local series inside a franchise: <i>named_by_rule</i> says"
        " which rule). <i>auto</i> rows are the linker's proposals, made again after every"
        " linking; the operator's (<i>manual</i>) and the advisers' rows stand."
        f" <i>unsure</i>: proposals under {SURE_P:.0%}.</p>"
        + _button("/series/rebuild", "propose the series again")
        + _search_form("/series", q)
        + _table(rows, {"series_id": _series_href, "name": _series_href})
    )
    return _page(PAGES["/series"], body)


async def series_page(request: web.Request) -> web.Response:
    series_id = int(request.match_info["series_id"])
    with _db(request) as conn:
        row = conn.execute("SELECT * FROM series WHERE series_id = ?", (series_id,)).fetchone()
        if row is not None and row["merged_into"]:
            raise web.HTTPFound(f"/series/{row['merged_into']}")
        members = _series_members(conn, series_id)
    if row is None:
        return _page(f"Series {series_id}", "<p>(not found)</p>")
    here = f"/series/{series_id}"
    controls = (
        f'<form method=post action="{here}/rename">name: '
        f'<input name=name value="{escape(row["name"])}" size=40> '
        f'ru: <input name=name_ru value="{escape(row["name_ru"] or "")}" size=30> '
        f"<button>rename</button> <small>({escape(row['name_source'])})</small></form>"
        f'<form method=post action="{here}/merge">merge this series into series id: '
        "<input name=into size=8> <button>merge</button></form>"
        f'<form method=post action="{here}/member"><input type=hidden name=member value=1>'
        f'<input type=hidden name=back value="{here}"><input type=hidden name=ask value=1>'
        "add game id: "
        "<input name=game_id size=8> <button>add</button></form>"
    )
    body = (
        _flash(request)
        + controls
        + "<h2>Games, by year</h2>"
        + _table(
            [{**dict(m), "member": "yes" if m["member"] else "no (said so)"} for m in members],  # type: ignore[arg-type]
            {"game_id": _game_href, "name": _game_href},
            # The way out of the series on the game's own row (owner,
            # 2026-10-24), and back in for one said not to be in it.
            {
                "": lambda m: _member_toggle(
                    series_id, m["game_id"], m["name"], m["member"] == "yes", here, short=True
                )
            },
        )
    )
    return _page(f"Series: {row['name']}", body)


# ---------------------------------------------------------------- octopus


async def octopus_page(request: web.Request) -> web.Response:
    """The octopus (#215): feed it anything — links, keys, names, one a line —
    see its queue, run it, and the step-12 checks: what assembled games
    still lack."""
    state = request.app["octopus"]
    busy = state["task"] is not None and not state["task"].done()
    last = state["last"]
    with _db(request) as conn:
        waiting = conn.execute(
            "SELECT key, reason, due_at, attempts, last_error FROM octopus_queue"
            " ORDER BY due_at, created_at, key LIMIT 100"
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM octopus_queue").fetchone()[0]
        checks = [
            {
                "check": what,
                "count": conn.execute(sql).fetchone()[0],
            }
            for what, sql in (
                ("versions in no game", "SELECT COUNT(*) FROM versions WHERE game_id IS NULL"),
                (
                    "stand-ins (a list no store page was found for)",
                    "SELECT COUNT(*) FROM versions WHERE stand_in = 1",
                ),
                (
                    "games with no HLTB entry",
                    "SELECT COUNT(*) FROM games g WHERE g.merged_into IS NULL AND NOT EXISTS"
                    " (SELECT 1 FROM versions v JOIN version_hltb vh"
                    "  ON vh.version_id = v.version_id AND vh.source <> 'rejected'"
                    "  WHERE v.game_id = g.game_id)",
                ),
                (
                    "versions assembled by the octopus",
                    "SELECT COUNT(*) FROM fetch_state WHERE source = 'octopus'",
                ),
            )
        ]
        recent = conn.execute(
            "SELECT subject, status, checked_at, next_check_at FROM fetch_state"
            " WHERE source = 'octopus' ORDER BY checked_at DESC LIMIT 30"
        ).fetchall()
    feed = (
        '<form method=post action="/octopus/add"><p>Links (Steam, Xbox, PlayStation Store,'
        " HowLongToBeat), keys (<code>game:12</code>, <code>list:psn:NPWR…</code>,"
        " <code>edition:5</code>, <code>series:7</code>, <code>account:psn:…</code>)"
        " or names — one per line:</p>"
        "<textarea name=keys rows=5 cols=80></textarea><br><button>queue</button></form>"
    )
    run = (
        "<p><b>running…</b> (reload the page)</p>"
        if busy
        else '<form method=post action="/octopus/run">run <input name=limit value=10 size=4>'
        " entries <button>start</button></form>"
    )
    body = (
        _flash(request)
        + feed
        + run
        + (f"<pre>{escape(last)}</pre>" if last else "")
        + "<h2>Checks</h2>"
        + _table(checks)  # type: ignore[arg-type]
        + f"<h2>Queue: {total}</h2>"
        + _table(waiting)
        + "<h2>Latest assemblies</h2>"
        + _table(recent)
    )
    return _page(PAGES["/octopus"], body)


async def octopus_add(request: web.Request) -> web.Response:
    from bot.services.octopus import OctopusCollector, entry_key

    form = await request.post()
    octopus = OctopusCollector(_repo(request), request.app["collector"])
    added, unread = 0, []
    for line in str(form.get("keys") or "").splitlines():
        if not line.strip():
            continue
        key = entry_key(line)
        if key is None:
            unread.append(line.strip())
            continue
        added += await octopus.enqueue(key, reason="viewer")
    message = f"queued {added}" + (f"; not understood: {', '.join(unread)}" if unread else "")
    raise _back("/octopus", message)


async def octopus_run(request: web.Request) -> web.Response:
    """A run in the background, one at a time; the page shows it done."""
    import asyncio

    from bot.services.octopus import OctopusCollector

    state = request.app["octopus"]
    if state["task"] is not None and not state["task"].done():
        raise _back("/octopus", "a run is going already")
    form = await request.post()
    limit = str(form.get("limit") or "10").strip()
    octopus = OctopusCollector(_repo(request), request.app["collector"])

    async def go() -> None:
        try:
            report = await octopus.run(limit=int(limit) if limit.isdigit() else 10)
        except Exception as exc:  # shown on the page, the viewer goes on
            state["last"] = f"failed: {exc!r}"
            return
        lines = [
            f"{g.entry} → game {g.game_id} {g.name!r}: versions {g.versions_before} →"
            f" {g.versions_after} in {g.rounds} rounds, found {len(set(g.found))},"
            f" to review {g.review}; stand-ins {g.stand_ins}, HLTB on {g.hltb}"
            for g in report.games
        ]
        lines.append(
            f"handled {report.handled}: games {len(report.games)}, searched {report.searched},"
            f" spread {report.spread}, not due {report.skipped}, led nowhere {report.gone},"
            f" queued on the way {report.queued}"
        )
        lines += [f"error: {line}" for line in report.failed[:20]]
        state["last"] = "\n".join(lines)

    state["task"] = asyncio.get_running_loop().create_task(go())
    raise _back("/octopus", "started")


async def series_rebuild(request: web.Request) -> web.Response:
    from bot.services.game_series import SeriesBuilder

    count = await SeriesBuilder(_repo(request)).rebuild()
    raise _back("/series", f"{count} series proposed")


async def series_rename(request: web.Request) -> web.Response:
    series_id = int(request.match_info["series_id"])
    form = await request.post()
    name = str(form.get("name") or "").strip()
    if name:
        await _repo(request).rename_series(
            series_id, name, str(form.get("name_ru") or "").strip() or None
        )
    raise _back(f"/series/{series_id}", "renamed")


async def series_merge(request: web.Request) -> web.Response:
    series_id = int(request.match_info["series_id"])
    form = await request.post()
    into = str(form.get("into") or "").strip()
    if not into.isdigit():
        raise _back(f"/series/{series_id}", "a series id, please")
    if not form.get("confirmed"):
        with _db(request) as conn:
            sides = [_series_said(conn, series_id), "→ into →", _series_said(conn, int(into))]
        return _confirm(request, form, "Merge the series?", sides)
    await _repo(request).merge_series(series_id, int(into))
    raise _back(f"/series/{into}", f"series {series_id} merged into this one")


async def series_member(request: web.Request) -> web.Response:
    """The operator says a game is in a series, or is not: a `manual` row,
    which no rebuild overwrites."""
    series_id = int(request.match_info["series_id"])
    form = await request.post()
    game = str(form.get("game_id") or "").strip()
    back = str(form.get("back") or f"/series/{series_id}")
    if not game.isdigit():
        raise _back(back, "a game id, please")
    member = str(form.get("member") or "1") == "1"
    if form.get("ask") and not form.get("confirmed"):
        # Typed by id on the series page (the toggles name their game).
        with _db(request) as conn:
            sides = [_game_said(conn, int(game)), "→ into series →", _series_said(conn, series_id)]
        return _confirm(request, form, "Add the game to the series?", sides)
    await _repo(request).set_series_member(int(game), series_id, member)
    raise _back(back, "in the series" if member else "not in the series")


async def game_series_add(request: web.Request) -> web.Response:
    """A game put in a series by hand: one by its id, or a new one by name."""
    game_id = int(request.match_info["game_id"])
    form = await request.post()
    repo = _repo(request)
    series = str(form.get("series_id") or "").strip()
    name = str(form.get("name") or "").strip()
    if series.isdigit():
        series_id = int(series)
        if not form.get("confirmed"):
            with _db(request) as conn:
                sides = [
                    _game_said(conn, game_id),
                    "→ into series →",
                    _series_said(conn, series_id),
                ]
            return _confirm(request, form, "Add the game to the series?", sides)
    elif name:
        series_id = await repo.create_series(name)
    else:
        raise _back(f"/game/{game_id}", "a series id or a name, please")
    await repo.set_series_member(game_id, series_id, True)
    raise _back(f"/game/{game_id}", f"added to series {series_id}")


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

    database = await tools.open_database(app["dsn"], schema=app["schema"])
    repo = Repo(database)
    app["database"], app["repo"] = database, repo
    from bot.services.game_link import load_weights

    await load_weights(repo)  # the rules page shows the weights in use
    settings = get_settings()
    cipher = TokenCipher(settings.fernet_key.get_secret_value())
    steam = SteamAuth(repo, cipher, env_key=_secret(settings.steam_api_key))
    app["collector"] = StoreCollector(repo, PsnAuth(repo, cipher), steam)
    # The octopus's run in the background and its last report (a dict made
    # here: the app's own state is fixed once it serves).
    app["octopus"] = {"task": None, "last": ""}


def _secret(value: object) -> str | None:
    """A pydantic secret's text, or None."""
    getter = getattr(value, "get_secret_value", None)
    return getter() if getter else (str(value) if value else None)


async def _close(app: web.Application) -> None:
    await app["database"].close()


def _pictures(row: Row | None) -> str:
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
    dsn: str,
    schema: str,
    proposals_path: Path | None = None,
    gemini_dir: Path | None = None,
    advised_path: Path | None = None,
    trial_dir: Path | None = None,
    data_dir: Path = Path("data"),
) -> web.Application:
    """`data_dir`: where the server keeps its files (the folder of `DB_PATH`):
    the advisers' answers, the covers."""
    app = web.Application()
    app["dsn"], app["schema"], app["data_dir"] = dsn, schema, data_dir.resolve()
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
    # The advisers' work for a second look (`--advised`, written by
    # `advise_pairs conflicts --review`).
    app["advised"] = (
        json.loads(advised_path.read_text(encoding="utf-8"))
        if advised_path and advised_path.exists()
        else []
    )
    covers = data_dir.resolve() / "covers"
    if covers.is_dir():
        # The covers the bot downloaded (#55).
        app.router.add_static("/covers/", covers)
    app.on_startup.append(_open)
    app.on_cleanup.append(_close)
    app.router.add_post("/title/{platform}/{title_id}/collect", collect)
    app.router.add_post("/fetch/due", fetch_due)
    app.router.add_get("/games", games)
    app.router.add_get("/series", series_list)
    app.router.add_get("/series/{series_id:\\d+}", series_page)
    app.router.add_post("/series/rebuild", series_rebuild)
    app.router.add_post("/series/{series_id:\\d+}/rename", series_rename)
    app.router.add_post("/series/{series_id:\\d+}/merge", series_merge)
    app.router.add_get("/octopus", octopus_page)
    app.router.add_post("/octopus/add", octopus_add)
    app.router.add_post("/octopus/run", octopus_run)
    app.router.add_post("/series/{series_id:\\d+}/member", series_member)
    app.router.add_post("/game/{game_id:\\d+}/series", game_series_add)
    app.router.add_get("/rules", rules)
    app.router.add_get("/list/{platform}/{title_id}", achievement_list)
    app.router.add_get("/steam-schema/{appid}", steam_schema)
    app.router.add_get("/game/{game_id:\\d+}", game)
    app.router.add_get("/review", review)
    app.router.add_get("/decisions", decisions)
    app.router.add_get("/conflicts", conflicts_page)
    app.router.add_get("/recheck", recheck_page)
    app.router.add_get("/proposals", proposals)
    app.router.add_get("/advised", advised)
    from scripts import trial_page

    trial_page.register(app, trial_dir, _page)
    app.router.add_post("/decision/undo", decision_undo)
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
    app.router.add_get("/dlc/{dlc_id:\\d+}", dlc)
    app.router.add_post("/dlc/{dlc_id:\\d+}/read", dlc_read)
    app.router.add_get("/hltb", hltb_list)
    app.router.add_get("/hltb/{hltb_id:\\d+}", hltb_entry)
    app.router.add_get("/fetch", fetch)
    app.router.add_get("/payloads", payloads)
    app.router.add_get("/payload", payload)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    tools.add_arguments(parser)
    parser.add_argument("--trial", help="a trial's folder (trial.txt, answers/), for /trial")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument(
        "--proposals", help="an adviser's proposals for the game pairs (JSON), shown at /proposals"
    )
    parser.add_argument(
        "--gemini",
        help="a folder of Gemini's answers about the proposals (*.txt, pair|relation|"
        "direction|confidence|why), shown on the /proposals cards",
    )
    parser.add_argument(
        "--advised",
        help="the advisers' pairs for a second look (advise_pairs conflicts --review), at /advised",
    )
    args = parser.parse_args()
    from bot.config import get_settings

    settings = get_settings()
    schema = args.schema or settings.database_schema
    print(f"schema {schema} — http://127.0.0.1:{args.port}/ (no authentication)")
    proposals = Path(args.proposals) if args.proposals else None
    gemini = Path(args.gemini) if args.gemini else None
    advised_path = Path(args.advised) if args.advised else None
    web.run_app(
        build(
            settings.database_url,
            schema,
            proposals,
            gemini,
            advised_path,
            Path(args.trial) if args.trial else None,
            settings.db_path.parent,
        ),
        host="127.0.0.1",
        port=args.port,
        print=None,
        loop=tools.event_loop(),
    )


if __name__ == "__main__":
    main()
