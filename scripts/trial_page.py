"""The viewer's /trial page (#147; owner, 2026-10-16): every question of the
trial file with each adviser's answer, decision by decision, and the
operator's own answer for each — the labels `compare_answers --labels` scores
the advisers by. Answers are read on every request from `<trial>/answers/*.jsonl`
(an adviser added later just appears); labels go to `<trial>/compare/labels.json`.

Laid out to be read (owner, 2026-10-16): each question shows what it is about
— the game, its releases, the HowLongToBeat entries, the editions — with their
pictures, and next to each item the choice to make, the advisers' answers on
pills (orange where they differ). The question's raw text is one click away.

**One tap is an answer** (owner, 2026-10-23): each adviser's answer is a
button that records it, the other answers sit under «Own answer…», and there
is no separate «save». The cards are drawn inside the viewer's one review
tab (`/review`); `/trial` only sends there. «Missing versions» (M) are not
the operator's to dig for: they wait for the octopus (#204) and are shown only
when asked for (`kind=M`).
"""

from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path
from urllib.parse import quote

from aiohttp import web

from bot.db.postgres import Row
from bot.db.repo._sql import OWN_EDITION
from bot.db.tools import Connection
from scripts.compare_answers import KINDS, decisions, read_answers

KIND_RU = {
    "G": "Game card",
    "M": "Missing versions",
    "R": "Games related",
    "D": "Similar games",
    "S": "Series",
    "P": "PSN trophy group",
    "E": "Editions",
    "H": "DLC ↔ HLTB",
    "X": "Rejected HLTB",
}
VALUE_RU = {
    "yes": "yes",
    "no": "no",
    "unsure": "unsure",
    "same": "the same",
    "wrong": "wrong",
    "True": "yes",
    "False": "no",
    "None": "—",
    "()": "nothing",
    "—": "no answer",
}

CSS = """
<style>
body{background:#fff;color:#111}
a{color:#0b57d0}
.tq{border:1px solid #ddd;border-radius:10px;padding:12px;margin:14px 0;background:#fafafa}
.tq h3{margin:0 0 6px;font-size:16px}
.badge{display:inline-block;background:#333;color:#fff;border-radius:6px;padding:1px 7px;
 font-size:12px;margin-right:6px}
.subj{display:flex;gap:10px;align-items:center;margin:6px 0}
.subj img{border-radius:6px;object-fit:cover}
.item{display:grid;grid-template-columns:minmax(0,420px) minmax(0,1fr);gap:10px;
 align-items:center;padding:6px;border-radius:8px;margin:4px 0;background:#fff;
 border:1px solid #eee}
@media (max-width:800px){.item{grid-template-columns:1fr}}
.item.diff{background:#fff3e0;border-color:#ffb74d}
.item .what{display:flex;gap:8px;align-items:center;min-width:0}
.item .what small{color:#666}
.ask{font-size:12px;color:#555}
.asks{display:flex;flex-direction:column;gap:4px;min-width:0}
.asks .one{display:grid;grid-template-columns:200px minmax(0,1fr) 140px;gap:8px;
 align-items:center;padding:3px;border-radius:6px}
@media (max-width:800px){.asks .one{grid-template-columns:1fr}}
.asks .one.diff{background:#fff3e0}
.pills label{display:inline-block;border:1px solid #bbb;border-radius:14px;padding:3px 9px;
 margin:2px;cursor:pointer;background:#fff;font-size:13px}
.pills input{display:none}
.pills label:has(input:checked){background:#2e7d32;color:#fff;border-color:#2e7d32}
.pills small{opacity:.7}
.pills label.free{border-style:dashed;color:#666;font-size:12px}
.other{width:100%;box-sizing:border-box;font-size:12px}
.other.on{background:#2e7d32;color:#fff;border:1px solid #2e7d32}
.con{display:inline-block;background:#e3f2fd;border-radius:5px;padding:0 5px;font-size:12px}
.done{color:#2e7d32;font-weight:bold}
.why div{font-size:12px;margin:2px 0}
.have{margin:6px 0 6px 12px;padding:6px;border-left:3px solid #90caf9;background:#fff}
.later{padding:6px 12px;font-size:13px;margin-top:6px}
.picks{display:flex;flex-direction:column;gap:4px}
.picks button{text-align:left;border:1px solid #9ec5fe;background:#e7f1ff;border-radius:10px;
 padding:6px 10px;font-size:14px;cursor:pointer}
.picks button small{color:#555;margin-left:6px}
.own summary{cursor:pointer;color:#0b57d0;font-size:13px;margin-top:4px}
.own .more{display:flex;flex-wrap:wrap;gap:4px;margin-top:4px}
.own .more button{border:1px solid #bbb;background:#fff;border-radius:10px;padding:4px 9px;
 font-size:13px;cursor:pointer}
.own .free{display:flex;gap:4px;margin-top:4px}
</style>
"""


