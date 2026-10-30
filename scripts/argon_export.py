"""The whole database as questions for one adviser at a time (#147; owner,
2026-10-16: a full run — every game, link and series asked, the model not
trusted yet). Text files an adviser reads whole (Gemini Argon, Claude) and
answers in a file of its own, JSON Lines, one line per question.

Four kinds of question:
- `G:<game>` a game's card: its releases, what each is, its HowLongToBeat entries
  and its DLC's entries. One answer judges every part of it.
- `R:<game>:<game>` two games the database relates (a remaster, a remake, a
  compilation, a VR version) or the model thinks might be.
- `S:<series>` a series and its games.
- `P:<version>:<group>` a PSN trophy group against the add-ons sold for that game.
- `M:<game>` the releases a game has in the stores that the database lacks
  (another console, another store, a store page for a release that has none).
- `D:<game>:<game>` two games with alike names nothing relates yet: one game
  stored twice, or related.
- `E:<game>` a game's editions (store bundles and packages): their kind and contents.
- `H:<game>` a game's DLC against its HowLongToBeat entry's additional content.
- `X:<version>:<hltb>` a HowLongToBeat link that was refused, asked again.

Each file is whole on its own: the same instructions, then its questions. The
questions are kept beside the files (`questions.json`) for the import.

    .venv/Scripts/python.exe -X utf8 -m scripts.argon_export [--schema dev] \\
        --out data/advice/argon --per-file 150
"""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

from bot.db import tools
from bot.db.postgres import Row
from bot.db.repo._sql import OWN_EDITION
from bot.services.stores import console_label

