"""The viewer's /trial page (#147; owner, 2026-10-16): every question of the
trial file with each adviser's answer, decision by decision, and the
operator's own answer for each — the labels `compare_answers --labels` scores
the advisers by. Answers are read on every request from `<trial>/answers/*.jsonl`
(an adviser added later just appears); labels go to `<trial>/compare/labels.json`.

Laid out to be read (owner, 2026-10-16): each question shows what it is about
— the game, its releases, the HowLongToBeat entries, the editions — with their
pictures, and next to each item the choice to make, the advisers' answers on
pills (orange where they differ). The question's raw text is one click away.
"""

from __future__ import annotations

import json
import re
import sqlite3
from html import escape
from pathlib import Path
from urllib.parse import quote

from aiohttp import web

from scripts.compare_answers import KINDS, decisions, read_answers

KIND_RU = {
    "G": "Карточка игры",
    "M": "Недостающие версии",
    "R": "Связь игр",
    "D": "Похожие игры",
    "S": "Серия",
    "P": "Группа трофеев PSN",
    "E": "Издания",
    "H": "DLC ↔ HLTB",
    "X": "Отклонённый HLTB",
}
VALUE_RU = {
    "yes": "да",
    "no": "нет",
    "unsure": "не уверен",
    "same": "та же",
    "wrong": "не та",
    "True": "да",
    "False": "нет",
    "None": "—",
    "()": "ничего",
    "—": "нет ответа",
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
.other{width:100%;box-sizing:border-box;font-size:12px}
.con{display:inline-block;background:#e3f2fd;border-radius:5px;padding:0 5px;font-size:12px}
.done{color:#2e7d32;font-weight:bold}
.why div{font-size:12px;margin:2px 0}
.save{padding:6px 18px;font-size:14px;margin-top:6px}
</style>
"""


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


def _labels(trial: Path) -> dict[str, str]:
    path = _labels_path(trial)
    return json.loads(path.read_text("utf-8")) if path.exists() else {}


class _Look:
    """What the database knows of an item, as a picture and a line."""

    def __init__(self, conn: sqlite3.Connection, img, store_href) -> None:
        self.conn, self.img, self.store_href = conn, img, store_href

    def _one(self, sql: str, args: tuple) -> sqlite3.Row | None:
        return self.conn.execute(sql, args).fetchone()

    def version_cover(self, v: sqlite3.Row) -> str | None:
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
        stand_in = " · заглушка" if v["stand_in"] else ""
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
            + f"<span>{escape(e['name'] or '?')}<br><small>{escape(e['store'])} · наш тип"
            f" {escape(e['kind'] or '?')} · {escape(holds)}</small></span>"
        )


# A question asked the other way round than the adviser's field (owner,
# 2026-10-16: no double negatives) shows its values turned round too; what is
# stored stays the field's own value.
VALUE_BY_KEY = {
    "facts_wrong": {"False": "да, верны", "True": "нет, есть ошибка"},
    "missing_hltb": {"False": "нет", "True": "да, есть"},
    "name_ok": {"True": "да", "False": "нет"},
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
    "missing_hltb": "У игры есть ещё запись HLTB, которой у нас нет?",
    "series": "В каких сериях игра",
    "facts_wrong": "Год, студия и издатель верны?",
    "missing": "Каких версий в магазинах не хватает",
    "relation": "Как связаны",
    "name_ok": "Название серии верное?",
    "addon": "Какой аддон принёс группу",
    "links": "Какие DLC — какие записи HLTB",
    "verdict": "Эта запись HLTB — та же игра?",
}


def _subject(key: str, look: _Look) -> tuple[str, str]:
    """`(what the decision is about, the question asked)`."""
    if m := re.fullmatch(r"v(\d+)\.belongs", key):
        return look.version(int(m[1])), "Относится к игре?"
    if m := re.fullmatch(r"v(\d+)\.kind", key):
        return look.version(int(m[1])), "Что это?"
    if m := re.fullmatch(r"v(\d+)\.hltb(\d+)", key):
        return look.version(int(m[1])) + " → " + look.hltb(int(m[2])), "HLTB верна?"
    if m := re.fullmatch(r"dlc(\d+)\.hltb(\d+)", key):
        return look.dlc(int(m[1])) + " → " + look.hltb(int(m[2])), "HLTB верна?"
    if m := re.fullmatch(r"e(\d+)\.kind", key):
        return look.edition(int(m[1])), "Тип издания"
    if m := re.fullmatch(r"e(\d+)\.holds", key):
        return look.edition(int(m[1])), "Это издание этой игры?"
    if m := re.fullmatch(r"g(\d+)", key):
        return look.game(int(m[1]), 48), "В серии?"
    return "", ASK.get(key, key)


def _head(qid: str, text: str, look: _Look) -> str:
    kind, _, rest = qid.partition(":")
    parts = rest.split(":")
    if kind in ("G", "M", "E", "H"):
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


def _ask(
    qid: str, key: str, names: list[str], per: dict, labels: dict, ask: str
) -> tuple[str, bool]:
    """One decision's pills, and whether the advisers agree on it."""
    said = {n: str(per[n].get(key, "—")) for n in names}
    values = list(dict.fromkeys(said.values()))
    current = labels.get(f"{qid}|{key}")
    agreed = len(values) == 1
    pills = "".join(
        f'<label><input type=radio name="d:{escape(key)}" value="{escape(v)}"'
        f"{' checked' if current == v or (current is None and agreed) else ''}>"
        f"<span>{escape(_value(v, key))}</span> <small>"
        f"{escape(', '.join(n for n in names if said[n] == v))}</small></label>"
        for v in values
    )
    other = current if current is not None and current not in values else ""
    mark = " <span class=done>✓</span>" if f"{qid}|{key}" in labels else ""
    html = (
        f'<div class="one{"" if agreed else " diff"}"><div class=ask>{escape(ask)}{mark}</div>'
        f"<div class=pills>{pills}</div>"
        f"<input class=other name='o:{escape(key)}' placeholder='свой ответ'"
        f" value='{escape(other)}'></div>"
    )
    return html, agreed


def _subject_of(key: str) -> str:
    """The item a decision is about: its release, edition or member."""
    m = re.fullmatch(r"(v\d+|e\d+)\.(belongs|kind|holds)", key)
    return m[1] if m else key


def _rows(qid: str, keys: list[str], names: list[str], per: dict, labels: dict, look: _Look) -> str:
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
            html, agreed = _ask(qid, key, names, per, labels, _subject(key, look)[1])
            asks.append(html)
            all_agree &= agreed
        out.append(
            f'<div class="item{"" if all_agree else " diff"}">'
            # An empty first column keeps every question in the same column.
            + f"<div class=what>{what}</div>"
            + f"<div class=asks>{''.join(asks)}</div></div>"
        )
    return "".join(out)


def _row(qid: str, key: str, names: list[str], per: dict, labels: dict, look: _Look) -> str:
    said = {n: str(per[n].get(key, "—")) for n in names}
    values = list(dict.fromkeys(said.values()))
    current = labels.get(f"{qid}|{key}")
    agreed = len(values) == 1
    pills = "".join(
        f'<label><input type=radio name="d:{escape(key)}" value="{escape(v)}"'
        f"{' checked' if current == v or (current is None and agreed) else ''}>"
        f"<span>{escape(_value(v, key))}</span> <small>"
        f"{escape(', '.join(n for n in names if said[n] == v))}</small></label>"
        for v in values
    )
    other = current if current is not None and current not in values else ""
    what, ask = _subject(key, look)
    mark = " <span class=done>✓</span>" if f"{qid}|{key}" in labels else ""
    return (
        f'<div class="item{"" if agreed else " diff"}">'
        + (f"<div class=what>{what}</div>" if what else "")
        + f"<div class=ask>{escape(ask)}{mark}</div>"
        f"<div class=pills>{pills}</div>"
        f"<input class=other name='o:{escape(key)}' placeholder='свой ответ'"
        f" value='{escape(other)}'></div>"
    )


def register(app: web.Application, trial: Path | None, page) -> None:
    """Mount the page; `page` is the viewer's own page wrapper."""
    if trial is None:

        async def none(request: web.Request) -> web.Response:
            return page("Trial", "<p>(no trial: start the viewer with --trial)</p>")

        app.router.add_get("/trial", none)
        return

    async def show(request: web.Request) -> web.Response:
        from scripts.catalog_viewer import _db, _img, _store_href

        kind = request.query.get("kind", "")
        only_open = request.query.get("open") == "1"
        advisers = _advisers(trial)
        names = list(advisers)
        labels = _labels(trial)
        cards, total, done = [], 0, 0
        with _db(request) as conn:
            look = _Look(conn, _img, _store_href)
            for qid, text in _questions(trial):
                per = {
                    n: decisions(qid, advisers[n][qid]) if qid in advisers[n] else {} for n in names
                }
                keys = sorted(set().union(*(d.keys() for d in per.values())) if per else set())
                total += len(keys)
                labelled = sum(1 for k in keys if f"{qid}|{k}" in labels)
                done += labelled
                if kind and not qid.startswith(kind + ":"):
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
                back = f"/trial?kind={quote(kind)}&open={'1' if only_open else ''}#{quote(qid)}"
                cards.append(
                    f'<div class=tq id="{escape(qid)}">'
                    f"<h3><span class=badge>{escape(KIND_RU.get(qid.split(':')[0], ''))}</span>"
                    f"{escape(qid)} · {labelled}/{len(keys)} размечено</h3>"
                    f"{_head(qid, text, look)}"
                    f"<details class=why><summary>почему так ответили</summary>{whys}</details>"
                    f'<form method=post action="/trial/label">'
                    f'<input type=hidden name=q value="{escape(qid)}">'
                    f'<input type=hidden name=back value="{escape(back)}">'
                    f"{rows}<button class=save>сохранить</button></form>"
                    f"<details><summary>текст вопроса</summary>"
                    f"<pre style='white-space:pre-wrap;font-size:12px'>{escape(text)}</pre>"
                    "</details></div>"
                )
        nav = " · ".join(f'<a href="/trial?kind={k}">{escape(KIND_RU[k])}</a>' for k in KINDS)
        head = (
            CSS + f"<p><b>{done}/{total}</b> решений размечено · модели: {escape(', '.join(names))}"
            f' · <a href="/trial?kind={quote(kind)}&open=1">только неразмеченные</a>'
            f' · <a href="/trial">все</a></p><p>{nav}</p>'
            "<p><small>Оранжевым — где модели расходятся. Отмеченный зелёным ответ сохранится"
            " как твой; где все согласны, он уже отмечен — сохрани, чтобы подтвердить."
            " «Свой ответ» важнее отмеченного.</small></p>"
        )
        return page("Trial", head + "".join(cards))

    async def label(request: web.Request) -> web.Response:
        form = await request.post()
        qid = str(form.get("q") or "")
        labels = _labels(trial)
        for name, value in form.items():
            if name.startswith("d:"):
                key = name[2:]
                other = str(form.get(f"o:{key}") or "").strip()
                labels[f"{qid}|{key}"] = other or str(value)
        for name, value in form.items():
            if name.startswith("o:") and str(value).strip() and f"d:{name[2:]}" not in form:
                labels[f"{qid}|{name[2:]}"] = str(value).strip()
        path = _labels_path(trial)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(labels, ensure_ascii=False, indent=1), "utf-8")
        raise web.HTTPFound(str(form.get("back") or "/trial"))

    app.router.add_get("/trial", show)
    app.router.add_post("/trial/label", label)
