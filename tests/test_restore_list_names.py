"""Lists known only by their id take a name another copy learned."""

from collections.abc import Iterator

import psycopg
import pytest

from bot.db import tools
from scripts.restore_list_names import names_from, restore


@pytest.fixture
def copies(_db_template: str) -> Iterator[tuple[tools.Connection, tools.Connection]]:
    """Two copies with tables of their own, in schemas nothing else reads: the
    older one's table has the list's former name."""
    with psycopg.connect(_db_template, autocommit=True) as admin:
        admin.execute("DROP SCHEMA IF EXISTS names_source CASCADE")
        admin.execute("DROP SCHEMA IF EXISTS names_target CASCADE")
        admin.execute("CREATE SCHEMA names_source")
        admin.execute("CREATE SCHEMA names_target")
        source = tools.connect(_db_template, schema="names_source")
        db = tools.connect(_db_template, schema="names_target")
        try:
            yield source, db
        finally:
            source.close()
            db.close()
            admin.execute("DROP SCHEMA names_source CASCADE")
            admin.execute("DROP SCHEMA names_target CASCADE")


def test_a_list_named_by_its_id_takes_the_name_another_copy_knows(copies) -> None:
    source, db = copies
    source.execute(
        "CREATE TABLE names_source.achievement_list_connectors"
        " (platform TEXT, title_id TEXT, name TEXT)"
    )
    source.execute(
        "INSERT INTO names_source.achievement_list_connectors VALUES"
        " ('xbox_modern', '2046213688', 'Weird West'),"
        " ('xbox_modern', '7', '7'), ('steam', '9', 'Other name')"
    )
    db.execute(
        "CREATE TABLE names_target.achievement_list_connectors"
        " (platform TEXT, title_id TEXT, name TEXT)"
    )
    db.execute(
        "INSERT INTO names_target.achievement_list_connectors VALUES"
        " ('xbox_modern', '2046213688', '2046213688'), ('xbox_modern', '7', '7'),"
        " ('steam', '9', 'Its own name')"
    )
    done = restore(db, names_from(source))
    assert done == [("xbox_modern", "2046213688", "Weird West")]
    assert db.execute("SELECT name FROM achievement_list_connectors WHERE title_id = '9'"
                      ).fetchone() == ("Its own name",)  # fmt: skip


def test_a_stand_in_is_never_named_by_its_list_id() -> None:
    from bot.services.stores import stand_in_for

    record = {"platform": "xbox_modern", "title_id": "2046213688", "name": "2046213688"}
    assert stand_in_for({**record, "name_en": "Weird West"}).name == "Weird West"
    assert stand_in_for(record).name is None


def test_names_can_come_from_a_dump(tmp_path) -> None:
    from scripts.restore_list_names import names_in

    dump = tmp_path / "names.json"
    dump.write_text('[["xbox_360", "1297287339", "Gears of War 3"]]', "utf-8")
    assert names_in(str(dump)) == {("xbox_360", "1297287339"): "Gears of War 3"}
