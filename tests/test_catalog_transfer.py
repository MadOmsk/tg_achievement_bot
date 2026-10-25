"""Carrying the games catalog between databases (scripts/catalog_transfer.py)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from bot.db.repo import Database, Repo
from bot.services.stores import StoreVersion
from scripts.catalog_transfer import export, import_


async def _db(path: Path, versions: list[tuple[str, str, str | None]]) -> list[int]:
    """A database with these versions (product, name, the list's title id)."""
    database = await Database(path).connect()
    try:
        repo = Repo(database)
        ids = []
        for product, name, title_id in versions:
            ids.append(
                await repo.save_version(
                    StoreVersion(store="steam", product_id=product, console="steam", name=name),
                    platform="steam" if title_id else None,
                    title_id=title_id,
                )
            )
        return ids
    finally:
        await database.close()


async def test_the_catalog_travels_and_a_list_it_lacks_keeps_its_version(tmp_path) -> None:
    source, target, file = tmp_path / "dev.db", tmp_path / "prod.db", tmp_path / "catalog.db"
    await _db(source, [("10", "Portal", "10"), ("20", "Portal 2", "20")])
    await _db(target, [("20", "Portal 2", "20"), ("30", "Half-Life", "30")])
    conn = sqlite3.connect(source)
    conn.execute(
        "INSERT INTO match_weights (weights, labels, created_at, active)"
        " VALUES ('{}', 1, '2026-10-25', 1)"
    )
    conn.commit()
    conn.close()

    export(source, file, ("versions", "match_weights"))
    kept = import_(target, file, dry_run=False)

    conn = sqlite3.connect(target)
    products = sorted(r[0] for r in conn.execute("SELECT product_id FROM versions"))
    assert products == ["10", "20", "30"]  # the file's two, and Half-Life kept
    assert len(kept) == 1
    assert conn.execute("SELECT active FROM match_weights").fetchall() == [(1,)]
    assert conn.execute("SELECT COUNT(*) FROM users").fetchone() == (0,)
    conn.close()
    assert list(tmp_path.glob("prod-pre-catalog-*.db"))  # a backup was made first


async def test_a_dry_run_writes_nothing(tmp_path) -> None:
    source, target, file = tmp_path / "dev.db", tmp_path / "prod.db", tmp_path / "catalog.db"
    await _db(source, [("10", "Portal", "10")])
    await _db(target, [("30", "Half-Life", "30")])
    export(source, file, ("versions",))
    assert import_(target, file, dry_run=True) == []
    conn = sqlite3.connect(target)
    assert [r[0] for r in conn.execute("SELECT product_id FROM versions")] == ["30"]
    conn.close()
