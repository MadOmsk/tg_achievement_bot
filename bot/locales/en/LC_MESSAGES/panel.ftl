# The personal panel (/panel) — bot/handlers/panel.py.
# Connection status and sync
panel-login-active = ✅ active
panel-login-invalid = ⚠️ needs signing in again
panel-login-revoked = 🔘 disconnected
# Distinct from panel-login-revoked above (2026-09-09): "disconnected"
# implies a token existed and was deliberately removed, "not connected" is
# for a person who never linked Xbox at all — same distinction Steam/PSN's
# own login rows already draw via visibility_status_text's "not checked".
panel-login-not-connected = 🔘 not connected
panel-group-hint = Settings live in a DM.
panel-refreshed = Refreshed
# panel_chat_subscribe's own message (2026-09-09) — publishing needs any
# one platform connected, not Xbox specifically; panel-xbox-not-connected
# above stays as-is for panel_sync, which really is Xbox-only.
panel-connect-any-platform-first = Connect at least one platform first.
panel-sync-cooldown = Already synced. You can do it again in { $minutes } min.
panel-syncing = Syncing…
panel-default-player-name = Player
panel-sync-failed = The sync didn't work, try again later.
panel-sync-summary-found = Games checked: { $titles }. New achievements posted: { $published }.
panel-sync-summary-none = Nothing new — you haven't been in a game since the last poll.
panel-xbox-already-disconnected = XBOX isn't connected anyway.

# Account and privacy controls
panel-disconnect-prompt =
    Disconnect XBOX?

    I'll delete your token and subscriptions. Your achievement history stays — the chat's stats need it, and it keeps old achievements from flooding back into the chat if you sign in again.

    The permission itself stays in your Microsoft account — only you can remove it, here: { $revoke_url }
panel-links-hidden-toast = Hidden
panel-links-shown-toast = Showing
panel-timezone-prompt = 🕐 Your timezone — "today" and "this month" are counted by it.
panel-timezone-toast = Timezone: { $offset }
panel-my-chats-title = 💬 My chats
panel-my-chats-empty =

    I haven't seen you in any chat yet — no subscriptions, no messages.
panel-back = ‹ Back
panel-chat-card-title = 💬 { $title }
panel-publication-enabled = Publishing: ✅ on
panel-publication-disabled = Publishing: ⏸ off
panel-unsubscribe = Unsubscribe
panel-subscribe = Subscribe
panel-remove-from-list = Remove from the list
panel-back-to-chat-list = ‹ Back to the chat list
panel-subscribed-toast = Subscribed
panel-unsub-prompt = Stop publishing your achievements in “{ $title }”?
panel-unsub-yes = Yes, unsubscribe
panel-unsub-cancel = Cancel
panel-unsubscribed-toast = Unsubscribed
panel-delete-prompt =
    Remove “{ $title }” from the list? As if you'd never been there — not a ban, it comes back the moment you subscribe or write there again.
panel-delete-yes = Yes, remove it
panel-deleted-toast = Removed

# Panel content
# Truly defensive only (2026-09-09) — every real call site ensures the user
# row exists before render_panel ever runs, so this bare fallback is not
# expected to actually render; it used to also hardcode a Xbox-specific
# "not connected" tail that no longer matches the real (per-platform,
# generalized) body shape below.
panel-header-not-connected = 👤 Panel
# Header (#18): the person's own Telegram identity, then one line per
# connected platform — built by the same function /stats' own header uses
# (services/achievements.py::platform_header_lines, #5) rather than a
# second, hand-duplicated copy of it.
panel-header-identity = 👤 { $name }
# The trailing padding lines these rows up into one column, the same way the
# Russian file does it — the label lengths differ per language, so the
# padding is part of the translation rather than something Python adds.
panel-login-row = { $platform } login: { $status }
# No "-connected" suffix (2026-09-09) — these render the same regardless of
# whether Xbox happens to be connected; the old plain (non-suffixed) keys
# only ever existed for the Xbox-gated early-return branch that used them,
# now removed, so this name freed up.
# Steam/PSN's achievement/trophy visibility, as of the last actual check
# (#5) — connect time, or any backfill/resync since. Xbox has no
# equivalent row here: its own token status (panel-login-xbox-row above)
# already answers a similar "can I actually read this account" question.
panel-visibility-visible = ✅ achievements visible
panel-visibility-hidden = ⚠️ achievements hidden
panel-visibility-unknown = ❓ not checked
panel-publication-row = Publishing: { $status }
panel-now-playing-row = Now: { $playing }
panel-reconnect-hint = Your XBOX access has expired — press “Connect again” below.
panel-no-presence-data = no data
panel-offline = offline ({ $ago })
panel-online-idle = online, not playing
panel-playing = playing — { $game }
panel-excluded = 🚫 excluded by a super-admin
panel-not-subscribed-anywhere = 🔘 not subscribed in any chat
panel-subscribed-in = ✅ in { $chats }
panel-publishing-without = {" "}· except { $platforms }
panel-publishes-on-toast = Posting this account's achievements
panel-publishes-off-toast = This account's achievements are no longer posted