INSTRUCTIONS = """You are checking a video game database, question by question. Rely on what you
know about the real games; the data shown comes from store pages and may be incomplete
or wrong (a store's date is often a re-release's). A name that is only digits is an
id whose name we never learned: a Steam app id on Steam, an Xbox title id on Xbox (use
what you know of it). When you are not sure, say so
("unsure", or confidence "low"): a wrong sure answer costs more than an unsure one.

THE RULES OF THIS DATABASE
- A GAME is one work. Its RELEASES (versions) are store products on one console each:
  PS4 and PS5, Xbox One and Series, PC on Steam and on the Microsoft Store are
  releases of one game when they are the same work. A port is the same game however
  late. A GOTY / Complete / Deluxe / Gold / Ultimate edition is the same game (an
  edition = the game, maybe with its DLC).
- A REMASTER is the same game re-released with better technology, its design kept;
  it is a game of its own. A next-generation release is a remaster when it is a
  separate product (own store page and achievement list, a subtitle or "Remastered")
  sold beside the previous one; it is the same game when one product runs on both
  (Smart Delivery, cross-buy) or it replaced the previous one by an update. A remaster
  of a remake is a remaster of the remake.
- A REMAKE is rebuilt from the ground up and is an original of its own. "Remake" in a
  name marks one; "Intergrade", "Director's Cut", "Special Edition" alone do not.
- A COMPILATION holds at least two games ("Collection", "Trilogy" in a name is not
  enough: one game with its DLC is an edition, not a compilation).
- A DEMO, beta, trial, playtest, tech test or Insider build belongs to its game as a
  demo. An editor, SDK, creation kit or dedicated server is a tool of it. A launcher of
  one mode ("… - Zombies", "… - Multiplayer") is a mode of it. A soundtrack or an
  artbook is an extra of its game. A companion app or a video is not a game.
- An EPISODE sold as a product of its own is a game of its own (Poppy Playtime's
  chapters), whatever HowLongToBeat files it as.
- HOWLONGTOBEAT (HLTB): an entry times a game. A release's entry is right when it
  times that very work (not a sequel, not the remake/remaster unless the release is
  it, not a DLC, not a compilation unless the release is that compilation). A demo
  has no entry unless the entry is the demo's own.
- A SERIES groups different games: sequels, prequels, spin-offs, a reboot. A game can
  be in several series (its franchise's, a local one inside it; a LEGO game is in
  LEGO and in its licence's).

HOW TO ANSWER
Answer every question below, in the order asked. Put the answers in a FILE to
download, named after this file with "_answers.jsonl" (01_games.txt →
01_games_answers.jsonl): if you can create files (code execution, a canvas, an
attachment), do so; if you cannot, reply with the same content as plain text.
The content is JSON Lines only: one JSON object per line, one line per question,
nothing else (no prose, no code fence). Copy each "id" exactly. If the answer is cut
short, stop at a whole line: you will be told "continue" and go on from the next id.
"confidence" is "high", "medium" or "low"; "why" is at most 25 words.

For a G (game card) question:
{"id": "G:12", "releases": [{"v": 101, "belongs": "yes"|"no"|"unsure",
   "kind": "game"|"edition"|"compilation"|"remaster"|"remake"|"dlc"|"episode"|"demo"
           |"tool"|"mode"|"soundtrack"|"app"|"other",
   ("kind" says what the game is, alike for all its releases: a release of a remake is
   "remake", of a remaster "remaster", of an original "game"; which older game it remakes
   is an R/D question)
   "same_game_as": null or the v of another release here this one really is (when it
   belongs elsewhere: null)}],
 "hltb": [{"v": 101, "hltb": 555, "verdict": "same"|"wrong"|"unsure"}],
 "dlc_hltb": [{"dlc": 77, "hltb": 888, "verdict": "same"|"wrong"|"unsure"}],
 "missing_hltb": "the name of this game's own HowLongToBeat entry (not a DLC's) when none
   of the links shown is it and you are sure one exists, or null",
 "series": ["every series this game is in (franchise, sub-series, LEGO, …)"] or [],
 "facts": null, or the right {"year": first release year, "developer": "...",
   "publisher": "..."} when the GAME line's are wrong (only the wrong ones),
 "confidence": "...", "why": "..."}
List every release and every HLTB link shown, each once.

For an R (two games) question:
{"id": "R:12:34", "relation": "same"|"remaster_of"|"remake_of"|"contains"|"vr_of"
   |"series"|"not_related"|"unsure",
 "direction": "first"|"second"|null  (first = FIRST is the remaster / remake /
   compilation / VR version of SECOND; null for same, series, not_related, unsure),
 "confidence": "...", "why": "..."}

For an S (series) question:
{"id": "S:7", "name_ok": true|false, "better_name": null or a better name,
 "members": [{"g": 12, "belongs": "yes"|"no"|"unsure"}],
 "missing": ["names of games of ours shown elsewhere you know belong here"] or [],
 "confidence": "...", "why": "..."}

For an M (missing releases) question: every release of this game in these stores
that is NOT listed — Xbox (One, Series, PC on the Microsoft Store, 360), PlayStation
(PS3, PS4, PS5, Vita), Steam — and a store page for a release marked "stand-in".
Only real store products of this very game (no remasters, remakes, sequels or DLC:
those are other games). Give the store's own title and its id when you know it
(a Steam app id, an Xbox product id like 9NBLGGH4R315 or C3KLDKZBHNCZ, a PlayStation
title id like CUSA00133 or PPSA01234, a PSN concept id).
{"id": "M:12", "missing": [{"store": "steam"|"xbox"|"psn", "console": "steam"|"pc"|"one"
   |"series"|"360"|"ps3"|"ps4"|"ps5"|"vita", "title": "...", "store_id": "..."|null,
   "for_stand_in": the v of the stand-in it is the page of, or null}],
 "confidence": "...", "why": "..."}
"missing" is [] when nothing is missing.

For a D (two games alike) question: the same answer as for R —
{"id": "D:12:34", "relation": "same"|"remaster_of"|"remake_of"|"contains"|"vr_of"
   |"series"|"not_related"|"unsure", "direction": ..., "confidence": "...", "why": "..."}

For an E (editions) question: for each edition shown, its kind and whether it holds
this game (an edition of another game, or a bundle of several games, is "no").
{"id": "E:12", "editions": [{"e": 501, "kind": "standard"|"deluxe"|"premium"|"ultimate"
   |"gold"|"goty"|"complete"|"definitive"|"anniversary"|"collection"|"bundle"|"preorder"
   |"other", "holds_game": "yes"|"no"|"unsure"}], "confidence": "...", "why": "..."}

For an H (DLC and HowLongToBeat) question: which of our DLC (listed) is which of the
entry's additional content (listed); a DLC with no entry is left out.
{"id": "H:12", "links": [{"dlc": 77, "hltb": 888}], "confidence": "...", "why": "..."}

For an X (refused HowLongToBeat link) question: is the entry this release after all?
{"id": "X:101:555", "verdict": "same"|"wrong"|"unsure", "confidence": "...", "why": "..."}

For a P (PSN trophy group) question: which add-on of the store (listed) brings this
trophy group, if any (a free update, a season of content, a bundle, or none listed).
{"id": "P:101:001", "addon": "<the add-on's id as listed>"|null, "free_update": true|false|null,
 "confidence": "...", "why": "..."}
"""


