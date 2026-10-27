"""A batch of review questions for a web-searching agent (owner, 2026-10-25:
"the work I did by hand goes to an agent" — every decision about how two
things relate, not only enhanced editions). Four kinds, each answered by
`scripts/web_labels.py`:

- `pair` — two versions: the model's review list first, then one game, an
  enhanced edition, a remaster, a demo, another game of the series, …; the
  automatic relations between games (`game_relations`) are asked as a pair
  of their versions, and so are the versions the linker put in one game
  under different names;
- `hltb` — is this HowLongToBeat entry this version (an automatic link the
  matcher was least sure of);
- `series` — is this game in this series (the linker's proposals, least
  sure first).

Nothing already labelled is asked again. Read-only, safe beside the viewer.

`--recheck` asks instead about every relation the linker set by itself
(`to_recheck`; owner, 2026-10-27): the model's answer is its first guess,
written so the catalog has one, and settled by the advisers' labels — and
about the old labels the owner's definitions changed (`to_relabel`): an
edition labelled "same" before an enhanced edition was an answer of its own.
`--prompt` also writes the file to hand each adviser (`<out stem>.<adviser>.md`),
whose answer file is named after the model that answered
(`<out stem>.<model>.json`).

Usage:
    … -m scripts.review_questions --db data/games.db --out questions.json [--total 500]
    … -m scripts.review_questions --db data/games.db --out recheck.json --recheck
        [--prompt gemini,claude]
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

from bot.services.advice import DEFINITIONS
from scripts.advise_pairs import read_only_uri

SHARES = {"relations": 0.1, "hltb": 0.15, "series": 0.3}  # the rest: pairs in one game

# A version's role in its game that the linker gives it and an adviser checks.
PART_ROLES = ("enhanced", "demo", "tool", "mode", "extra", "pass")
# What to ask beside a VR version (owner, 2026-10-27): a VR version of the
# very game, or another game of its series made for VR.
VR_QUESTION = "the VR version of this very game, or another game of its series made for VR?"
# The words of an edition's name (owner, 2026-10-27: a pair labelled "same"
# where one side is named so is asked again under the enhanced definition).
EDITION_WORDS = re.compile(
    r"game of the year|\bgoty\b|complete|definitive|director.?s cut|enhanced|special edition"
    r"|anniversary|ultimate edition|deluxe|gold edition|legendary edition|royal edition"
    r"|extended|redux|final cut|premium edition",
    re.I,
)


def _version(conn: sqlite3.Connection, vid: int) -> dict:
    r = conn.execute(
        "SELECT v.version_id, v.name, v.console, v.store, v.product_id, v.release_date,"
        " v.developer, v.publisher, g.name AS game FROM versions v"
        " LEFT JOIN games g ON g.game_id = v.game_id WHERE v.version_id = ?",
        (vid,),
    ).fetchone()
    return {k: r[k] for k in r.keys()}


def _plain(conn: sqlite3.Connection, game_id: int) -> int | None:
    """A game's own version to ask about it by: its earliest named one."""
    row = conn.execute(
        "SELECT version_id FROM versions WHERE game_id = ? AND name IS NOT NULL"
        " AND COALESCE(role, 'version') IN ('version', 'enhanced')"
        " ORDER BY release_date IS NULL, release_date, version_id LIMIT 1",
        (game_id,),
    ).fetchone()
    return int(row[0]) if row else None


