# Administrator panel (handlers/admin.py). Keeping these strings here also
# makes callback alerts and generated cards follow the same locale as menus.
admin-unlimited = no limit
admin-disabled = off
admin-back = ‹ Back
admin-cancel = Cancel
admin-yes = yes
admin-no = no
admin-enabled = on
admin-disabled-state = off
admin-active = active
admin-inactive = disabled

# Runtime settings
admin-setting-summary-rows = Rows in /summary
admin-setting-stats-games = Games in /stats
admin-setting-hltb-results = HLTB search results and suggestions
admin-setting-hltb-page = Results per page (HLTB)
admin-setting-system-ttl = Auto-delete system messages (min)
admin-setting-online-interval = /online auto-refresh interval (min)
admin-setting-online-ttl = /online auto-refresh, hours
admin-setting-key-check = Key check / /admin auto-refresh (min)

# Platform keys (#17; Anthropic added 2026-09-09 — achievement-description
# translation only, same admin-settable-shared-credential shape)
admin-keys-screen =
    🔑 Platform keys

    PSN: { $psn }
    Steam: { $steam }
    Anthropic: { $anthropic }
admin-keys-set = ✅ configured
admin-keys-unset = ⚠️ not configured
admin-keys-steam-add = Set the Steam key
admin-keys-steam-change = Change the Steam key
admin-keys-steam-clear = Remove the Steam key
admin-keys-psn-add = Set the NPSSO (PSN)
admin-keys-psn-change = Change the NPSSO (PSN)
admin-keys-psn-clear = Remove the NPSSO (PSN)
admin-keys-anthropic-add = Set the Anthropic key
admin-keys-anthropic-change = Change the Anthropic key
admin-keys-anthropic-clear = Remove the Anthropic key
admin-keys-steam-prompt =
    Send the Steam Web API key in a single message — get one here:
    https://steamcommunity.com/dev/apikey
admin-keys-steam-invalid = That Steam key didn't work — check it and send it again.
admin-keys-steam-saved =
    Steam key saved.

    { $text }
admin-keys-psn-prompt =
    Send the NPSSO in a single message — to get it: sign in at my.playstation.com,
    then open https://ca.account.sony.com/api/v1/ssocookie and copy the
    "npsso" value from the JSON on screen.
admin-keys-psn-saved =
    NPSSO saved.

    { $text }
admin-keys-anthropic-prompt =
    Send the Anthropic API key in a single message — get one here:
    console.anthropic.com → Settings → API Keys → Create Key
    (a payment method has to be attached — the key is paid, but translating
    short achievement descriptions costs pennies on Haiku).
admin-keys-anthropic-invalid = That Anthropic key didn't work — check it and send it again.
admin-keys-anthropic-saved =
    Anthropic key saved.

    { $text }

# PSN status and one-line messages
admin-psn-npsso-invalid = That NPSSO didn't work — Sony rejected it. Check it and send it again.
admin-psn-client-error = Couldn't build a PSN client — a technical error on the server ({ $error }). The NPSSO is probably not the problem — check the bot's logs.

# Limits and input prompts
admin-limits-screen =
    ⚙️ Global settings

    The /summary and /stats lists can be made unlimited (0) — they already sit
    inside a collapsible quote, so there's nothing to trim.
admin-limit-prompt = { $label }: { $current }

    Send a new value as a whole number, from { $minimum } to { $maximum }{ $zero_hint }.
admin-number-range-retry = The number has to be between { $minimum } and { $maximum }. Again?
admin-threshold-saved = Rarity threshold: { $value }%

{ $text }
admin-integer-retry = A whole number only here. Again?
admin-timezone-button = Timezone ▸
admin-timezone-manual = ✏️ Enter manually
admin-chat-not-found = Chat not found
admin-chat-not-found-period = Chat not found.

# Chat settings prompts
admin-chat-threshold-prompt =
    The "rare" achievement threshold in “{ $title }”: { $value }%

    Send a new value as one number, for example 12 or 7.5 — from 0 to 100.
    It applies to this chat only.
