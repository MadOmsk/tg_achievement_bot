"""The one SQL fragment that answers "whose achievement is this row" (#52).

`seen_achievements` is keyed by the account that earned a row, not by the
person who happened to have that account linked — so a person's achievements
are *the rows of the accounts they hold right now*, resolved through
`account_links`. Written once here because every statistic asks the same
question, and because an answer copied into twenty queries is an answer that
will eventually disagree with itself; the naming chains (#51) had exactly
that failure a week earlier.

Two consequences fall out of this join and are both intended:

- An account nobody has linked is invisible everywhere. Its rows are still
  there, waiting for whoever links it next.
- An account that changes hands takes its history with it, retroactively.
  A summary already posted will recompute differently. Accepted by the
  project owner — the alternative is a person keeping numbers earned on an
  account that is no longer theirs.

Multi-account (#10) needs no change here: a person with two active links on
one platform simply matches twice.
"""

from __future__ import annotations

# Joins `seen_achievements s` to the person who currently owns each row.
# `account_platform` is GENERATED on the table, so both Xbox generations
# resolve to the single `xbox` account without the caller knowing.
OWNED_BY_PERSON = (
    "JOIN account_links al ON al.platform = s.account_platform"
    "   AND al.external_id = s.xuid AND al.is_active = 1 "
)

# The same thing as a subquery, for statements that cannot take a join —
# UPDATE/DELETE, and any SELECT whose shape would change if a join were
# added to it.
OWNED_BY_PERSON_EXISTS = (
    "EXISTS (SELECT 1 FROM account_links al"
    "        WHERE al.tg_id = ? AND al.is_active = 1"
    "          AND al.platform = seen_achievements.account_platform"
    "          AND al.external_id = seen_achievements.xuid) "
)


def active_account(alias: str, platform: str, *, on: str = "u.tg_id") -> str:
    """The two LEFT JOINs that reach one platform's *currently linked*
    account for a person, exposed under `alias` so a query can keep reading
    `alias.display_name` the way it read `platform_links.display_name`
    before #52.

    Two joins rather than one because who has an account and what the
    account is are now separate facts; `is_active` is the whole point — an
    account somebody used to hold must contribute nothing.
    """
    link = f"{alias}_link"
    return (
        f"LEFT JOIN account_links {link} ON {link}.tg_id = {on}"
        f"   AND {link}.platform = '{platform}' AND {link}.is_active = 1 "
        f"LEFT JOIN accounts {alias} ON {alias}.platform = {link}.platform"
        f"   AND {alias}.external_id = {link}.external_id "
    )


# `users` holds only the Telegram identity since #52's cleanup step: an Xbox
# account is an `accounts` row like any other, reached through the same active
# link. Every query that used to read u.xuid / u.gamertag / u.gamerscore joins
# this instead and reads xb.external_id / xb.secondary_name / xb.gamerscore.
#
# The two nicknames map the way the naming chain (#51) wants them:
#   xb.display_name   -> the modern gamertag (what to show)
#   xb.secondary_name -> the classic one (what profile links are built from)
XBOX_ACCOUNT = (
    "LEFT JOIN account_links xb_link ON xb_link.tg_id = u.tg_id"
    "   AND xb_link.platform = 'xbox' AND xb_link.is_active = 1 "
    "LEFT JOIN accounts xb ON xb.platform = xb_link.platform"
    "   AND xb.external_id = xb_link.external_id "
)

# The same columns, aliased back to the names every row-mapper already reads.
XBOX_COLUMNS = (
    "xb.external_id AS xuid, xb.display_name AS gamertag_modern,"
    "       xb.secondary_name AS gamertag, xb.gamerscore "
)


# ------------------------------------------------------- when it was earned (#69)
#
# Two questions, one answer each, written once here for the same reason
# OWNED_BY_PERSON is: sixteen copies of a date rule will eventually disagree.


def earned_at(prefix: str = "s.") -> str:
    """When this row was earned, as well as it can be known.

    `created_at` stands in when the platform gave no usable time — Microsoft
    sends a placeholder date for some Xbox 360 achievements, which the parser
    discards (services/xbox/models.py). Those rows still count (owner
    decision, 2026-09-13): the stored column keeps its NULL, only what is
    read carries the fallback.
    """
    return f"COALESCE({prefix}unlocked_at, {prefix}created_at)"


def earned_date_is_real(prefix: str = "s.") -> str:
    """Whether `earned_at` above is worth believing for this row.

    It is not, in exactly one case: a backfill row with no platform
    timestamp. Its `created_at` is when the one-off import ran, which has no
    relationship at all to when the achievement was earned — that is #69's
    whole mechanism, a freshly linked library reading as "played this month"
    (real production data: 767 achievements across 15 games for somebody who
    had earned none of it). For a live-polled row the fallback is honest: the
    poller sees an unlock within minutes to hours of it happening.

    Deliberately **not** `is_backfill = 0` on its own, which was the first
    attempt and failed the other way — it also threw away backfill rows the
    platform itself had dated, and a person's Steam and Xbox games vanished
    from /stats entirely. The flag means "do not publish", not "did not
    happen" (services/stats.py); it earns a say here only where there is no
    date to believe instead.
    """
    return f"({prefix}unlocked_at IS NOT NULL OR {prefix}is_backfill = 0)"


def earned_since(prefix: str = "s.") -> str:
    """The window filter both of the above compose into: one `?`, bound to
    the start of the window."""
    return f"{earned_date_is_real(prefix)} AND {earned_at(prefix)} >= ?"


# --------------------------------------------------------------- names (#61)

# The caches that hold a name in both languages, joined to a `seen_achievements
# s` (and its `titles t`). A list renders from SQL rather than through the
# publisher's own localization pass, so without these joins /recent, /stats'
# game list and the monthly "Игры за месяц" showed the language the platform
# happened to answer in while the notification beside them showed the chat's.
NAME_CACHE_JOIN = (
    "LEFT JOIN achievement_name_cache nc ON nc.platform = s.platform"
    "   AND nc.title_id = s.title_id AND nc.achievement_id = s.achievement_id "
)

# Selected rather than resolved in SQL: picking with a CASE would mean
# threading the locale through as a bound parameter in the middle of every
# query's own parameter list, which is exactly the sort of thing that breaks
# silently when somebody adds a WHERE clause. The choice is one function,
# below.
LOCALIZED_NAME_COLUMNS = "nc.name_ru AS name_ru, nc.name_en AS name_en"
LOCALIZED_TITLE_COLUMNS = "t.name_ru AS game_ru, t.name_en AS game_en"


def pick_name(
    locale: str, name_ru: str | None, name_en: str | None, stored: str | None
) -> str | None:
    """The asked-for language, then the other one, then whatever was stored.

    Same order as the render path uses for a published card
    (services/descriptions_view.py) — a name is never translated, so "the
    other language" is the platform's own string too, and better than nothing.
    """
    wanted, other = (name_en, name_ru) if locale == "en" else (name_ru, name_en)
    for candidate in (wanted, other, stored):
        if candidate and candidate.strip():
            return candidate
    return stored
