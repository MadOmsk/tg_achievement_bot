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