admin-chat-time-prompt = Daily summary time in “{ $title }”: { $time }
admin-chat-time-saved = Daily summary at { $time }
admin-chat-zone-prompt = Timezone of “{ $title }”: { $offset }
admin-chat-zone-manual-prompt =
    Timezone of “{ $title }”: { $offset }

    Send the offset in a single message, with a sign: for example +3, -5 or +5:30.
admin-timezone-invalid = That doesn't look like a real timezone. For example: +3 or -5:30.
admin-timezone-saved = Timezone: { $offset }

# Anti-flood filter (2026-09-09): after N individually-notified achievements
# for one person land in this chat within the window, further ones stop
# posting on their own and get grouped into one message once the window
# closes. 0 = off for this chat.
admin-chat-flood-prompt =
    Anti-flood filter in “{ $title }”: { $value } ach.

    Send a new value as a whole number, from { $minimum } to { $maximum } (0 turns it off).
    It applies to this chat only.
admin-chat-flood-window-prompt =
    Anti-flood window in “{ $title }”: { $value } min

    Send a new value as a whole number, from { $minimum } to { $maximum }.
    It applies to this chat only.
admin-flood-saved = Anti-flood filter: { $value } ach.

{ $text }
admin-flood-window-saved = Anti-flood window: { $value } min

{ $text }

# User and message actions
admin-user-excluded = Excluded
admin-user-restored = Restored
admin-user-not-connected = Not connected
admin-refreshing = Refreshing…
admin-refresh-failed = Couldn't refresh
# The second line of "🔄 Обновить"'s answer: what turned up since the newest
# achievement already stored. Only what falls inside the usual catch-up window
# is announced; the rest is stored quietly.
admin-sync-delta =
    { $titles ->
        [0] Nothing new since last time.
       *[other] Checked { $titles } game(s), posted { $published }.
    }
admin-sync-delta-steam = Posted since last time: { $published }.
admin-steam-not-connected = Steam isn't connected
admin-psn-not-connected = PSN isn't connected

# Chat and cleanup actions
admin-chat-disabled = Disabled
admin-chat-enabled = Enabled
admin-no-bot-messages = I found no messages of mine in this chat.
admin-delete-old-failed = Couldn't delete it — the message may be too old.
admin-deleted-last = 🗑 Deleted the last message.
# Toast text (2026-09-09) — Telegram caps this at 200 chars total, see
# handlers/admin.py's own TOAST_PREVIEW_MAX_CHARS/_toast_preview.
admin-deleted-last-preview = 🗑 Deleted: “{ $preview }”
admin-no-bot-messages-24h = No messages of mine in the last 24 hours.
admin-confirm-delete = Yes, wipe them
admin-wipe-prompt =
    Wipe { $count } of the bot's messages in “{ $title }” from the last { $hours } hours?

    This can't be undone. Only messages sent since this log was started are
    counted — the bot doesn't remember older ones.
admin-wipe-done = Done.
admin-wipe-partial = Partially — some of them couldn't be wiped.
admin-no-system-messages = No system messages found.
admin-system-wipe-prompt =
    Wipe { $count } system messages in “{ $title }”?

    Achievements, /stats, /summary and the daily summary are untouched — only
    the in-between messages (hints, confirmations, /help and the like).

# New users and user cards
admin-new-users-screen =
    👤 New users — default settings

    Applies only to subscriptions created from now on — existing ones are left
    alone.
admin-default-rarity = Default achievements: { $rarity } ▸
admin-default-links = Profile visible to others: { $visible } ▸
admin-users-empty = 👥 Nobody has connected yet.
admin-users-header = 👥 Users  ({ $page }/{ $pages })
admin-users-columns = Columns: last seen · achievements today / this month
admin-id = id{ $tg_id }
admin-users-row = { $icon } { $name } · { $ago } · { $today} / { $month }{ $note }
admin-user-not-found = User not found.
admin-no-name = no name
# The card's own top line — every known bit of Telegram identity at once
# (2026-09-08 user request), unlike /stats' header which picks one best
# name. { $identity } is already the fully composed "First Last, @username,
# tg_id N" string (admin.py::_admin_tg_header) — never "@" + a bare id, only
# a real username earns the "@".
admin-user-header = 👤 { $identity }
# $tg_id arrives as a string on purpose — as a number Fluent groups the
# digits, and an identifier is not a quantity.
admin-user-tgid = tg_id { $tg_id }
admin-login-not-connected = not connected
admin-login-active = ✅ active, refreshed { $ago }
admin-login-invalid = ⚠️ expired
admin-login-revoked = 🔕 disconnected by the user
admin-no-data = no data
admin-no-game = no game
admin-online-playing = { $ago }, { $game }
admin-online-idle = online, not playing
admin-today-tag = { $count } today
admin-gamerscore-tag = gamerscore { $score }

