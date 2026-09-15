"""The small pieces every screen is built from (#63).

Badges, the platform palette and its labels, the counted-noun helpers, the
per-platform header rows shared by /stats and /panel — the vocabulary of
this interface rather than any one screen of it. Split out of
services/achievements.py, which had grown into three unrelated jobs at
once: these pieces, the notification cards (views/notification.py), and the
publication filter that is not rendering at all and stayed behind.

Every function that produces visible text takes an explicit `locale` and
binds its own translator from it (#48). There is deliberately no
module-level shorthand and no default: these render for a chat the
publisher is looping over, so a locale that could be left out is a locale
that eventually renders one chat's message in another chat's language.
"""

from __future__ import annotations

from html import escape as html_escape

from bot.constants import (
    AchievementBadge,
    Platform,
    PsnTrophyTier,
    platform_display_rank,
)
from bot.db.repo import PlatformLink, Repo
from bot.i18n import gettext, translator
from bot.services.profile_links import link_html, platform_profile_url, xbox_profile_url
from bot.util import humanize_ago, thousands

# that eventually renders one chat's message in another chat's language.

#  Two badges (2026-09-05 style pass) — a diamond for "редкая" (rare), a
#  cup for "обычная" (common).
#  Every achievement gets one or the other,
#  including when there's no rarity_percent to judge by at all (Xbox 360,
#  backfilled rows) — unproven is not "rare", so it defaults to the cup
#  rather than going unbadged (found live: a whole game's worth of
#  achievements with no badge at all read as broken, not as "no data").
RARE_BADGE_MAX_PERCENT = 15.0


def rarity_badge(rarity_percent: float | None) -> str:
    if rarity_percent is not None and rarity_percent <= RARE_BADGE_MAX_PERCENT:
        return AchievementBadge.DIAMOND
    return AchievementBadge.CUP


# PSN's trophy tier — a dimension with no analogue on Xbox/Steam (M-PSN-1's
# design notes, SPEC 9 M-PSN-2), shown *alongside* rarity_badge() above, not
# instead of it: rarity says how many players got it, tier says how much
# Sony itself weighted it — two different questions about the same trophy.
TROPHY_TIER_BADGE = {
    PsnTrophyTier.PLATINUM: AchievementBadge.CUP,
    PsnTrophyTier.GOLD: AchievementBadge.GOLD,
    PsnTrophyTier.SILVER: AchievementBadge.SILVER,
    PsnTrophyTier.BRONZE: AchievementBadge.BRONZE,
}


def trophy_tier_badge(trophy_type: str | None) -> str:
    """Empty for every non-PSN row (trophy_type is always None there) —
    appended, never leaving a stray space for platforms that don't have
    one."""
    return TROPHY_TIER_BADGE.get(trophy_type or "", "")


# The one canonical platform palette (2026-09-05 refactor — chat.py and
# online_view.py used to keep their own, smaller copies with no "xbox_360" key
# at all, so an Xbox 360 game silently got no icon in /stats' games list and
# no colour in presence rows; both now import this one instead). Public
# names, not underscore-prefixed: this module is the home for them, other
# services are allowed to depend on it (only handlers->services is one-way).
PLATFORM_ICON = {
    Platform.XBOX_MODERN: "🟢",
    Platform.XBOX_360: "🟢",
    Platform.STEAM: "⚫",
    Platform.PSN: "🔵",
}
PLATFORM_LABEL_KEYS = {
    Platform.XBOX_MODERN: "achievement-platform-xbox",
    Platform.XBOX_360: "achievement-platform-xbox360",
    Platform.STEAM: "achievement-platform-steam",
    Platform.PSN: "achievement-platform-psn",
}
# Fallback used wherever a platform is unknown or the presence itself is
# offline/no-data (platform_tag() below, /online's own offline rows in
# views/online.py) — grey rather than any platform's own colour.
PLATFORM_ICON_UNKNOWN = "⚪"


def platform_label(platform: str, locale: str) -> str:
    """A platform's own display name. Was a module-level dict built once at
    import time, which stopped being safe the moment a second locale existed
    (#48): the dict would have frozen whichever locale happened to be loaded
    first. These are brand names and read identically in ru and en today, so
    nothing actually changes on screen — but a lookup that is right by
    accident is exactly the kind that breaks on the next locale."""
    _ = translator("achievements", locale)
    key = PLATFORM_LABEL_KEYS.get(platform)
    return _(key) if key else platform


