"""A database file opened outside the bot, with its games file (#229).

Scripts and the catalog viewer read and copy databases with `sqlite3`
directly. Since the catalog lives in a file of its own, attached as `games`,
they open a database here: the games file it names in `app_settings` is
attached too (read-only when the database is), so every query of theirs sees
both, as the bot does. A copy is made of both files, the copy naming its own
games copy.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from bot.db.repo._games_db import GAMES, GAMES_DB_KEY


def games_of(conn: sqlite3.Connection) -> Path | None:
    """The games file this database names, if any."""
    try:
        row = conn.execute(
            "SELECT value FROM main.app_settings WHERE key = ?", (GAMES_DB_KEY,)
        ).fetchone()
    except sqlite3.OperationalError:  # no app_settings: a bare file
        return None
    return Path(row[0]) if row and row[0] else None


def _uri(path: Path) -> str:
    return f"file:{Path(path).as_posix()}?mode=ro"


def connect(path: Path | str, *, readonly: bool = False, **kwargs) -> sqlite3.Connection:
    """`sqlite3.connect`, with the games file attached when there is one."""
    path = Path(path)
    if readonly:
        conn = sqlite3.connect(_uri(path), uri=True, **kwargs)
    else:
        conn = sqlite3.connect(path, **kwargs)
    games = games_of(conn)
    if games is not None:
        if not games.exists():
            conn.close()
            raise FileNotFoundError(f"{path} keeps its games in {games}, not found")
        target = _uri(games) if readonly else str(games)
        conn.execute(f"ATTACH DATABASE ? AS {GAMES}", (target,))
    return conn


def copy_of(target: Path) -> Path:
    """Where a copy's games file goes: beside it."""
    return target.with_name(target.stem + ".games" + target.suffix)


def backup(path: Path | str, target: Path | str) -> Path:
    """A copy of the database (`sqlite3`'s backup, never `cp`: WAL), and of
    its games file beside it; the copy names its own games copy, so it opens
    whole and never reaches into the live catalog."""
    path, target = Path(path), Path(target)
    source = sqlite3.connect(_uri(path), uri=True)
    copy = sqlite3.connect(target)
    try:
        source.backup(copy)
        games = games_of(source)
        if games is not None:
            games_source = sqlite3.connect(_uri(games), uri=True)
            games_copy = sqlite3.connect(copy_of(target))
            try:
                games_source.backup(games_copy)
            finally:
                games_copy.close()
                games_source.close()
            copy.execute(
                "UPDATE app_settings SET value = ? WHERE key = ?",
                (str(copy_of(target).resolve()), GAMES_DB_KEY),
            )
            copy.commit()
    finally:
        copy.close()
        source.close()
    return target


async def open_database(path: Path | str, *, readonly: bool = False):
    """A `Database` on the file as it is — no bring-up, no migration of a
    running bot's file —, its games file attached. Read-only when asked."""
    import aiosqlite

    from bot.db.repo import Database

    path = Path(path)
    database = Database(path)
    if readonly:
        conn = await aiosqlite.connect(_uri(path.resolve()), uri=True)
    else:
        conn = await aiosqlite.connect(path)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA busy_timeout = 30000")
    cursor = await conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'app_settings'"
    )
    if await cursor.fetchone() is not None:
        cursor = await conn.execute("SELECT value FROM app_settings WHERE key = ?", (GAMES_DB_KEY,))
        row = await cursor.fetchone()
        if row and row[0]:
            games = Path(row[0])
            # A local stat before the bot serves anything: no event loop to spare.
            if not games.exists():  # noqa: ASYNC240
                await conn.close()
                raise FileNotFoundError(f"{path} keeps its games in {games}, not found")
            target = _uri(games.resolve()) if readonly else str(games)  # noqa: ASYNC240
            await conn.execute(f"ATTACH DATABASE ? AS {GAMES}", (target,))
            database.games_path = games
    database._conn = conn
    return database
