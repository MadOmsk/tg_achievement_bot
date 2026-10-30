"""One small catalog with a row of every kind the operator's tools read."""

from __future__ import annotations

import json
import zlib

NOW = "2026-10-15T00:00:00+00:00"


async def seed_catalog(conn) -> None:
    await conn.execute(
        "INSERT INTO games (game_id, name, year, last_year, kind, kind_source, name_source,"
        " developer, publisher, more_developers, merged_into, created_at, updated_at) VALUES"
        " (1, 'Control', 2019, 2021, 'game', 'auto', 'auto', 'Remedy', '505', 1, NULL, ?, ?),"
        " (2, 'Control Remastered', 2021, NULL, 'game', 'auto', 'auto', NULL, NULL, 0, NULL, ?, ?),"
        " (3, 'Control Collection', NULL, NULL, 'compilation', 'manual', 'auto', NULL, NULL, 0,"
        "  NULL, ?, ?),"
        " (4, 'Old Control', 2019, NULL, 'game', 'auto', 'auto', NULL, NULL, 0, 1, ?, ?)",
        (NOW,) * 8,
    )
    media = json.dumps({"cover": "https://x/cover.png", "hero": "http://x/hero.png"})
    versions = [
        # id, store, product, console, platform, title, name, date, game, role, of, stand_in, media
        (10, "xbox", "P1", "series", "xbox_modern", "77", "Control", "2019-08-27", 1, "version",
         None, 0, media),
        (11, "steam", "110", "steam", "steam", "110", "Control", None, 1, "version", None, 0, None),
        (12, "psn", "CON1", "ps5", "psn", "NPWR1", "Control Remastered", "2021-02-02", 2, "version",
         None, 0, json.dumps({"poster": "https://x/poster.png"})),
        (13, "xbox", "P2", "pc", None, None, "Control Demo", "2019-01-01", 1, "demo", 10, 0, None),
        (14, "list", "88", "360", "xbox_360", "88", "Control Collection", None, 3, "version", None,
         1, None),
        (15, "unknown", "99", "pc", None, None, "Nowhere", None, None, None, None, 0, None),
        (16, "steam", "160", "steam", None, None, "Control GOTY", "2020-01-01", 1, "enhanced", 11,
         0, None),
    ]  # fmt: skip
    for v in versions:
        await conn.execute(
            "INSERT INTO versions (version_id, store, product_id, console, platform, title_id,"
            " name, release_date, game_id, role, of_version_id, stand_in, media, store_group,"
            " store_ids, on_sale, updated_at, link_p)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'G1', '[[\"title\", \"77\"]]', 1, ?,"
            " 0.9)",
            (*v, NOW),
        )
    await conn.execute("UPDATE games SET anchor_version_id = 10 WHERE game_id = 1")
    await conn.execute("UPDATE games SET anchor_version_id = 12 WHERE game_id = 2")
    await conn.execute("UPDATE games SET anchor_version_id = 14 WHERE game_id = 3")

    for platform, title, name in (
        ("xbox_modern", "77", "Control"),
        ("steam", "110", "Control"),
        ("psn", "NPWR1", "Control Remastered"),
        ("xbox_360", "88", "Control Collection"),
    ):
        await conn.execute(
            "INSERT INTO achievement_list_connectors (platform, title_id, name, name_en,"
            " cover_path, icon_url, achievements_total, updated_at) VALUES (?, ?, ?, ?, 'c/a.png', 'http://i',"
            " 10, ?)",
            (platform, title, name, name, NOW),
        )
    await conn.execute(
        "INSERT INTO title_achievements (platform, title_id, achievement_id, name_en, listed,"
        " rarity_percent, updated_at) VALUES ('xbox_modern', '77', '1', 'First', 1, 5.5, ?),"
        " ('xbox_modern', '77', '2', NULL, 1, NULL, ?)",
        (NOW, NOW),
    )
    await conn.execute(
        "INSERT INTO title_groups (title_id, group_id, name, total, updated_at)"
        " VALUES ('NPWR1', '001', 'The DLC', 7, ?)",
        (NOW,),
    )
    for subject, source, status, interval in (
        ("xbox_title:77", "xbox", "failed", 7),
        ("hltb:100", "hltb_page", "ok", 30),
        ("xbox:P1:series", "octopus", "ok", 30),
    ):
        await conn.execute(
            "INSERT INTO fetch_state (subject, source, status, interval_days, checked_at,"
            " next_check_at) VALUES (?, ?, ?, ?, ?, ?)",
            (subject, source, status, interval, NOW, NOW),
        )
    for subject, source, body in (
        ("steam_schema:110", "steam_schema", ["First", "Second"]),
        ("hltb:100", "hltb_page", {"a": 1}),
        ("xbox:P1", "xbox_catalog", {"b": 2}),
    ):
        await conn.execute(
            "INSERT INTO source_payloads (subject, source, fetched_at, sha256, payload)"
            " VALUES (?, ?, ?, 'x', ?)",
            (subject, source, NOW, zlib.compress(json.dumps(body).encode())),
        )
    await conn.execute(
        "INSERT INTO octopus_queue (key, reason, due_at, created_at)"
        " VALUES ('game:1', 'viewer', ?, ?)",
        (NOW, NOW),
    )

    await conn.execute(
        "INSERT INTO hltb_entries (hltb_id, name, alias, game_type, parent_hltb_id, comp_main,"
        " comp_plus, comp_100, comp_main_count, review_score, count_comp, release_world, name_year,"
        " page_read_at, developer, checked_at) VALUES"
        " (100, 'Control', 'Ctrl', 'game', NULL, 36000, 50000, 90000, 3, 80, 9, '2019-08-27', NULL,"
        "  ?, 'Remedy', ?),"
        " (101, 'Control: The Foundation', NULL, 'dlc', 100, 3600, 0, 0, 0, 0, 1, NULL, 2020,"
        "  NULL, NULL, ?),"
        " (102, 'Control Remastered', NULL, 'game', NULL, 0, 0, 0, 0, 0, 0, NULL, 2021, NULL,"
        "  NULL, ?)",
        (NOW, NOW, NOW, NOW),
    )
    await conn.execute(
        "INSERT INTO hltb_platform_times (hltb_id, platform, comp_main, count_comp, count_total)"
        " VALUES (100, 'PC', 30000, 4, 10), (100, 'Xbox Series X/S', 30600, 9, NULL)"
    )
    await conn.execute(
        "INSERT INTO hltb_platform_groups (hltb_id, platforms, comp_main, count_comp)"
        " VALUES (100, 'PS4, PS5', 30000, 4), (100, 'One', 30000, NULL)"
    )
    await conn.execute(
        "INSERT INTO hltb_entry_platforms (hltb_id, platform) VALUES (100, 'Xbox'), (100, 'PC')"
    )
    await conn.execute(
        "INSERT INTO hltb_review_scores (hltb_id, score, votes) VALUES (100, 80, 3), (100, 60, 1)"
    )
    await conn.execute("INSERT INTO hltb_related (hltb_id, related_id) VALUES (100, 102)")
    await conn.execute(
        "INSERT INTO version_hltb (version_id, hltb_id, source, score) VALUES"
        " (10, 100, 'auto', 0.8), (11, 100, 'manual', NULL), (12, 102, 'rejected', NULL),"
        " (16, 100, 'auto', 0.99)"
    )
    await conn.execute(
        "INSERT INTO dlcs (dlc_id, version_id, store_id, name, kind, release_date,"
        " trophy_group_id, updated_at) VALUES"
        " (20, 10, 'D1', 'The Foundation', 'dlc', '2020-03-26', NULL, ?),"
        " (21, 13, 'D1', 'The Foundation', 'dlc', NULL, NULL, ?),"
        " (22, 12, NULL, 'The DLC', NULL, NULL, '001', ?),"
        " (23, 12, 'EP1-CUSA', NULL, NULL, NULL, NULL, ?),"
        " (24, 11, '240', 'Control: The Foundation', NULL, NULL, NULL, ?),"
        " (25, 11, '250', 'Control: The Foundation', NULL, NULL, NULL, ?)",
        (NOW,) * 6,
    )
    await conn.execute(
        "INSERT INTO dlc_hltb (dlc_id, hltb_id, source) VALUES (20, 101, 'auto'),"
        " (21, 101, 'rejected')"
    )
    for edition, store_id, scope, name, kind in (
        (30, "E1", "edition", "Control Ultimate", "ultimate"),
        (31, "E2", "bundle", "Remedy Bundle", None),
        (32, "E3", "edition", None, None),
        (33, "E4", "addon_pack", "Expansion Pass", None),
    ):
        await conn.execute(
            "INSERT INTO editions (edition_id, store, store_id, scope, name, kind, first_seen_at,"
            " last_seen_at) VALUES (?, 'xbox', ?, ?, ?, ?, ?, ?)",
            (edition, store_id, scope, name, kind, NOW, NOW),
        )
    for edition, store_id, kind, version, role, name, primary in (
        (30, "P1", "game", 10, "main", "Control", 1),
        (30, "D1", "dlc", None, None, "The Foundation", 0),
        (31, "P1", "game", 10, "part", "Control", 0),
        (32, "P1", "game", 10, "bonus", None, 0),
        (33, "D1", "dlc", None, None, None, 0),
    ):
        await conn.execute(
            "INSERT INTO edition_items (edition_id, store_id, item_kind, version_id, role, name,"
            " is_primary) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (edition, store_id, kind, version, role, name, primary),
        )

    await conn.execute(
        "INSERT INTO game_relations (game_id, related_id, kind, source, p, created_at) VALUES"
        " (2, 1, 'remaster_of', 'auto', 0.876, ?), (3, 1, 'contains', 'manual', NULL, ?),"
        " (3, 2, 'contains', 'auto', 0.5, ?)",
        (NOW, NOW, NOW),
    )
    await conn.execute(
        "INSERT INTO series (series_id, name, name_source, merged_into, created_at, updated_at)"
        " VALUES (40, 'Control', 'auto', NULL, ?, ?), (41, 'Old', 'auto', 40, ?, ?),"
        " (42, 'Remedy Verse', 'auto', NULL, ?, ?)",
        (NOW,) * 6,
    )
    await conn.execute(
        "INSERT INTO game_series (game_id, series_id, member, source, p, reason, created_at,"
        " updated_at) VALUES (1, 40, 1, 'auto', 0.876, 'franchise', ?, ?),"
        " (2, 40, 1, 'auto', NULL, NULL, ?, ?), (3, 40, 0, 'manual', 0.5, NULL, ?, ?),"
        " (1, 42, 1, 'advisers', 0.9, NULL, ?, ?)",
        (NOW,) * 8,
    )
    await conn.execute(
        "INSERT INTO match_pairs (version_id, other_id, relation, p, probs, features, model,"
        " scored_at) VALUES"
        " (12, 10, 'remaster_of', 0.6, '{\"remaster_of\": 0.6}', '{\"bias\": 1, \"name\": 1}',"
        "  'm', ?),"
        " (10, 11, 'same', 0.5, '{\"same\": 0.5}', '{}', 'm', ?),"
        " (14, 12, 'contains', 0.3, '{\"contains\": 0.3}', '{}', 'm', ?)",
        (NOW, NOW, NOW),
    )
    await conn.execute(
        "INSERT INTO match_decisions (version_id, other_id, relation, decided_by, decided_at,"
        " features, model) VALUES"
        " (11, 16, 'same', 'viewer', ?, '{\"name\": 1}', 'm'),"
        " (16, 13, 'same', 'claude+gemini', ?, NULL, 'm'),"
        " (11, 13, 'other', 'viewer', ?, NULL, 'm')",
        (NOW, NOW, NOW),
    )
    # The ids above were given by hand: a new row starts past them.
    for table, column in (
        ("games", "game_id"),
        ("versions", "version_id"),
        ("dlcs", "dlc_id"),
        ("editions", "edition_id"),
        ("series", "series_id"),
    ):
        await conn.execute(
            f"SELECT setval(pg_get_serial_sequence('games.{table}', '{column}'), 1000)"
        )
