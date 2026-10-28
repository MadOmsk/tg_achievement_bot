"""One games database for prod and the test server (owner, 2026-10-28; #229).

The catalog — what is known about games, not about people — lives in a file
of its own that both bots `ATTACH` as `games`. SQLite resolves a table name
nobody qualified by looking in `main` first, then in the attached files, so
every query stays as it was: the catalog's tables are simply not in `main`.

Only what *creates* something has to say where: a table, an index or a
trigger on a catalog table is made in `games` (`placed`), for schema.sql, the
migrations and the indexes made after them alike. One schema.sql and one
migration line stay the source of both files; each server applies the
migrations to its own `main`, so a migration touching the catalog runs
against the shared file once per server — it must be idempotent and only
add (CLAUDE.md, Data model).

Where a bot's games file is, is the bot's own `app_settings`
(`GAMES_DB_KEY`), written by `scripts/games_db.py` when the catalog is moved
out — never guessed: a script opening a database finds the same file the bot
uses, and a database with no such key is one file, as before.
"""

from __future__ import annotations

import re

GAMES = "games"
GAMES_DB_KEY = "games_db_path"

# The catalog: facts about games, achievement lists and the stores, shared by
# every server. People, their accounts, what they earned, chats and the
# app's own settings stay each server's (`main`).
CATALOG_TABLES = frozenset(
    {
        # achievement lists and their achievements
        "achievement_list_connectors",
        "title_groups",
        "title_achievements",
        "steam_schema_cache",
        "steam_rarity_cache",
        # Steam's side of a game, guides
        "steam_apps",
        "title_guide_reads",
        "game_patches",
        "guide_channels",
        "guide_videos",
        "guide_marks",
        # the games catalog (#147)
        "versions",
        "dlcs",
        "editions",
        "edition_items",
        "games",
        "game_relations",
        "series",
        "game_series",
        "match_decisions",
        "label_log",
        "match_pairs",
        "adviser_labels",
        "match_weights",
        "hltb_entries",
        "hltb_platform_times",
        "hltb_platform_groups",
        "hltb_entry_platforms",
        "hltb_review_scores",
        "hltb_related",
        "version_hltb",
        "dlc_hltb",
        "source_payloads",
        "fetch_state",
        "octopus_queue",
    }
)

_COMMENT = r"(?:\s|--[^\n]*\n|/\*.*?\*/)*"
_NAME = r"[\"`]?(\w+)[\"`]?"
_CREATE_TABLE = re.compile(
    rf"^({_COMMENT}CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?){_NAME}", re.I | re.S
)
_CREATE_INDEX = re.compile(
    rf"^({_COMMENT}CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?){_NAME}"
    rf"(\s+ON\s+){_NAME}",
    re.I | re.S,
)
_CREATE_TRIGGER = re.compile(
    rf"^({_COMMENT}CREATE\s+TRIGGER\s+(?:IF\s+NOT\s+EXISTS\s+)?){_NAME}"
    rf"(.*?\bON\s+){_NAME}",
    re.I | re.S,
)


def placed(statement: str, attached: bool) -> str:
    """`statement` made where its table lives: in `games` when it creates a
    table, an index or a trigger of the catalog and the games file is
    attached; untouched otherwise."""
    if not attached:
        return statement
    if found := _CREATE_TABLE.match(statement):
        if found[2].lower() in CATALOG_TABLES:
            return f"{found[1]}{GAMES}.{found[2]}{statement[found.end() :]}"
        return statement
    if found := _CREATE_INDEX.match(statement):
        if found[4].lower() in CATALOG_TABLES:
            return f"{found[1]}{GAMES}.{found[2]}{found[3]}{found[4]}{statement[found.end() :]}"
        return statement
    if found := _CREATE_TRIGGER.match(statement):
        if found[4].lower() in CATALOG_TABLES:
            return f"{found[1]}{GAMES}.{found[2]}{found[3]}{found[4]}{statement[found.end() :]}"
    return statement
