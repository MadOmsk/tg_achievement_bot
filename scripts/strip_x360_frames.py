"""Cut the console's frame off the Xbox 360 art already kept (owner,
2026-10-28; `bot/services/x360_frame.py`): the lists' covers
(`covers/xbox_360-*`) in place, and each 360 game's poster in `covers/art/`
(its list's icon, or its store product's poster) kept again under its marked
address, from the file already there — no request. A picture with no frame,
or one cut before, is left alone, so it can run again. Beside a running bot:
every write is a rename, and the databases are only read.

    .venv/Scripts/python.exe -X utf8 -m scripts.strip_x360_frames --media /srv/unlocked-media \
        --schema prod --apply
"""

from __future__ import annotations

import argparse
from pathlib import Path

from bot.db import tools
from bot.services import covers, game_art, media, x360_frame
from bot.services.achievement_icons import detect_mime
from bot.services.game_page import https


def _replace(path: Path, data: bytes) -> None:
    temporary = path.with_name(path.name + ".part")
    temporary.write_bytes(data)
    temporary.replace(path)


def strip_covers(apply: bool) -> tuple[int, int]:
    seen = cut = 0
    for path in sorted(covers.cover_dir().glob("xbox_360-*")):
        if path.suffix == ".part":
            continue
        seen += 1
        data = path.read_bytes()
        stripped = x360_frame.strip(data)
        if stripped is not data:
            cut += 1
            if apply:
                _replace(path, stripped)
    return seen, cut


def list_icons(schema: str) -> set[str]:
    # Read-only: the database may belong to a running bot.
    with tools.connect(schema=schema, readonly=True) as conn:
        rows = conn.execute(
            "SELECT icon_url FROM achievement_list_connectors"
            " WHERE platform = 'xbox_360' AND icon_url IS NOT NULL"
        ).fetchall()
        # A 360 game's backward-compatible product: its store poster is
        # framed too (`game_page.store_art` marks it).
        rows += conn.execute(
            "SELECT DISTINCT media::jsonb->>'poster' FROM versions"
            " WHERE store = 'xbox' AND console = '360' AND stand_in = 0 AND media IS NOT NULL"
        ).fetchall()
    return {https(row[0]) for row in rows if row[0]}


def strip_posters(urls: set[str], apply: bool) -> tuple[int, int]:
    found = cut = 0
    for url in sorted(urls):
        old = game_art.cached(url)
        marked = x360_frame.mark(url, "xbox_360")
        if old is None or game_art.cached(marked) is not None:
            continue
        found += 1
        data = old.read_bytes()
        stripped = x360_frame.strip(data)
        cut += stripped is not data
        if apply:
            ext = detect_mime(stripped)[1]
            path = game_art.art_dir() / game_art.file_key(marked)[:2]
            path.mkdir(parents=True, exist_ok=True)
            _replace(path / f"{game_art.file_key(marked)}{ext}", stripped)
    return found, cut


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--media", type=Path, default=None, help="MEDIA_DIR; data/ when unset")
    parser.add_argument("--schema", action="append", default=[], help="a bot's schema")
    parser.add_argument("--apply", action="store_true", help="write; a dry run without it")
    args = parser.parse_args()
    media.configure(args.media)

    seen, cut = strip_covers(args.apply)
    print(f"covers: {seen} 360 covers, {cut} with a frame")
    urls: set[str] = set()
    for schema in args.schema:
        urls |= list_icons(schema)
    found, cut = strip_posters(urls, args.apply)
    print(f"posters: {len(urls)} 360 list icons, {found} to keep marked, {cut} of them framed")
    if not args.apply:
        print("dry run: nothing written (--apply writes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
