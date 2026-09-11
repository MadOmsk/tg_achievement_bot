"""Filtering and wording of achievement messages (SPEC 5.5, 7.1, 7.2).

No I/O here: the poller decides when, this module decides whether and how.
"""

from __future__ import annotations

from html import escape as html_escape

from bot.constants import AchievementBadge, Platform, PsnTrophyTier, RarityMode
from bot.db.repo import AchievementRow, ChatTarget, PlatformLink, Repo
from bot.i18n import gettext, translator
from bot.services.profile_links import link_html, platform_profile_url, xbox_profile_url
from bot.util import humanize_ago, thousands

# Every function here that produces visible text takes an explicit `locale`
# and binds its own translator from it (#48). There is deliberately no
# module-level shorthand and no default: this module renders for a chat the
# publisher is looping over, so a locale that could be left out is a locale
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
# online_view.py used to keep their own, smaller copies with no "x360" key
# at all, so an Xbox 360 game silently got no icon in /stats' games list and
# no colour in presence rows; both now import this one instead). Public
# names, not underscore-prefixed: this module is the home for them, other
# services are allowed to depend on it (only handlers->services is one-way).
PLATFORM_ICON = {
    Platform.MODERN: "🟢",
    Platform.X360: "🟢",
    Platform.STEAM: "⚫",
    Platform.PSN: "🔵",
}
PLATFORM_LABEL_KEYS = {
    Platform.MODERN: "achievement-platform-xbox",
    Platform.X360: "achievement-platform-xbox360",
    Platform.STEAM: "achievement-platform-steam",
    Platform.PSN: "achievement-platform-psn",
}
# Fallback used wherever a platform is unknown or the presence itself is
# offline/no-data (platform_tag() below, /online's own offline rows in
# services/online_view.py) — grey rather than any platform's own colour.
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
    parts = []
    if xbox_count:
        parts.append(f"{PLATFORM_ICON[Platform.MODERN]} {xbox_count}")
    if steam_count:
        parts.append(f"{PLATFORM_ICON[Platform.STEAM]} {steam_count}")
    if psn_count:
        parts.append(f"{PLATFORM_ICON[Platform.PSN]} {psn_count}")
    if not parts or (len(parts) < 2 and not always):
        return ""
    return " (" + " · ".join(parts) + ")"


def telegram_identity(
    *,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
    gamertag: str | None = None,
) -> str | None:
    """The common prefix of every "identify this person" fallback chain in
    the bot: `@username`, else first+last name, else a gamertag. Pulled out
    (2026-09-08 review) after this exact sequence turned up independently
    duplicated three times — /stats' header (`_display_name`), /who's
    picker buttons (`_who_label`, #40), and /panel's own header (#18) — each
    reimplementing it slightly differently rather than sharing it.

    Returns `None`, not a bare id, when nothing here is known — every
    caller has its own next-best fallback (a platform link's display name,
    Steam/PSN fields already on hand, or a plain tg_id), which only the
    caller knows how to name, so this stays agnostic of it."""
    if username:
        return f"@{username}"
    full_name = " ".join(part for part in (first_name, last_name) if part)
    if full_name:
        return full_name
    return gamertag or None


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
_NO_RARITY_DATA_PLATFORMS = {Platform.X360}


def passes_filters(
    achievement: AchievementRow,
    chat: ChatTarget,
    rare_threshold: float,
) -> bool:
    """The person's own rarity choice for *this* chat, plus the chat's own
    spam guards.

    Rarity mode (all/rare/hidden) used to be one value for every chat a
    person publishes to (`user_settings.rarity_mode`) — moved to
    `subscriptions.rarity_mode`, one per chat (SPEC 9, M-Steam-2e's
    follow-up): a close-friends chat and a big public one can reasonably
    want different answers to "what's worth showing". A chat-*admin*-
    controlled rarity toggle used to exist too, gating this alongside the
    person's own choice — dropped once it turned out redundant, a second
    switch people had to find and agree on for no real benefit.

    One `rarity_mode`, not one per platform (SPEC 9, M-Steam-2e) — there
    used to be a separate `show_x360` switch here, folded into this single
    check when Steam arrived rather than growing a second platform-specific
    toggle to match it.
    """
    if chat.rarity_mode == RarityMode.HIDDEN:
        # Every platform's feed off entirely, for this chat.
        return False

    if achievement.platform not in _NO_RARITY_DATA_PLATFORMS and not _passes_rarity(
        achievement, chat.rarity_mode, rare_threshold
    ):
        return False

    if achievement.gamerscore < chat.min_gamerscore:
        return False

    return achievement.title_id not in chat.muted_title_ids


