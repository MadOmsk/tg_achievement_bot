"""Public profile URLs, one function per platform (Follow-up 2026-09-06) —
used by /stats and /who to turn a person's nickname into a link, gated by
that person's own `user_settings.show_profile_links` (off by default).

Xbox's own profile page shows up regardless of the account's Xbox privacy
settings (it's Microsoft's public profile card, same one anyone gets from a
gamertag search); Steam's link only actually renders anything if that
person's own Steam profile is public, same visibility rule the bot's own
polling already depends on; PSN's is best-effort the same way — nothing here
grants access beyond what each platform already exposes on its own, this
just points at it.
"""

from __future__ import annotations

from urllib.parse import quote

from bot.constants import Platform


def xbox_profile_url(gamertag: str) -> str:
    return f"https://account.xbox.com/en-us/profile?gamertag={quote(gamertag)}"


def steam_profile_url(steam_id64: str) -> str:
    # steamid64 is always numeric-ASCII, no vanity name involved — the one
    # link shape that works regardless of whether the person ever set a
    # vanity URL (services/steam/client.py only ever resolves to this id).
    return f"https://steamcommunity.com/profiles/{steam_id64}"


def psn_profile_url(online_id: str) -> str:
    return f"https://my.playstation.com/profile/{quote(online_id)}"


def platform_profile_url(
    platform: str, *, external_id: str, display_name: str | None
) -> str | None:
    """Dispatch for `platform_links` rows (steam/psn) — Xbox isn't here, it
    has no row in that table, callers use xbox_profile_url directly.

    Takes both id fields, not just one, because the two platforms don't
    agree on which of them is the linkable identity: Steam wants
    `external_id` (SteamID64 — steam_profile_url's own reasoning: always
    present, unlike a vanity name); PSN wants `display_name` instead
    (`link_platform_account` stores the onlineId there, `external_id` is
    PSN's internal account_id, meaningless in a my.playstation.com URL)."""
    if platform == Platform.STEAM:
        return steam_profile_url(external_id)
    if platform == Platform.PSN:
        return psn_profile_url(display_name) if display_name else None
    return None


def link_html(url: str | None, escaped_text: str) -> str:
    """Wraps already-HTML-escaped display text in an `<a href>` when a link
    is available, otherwise returns it unchanged — the one place that
    decides whether a nickname becomes clickable."""
    if url is None:
        return escaped_text
    return f'<a href="{url}">{escaped_text}</a>'