def _q(conn: tools.Connection, sql: str, args: tuple = ()) -> list[Row]:
    return conn.execute(sql, args).fetchall()


def _hltb_label(e: Row) -> str:
    year = e["release_world"][:4] if e["release_world"] else (e["name_year"] or "?")
    return f'hltb {e["hltb_id"]} "{e["name"]}" ({e["game_type"] or "?"}, {year})'


def game_cards(conn: tools.Connection) -> list[dict]:
    games = _q(conn, "SELECT * FROM games WHERE merged_into IS NULL ORDER BY game_id")
    versions = defaultdict(list)
    for v in _q(
        conn,
        "SELECT v.*, t.name AS list_name, t.achievements_total AS list_total"
        " FROM versions v LEFT JOIN achievement_list_connectors t"
        " ON t.platform = v.platform AND t.title_id = v.title_id ORDER BY v.version_id",
    ):
        versions[v["game_id"]].append(v)
    entries = {e["hltb_id"]: e for e in _q(conn, "SELECT * FROM hltb_entries")}
    vh = defaultdict(list)
    for r in _q(conn, "SELECT * FROM version_hltb WHERE source <> 'rejected'"):
        vh[r["version_id"]].append(r)
    dlc_links = defaultdict(list)
    for r in _q(
        conn,
        "SELECT d.dlc_id, d.version_id, d.name, d.store_id, d.trophy_group_id, dh.hltb_id"
        " FROM dlc_hltb dh JOIN dlcs d ON d.dlc_id = dh.dlc_id WHERE dh.source <> 'rejected'",
    ):
        dlc_links[r["version_id"]].append(r)
    dlc_counts = {
        r[0]: r[1] for r in _q(conn, "SELECT version_id, COUNT(*) FROM dlcs GROUP BY version_id")
    }
    cards = []
    for g in games:
        vs = versions.get(g["game_id"]) or []
        if not vs:
            continue
        lines = [
            f'GAME {g["game_id"]}: "{g["name"]}"'
            + (f' / "{g["name_ru"]}"' if g["name_ru"] and g["name_ru"] != g["name"] else "")
            + f" · {g['year'] or '?'} · {g['developer'] or '?'} / {g['publisher'] or '?'}"
        ]
        links: list[str] = []
        for v in vs:
            console = console_label(v["store"], v["console"])
            listed = (
                f" · achievement list {v['platform']}:{v['title_id']}"
                f' "{v["list_name"] or "?"}" ({v["list_total"] or "?"} ach.)'
                if v["title_id"]
                else " · no achievement list of ours"
            )
            lines.append(
                f'  release v{v["version_id"]}: {v["store"]} {console} · "{v["name"] or "?"}"'
                f" · {v['release_date'] or '?'} · store kind {v['kind'] or '?'}"
                f" · our role {v['role'] or 'version'}{listed}"
                + (" · stand-in (no store page)" if v["stand_in"] else "")
                + (
                    f" · {dlc_counts[v['version_id']]} DLC known"
                    if v["version_id"] in dlc_counts
                    else ""
                )
            )
            for link in vh.get(v["version_id"], []):
                e = entries.get(link["hltb_id"])
                if e is not None:
                    links.append(f"  v{v['version_id']} → {_hltb_label(e)}")
            for d in dlc_links.get(v["version_id"], []):
                e = entries.get(d["hltb_id"])
                if e is not None:
                    links.append(
                        f'  dlc {d["dlc_id"]} "{d["name"] or "?"}" of v{v["version_id"]} → {_hltb_label(e)}'  # noqa: E501
                    )
        if links:
            lines.append(" HLTB links:")
            lines += links
        cards.append(
            {
                "id": f"G:{g['game_id']}",
                "kind": "game",
                "game_id": g["game_id"],
                "text": "\n".join(lines),
            }
        )
    return cards


def _game_line(conn: tools.Connection, game_id: int) -> str:
    g = conn.execute("SELECT * FROM games WHERE game_id = ?", (game_id,)).fetchone()
    vs = _q(
        conn,
        "SELECT store, console, name, release_date FROM versions WHERE game_id = ?"
        " ORDER BY version_id",
        (game_id,),
    )
    releases = "; ".join(
        f'{console_label(v["store"], v["console"])} "{v["name"]}" {v["release_date"] or "?"}'
        for v in vs
    )
    return f'game {game_id} "{g["name"]}" ({g["year"] or "?"}) — releases: {releases or "none"}'