def own_editions(conn: Connection, game_id: int) -> set[int]:
    """The game's own editions as the database says now (`_sql.OWN_EDITION`)."""
    return {
        int(r[0])
        for r in conn.execute(
            "SELECT DISTINCT e.edition_id FROM editions e"
            " JOIN edition_items i ON i.edition_id = e.edition_id"
            " JOIN versions v ON v.version_id = i.version_id"
            f" WHERE v.game_id = ? AND {OWN_EDITION}",
            (game_id,),
        )
    }


def current_keys(conn: Connection, qid: str, keys: list[str]) -> list[str]:
    """The trial is a snapshot (2026-10-16): of an editions question, only
    the editions still the game's own are asked — FIFA 16's bundles were
    filed under Plants vs. Zombies, which they only throw in."""
    kind, _, rest = qid.partition(":")
    if kind != "E" or not rest.isdigit():
        return keys
    own = own_editions(conn, int(rest))
    return [k for k in keys if not (m := re.fullmatch(r"e(\d+)\.\w+", k)) or int(m[1]) in own]


def _questions(trial: Path) -> list[tuple[str, str]]:
    text = (trial / "trial.txt").read_text("utf-8")
    body = text.split("\nQUESTIONS (", 1)[1]
    out = []
    for chunk in body.split("\nid: ")[1:]:
        qid, _, rest = chunk.partition("\n")
        out.append((qid.strip(), rest.strip()))
    return out


def _advisers(trial: Path) -> dict[str, dict[str, dict]]:
    return {
        p.stem.removeprefix("trial_"): read_answers(p)
        for p in sorted((trial / "answers").glob("*.jsonl"))
    }


def _labels_path(trial: Path) -> Path:
    return trial / "compare" / "labels.json"


def _later_path(trial: Path) -> Path:
    path = trial / "compare" / "later.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _later(trial: Path) -> dict[str, bool]:
    path = _later_path(trial)
    return json.loads(path.read_text("utf-8")) if path.exists() else {}


def _labels(trial: Path) -> dict[str, str]:
    path = _labels_path(trial)
    return json.loads(path.read_text("utf-8")) if path.exists() else {}