def _passes_rarity(achievement: AchievementRow, mode: str, threshold: float) -> bool:
    if mode != RarityMode.RARE:
        return True
    if achievement.rarity_percent is None:
        return False
    return achievement.rarity_percent <= threshold


def _spoiler(text: str, *, secret: bool) -> str:
    """Wraps already-escaped HTML text in a Telegram spoiler (SPEC 5.5, 7.1).

    Xbox's own isSecret does not redact name/description — found live, they
    carry the real, spoiler-containing text even while still locked. Hiding
    it from chat members who haven't unlocked (or don't want to know) it is
    entirely this bot's own doing, not something Microsoft did for us.
    """
    return f'<span class="tg-spoiler">{text}</span>' if secret else text


def _badge(achievement: AchievementRow) -> str:
    """PSN trophies show only their own tier icon, not rarity_badge()'s
    diamond/cup as well (Follow-up 2026-09-06, user request, reversing the
    "shown alongside, two different questions" call from M-PSN-2) — the
    tier already answers the same question rarity_badge() does for every
    other platform (how uncommon is this one), just with Sony's own scale
    instead of a raw percentage, and showing both could literally repeat
    itself: a platinum trophy and an "ordinary" rarity cup are the same 🏆.
    Falls back to 🏆 in the (practically unreachable) case of a PSN row
    with no trophy_type at all, same "unproven is not rare" default
    rarity_badge() itself uses. Every other platform is unaffected —
    rarity_badge() alone, exactly as before."""
    if achievement.platform == Platform.PSN:
        return TROPHY_TIER_BADGE.get(achievement.trophy_type or "", AchievementBadge.CUP)
    return rarity_badge(achievement.rarity_percent)


def _rarity_line(achievement: AchievementRow, locale: str) -> str:
    """ "(rarity badge)«name» · G · rarity %" — badge leads the name
    rather than trailing the percentage (standardized form, 2026-09-05
    follow-up); gamerscore appears only when it isn't 0, replacing the
    older platform-keyed rules (Steam/PSN got a hardcoded "no G" each) —
    zero is zero on any platform, no need to name which ones have none at
    all (SPEC 9, future platforms fall under this for free).
    """
    _ = translator("achievements", locale)
    name = _spoiler(html_escape(achievement.name), secret=achievement.is_secret)
    name_part = _("achievement-name", badge=_badge(achievement), name=name)

    tail = []
    if achievement.gamerscore:
        tail.append(_("achievement-gamerscore", score=achievement.gamerscore))
    if achievement.rarity_percent is not None:
        tail.append(_("achievement-rarity", percent=f"{achievement.rarity_percent:g}"))
    return name_part if not tail else f"{name_part} · {' · '.join(tail)}"


def _game_line(title: str, platform: str, locale: str) -> str:
    _ = translator("achievements", locale)
    return _(
        "achievement-game-line",
        title=html_escape(title),
        platform=platform_tag(platform, locale),
    )


def _achievement_word(platform: str, locale: str) -> str:
    """PSN calls them trophies, everyone else achievements (Follow-up
    2026-09-06, user request — this is the "трофей" wording M-Steam-2e's
    original standardization explicitly left for later, once PSN trophies
    were real data and not just a reserved word)."""
    _ = translator("achievements", locale)
    return _("achievement-word-trophy") if platform == Platform.PSN else _("achievement-word")