def missing_questions(cards: list[dict]) -> list[dict]:
    """The same game, asked what the stores sell of it that we lack."""
    return [
        {
            "id": "M:" + card["id"].split(":", 1)[1],
            "kind": "missing",
            "game_id": card["game_id"],
            "text": card["text"].split("\n HLTB links:")[0],
        }
        for card in cards
    ]


def _key(name: str) -> str:
    from bot.services.hltb_match import core, normalize

    return core(normalize(name or ""))


def duplicate_questions(conn: tools.Connection, related: set[frozenset]) -> list[dict]:
    """Games whose names are alike (the same core name, or one the other's start
    plus a word) and that nothing relates: one game stored twice, or a remaster,
    a remake, a part of a series the matcher never put side by side."""
    from bot.services.hltb_match import similarity

    games = _q(
        conn, "SELECT game_id, name FROM games WHERE merged_into IS NULL AND name IS NOT NULL"
    )
    by_word: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for g in games:
        key = _key(g["name"])
        if key:
            by_word[key.split()[0]].append((g["game_id"], key))
    seen: set[frozenset] = set()
    out = []
    for bucket in by_word.values():
        if len(bucket) > 400:  # a word too common to pair on ("the")
            continue
        for i, (a, ka) in enumerate(bucket):
            for b, kb in bucket[i + 1 :]:
                pair = frozenset((a, b))
                if pair in seen or pair in related:
                    continue
                if ka == kb or similarity(ka, kb) >= 0.85:
                    seen.add(pair)
                    out.append(
                        {
                            "id": f"D:{min(a, b)}:{max(a, b)}",
                            "kind": "duplicate",
                            "games": [min(a, b), max(a, b)],
                            "text": f"FIRST: {_game_line(conn, min(a, b))}\n"
                            f"SECOND: {_game_line(conn, max(a, b))}",
                        }
                    )
    return out


def edition_questions(conn: tools.Connection) -> list[dict]:
    rows = _q(
        conn,
        "SELECT DISTINCT v.game_id, e.edition_id, e.store, e.name, e.kind FROM editions e"
        " JOIN edition_items i ON i.edition_id = e.edition_id"
        " JOIN versions v ON v.version_id = i.version_id WHERE v.game_id IS NOT NULL"
        # Only a game's own editions: a bundle of several games, a game
        # thrown in, a pack of add-ons are not asked about.
        f" AND {OWN_EDITION}"
        " ORDER BY v.game_id, e.edition_id",
    )
    by_game: dict[int, list] = defaultdict(list)
    for r in rows:
        by_game[r["game_id"]].append(r)
    out = []
    for game_id, editions in by_game.items():
        lines = [_game_line(conn, game_id), " editions:"]
        for e in editions[:40]:
            items = _q(
                conn,
                "SELECT name, item_kind FROM edition_items WHERE edition_id = ? ORDER BY is_primary DESC",  # noqa: E501
                (e["edition_id"],),
            )
            holds = "; ".join(f"{i['name'] or '?'} ({i['item_kind']})" for i in items[:12])
            lines.append(
                f'  edition {e["edition_id"]}: {e["store"]} "{e["name"] or "?"}"'
                f" · our kind {e['kind'] or '?'} · holds: {holds or '?'}"
            )
        out.append({"id": f"E:{game_id}", "kind": "editions", "text": "\n".join(lines)})
    return out