class _Look:
    """What the database knows of an item, as a picture and a line."""

    def __init__(self, conn: Connection, img, store_href) -> None:
        self.conn, self.img, self.store_href = conn, img, store_href

    def _one(self, sql: str, args: tuple) -> Row | None:
        return self.conn.execute(sql, args).fetchone()

    def version_cover(self, v: Row) -> str | None:
        media = json.loads(v["media"] or "{}") if v["media"] else {}
        for role in ("cover", "poster", "background"):
            if media.get(role):
                return str(media[role])
        if v["title_id"]:
            t = self._one(
                "SELECT cover_path FROM achievement_list_connectors"
                " WHERE platform = ? AND title_id = ?",
                (v["platform"], v["title_id"]),
            )
            if t is not None and t["cover_path"]:
                return "/covers/" + t["cover_path"]
        return None

    def version(self, vid: int) -> str:
        from bot.services.stores import console_label

        v = self._one("SELECT * FROM versions WHERE version_id = ?", (vid,))
        if v is None:
            return f"release v{vid} <small>(gone)</small>"
        href = self.store_href(v)
        name = escape(v["name"] or "?")
        link = f'<a href="{escape(href)}" target=_blank>{name} ↗</a>' if href else name
        stand_in = " · stand-in" if v["stand_in"] else ""
        return (
            self.img(self.version_cover(v), 54)
            + f"<span><span class=con>{escape(console_label(v['store'], v['console']))}</span>"
            f" {link}<br><small>{escape(v['store'])} · {escape(v['release_date'] or '?')}"
            f" · v{vid}{stand_in}</small></span>"
        )

    def hltb(self, hid: int) -> str:
        e = self._one("SELECT * FROM hltb_entries WHERE hltb_id = ?", (hid,))
        if e is None:
            return f"HLTB {hid}"
        pic = ("/covers/" + e["image_path"]) if e["image_path"] else e["image_url"]
        year = (e["release_world"] or "")[:4] or e["name_year"] or "?"
        return (
            self.img(pic, 54)
            + f'<span><a href="https://howlongtobeat.com/game/{hid}" target=_blank>'
            f"{escape(e['name'])} ↗</a><br><small>HLTB · {escape(e['game_type'] or '?')}"
            f" · {escape(str(year))}</small></span>"
        )

    def dlc(self, did: int) -> str:
        d = self._one("SELECT * FROM dlcs WHERE dlc_id = ?", (did,))
        if d is None:
            return f"DLC {did}"
        return (
            self.img(d["image_url"], 40) + f"<span>{escape(d['name'] or '?')}<br>"
            f"<small>DLC · {escape(d['release_date'] or '?')}</small></span>"
        )

    def game(self, gid: int, size: int = 72) -> str:
        g = self._one("SELECT * FROM games WHERE game_id = ?", (gid,))
        if g is None:
            return f"game {gid}"
        cover = None
        for v in self.conn.execute(
            "SELECT * FROM versions WHERE game_id = ? ORDER BY stand_in, version_id", (gid,)
        ):
            cover = self.version_cover(v)
            if cover:
                break
        return (
            self.img(cover, size)
            + f'<span><a href="/game/{gid}" target=_blank><b>{escape(g["name"] or "?")}</b></a>'
            f"<br><small>{escape(str(g['year'] or '?'))} · {escape(g['developer'] or '?')}"
            f" / {escape(g['publisher'] or '?')}</small></span>"
        )

    def shared_series(self, first: int, second: int) -> list[tuple[int, str]]:
        """The series both games are in, as `(series_id, name)`."""
        return [
            (int(r[0]), str(r[1]))
            for r in self.conn.execute(
                "SELECT s.series_id, s.name FROM series s"
                " JOIN game_series a ON a.series_id = s.series_id AND a.game_id = ?"
                " JOIN game_series b ON b.series_id = s.series_id AND b.game_id = ?"
                " WHERE s.merged_into IS NULL ORDER BY s.name",
                (first, second),
            )
        ]

    def series_names(self) -> list[str]:
        return [
            str(r[0])
            for r in self.conn.execute(
                "SELECT name FROM series WHERE merged_into IS NULL ORDER BY name"
            )
        ]

    def releases(self, gid: int) -> str:
        """Every release of a game, a line each, with its picture."""
        rows = self.conn.execute(
            "SELECT version_id FROM versions WHERE game_id = ? ORDER BY console, version_id",
            (gid,),
        ).fetchall()
        return "".join(f"<div class=subj>{self.version(int(r[0]))}</div>" for r in rows)

    def edition_word(self, eid: int) -> str | None:
        """What an edition's own name calls it: the name past its game's
        ("The Evil Within Digital Bundle" → "digital bundle"; owner,
        2026-10-24: offered first, not typed). None when it is the game's
        name alone, or does not start with it."""
        e = self._one("SELECT name FROM editions WHERE edition_id = ?", (eid,))
        if e is None or not e["name"]:
            return None
        games = [
            str(r[0])
            for r in self.conn.execute(
                "SELECT i.name FROM edition_items i WHERE i.edition_id = ? AND i.name IS NOT NULL"
                " AND i.item_kind = 'game' ORDER BY i.is_primary DESC",
                (eid,),
            )
        ]
        return edition_word(str(e["name"]), games)

    def edition(self, eid: int) -> str:
        e = self._one("SELECT * FROM editions WHERE edition_id = ?", (eid,))
        if e is None:
            return f"edition {eid}"
        pic = ("/covers/" + e["image_path"]) if e["image_path"] else None
        items = self.conn.execute(
            "SELECT name, item_kind FROM edition_items WHERE edition_id = ?"
            " ORDER BY is_primary DESC",
            (eid,),
        ).fetchall()
        holds = "; ".join(f"{i['name'] or '?'} ({i['item_kind']})" for i in items[:6])
        return (
            self.img(pic, 54)
            + f"<span>{escape(e['name'] or '?')}<br><small>{escape(e['store'])} · our type"
            f" {escape(e['kind'] or '?')} · {escape(holds)}</small></span>"
        )


