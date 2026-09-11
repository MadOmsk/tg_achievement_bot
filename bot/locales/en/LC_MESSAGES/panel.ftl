# The personal panel (/panel) — bot/handlers/panel.py.
# Connection status and sync
panel-login-active = ✅ active
panel-login-invalid = ⚠️ needs signing in again
panel-login-revoked = — disconnected
# Distinct from panel-login-revoked above (2026-09-09): "disconnected"
# implies a token existed and was deliberately removed, "not connected" is
# for a person who never linked Xbox at all — same distinction Steam/PSN's
# own login rows already draw via visibility_status_text's "not checked".
panel-login-not-connected = — not connected
panel-group-hint = Settings live in a DM.
panel-refreshed = Refreshed
panel-xbox-not-connected = Connect XBOX first: /connect_xbox
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
panel-my-chats-title = 💬 My chats
panel-my-chats-empty =

    I haven't seen you in any chat yet — no subscriptions, no messages.
panel-back = ‹ Back
panel-chat-card-title = 💬 { $title }
panel-publication-enabled = Publishing: ✅ on
panel-publication-disabled = Publishing: ⏸ off
panel-achievements-mode = Achievements: { $mode }
panel-digest-row = Digest: { $threshold } ▸
panel-unsubscribe = Unsubscribe
panel-subscribe = Subscribe
panel-remove-from-list = Remove from the list
panel-back-to-chat-list = ‹ Back to the chat list
panel-digest-menu =
    One digest instead of separate messages

    If this many achievements or more are unlocked at once in one game, this chat gets a single combined message.
panel-digest-set-never-toast = Never
panel-digest-set-from-toast = From { $value }
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
panel-login-xbox-row = XBOX login:   { $status }
# No "-connected" suffix (2026-09-09) — these render the same regardless of
# whether Xbox happens to be connected; the old plain (non-suffixed) keys
# only ever existed for the Xbox-gated early-return branch that used them,
# now removed, so this name freed up.
panel-login-steam-row = Steam login:  { $name }  ·  { $status }
panel-login-psn-row = PSN login:    { $name }  ·  { $status }
# Steam/PSN's achievement/trophy visibility, as of the last actual check
# (#5) — connect time, or any backfill/resync since. Xbox has no
# equivalent row here: its own token status (panel-login-xbox-row above)
# already answers a similar "can I actually read this account" question.
panel-visibility-visible = ✅ achievements visible
panel-visibility-hidden = ⚠️ achievements hidden
panel-visibility-unknown = ❓ not checked
panel-publication-row = Publishing:   { $status }
panel-now-playing-row = Now:          { $playing }
panel-timezone-row = Timezone:     { $offset }
panel-reconnect-hint = Your XBOX access has expired — press “Connect again” below.
panel-unknown-game = unknown game
panel-no-presence-data = no data
panel-offline = offline ({ $ago })
panel-online-idle = online, not playing
panel-playing = playing — { $game }
panel-excluded = 🚫 excluded by the administrator
panel-not-subscribed-anywhere = — not subscribed in any chat
panel-subscribed-in = ✅ in { $chats }