def dlc_hltb_questions(conn: tools.Connection) -> list[dict]:
    rows = _q(
        conn,
        "SELECT DISTINCT v.game_id, vh.hltb_id FROM version_hltb vh"
        " JOIN versions v ON v.version_id = vh.version_id"
        " WHERE vh.source <> 'rejected' AND v.game_id IS NOT NULL"
        " AND EXISTS (SELECT 1 FROM hltb_entries c WHERE c.parent_hltb_id = vh.hltb_id)",
    )
    out = []
    for r in rows:
        children = _q(
            conn,
            "SELECT * FROM hltb_entries WHERE parent_hltb_id = ?"
            " ORDER BY release_world NULLS FIRST, name",
            (r["hltb_id"],),
        )
        dlcs = _q(
            conn,
            "SELECT d.dlc_id, d.name, d.release_date FROM dlcs d JOIN versions v ON v.version_id = d.version_id"  # noqa: E501
            " WHERE v.game_id = ? AND d.name IS NOT NULL AND COALESCE(d.kind, 'dlc') <> 'consumable'"  # noqa: E501
            " AND NOT EXISTS (SELECT 1 FROM dlc_hltb dh WHERE dh.dlc_id = d.dlc_id)"
            " ORDER BY d.release_date NULLS FIRST, d.name NULLS FIRST LIMIT 60",
            (r["game_id"],),
        )
        if not dlcs:
            continue
        lines = [
            _game_line(conn, r["game_id"]),
            f" its HowLongToBeat entry {r['hltb_id']}'s additional content:",
        ]
        lines += [f"  {_hltb_label(c)}" for c in children[:40]]
        lines.append(" our DLC with no entry yet:")
        lines += [f'  dlc {d["dlc_id"]} "{d["name"]}" {d["release_date"] or "?"}' for d in dlcs]
        out.append({"id": f"H:{r['game_id']}", "kind": "dlc_hltb", "text": "\n".join(lines)})
    return out


def refused_questions(conn: tools.Connection) -> list[dict]:
    out = []
    for r in _q(
        conn,
        "SELECT vh.version_id, vh.hltb_id, v.game_id FROM version_hltb vh"
        " JOIN versions v ON v.version_id = vh.version_id WHERE vh.source = 'rejected'",
    ):
        e = conn.execute("SELECT * FROM hltb_entries WHERE hltb_id = ?", (r["hltb_id"],)).fetchone()
        v = conn.execute(
            "SELECT * FROM versions WHERE version_id = ?", (r["version_id"],)
        ).fetchone()
        if e is None or v is None:
            continue
        out.append(
            {
                "id": f"X:{r['version_id']}:{r['hltb_id']}",
                "kind": "refused_hltb",
                "text": f"release v{v['version_id']}: {v['store']} {console_label(v['store'], v['console'])}"  # noqa: E501
                f' "{v["name"]}" {v["release_date"] or "?"} (of {_game_line(conn, r["game_id"])})\n'
                f"refused: {_hltb_label(e)}",
            }
        )
    return out


def relation_questions(conn: tools.Connection) -> list[dict]:
    pairs: dict[tuple[int, int], str] = {}
    for r in _q(conn, "SELECT game_id, related_id, kind FROM game_relations"):
        pairs[(r[0], r[1])] = f"the database says FIRST {r[2]} SECOND"
    for r in _q(
        conn,
        "SELECT a.game_id AS ga, b.game_id AS gb, m.relation, m.p FROM match_pairs m"
        " JOIN versions a ON a.version_id = m.version_id JOIN versions b ON b.version_id = m.other_id"  # noqa: E501
        " WHERE a.game_id IS NOT NULL AND b.game_id IS NOT NULL AND a.game_id <> b.game_id",
    ):
        key = (r["ga"], r["gb"])
        if key not in pairs and (key[1], key[0]) not in pairs:
            pairs[key] = f'the model is unsure (it leans to "{r["relation"]}")'
    out = []
    for (a, b), said in pairs.items():
        out.append(
            {
                "id": f"R:{a}:{b}",
                "kind": "relation",
                "games": [a, b],
                "text": f"FIRST: {_game_line(conn, a)}\nSECOND: {_game_line(conn, b)}\n({said})",
            }
        )
    return out


def series_questions(conn: tools.Connection) -> list[dict]:
    out = []
    for s in _q(conn, "SELECT * FROM series WHERE merged_into IS NULL ORDER BY series_id"):
        members = _q(
            conn,
            "SELECT g.game_id, g.name, g.year FROM game_series gs JOIN games g ON g.game_id = gs.game_id"  # noqa: E501
            " WHERE gs.series_id = ? AND COALESCE(gs.member, 1) = 1 AND g.merged_into IS NULL"
            " ORDER BY g.year NULLS FIRST, g.name",
            (s["series_id"],),
        )
        if not members:
            continue
        lines = [f'SERIES {s["series_id"]}: "{s["name"]}"']
        lines += [f'  game {m["game_id"]}: "{m["name"]}" ({m["year"] or "?"})' for m in members]
        out.append({"id": f"S:{s['series_id']}", "kind": "series", "text": "\n".join(lines)})
    return out