_MARKS = re.compile(r"[™®©]")


def _plain(text: str) -> str:
    return " ".join(_MARKS.sub("", text).split())


def edition_word(name: str, games: list[str]) -> str | None:
    """An edition's name past the name of a game it holds, lower-cased and
    without the marks and the separators between them; None when nothing is
    left or no game's name opens it."""
    plain = _plain(name)
    for game in sorted((_plain(g) for g in games), key=len, reverse=True):
        if game and plain.casefold().startswith(game.casefold()):
            rest = plain[len(game) :].strip(" -–—:|,").strip()
            return rest.casefold() or None
    return None


# A question asked the other way round than the adviser's field (owner,
# 2026-10-16: no double negatives) shows its values turned round too; what is
# stored stays the field's own value.
VALUE_BY_KEY = {
    "relation": {
        "('same', None)": "one game",
        "('series', None)": "one series",
        "('not_related', None)": "not related",
        "('unsure', None)": "unsure",
        "('remaster_of', 'first')": "1 is a remaster of 2",
        "('remaster_of', 'second')": "2 is a remaster of 1",
        "('remake_of', 'first')": "1 is a remake of 2",
        "('remake_of', 'second')": "2 is a remake of 1",
        "('contains', 'first')": "1 contains 2",
        "('contains', 'second')": "2 contains 1",
        "('vr_of', 'first')": "1 is the VR version of 2",
        "('vr_of', 'second')": "2 is the VR version of 1",
    },
    "facts_wrong": {"False": "yes, right", "True": "no, a mistake"},
    "missing_hltb": {"False": "no", "True": "yes, there is"},
    "name_ok": {"True": "yes", "False": "no"},
}


def _value(v: str, key: str = "") -> str:
    if v in VALUE_BY_KEY.get(key, {}):
        return VALUE_BY_KEY[key][v]
    if v.startswith("(") and v.endswith(")") and v != "()":
        inner = [x.strip(" '\"") for x in v[1:-1].split(",") if x.strip(" '\"")]
        if inner and inner[-1] == "None":
            inner = inner[:-1]
        return ", ".join(VALUE_RU.get(x, x) for x in inner) or "—"
    return VALUE_RU.get(v, v)


ASK = {
    "missing_hltb": "Does the game itself (not a DLC) have an HLTB entry we lack?",
    "series": "Which series is the game in",
    "facts_wrong": "Are the year, studio and publisher right?",
    "missing": "Which store versions are missing",
    "relation": "How are they related",
    "name_ok": "Is the series name right?",
    "addon": "Which add-on brought the group",
    "links": "Which DLC is which HLTB entry",
    "verdict": "Is this HLTB entry the same game?",
}