def platform_breakdown_suffix(
    xbox_count: int, steam_count: int, psn_count: int = 0, *, always: bool = False
) -> str:
    """The small "(🟢 3 · ⚫ 5 · 🔵 2)" next to a combined achievement total in
    /stats and /summary (2026-09-05 follow-up) — a parenthetical, not a
    second sort key or a second row: the combined number still leads and
    still sorts, this is purely for reference.

    `psn_count` defaults to 0 rather than being required — added in #32,
    after the combined total it sits next to had already included PSN for
    a while (that sum is a plain `tg_id` group-by, no platform filter) but
    this breakdown's own two `CASE`s had nowhere for a PSN row to land, so
    it silently vanished from here specifically while still counting
    toward the total next to it.

    `always=False` (the default, used by /stats): empty for anyone with
    achievements on only one platform in the window — /stats already spells
    out each connected platform on its own line right above this, so
    repeating the one platform here would just be noise.

    `always=True` (/summary's leaderboard and the daily итог, which share
    _leader_row, poller/daily.py): shows even for a single platform — a
    leaderboard has no per-platform header to lean on, so "(🟢 3)" is the
    only thing on the row saying which platform those achievements came
    from at all. Still empty when there's nothing to show at all (a
    zero-achievement row)."""
    # Xbox, PlayStation, Steam — the one display order for a platform list
    # (constants.platform_display_rank). The argument order is the older
    # (xbox, steam, psn) one every caller already passes; only what the reader
    # sees is ordered here.
    parts = []
    if xbox_count:
        parts.append(f"{PLATFORM_ICON[Platform.XBOX_MODERN]} {xbox_count}")
    if psn_count:
        parts.append(f"{PLATFORM_ICON[Platform.PSN]} {psn_count}")
    if steam_count:
        parts.append(f"{PLATFORM_ICON[Platform.STEAM]} {steam_count}")
    if not parts or (len(parts) < 2 and not always):
        return ""
    return " (" + " · ".join(parts) + ")"


def score_suffix(score: int) -> str:
    """The "(+N G)" tail, or nothing at all for a zero score (2026-09-08
    preview round, user request) — a Steam row's gamerscore is always 0
    (Steam has no such concept), and "(+0 G)" on every single line just
    reads as noise. Same "if nonzero" shape format_single()'s own tail
    already uses for one achievement's gamerscore, generalized for /stats'
    today/month lines and its per-game list, which built this suffix
    unconditionally until now."""
    return f" (+{thousands(score)} G)" if score else ""


def platform_tag(platform: str, locale: str) -> str:
    """SPEC 9, M-Steam-2e — which platform an achievement came from, right
    in the message itself, not just inferred from context. Found live: a
    Steam achievement arriving with no platform mention at all reads the
    same as any other message, easy to miss."""
    _ = translator("achievements", locale)
    icon = PLATFORM_ICON.get(platform, PLATFORM_ICON_UNKNOWN)
    label = _(
        PLATFORM_LABEL_KEYS.get(platform, "achievement-platform-unknown"),
        platform=platform,
    )
    return f"{icon} {label}"


#  Platforms with no rarity data at all — the rarity filter can't decide
#  "rare" for them, so 'rare' mode falls back to showing everything, the
#  same way 'all' mode would (SPEC 5.5, 1.4). Currently only Xbox 360
#  (contract 1 never carries a rarity block); Steam is NOT here — it has a
#  real rarity_percent (GetGlobalAchievementPercentagesForApp, M-Steam-2b),
#  so it goes through the ordinary rarity check like modern Xbox.
def plural_achievements(count: int, locale: str) -> str:
    """ "Достижение" everywhere, not "ачивка" — the two used to appear
    side by side across different messages (2026-09-05 terminology pass);
    "ач." stays fine as a space-saving abbreviation where one is needed,
    just not the full colloquial word.

    The plural form itself is Fluent's job, not this function's (#48): it
    picks the CLDR category for whichever locale the .ftl belongs to, so a
    second language brings its own rules with it instead of being handed
    Russian's one/few/many. `count` selects, `pretty` displays — selecting
    on the thousands-separated string would never match a category."""
    _ = translator("achievements", locale)
    return _("achievement-plural", count=count, pretty=thousands(count))


def plural_trophies(count: int, locale: str) -> str:
    """PSN's own word — format_digest's header (Follow-up 2026-09-06), and
    /stats' per-PSN-link line (Follow-up 2026-09-08, was wrongly
    plural_achievements there too). plural_achievements() below stays
    untouched everywhere it serves a *combined* cross-platform total (e.g.
    /stats' "Сегодня"), which is correctly "достижений" regardless of how
    many of them came from PSN specifically — this is only for a count
    that is entirely PSN's own. Plural form selection is Fluent's, same as
    plural_achievements above."""
    _ = translator("achievements", locale)
    return _("achievement-trophy-plural", count=count, pretty=thousands(count))


#  Xbox/Steam's "100%-completed game" count and PSN's own platinum count
#  (#19) both render as this one symbol + a number, not a word (2026-09-08,
#  user request, reversing an initial "комплитов"/"платин" text attempt) —
#  a 100%-completed game and a PSN platinum answer the same question, so
#  one symbol answers it for every platform. The same icon PSN's own trophy
#  tier badge already uses for a platinum (services/achievements.py's own
#  TROPHY_TIER_BADGE above).
COMPLETED_BADGE = AchievementBadge.CUP


