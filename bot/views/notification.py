"""The achievement and trophy cards themselves (#63) — one unlock, and the
digest that several become.

A single card is a photo whose caption is everything below; a digest is a
media group carrying its caption on the first image. Both are capped by
Telegram at 1024 characters, which is why nothing here grows without a
reason. The rules these follow — the counter beside the game, PSN's own
second line for the trophy group, what a digest may never name — are in
CLAUDE.md's "Message formats".
"""

from __future__ import annotations

from html import escape as html_escape

from bot.constants import (
    AchievementBadge,
    Platform,
)
from bot.db.repo import AchievementRow, TitleProgress
from bot.i18n import translator
from bot.views.parts import (
    TROPHY_TIER_BADGE,
    platform_tag,
    plural_achievements,
    plural_trophies,
    rarity_badge,
)


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


def _game_line(
    title: str, platform: str, locale: str, progress: TitleProgress | None = None
) -> str:
    """The game, its platform, and how far this person is through it (#46).

    The counter is omitted rather than guessed when the total is unknown —
    PSN keeps progress as a percentage and never a count, and a Steam game
    whose schema has not been cached yet has no total either.

    A PlayStation trophy list split into groups (the base game plus one per
    DLC) gets a second line naming the group this trophy came from and the
    count inside it — always a count, never Sony's own percentage, which is
    weighted by trophy tier and so would disagree with the line above it.
    Sony names the base group after the game itself, and printing the title
    twice says nothing, so that one group is renamed (owner decision).
    """
    _ = translator("achievements", locale)
    line = _(
        "achievement-game-line",
        title=html_escape(title),
        platform=platform_tag(platform, locale),
    )
    if progress is None:
        return line
    line += _("achievement-game-progress", unlocked=progress.unlocked, total=progress.total)
    if progress.group_total:
        line += "\n" + _(
            "achievement-group-line",
            group=_group_label(progress, title, locale),
            unlocked=progress.group_unlocked,
            total=progress.group_total,
        )
    return line


# Sony puts the game's own title inside a group name often enough that the rule
# has to be about the duplication itself, not about which group it is (user
# request): the base group is normally named after the game exactly, and a DLC
# group is sometimes the game's name plus the add-on's ("Marvel's Spider-Man:
# The Heist"). Either way the title is already on the line above.
_TITLE_SEPARATORS = (":", "-", "–", "—", "|", "·")


def _group_label(progress: TitleProgress, title: str, locale: str) -> str:
    """What to call this trophy group on the second line.

    Never anything that merely repeats the game's own name: a group named
    exactly after the game becomes "Основная игра", and one that *starts* with
    the game's name keeps only the part that is actually about the add-on. A
    name that survives both is printed as Sony wrote it — and never with a
    "DLC" prefix, since a group is not always one (Spider-Man's `001` is New
    Game+, a mode).

    In the chat's own language where Sony has one (#61): unlike a game's
    title, group names *are* localized — "CTNS: The Heist" comes back as
    "Город, который никогда не спит: Ограбление".
    """
    _ = translator("achievements", locale)
    localized = progress.group_name_en if locale == "en" else progress.group_name_ru
    name = (localized or progress.group_name or "").strip()
    bare_title = title.strip()
    if not name or name.casefold() == bare_title.casefold():
        return _("achievement-group-main")
    if name.casefold().startswith(bare_title.casefold()):
        tail = name[len(bare_title) :].lstrip()
        while tail[:1] in _TITLE_SEPARATORS:
            tail = tail[1:].lstrip()
        return html_escape(tail) if tail else _("achievement-group-main")
    return html_escape(name)


def _achievement_word(platform: str, locale: str, *, secret: bool = False) -> str:
    """PSN calls them trophies, everyone else achievements (Follow-up
    2026-09-06, user request — this is the "трофей" wording M-Steam-2e's
    original standardization explicitly left for later, once PSN trophies
    were real data and not just a reserved word).

    A secret one says so in the header (#16, owner decision 2026-09-16):
    "получает секретное достижение". The name below it is behind a real
    Telegram spoiler, and a blurred word with nothing explaining it reads
    as a rendering glitch rather than as a deliberate secret — the header
    is where that belongs, because it is the one line that is never hidden.
    """
    _ = translator("achievements", locale)
    if platform == Platform.PSN:
        return _("achievement-word-secret-trophy") if secret else _("achievement-word-trophy")
    return _("achievement-word-secret") if secret else _("achievement-word")


def format_single(
    gamertag: str,
    achievement: AchievementRow,
    title_name: str | None,
    *,
    locale: str,
    progress: TitleProgress | None = None,
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
        word=_achievement_word(achievement.platform, locale, secret=achievement.is_secret),
    )
    game_line = _game_line(title, achievement.platform, locale, progress)
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
    gamertag: str,
    title_name: str | None,
    achievements: list[AchievementRow],
    *,
    locale: str,
    progress: dict[tuple[str, str, str | None], TitleProgress] | None = None,
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
        # Keyed the same way _group_by_title groups (#46) — one progress
        # figure per game, and a digest can span several.
        # A digest never names a trophy group, even when every trophy in
        # this game's block happens to share one (owner decision, #46):
        # one block is one *game*, so its line carries the game's name and
        # the game's own total, and a group line would be a second subject
        # in a message that is already grouping things. `None` is the
        # game-only progress entry every platform has.
        key = (group[0].platform, group[0].title_id, None)
        lines.append(_game_line(title, group[0].platform, locale, (progress or {}).get(key)))
        lines.extend(_rarity_line(item, locale) for item in group)
    return "\n".join(lines)