def _subject(key: str, look: _Look) -> tuple[str, str]:
    """`(what the decision is about, the question asked)`."""
    if m := re.fullmatch(r"v(\d+)\.belongs", key):
        return look.version(int(m[1])), "Is it part of the game?"
    if m := re.fullmatch(r"v(\d+)\.kind", key):
        return look.version(
            int(m[1])
        ), "What kind of game is it? (the same for all versions of one game)"
    if m := re.fullmatch(r"v(\d+)\.hltb(\d+)", key):
        return look.version(int(m[1])) + " → " + look.hltb(int(m[2])), "Is the HLTB right?"
    if m := re.fullmatch(r"dlc(\d+)\.hltb(\d+)", key):
        return look.dlc(int(m[1])) + " → " + look.hltb(int(m[2])), "Is the HLTB right?"
    if m := re.fullmatch(r"e(\d+)\.kind", key):
        return look.edition(int(m[1])), "Edition type"
    if m := re.fullmatch(r"e(\d+)\.holds", key):
        return look.edition(int(m[1])), "Is this an edition of this game?"
    if m := re.fullmatch(r"g(\d+)", key):
        return look.game(int(m[1]), 48), "In the series?"
    return "", ASK.get(key, key)


def _head(qid: str, text: str, look: _Look) -> str:
    kind, _, rest = qid.partition(":")
    parts = rest.split(":")
    if kind == "M":
        # What we have already (owner, 2026-10-17: the question is unanswerable
        # without it): every release of the game, then the choice.
        return (
            f"<div class=subj>{look.game(int(parts[0]))}</div>"
            f"<div class=have><b>We already have:</b>{look.releases(int(parts[0]))}</div>"
        )
    if kind in ("G", "E", "H"):
        return f"<div class=subj>{look.game(int(parts[0]))}</div>"
    if kind in ("R", "D"):
        return (
            f"<div class=subj><b>1.</b> {look.game(int(parts[0]))}</div>"
            f"<div class=subj><b>2.</b> {look.game(int(parts[1]))}</div>"
        )
    if kind == "X":
        return f"<div class=subj>{look.version(int(parts[0]))} → {look.hltb(int(parts[1]))}</div>"
    first = escape(text.splitlines()[0]) if text else ""
    return f"<div class=subj><b>{first}</b></div>"


YES_NO = ["yes", "no", "unsure"]
VERDICT = ["same", "wrong", "unsure"]
GAME_KINDS = [
    "game", "edition", "compilation", "remaster", "remake", "dlc", "episode",
    "demo", "tool", "mode", "soundtrack", "app", "other",
]  # fmt: skip
EDITION_KINDS = [
    "standard", "deluxe", "premium", "ultimate", "gold", "goty", "complete",
    "definitive", "anniversary", "collection", "bundle", "preorder", "other",
]  # fmt: skip
RELATIONS = [
    "('same', None)", "('series', None)", "('not_related', None)",
    "('remaster_of', 'first')", "('remaster_of', 'second')",
    "('remake_of', 'first')", "('remake_of', 'second')",
    "('contains', 'first')", "('contains', 'second')",
    "('vr_of', 'first')", "('vr_of', 'second')", "('unsure', None)",
]  # fmt: skip


def _choices(key: str) -> list[str]:
    """Every answer a decision can take (owner, 2026-10-16: a row where all the
    advisers agree still needs a way to say they are wrong)."""
    if key.endswith((".belongs", ".holds")) or re.fullmatch(r"g\d+", key):
        return YES_NO
    if ".hltb" in key or key == "verdict":
        return VERDICT
    if re.fullmatch(r"v\d+\.kind", key):
        return GAME_KINDS
    if re.fullmatch(r"e\d+\.kind", key):
        return EDITION_KINDS
    if key in ("facts_wrong", "missing_hltb"):
        return ["False", "True"]
    if key == "name_ok":
        return ["True", "False"]
    if key == "relation":
        return RELATIONS
    return []


# "One series" says which (owner, 2026-10-24: LEGO Harry Potter and LEGO
# Batman meet only in LEGO): the answer is the relation, and beside it, under
# `<key>.series`, the series — an id from ours, or a name typed for a new one.
SERIES = "('series', None)"


def series_names(typed: str) -> list[str]:
    """Series typed by name, several by commas (owner, 2026-10-24; no
    series of ours has a comma in its name): each trimmed, once each."""
    return list(dict.fromkeys(n.strip() for n in typed.split(",") if n.strip()))


def _series_label(value: str | None, choices: list[tuple[int, str]]) -> str:
    if not value:
        return ""
    named = dict(choices)
    return named.get(int(value), f"series {value}") if value.isdigit() else value