def to_recheck(conn: sqlite3.Connection) -> list[tuple[int, int, str]]:
    """Every relation the linker set by itself and no label settles yet, as
    `(the version it is about, the other, the relation)`: between two games
    (a remaster, a remake, a compilation, a VR version, an enhanced edition
    of its own), as a pair of their own versions, and inside a game (an
    enhanced edition, a demo, a tool, a mode, an extra, a pass) — the
    version and the one it is of."""
    labelled = {
        frozenset((int(a), int(b)))
        for a, b in conn.execute("SELECT version_id, other_id FROM match_decisions")
    }
    found: list[tuple[int, int, str]] = []
    for game, related, kind in conn.execute(
        "SELECT game_id, related_id, kind FROM game_relations WHERE source = 'auto'"
        " ORDER BY kind, game_id"
    ):
        a, b = _plain(conn, game), _plain(conn, related)
        if a and b and a != b and frozenset((a, b)) not in labelled:
            found.append((a, b, str(kind)))
    marks = ",".join("?" * len(PART_ROLES))
    for vid, of, role in conn.execute(
        "SELECT version_id, of_version_id, role FROM versions WHERE role IN (" + marks + ")"
        " AND of_version_id IS NOT NULL ORDER BY role, version_id",
        PART_ROLES,
    ):
        if frozenset((int(vid), int(of))) not in labelled:
            found.append((int(vid), int(of), f"{role}_of"))
    return found


def to_relabel(conn: sqlite3.Connection) -> list[tuple[int, int]]:
    """The labels "same" between an edition and a version not named so —
    given before the enhanced edition had an answer of its own."""
    found = []
    for a, b, na, nb in conn.execute(
        "SELECT d.version_id, d.other_id, va.name, vb.name FROM match_decisions d"
        " JOIN versions va ON va.version_id = d.version_id"
        " JOIN versions vb ON vb.version_id = d.other_id"
        " WHERE d.relation = 'same' ORDER BY d.version_id, d.other_id"
    ):
        if bool(EDITION_WORDS.search(na or "")) != bool(EDITION_WORDS.search(nb or "")):
            found.append((int(a), int(b)))
    return found


def recheck_questions(db: Path) -> list[dict]:
    conn = sqlite3.connect(read_only_uri(db), uri=True)
    conn.row_factory = sqlite3.Row
    out = []
    for a, b, relation in to_recheck(conn):
        q = {"type": "pair", "a": a, "b": b, "asked_for": f"recheck: the model said A {relation} B",
             "A": _version(conn, a), "B": _version(conn, b)}  # fmt: skip
        if relation == "vr_of":
            q["question"] = VR_QUESTION
        out.append(q)
    for a, b in to_relabel(conn):
        out.append({"type": "pair", "a": a, "b": b,
                    "asked_for": "relabel: an edition labelled before the enhanced definition",
                    "A": _version(conn, a), "B": _version(conn, b)})  # fmt: skip
    conn.close()
    return out


