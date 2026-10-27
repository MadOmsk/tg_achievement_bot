"""Lists known only by their id take a name another copy learned."""

import sqlite3

from scripts.restore_list_names import names_from, restore


def test_a_list_named_by_its_id_takes_the_name_another_copy_knows() -> None:
    source = sqlite3.connect(":memory:")
    source.executescript(
        "CREATE TABLE titles (platform TEXT, title_id TEXT, name TEXT);"
        "INSERT INTO titles VALUES ('xbox_modern', '2046213688', 'Weird West'),"
        " ('xbox_modern', '7', '7'), ('steam', '9', 'Other name');"
    )
    db = sqlite3.connect(":memory:")
    db.executescript(
        "CREATE TABLE achievement_list_connectors (platform TEXT, title_id TEXT, name TEXT);"
        "INSERT INTO achievement_list_connectors VALUES"
        " ('xbox_modern', '2046213688', '2046213688'), ('xbox_modern', '7', '7'),"
        " ('steam', '9', 'Its own name');"
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