def _ask(
    qid: str,
    key: str,
    names: list[str],
    per: dict,
    labels: dict,
    ask: str,
    series: list[tuple[int, str]] | None = None,
    named: str | None = None,
) -> tuple[str, bool]:
    """One decision: a button for each answer the advisers gave, saying who
    gave it, then «Own answer…» with every other answer it can take and a field
    for one typed — a tap records it (owner, 2026-10-23). `named`: an answer
    the item's own name gives (an edition's type), offered among the first.
    Returns the html and whether the advisers agree on it."""
    said = {n: str(per[n].get(key, "—")) for n in names}
    given = list(dict.fromkeys(said.values()))
    others = [v for v in _choices(key) if v not in given]
    current = labels.get(f"{qid}|{key}")
    agreed = len(given) == 1
    choices = series or []

    def button(v: str, who: str = "") -> str:
        small = f"<small>{escape(who)}</small>" if who else ""
        if v == SERIES and choices:
            # One button per series both games are in: the tap says which.
            return "".join(
                f'<button name="d:{escape(key)}" value="{escape(v)}#{sid}">'
                f"one series — {escape(name)}{small}</button>"
                for sid, name in choices
            )
        if v == SERIES:
            # No series both are in yet: the answer names it, typed.
            return (
                f"<div class='free series'><input class=other name='s:{escape(key)}'"
                f" list=series-names placeholder='one series — which? (several: comma-separated)'>"
                f'<button name="d:{escape(key)}" value="{escape(v)}#new">'
                f"one series{small}</button></div>"
            )
        return (
            f'<button name="d:{escape(key)}" value="{escape(v)}">'
            f"{escape(_value(v, key))}{small}</button>"
        )

    picks = "".join(button(v, ", ".join(n for n in names if said[n] == v)) for v in given)
    if named and named not in given:
        picks += button(named, "its name")
    more = "".join(button(v) for v in others if v != named)
    series_field = (
        f"<div class=free><input class=other name='s:{escape(key)}' list=series-names"
        f" placeholder='one series — another (several: comma-separated)'>"
        f'<button name="d:{escape(key)}" value="{escape(SERIES)}#new">ok</button></div>'
        if key == "relation" and choices
        else ""
    )
    own = (
        "<details class=own><summary>Own answer…</summary>"
        + (f"<div class=more>{more}</div>" if more else "")
        + series_field
        + f"<div class=free><input class=other name='o:{escape(key)}' placeholder='type one'>"
        f'<button name="d:{escape(key)}" value="">ok</button></div></details>'
    )
    which = _series_label(labels.get(f"{qid}|{key}.series"), choices)
    mark = (
        f" <span class=done>✓ {escape(_value(current, key))}"
        f"{' — ' + escape(which) if which else ''}</span>"
        if current is not None
        else ""
    )
    html = (
        f'<div class="one{"" if agreed else " diff"}"><div class=ask>{escape(ask)}{mark}</div>'
        f"<div><div class=picks>{picks}</div>{own}</div></div>"
    )
    return html, agreed


def _subject_of(key: str) -> str:
    """The item a decision is about: its release, edition or member."""
    m = re.fullmatch(r"(v\d+|e\d+)\.(belongs|kind|holds)", key)
    return m[1] if m else key


def _rows(qid: str, keys: list[str], names: list[str], per: dict, labels: dict, look: _Look) -> str:
    kind, _, rest = qid.partition(":")
    parts = rest.split(":")
    series = (
        look.shared_series(int(parts[0]), int(parts[1]))
        if kind in ("R", "D") and len(parts) == 2 and all(x.isdigit() for x in parts)
        else []
    )
    """Decisions grouped by the item they are about: a release's "belongs" and
    "kind" sit beside one picture of it."""
    groups: dict[str, list[str]] = {}
    for key in keys:
        groups.setdefault(_subject_of(key), []).append(key)
    out = []
    for group in groups.values():
        what, _ask0 = _subject(group[0], look)
        asks, all_agree = [], True
        for key in group:
            m = re.fullmatch(r"e(\d+)\.kind", key)
            named = look.edition_word(int(m[1])) if m else None
            html, agreed = _ask(qid, key, names, per, labels, _subject(key, look)[1], series, named)
            asks.append(html)
            all_agree &= agreed
        out.append(
            f'<div class="item{"" if all_agree else " diff"}">'
            # An empty first column keeps every question in the same column.
            + f"<div class=what>{what}</div>"
            + f"<div class=asks>{''.join(asks)}</div></div>"
        )
    return "".join(out)


