"""The viewer's /trial page (#147; owner, 2026-10-16): every question of the
trial file with each adviser's answer, decision by decision, and the
operator's own answer for each — the labels `compare_answers --labels` scores
the advisers by. Answers are read on every request from `<trial>/answers/*.jsonl`
(an adviser added later just appears); labels go to `<trial>/compare/labels.json`.
"""

from __future__ import annotations

import json
from html import escape
from pathlib import Path
from urllib.parse import quote

from aiohttp import web

from scripts.compare_answers import KINDS, decisions, read_answers


def _questions(trial: Path) -> list[tuple[str, str]]:
    """`(id, text)` of the trial file's questions, in its order."""
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


def register(app: web.Application, trial: Path | None, page) -> None:
    """Mount the page; `page` is the viewer's own page wrapper."""
    if trial is None:

        async def none(request: web.Request) -> web.Response:
            return page("Trial", "<p>(no trial: start the viewer with --trial)</p>")

        app.router.add_get("/trial", none)
        return

    async def show(request: web.Request) -> web.Response:
        kind = request.query.get("kind", "")
        only_open = request.query.get("open") == "1"
        advisers = _advisers(trial)
        names = list(advisers)
        labels = _labels(trial)
        questions = _questions(trial)
        cards, total, done = [], 0, 0
        for qid, text in questions:
            per = {n: decisions(qid, advisers[n][qid]) if qid in advisers[n] else {} for n in names}
            keys = sorted(set().union(*(d.keys() for d in per.values())) if per else set())
            total += len(keys)
            labelled = sum(1 for k in keys if f"{qid}|{k}" in labels)
            done += labelled
            if kind and not qid.startswith(kind + ":"):
                continue
            if only_open and labelled == len(keys):
                continue
            rows = []
            for key in keys:
                said = {n: str(per[n].get(key, "—")) for n in names}
                values = list(dict.fromkeys(said.values()))
                current = labels.get(f"{qid}|{key}")
                agreed = len(values) == 1
                choices = "".join(
                    f'<label style="margin-right:8px"><input type=radio name="d:{escape(key)}"'
                    f' value="{escape(v)}"{" checked" if current == v or (current is None and agreed) else ""}>'  # noqa: E501
                    f"{escape(v)} <small>({', '.join(n for n in names if said[n] == v)})</small></label>"  # noqa: E501
                    for v in values
                )
                other = current if current is not None and current not in values else ""
                rows.append(
                    f'<tr style="background:{"#fff" if agreed else "#fff3e0"}"><td>{escape(key)}</td>'  # noqa: E501
                    f"<td>{choices}<input name='o:{escape(key)}' size=18 placeholder='другое'"
                    f" value='{escape(other)}'></td>"
                    f"<td>{'✓' if f'{qid}|{key}' in labels else ''}</td></tr>"
                )
            whys = "".join(
                f"<div><b>{escape(n)}</b> ({escape(str(advisers[n].get(qid, {}).get('confidence', '—')))}):"  # noqa: E501
                f" {escape(str(advisers[n].get(qid, {}).get('why', '—')))}</div>"
                for n in names
            )
            back = f"/trial?kind={quote(kind)}&open={'1' if only_open else ''}#{quote(qid)}"
            cards.append(
                f'<div id="{escape(qid)}" style="border:1px solid #ccc;padding:8px;margin:10px 0">'
                f"<b>{escape(qid)}</b> · {escape(KINDS.get(qid.split(':')[0], ''))}"
                f" · {labelled}/{len(keys)} marked"
                f"<pre style='white-space:pre-wrap;font-size:12px'>{escape(text)}</pre>"
                f"<details><summary>why</summary>{whys}</details>"
                f'<form method=post action="/trial/label">'
                f'<input type=hidden name=q value="{escape(qid)}">'
                f'<input type=hidden name=back value="{escape(back)}">'
                f"<table>{''.join(rows)}</table><button>save</button></form></div>"
            )
        nav = " · ".join(f'<a href="/trial?kind={k}">{k} {escape(v)}</a>' for k, v in KINDS.items())
        head = (
            f"<p>{done}/{total} decisions marked · advisers: {escape(', '.join(names))}"
            f' · <a href="/trial?kind={quote(kind)}&open=1">only not marked</a>'
            f' · <a href="/trial">all</a></p><p>{nav}</p>'
            "<p><small>Orange rows: the advisers differ. The checked answer is saved as yours;"
            " where all agree it is checked already — save to confirm. 'другое' overrides.</small></p>"  # noqa: E501
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