def visibility_status_text(link: PlatformLink, locale: str) -> str:
    """Steam/PSN's achievement/trophy visibility as found by the last actual
    check (#5) — shared by /panel's own login row and the admin card
    (2026-09-08, user request: the admin card's status line should read
    "как в панели юзера"), so the two never drift into different wording.
    Sourced from panel.ftl (that screen is where this text was written
    first) the same way this module already borrows chat.ftl's
    `chat-stats-no-gamertag` below, rather than duplicating it per module.

    Appends when the check last ran, when known — "unknown" has no
    timestamp to show at all."""
    if link.achievements_visible is None:
        return gettext("panel", "panel-visibility-unknown", locale=locale)
    label = gettext(
        "panel",
        "panel-visibility-visible" if link.achievements_visible else "panel-visibility-hidden",
        locale=locale,
    )
    if link.achievements_visible_checked_at:
        return f"{label} · {humanize_ago(link.achievements_visible_checked_at, locale)}"
    return label


async def platform_header_lines(
    repo: Repo,
    *,
    tg_id: int,
    xuid: str | None,
    gamertag: str | None,
    gamerscore: int | None,
    platform_links: list[PlatformLink],
    show_links: bool,
    locale: str,
) -> list[str]:
    """The per-platform header lines shared by /stats' card and /panel's own
    header (2026-09-08, user request: "пусть одни одинаково формируются" —
    /panel used to reimplement this on its own, HTML-identical but
    hand-duplicated). One line per connected platform: nickname/name first,
    then lifetime count, completions, gamerscore (Xbox) or level (PSN).

    `show_links` is the only thing that differs between callers: /stats
    gates it on the *target's* own show_profile_links, while /panel's own
    screen always passes True — its links are always visible regardless of
    that toggle, since the screen is never rendered to anyone but its owner
    (CLAUDE.md's "User interface" section).
    """
    lines = []
    if xuid:
        gamertag_html = html_escape(
            gamertag or gettext("chat", "chat-stats-no-gamertag", locale=locale)
        )
        if show_links and gamertag:
            gamertag_html = link_html(xbox_profile_url(gamertag), gamertag_html)
        # A lifetime Xbox count (2026-09-08, user request) — see
        # repo.py::xbox_achievement_count's own docstring for why this is
        # trustworthy for modern Xbox and CLAUDE.md's Statistics rules for
        # the one remaining x360-specific gap this doesn't close.
        xbox_count = await repo.xbox_achievement_count(tg_id)
        xbox_completed = await repo.xbox_completed_games_count(xuid)
        parts = [plural_achievements(xbox_count, locale)]
        if xbox_completed:
            parts.append(f"{COMPLETED_BADGE} {xbox_completed}")
        parts.append(f"gamerscore {thousands(gamerscore or 0)}")
        lines.append(
            f"{PLATFORM_ICON[Platform.XBOX_MODERN]} XBOX: {gamertag_html}  ·  "
            + "  ·  ".join(parts)
        )

    # Sorted here rather than trusted from the caller (2026-09-13): one of
    # the two callers used to pass Steam before PSN and the other the other
    # way round, which is how the same header rendered two different orders.
    for link in sorted(platform_links, key=lambda item: platform_display_rank(item.platform)):
        icon = PLATFORM_ICON.get(link.platform, PLATFORM_ICON_UNKNOWN)
        label = platform_label(link.platform, locale)
        # A lifetime Steam/PSN count has always been fine here — a Steam
        # backfill has no title cap (GetOwnedGames sees the whole owned-
        # games library) and PSN's own poller scans every trophy title
        # directly; neither carries the x360-specific gap
        # repo.py::xbox_achievement_count's own docstring flags for Xbox.
        count = await repo.platform_achievement_count(tg_id, link.platform)
        name_html = html_escape(link.display_name or link.external_id)
        if show_links:
            url = platform_profile_url(
                link.platform, external_id=link.external_id, display_name=link.display_name
            )
            name_html = link_html(url, name_html)

        # PSN calls its own achievements "trophies" everywhere (CLAUDE.md).
        is_psn = link.platform == Platform.PSN
        link_parts = [
            plural_trophies(count, locale) if is_psn else plural_achievements(count, locale)
        ]
        if is_psn:
            # PSN's own equivalent of a 100%-completed game (#19) — a
            # platinum is only awarded once every other trophy in that game
            # is earned, so this count already *is* that.
            platinum = await repo.psn_platinum_count(tg_id)
            if platinum:
                link_parts.append(f"{COMPLETED_BADGE} {platinum}")
            # PSN's own account-wide level (Follow-up 2026-09-06) — cached
            # by poller/psn_fetcher.py, never fetched here (SPEC 1.5's
            # cache-only rule); absent until the poller has had a chance to
            # set it (right after backfill, or a one-off backfill for an
            # account linked before this feature existed —
            # scripts/backfill_psn_levels.py, #23).
            if link.psn_trophy_level is not None:
                link_parts.append(
                    gettext(
                        "chat", "chat-stats-psn-level", locale=locale, level=link.psn_trophy_level
                    )
                )
        elif link.platform == Platform.STEAM:
            completed = await repo.steam_completed_games_count(tg_id)
            if completed:
                link_parts.append(f"{COMPLETED_BADGE} {completed}")
        lines.append(f"{icon} {label}: {name_html}  ·  " + "  ·  ".join(link_parts))

    return lines