# Not the operator's to dig for (owner, 2026-10-23): what versions are missing
# is a search of the stores, the octopus's (#204). Shown only when asked for.
WAITING_FOR_OCTOPUS = ("M",)


def _disputed(qid: str, per: dict, names: list[str]) -> tuple[list[str], dict[str, str]]:
    """`(the decisions the advisers disagree on, those they all gave alike)`."""
    every = sorted(set().union(*(d.keys() for d in per.values())) if per else set())
    disputed, accepted = [], {}
    for k in every:
        said = {str(per[n].get(k, "—")) for n in names}
        if len(said) == 1:
            accepted[k] = said.pop()
        else:
            disputed.append(k)
    return disputed, accepted


def _per(qid: str, advisers: dict, names: list[str]) -> dict:
    return {n: decisions(qid, advisers[n][qid]) if qid in advisers[n] else {} for n in names}


def cards(request: web.Request, trial: Path, *, back_base: str) -> tuple[str, list[str], int]:
    """The trial's questions as review cards: `(the line above them, the
    cards, how many decisions are still open)`. `back_base` is the review
    tab's own address, with its filters; a card's answer comes back there."""
    from scripts.catalog_viewer import _db, _img, _store_href

    kind = request.query.get("kind", "")
    # A question answered whole leaves the list (owner, 2026-10-16);
    # `done=1` shows the answered ones as well.
    only_open = request.query.get("done") != "1"
    # Only what the advisers disagree on is the operator's (owner,
    # 2026-10-16); a decision they all gave alike is taken as theirs.
    show_all = request.query.get("all") == "1"
    show_later = request.query.get("later") == "1"
    deferred = _later(trial)
    advisers = _advisers(trial)
    names = list(advisers)
    labels = _labels(trial)
    accepted: dict[str, str] = {}
    out, total, done = [], 0, 0
    with _db(request) as conn:
        look = _Look(conn, _img, _store_href)
        for qid, text in _questions(trial):
            per = _per(qid, advisers, names)
            disputed, alike = _disputed(qid, per, names)
            accepted.update({f"{qid}|{k}": v for k, v in alike.items()})
            keys = sorted(set(disputed) | set(alike)) if show_all else disputed
            keys = current_keys(conn, qid, keys)
            qkind = qid.split(":")[0]
            if not keys or (qkind in WAITING_FOR_OCTOPUS and kind != qkind):
                continue
            labelled = sum(1 for k in keys if f"{qid}|{k}" in labels)
            total += len(keys)
            done += labelled
            if (qid in deferred) != show_later:
                continue
            if kind and qkind != kind:
                continue
            if only_open and labelled == len(keys):
                continue
            rows = _rows(qid, keys, names, per, labels, look)
            whys = "".join(
                f"<div><b>{escape(n)}</b>"
                f" ({escape(str(advisers[n].get(qid, {}).get('confidence', '—')))}):"
                f" {escape(str(advisers[n].get(qid, {}).get('why', '—')))}</div>"
                for n in names
            )
            out.append(
                f'<div class=tq id="{escape(qid)}">'
                f"<h3><span class=badge>{escape(KIND_RU.get(qkind, ''))}</span>"
                f"<small>advisers disagree · {labelled}/{len(keys)} answered</small></h3>"
                f"{_head(qid, text, look)}"
                f'<form method=post action="/trial/label">'
                f'<input type=hidden name=q value="{escape(qid)}">'
                f'<input type=hidden name=back value="{escape(back_base)}">'
                f"{rows}"
                f'<button class=later formaction="/trial/later">Later</button></form>'
                f"<details class=why><summary>why they answered so</summary>{whys}</details>"
                f"<details><summary>the question's text</summary>"
                f"<pre style='white-space:pre-wrap;font-size:12px'>{escape(text)}</pre>"
                "</details></div>"
            )
        names_list = look.series_names()
    path = trial / "compare" / "accepted.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(accepted, ensure_ascii=False, indent=1), "utf-8")
    line = (
        f"<p><small>Advisers: {escape(', '.join(names))} · answered {done}/{total}"
        f" disputed · where all three agree, the answer is taken without you ({len(accepted)})"
        f" · «Missing versions» wait for the octopus (#204)</small></p>"
        "<datalist id=series-names>"
        + "".join(f'<option value="{escape(n)}">' for n in names_list)
        + "</datalist>"
    )
    return line, out, total - done