PROMPT = """# Recheck game-catalog pairs — web search required

You label how two store versions of video games relate, for a small games catalog.
Your answers train a matching model, so a wrong answer is worse than none.

**Look each one up on the web.** Use web search for EVERY question — store pages
(Steam, Microsoft Store, PlayStation Store), Wikipedia, MobyGames, HowLongToBeat,
PSNProfiles, TrueAchievements, publisher announcements. An answer from memory alone
must be marked `"searched": false` and will be thrown away. Never invent a source URL:
`source` is a page you actually opened or a search result you actually saw.

## Input

A JSON array of `pair` questions at the end of this file: two versions `A` and `B`
(name, console, store, product id, release date, developer, publisher, and the game
the catalog filed them under). `asked_for` says why it is asked; it is not the answer,
and a guess of the model's it names may well be wrong. A `question` field, where there
is one, is the one thing to settle. The store data may be incomplete or wrong (a
store's date is often a re-release's); rely on what the sources say about the games.

## Relations

Use these definitions exactly as written:

- same: one game — the same release on another console or store, a regional id, a
  standard or Deluxe edition sold under one id, a port however late. Two demos of one
  game are `same`.
{definitions}
- demo_of: a demo, beta, trial, playtest, prologue or tech test of the other.
- tool_of: an editor, creation kit, SDK, benchmark or dedicated server for the other.
- mode_of: a launcher of one mode of the other ("Call of Duty: Black Ops II - Zombies").
- extra_of: a soundtrack, an artbook or a DLC of the other, sold as its own product.
- pass_of: a friend's pass — a free copy to play the whole game with its owner.
- contains: a compilation or collection that holds the other; a compilation holds at
  least two games.
- vr_of: the VR version of this very game; another game of its series made for VR is
  `series`.
- series: different games of one series — sequels, prequels, spin-offs, a reboot that
  is a new game (give `series_name`).
- not_related: unrelated.

For a directed relation (enhanced_of, remaster_of, remake_of, demo_of, tool_of,
mode_of, extra_of, pass_of, contains, vr_of) give `direction`: `"a"` if A is the
enhanced edition / remaster / remake / demo / … / compilation / VR version, `"b"` if
B is; null for every other answer.

## Confidence — doubt is welcome

`high` answers go straight into training; `low` and `medium` are checked again. Use
`high` only when a source you opened says it in so many words. Say `medium` or `low`
when you identified a version only by its name or date, when the answer is a judgement
between two close relations (same or enhanced, enhanced or remaster, remaster or
remake), when sources disagree, or when you found the game but not this release.

## Output

{count} questions. Answer every one and give the whole answer as ONE file named
**`{stem}.<model>.json`**, where `<model>` is your own exact model name and version
(for example `{example}`), in lower case with hyphens. The file is a JSON array, one
object per question, in the questions' order:

`{{"a": <A version_id>, "b": <B version_id>, "relation": "...", "direction":
"a"|"b"|null, "series_name": "..."|null, "confidence": "high"|"medium"|"low",
"searched": true|false, "why": "<one sentence>", "source": "<url>", "model": "<model>"}}`

If the questions do not all fit in one reply, work through them in parts as large as
you can, and say at the end of each part which pair you stopped at; I will reply
"continue". The final file must hold every answer, the earlier parts' included.

## Questions

```json
{questions}
```
"""
EXAMPLES = {"gemini": "gemini-3-pro", "claude": "claude-opus-5-5"}


def prompt(questions: list[dict], stem: str, adviser: str) -> str:
    """The file to hand one adviser, with the owner's definitions as they stand."""
    return PROMPT.format(
        definitions=DEFINITIONS,
        count=len(questions),
        stem=stem,
        example=EXAMPLES.get(adviser, adviser),
        questions=json.dumps(questions, ensure_ascii=False, indent=1),
    )