# One block per platform (2026-09-08 rework) — header line first (nickname +
# id + lifetime count + today's count [+ completions/level]), then whatever
# admin-only diagnostics apply to that platform on their own indented lines.
admin-xbox-header = 🟢 XBOX: { $gamertag }
admin-xuid-tag = XUID { $xuid }
admin-login-row =   Login: { $login }
admin-online-row =   Online: { $online }
admin-steam-header = ⚫ Steam: { $name }
admin-steamid-tag = id { $external_id }
admin-psn-header = 🔵 PSN: { $name }
admin-psn-id-tag = account_id { $external_id }
admin-psn-level-tag = level { $level }

admin-nowhere = nowhere
admin-subscribed = Subscribed: { $chats }
admin-excluded = 🚫 Excluded from the system: not polled, not published.
admin-restore = ↩️ Restore
admin-exclude = 🚫 Exclude from the system
admin-refresh-xbox = 🔄 Refresh XBOX
admin-refresh-steam = 🔄 Refresh Steam
admin-refresh-psn = 🔄 Refresh PSN
admin-reset-xbox = 🗑 Reset XBOX
admin-reset-steam = 🗑 Reset Steam
admin-reset-psn = 🗑 Reset PSN
admin-reset-confirm-prompt =
    Wipe this user's { $platform } data and sync it again from scratch?

    This can't be undone: the whole achievement/trophy history for that
    platform is deleted and read back from nothing (nothing is published to
    any chat — same as a first-time link).
admin-reset-confirm-yes = Yes, wipe and resync
admin-back-to-users = ‹ Back to the list

# Chat cards
admin-chats-empty = The bot hasn't been added to any chat yet.
admin-chats-header = 💬 Chats  (title · how many people publish there)
admin-chat-list-row = { $mark }{ $title } · { $subscribers }
admin-chat-card =
    💬 { $title }

    State:         { $state }
    Publishing:    { $subscribers } people
    Rare below:    { $threshold }
    Daily summary: { $summary }, at { $time }
    Timezone:      { $offset }
    Min G:         { $min_score }
    Anti-flood:    { $flood }
    Language:      { $locale_name }

    { $names }
admin-chat-flood-value = { $limit } ach. / { $window } min
admin-chat-flood-off = off
admin-no-subscribers = No subscribers yet.
admin-subscribers-list = Subscribed: { $names }
admin-chat-threshold-button = Rarity threshold: { $threshold } ▸
admin-chat-summary-button = Daily summary: { $state }
admin-chat-time-button = Summary time: { $time } ({ $offset }) ▸
admin-chat-flood-toggle-button = Anti-flood filter: { $state }
admin-chat-flood-button = Anti-flood: { $limit } ach. ▸
admin-chat-summary-menu-button = Daily summary: { $state } ▸
admin-chat-flood-menu-button = Anti-flood: { $value } ▸
admin-chat-messages-menu-button = 🗑 Messages ▸
admin-chat-locale-button = Language: { $name }
admin-chat-flood-window-button = Anti-flood window: { $window } min ▸
admin-disable-chat = ⏸ Disable the chat
admin-enable-chat = ▶️ Enable the chat
admin-delete-last = 🗑 Last one
admin-wipe-bot-24h = 🗑 Bot's (24h)
admin-wipe-system-24h = 🗑 System (24h)
admin-wipe-system-all = 🗑 All system
admin-back-to-chats = ‹ Back to the list
admin-default-player = Player
admin-note-excluded =   excluded
admin-note-invalid =   login expired
admin-note-revoked =   unsubscribed