def kinds() -> list[tuple[str, str]]:
    """The kinds of question a review filter offers, as `(kind, name)`."""
    return [(k, KIND_RU[k]) for k in KINDS if k in KIND_RU and k not in WAITING_FOR_OCTOPUS]


def _open_keys(trial: Path, qid: str) -> list[str]:
    advisers = _advisers(trial)
    names = list(advisers)
    disputed, _alike = _disputed(qid, _per(qid, advisers, names), names)
    labels = _labels(trial)
    return [k for k in disputed if f"{qid}|{k}" not in labels]


def _back_after(trial: Path, qid: str, back: str) -> str:
    """Where an answer lands: the same question while a decision of it is
    still open, else the one after it (this one has left the list)."""
    back = back.split("#", 1)[0] or "/review"
    if _open_keys(trial, qid):
        return back + f"#{quote(qid)}"
    order = [q for q, _text in _questions(trial)]
    after = order[order.index(qid) + 1 :] if qid in order else []
    return back + (f"#{quote(after[0])}" if after else "")


def register(app: web.Application, trial: Path | None, page) -> None:
    """Mount the answer routes; the cards themselves are drawn by the review
    tab (`cards`). `/trial` is an old address of it."""
    app["trial_dir"] = trial

    async def old_address(request: web.Request) -> web.Response:
        query = request.query_string
        raise web.HTTPFound("/review?tab=advisers" + (f"&{query}" if query else ""))

    app.router.add_get("/trial", old_address)
    if trial is None:
        return

    async def label(request: web.Request) -> web.Response:
        form = await request.post()
        qid = str(form.get("q") or "")
        labels = _labels(trial)
        for name, value in form.items():
            if name.startswith("d:"):
                key = name[2:]
                # «ok» beside the field carries no value: the typed one is it.
                answer = str(value) or str(form.get(f"o:{key}") or "").strip()
                answer, _, which = answer.partition("#")
                if which == "new":
                    # Several series, by commas (owner, 2026-10-24).
                    which = ", ".join(series_names(str(form.get(f"s:{key}") or "")))
                if answer:
                    labels[f"{qid}|{key}"] = answer
                    if which:
                        labels[f"{qid}|{key}.series"] = which
                    else:
                        labels.pop(f"{qid}|{key}.series", None)
        path = _labels_path(trial)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(labels, ensure_ascii=False, indent=1), "utf-8")
        raise web.HTTPFound(_back_after(trial, qid, str(form.get("back") or "/review")))

    app.router.add_post("/trial/label", label)

    async def later(request: web.Request) -> web.Response:
        """Put a question off (owner, 2026-10-17: a stand-in with no name is not
        worth digging for now): it leaves the list until asked for."""
        form = await request.post()
        qid = str(form.get("q") or "")
        deferred = _later(trial)
        deferred[qid] = True
        _later_path(trial).write_text(json.dumps(deferred, ensure_ascii=False, indent=1), "utf-8")
        back = str(form.get("back") or "/review").split("#", 1)[0] or "/review"
        order = [q for q, _text in _questions(trial)]
        after = order[order.index(qid) + 1 :] if qid in order else []
        raise web.HTTPFound(back + (f"#{quote(after[0])}" if after else ""))

    app.router.add_post("/trial/later", later)