def format_single(
    gamertag: str, achievement: AchievementRow, title_name: str | None, *, locale: str
) -> str:
    """Standardized form (2026-09-05 follow-up to SPEC 9, M-Steam-2e), one
    wording per platform (Follow-up 2026-09-06: PSN's own "трофей" word).
    Platform moved off the header (found there for one round, then judged
    noisier than useful) onto the game-title line, in italics, next to the
    game.
    """
    _ = translator("achievements", locale)
    title = title_name or achievement.title_name or _("achievement-unknown-game")
    header = _(
        "achievement-single-header",
        gamertag=html_escape(gamertag),
        word=_achievement_word(achievement.platform, locale),
    )
    game_line = _game_line(title, achievement.platform, locale)
    text = f"{header}\n\n{game_line}\n{_rarity_line(achievement, locale)}"
    if achievement.description:
        description = _spoiler(html_escape(achievement.description), secret=achievement.is_secret)
        text += f"\n\n{description}"
    return text


def _group_by_title(
    achievements: list[AchievementRow],
) -> dict[tuple[str, str], list[AchievementRow]]:
    """Keyed on (platform, title_id), not title_id alone — Xbox's and
    Steam's own id spaces (title_id vs. appid) don't promise to avoid each
    other. In practice every publish() call is already scoped to one game
    on one platform (poller/fetcher.py, poller/steam_fetcher.py each poll
    one title at a time) — this grouping exists so the digest renders
    correctly if that ever stops being true, not because it commonly sees
    more than one group today.
    """
    groups: dict[tuple[str, str], list[AchievementRow]] = {}
    for item in achievements:
        groups.setdefault((item.platform, item.title_id), []).append(item)
    return groups


def format_digest(
    gamertag: str, title_name: str | None, achievements: list[AchievementRow], *, locale: str
) -> str:
    """Standardized form (2026-09-05 follow-up): one block per game, each
    shaped like format_single's own game+rarity lines — a digest reader who
    already knows the single-achievement layout should recognise this one.
    No total gamerscore in the header any more (same reasoning as
    _rarity_line dropping platform-specific "no G" rules): it used to add
    up to a real "+0 G" for an all-Steam session, which is exactly the kind
    of technically-true-but-misleading number the rest of this rework is
    getting rid of.

    Every achievement gets its own line, no "… и ещё N" cutoff (2026-09-05:
    dropped on request — a digest exists to say what happened, trimming it
    defeats that).
    """
    # Every achievement in one publish() call used to always share a
    # platform (Xbox/Steam pollers each poll one title at a time; PSN's own
    # multi-game burst is still all-PSN — SPEC 9, M-PSN-2's multi-achievement
    # paragraph) — no longer guaranteed once the anti-flood filter started
    # calling this across a person's whole buffered backlog, any mix of
    # platforms (2026-09-09). "Trophies" only when every item actually is
    # one — same rule CLAUDE.md already states for combined cross-platform
    # totals like /stats' "Today: N achievements".
    _ = translator("achievements", locale)
    all_psn = bool(achievements) and all(item.platform == Platform.PSN for item in achievements)
    count_phrase = (
        plural_trophies(len(achievements), locale)
        if all_psn
        else plural_achievements(len(achievements), locale)
    )
    header = _("achievement-digest-header", gamertag=html_escape(gamertag), phrase=count_phrase)
    lines = [header, ""]
    for index, group in enumerate(_group_by_title(achievements).values()):
        if index > 0:
            lines.append("")  # a blank line between one game's block and the next
        title = group[0].title_name or title_name or _("achievement-unknown-game")
        lines.append(_game_line(title, group[0].platform, locale))
        lines.extend(_rarity_line(item, locale) for item in group)
    return "\n".join(lines)


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
            f"{PLATFORM_ICON[Platform.MODERN]} XBOX: {gamertag_html}  ·  " + "  ·  ".join(parts)
        )

    for link in platform_links:
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