def build(db: Path, total: int) -> list[dict]:
    conn = sqlite3.connect(read_only_uri(db), uri=True)
    conn.row_factory = sqlite3.Row
    labelled = {
        frozenset((int(a), int(b)))
        for a, b in conn.execute("SELECT version_id, other_id FROM match_decisions")
    }
    out: list[dict] = []

    def pair(a: int, b: int, why: str) -> bool:
        if a == b or frozenset((a, b)) in labelled:
            return False
        labelled.add(frozenset((a, b)))
        out.append({"type": "pair", "a": a, "b": b, "asked_for": why,
                    "A": _version(conn, a), "B": _version(conn, b)})  # fmt: skip
        return True

    # The model's own doubtful pairs (the review list) come first, all of them.
    for a, b, relation, prob in conn.execute(
        "SELECT version_id, other_id, relation, p FROM match_pairs ORDER BY p DESC"
    ):
        pair(int(a), int(b), f"the model is unsure: {relation} {prob:.2f}")
    quota = {k: int(total * v) for k, v in SHARES.items()}
    for game, related, kind in conn.execute(
        "SELECT game_id, related_id, kind FROM game_relations WHERE source = 'auto'"
    ):
        a, b = _plain(conn, game), _plain(conn, related)
        if a and b and quota["relations"] > 0 and pair(a, b, f"games related: {kind}"):
            quota["relations"] -= 1
    for r in conn.execute(
        "SELECT vh.version_id, vh.hltb_id, vh.score, h.name, h.game_type, h.release_year,"
        " h.developer, (SELECT GROUP_CONCAT(p.platform, ', ') FROM hltb_entry_platforms p"
        "  WHERE p.hltb_id = h.hltb_id) AS platforms FROM version_hltb vh JOIN hltb_entries h"
        " ON h.hltb_id = vh.hltb_id WHERE vh.source = 'auto' AND vh.score IS NOT NULL"
        " AND vh.score <> 0.9 ORDER BY vh.score LIMIT ?",
        (quota["hltb"],),
    ):
        out.append(
            {
                "type": "hltb",
                "version_id": r["version_id"],
                "hltb_id": r["hltb_id"],
                "A": _version(conn, r["version_id"]),
                "hltb": {
                    "name": r["name"],
                    "type": r["game_type"],
                    "year": r["release_year"],
                    "developer": r["developer"],
                    "platforms": r["platforms"],
                    "url": f"https://howlongtobeat.com/game/{r['hltb_id']}",
                },
            }
        )
    for r in conn.execute(
        "SELECT gs.game_id, gs.series_id, gs.p, g.name AS game, g.year, s.name AS series,"
        " (SELECT GROUP_CONCAT(g2.name, ' | ') FROM game_series x JOIN games g2"
        "   ON g2.game_id = x.game_id WHERE x.series_id = gs.series_id AND x.member = 1"
        "   AND x.game_id <> gs.game_id) AS others"
        " FROM game_series gs JOIN games g ON g.game_id = gs.game_id"
        " JOIN series s ON s.series_id = gs.series_id"
        " WHERE gs.source = 'auto' AND gs.member = 1 AND s.merged_into IS NULL"
        " ORDER BY gs.p, gs.game_id LIMIT ?",
        (quota["series"],),
    ):
        out.append(
            {
                "type": "series",
                "game_id": r["game_id"],
                "series_id": r["series_id"],
                "game": f"{r['game']} ({r['year'] or '?'})",
                "series": r["series"],
                "other_games_in_series": (r["others"] or "")[:400],
            }
        )
    # Versions the linker put in one game under different names: the most
    # differently named against the game's own version first.
    rows = conn.execute(
        "SELECT v.version_id, v.game_id, v.name FROM versions v WHERE v.game_id IS NOT NULL"
        " AND v.name IS NOT NULL AND COALESCE(v.role, 'version') NOT IN ('covered')"
        " AND v.store <> 'unknown'"
    ).fetchall()
    candidates = []
    for r in rows:
        plain = _plain(conn, r["game_id"])
        if plain is None or plain == r["version_id"]:
            continue
        name = conn.execute("SELECT name FROM versions WHERE version_id = ?", (plain,)).fetchone()
        if str(name[0]).casefold() == str(r["name"]).casefold():
            continue
        candidates.append((len(set(str(r["name"]).lower()) ^ set(str(name[0]).lower())), r, plain))
    candidates.sort(key=lambda t: -t[0])
    for _, r, plain in candidates:
        if len(out) >= total:
            break
        pair(int(r["version_id"]), plain, "filed in one game")
    conn.close()
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--total", type=int, default=500)
    parser.add_argument("--recheck", action="store_true")
    parser.add_argument("--prompt", default="", help="advisers to write a file for: gemini,claude")
    args = parser.parse_args()
    questions = (
        recheck_questions(Path(args.db)) if args.recheck else build(Path(args.db), args.total)
    )
    out = Path(args.out)
    out.write_text(json.dumps(questions, ensure_ascii=False, indent=1), "utf-8")
    for adviser in filter(None, args.prompt.split(",")):
        path = out.with_name(f"{out.stem}.{adviser}.md")
        path.write_text(prompt(questions, out.stem, adviser), "utf-8")
        print(f"for {adviser}: {path}")
    counts: dict[str, int] = {}
    for q in questions:
        counts[q["type"]] = counts.get(q["type"], 0) + 1
    print(f"{len(questions)} questions {counts} → {args.out}")


if __name__ == "__main__":
    main()