# A platform's own screen behind its /panel button (#10).
panel-account-title = { $icon } <b>{ $platform }</b>
panel-account-login = Login: { $status }
panel-account-publication = Posting: { $state }
panel-account-publishes-on = 🔔 on
panel-account-publishes-off = 🔇 off
panel-psn-title = { $icon } <b>PSN</b> · { $count ->
    [one] { $count } account
   *[other] { $count } accounts
} of { $max }
panel-psn-account-state = {"    "}{ $login } · { $state }
panel-psn-summed = Trophies of every account add up in stats and summaries.
kb-account-profile = 👤 { $platform } profile: { $name }
kb-account-psn = 👤 PSN: { $name }
kb-account-publication-on = 🔔 Posting: on
kb-account-publication-off = 🔇 Posting: off
kb-account-unlink = 🔌 Unlink { $platform }
kb-account-relink = 🔁 Link another account
kb-psn-add = ➕ Link another PSN account

panel-delete-account = 🗑 Delete account
panel-delete-confirm-1 =
    Are you sure you want to delete your account from the bot?
    All your platform links, chat subscriptions, and settings will be removed.
panel-delete-confirm-1-yes = ⚠️ Yes, proceed
panel-delete-confirm-2 =
    This action cannot be undone!
    All your bot data will be permanently erased. Are you sure?
panel-delete-confirm-2-yes = 🔥 Permanently delete account
panel-delete-done = Your account and related data have been deleted. If you ever wish to return, send /start.
panel-delete-toast = Account deleted
panel-delete-not-found = Account already deleted.
panel-rarity-toast-all = Posting every achievement
panel-rarity-toast-rare = Rare only — at or below the rarity threshold ({ $threshold }%)
panel-rarity-toast-hidden = Posting nothing

# Hidden achievements: what it means, and how to open them (#95).
panel-hidden-steam =
    ⚠️ Your Steam achievements are hidden. The bot can't see them: it won't post new ones or show them in the app. How to open them — the button below.
panel-hidden-psn =
    ⚠️ Trophies of { $name } are hidden. The bot can't see them: it won't post new ones or show them in the app. How to open them — the button below.
kb-howto-steam = 🔓 How to open achievements
kb-howto-psn = 🔓 How to open { $name }'s trophies
kb-steam-privacy = ⚙️ Open Steam settings
kb-recheck = 🔄 Check again
panel-howto-steam =
    🔓 <b>Steam: how to open achievements</b>

    The bot only sees what is public on Steam.

    1. Open the privacy settings: { $privacy_url }
    2. “My profile” → “Public”.
    3. “Game details” → “Public” — Steam hides it separately from the profile.

    Changes apply at once. Then press “Check again”.
panel-howto-psn =
    🔓 <b>PSN { $name }: how to open trophies</b>

    The bot only sees trophies visible to everyone.

    In the PS App:
    1. Settings → Privacy.
    2. “Trophy level and game collection” → “Anyone”.

    Single games can be hidden too — their trophies stay invisible even when the whole profile is open.

    Then press “Check again”.