def psn_group_questions(conn: tools.Connection) -> list[dict]:
    out = []
    groups = _q(
        conn,
        "SELECT d.version_id, d.trophy_group_id, d.name, v.name AS game, v.console, v.title_id,"
        " (SELECT total FROM title_groups tg WHERE tg.title_id = v.title_id"
        "  AND tg.group_id = d.trophy_group_id) AS total"
        " FROM dlcs d JOIN versions v ON v.version_id = d.version_id"
        " WHERE d.trophy_group_id IS NOT NULL ORDER BY d.version_id, d.trophy_group_id",
    )
    for g in groups:
        addons = _q(
            conn,
            "SELECT store_id, name, release_date FROM dlcs WHERE version_id = ? AND store_id IS NOT NULL"  # noqa: E501
            " ORDER BY release_date NULLS FIRST, name NULLS FIRST",
            (g["version_id"],),
        )
        lines = [
            f'PSN game "{g["game"]}" ({g["console"]}), trophy group {g["trophy_group_id"]}:'
            f' "{g["name"] or "?"}" ({g["total"] or "?"} trophies)',
            "  add-ons sold for it:" if addons else "  no add-ons known for it",
        ]
        lines += [
            f'   {a["store_id"]} · "{a["name"] or "?"}" · {a["release_date"] or "?"}'
            for a in addons
        ]
        out.append(
            {
                "id": f"P:{g['version_id']}:{g['trophy_group_id']}",
                "kind": "psn_group",
                "text": "\n".join(lines),
            }
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    tools.add_arguments(parser)
    parser.add_argument("--out", required=True)
    parser.add_argument("--per-file", type=int, default=150)
    parser.add_argument(
        "--sample",
        type=int,
        default=0,
        help="a trial: this many questions of each kind, chosen at random, in one file",
    )
    parser.add_argument("--seed", type=int, default=20261016)
    args = parser.parse_args()
    conn = tools.connect(schema=args.schema, readonly=True)
    cards = game_cards(conn)
    relations = relation_questions(conn)
    parts = {
        "games": cards,
        "missing": missing_questions(cards),
        "relations": relations,
        "duplicates": duplicate_questions(conn, {frozenset(q["games"]) for q in relations}),
        "series": series_questions(conn),
        "psn_groups": psn_group_questions(conn),
        "editions": edition_questions(conn),
        "dlc_hltb": dlc_hltb_questions(conn),
        "refused_hltb": refused_questions(conn),
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.sample:
        # A trial to compare advisers on (owner, 2026-10-16): every kind, a few
        # dozen each — the games half with several releases, half with one.
        rng = random.Random(args.seed)
        chosen: list[dict] = []
        for part, questions in parts.items():
            if part in ("games", "missing"):
                many = [q for q in questions if q["text"].count("release v") > 1]
                one = [q for q in questions if q["text"].count("release v") == 1]
                half = args.sample // 2
                picked = rng.sample(many, min(len(many), args.sample - half))
                picked += rng.sample(one, min(len(one), half))
            else:
                picked = rng.sample(questions, min(len(questions), args.sample))
            chosen += picked
            print(f"{part}: {len(picked)} of {len(questions)}")
        name = "trial.txt"
        lf = "\n"
        body = [INSTRUCTIONS, f"{lf}QUESTIONS ({len(chosen)}, file {name}):"]
        body += [f"{lf}id: {q['id']}{lf}{q['text']}" for q in chosen]
        (out / name).write_text(lf.join(body) + lf, encoding="utf-8", newline=lf)
        (out / "trial_questions.json").write_text(
            json.dumps(
                [{k: v for k, v in q.items() if k != "text"} | {"file": name} for q in chosen],
                ensure_ascii=False,
            ),
            "utf-8",
        )
        print(f"{len(chosen)} questions in {out / name}")
        return 0
    index: list[dict] = []
    n = 0
    for part, questions in parts.items():
        for start in range(0, len(questions), args.per_file):
            n += 1
            chunk = questions[start : start + args.per_file]
            name = f"{n:02d}_{part}.txt"
            body = [INSTRUCTIONS, f"\nQUESTIONS ({len(chunk)}, file {name}):"]
            for q in chunk:
                body.append(f"\nid: {q['id']}\n{q['text']}")
                index.append({k: v for k, v in q.items() if k != "text"} | {"file": name})
            (out / name).write_text("\n".join(body) + "\n", encoding="utf-8", newline="\n")
        print(f"{part}: {len(questions)} questions")
    (out / "questions.json").write_text(json.dumps(index, ensure_ascii=False), "utf-8")
    print(f"{n} files in {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
