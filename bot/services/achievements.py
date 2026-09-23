"""Whether an achievement may be published at all (SPEC 5.5).

No I/O and no rendering: the poller decides when, views/ decide how, and
this decides whether. It was one module with all three jobs until #63 split
the wording out into views/parts.py and views/notification.py.
"""

from __future__ import annotations

from bot.constants import RarityMode
from bot.db.repo import AchievementRow, ChatTarget


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

    if not _passes_rarity(achievement, chat.rarity_mode, rare_threshold):
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
