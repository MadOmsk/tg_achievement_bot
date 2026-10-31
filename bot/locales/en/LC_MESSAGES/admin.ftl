# Administrator panel (handlers/admin.py). Keeping these strings here also
# makes callback alerts and generated cards follow the same locale as menus.
admin-unlimited = no limit
admin-disabled = off
admin-no-delay = no delay
admin-back = ‹ Back
admin-cancel = Cancel
admin-yes = yes
admin-no = no
admin-active = in the chat
admin-inactive = not in the chat

# Runtime settings
admin-setting-summary-rows = Rows in /summary
admin-setting-stats-games = Games in /stats
admin-setting-recent-rows = Achievements in /recent
admin-setting-hltb-results = HLTB search results and suggestions
admin-setting-hltb-page = Results per page (HLTB)
admin-setting-system-ttl = Auto-delete system messages (min)
admin-setting-online-interval = /online auto-refresh interval (min)
admin-setting-online-ttl = /online auto-refresh, hours
admin-setting-key-check = Key check / /admin auto-refresh (min)
admin-setting-monthly-delay = Month-end wrap-up delay (min)
admin-setting-account-reset-cooldown = Account reset cooldown (hours)
admin-setting-email-sends-client = Email codes per IP an hour
admin-setting-email-provider-daily = The mail service's daily limit
admin-setting-email-sends-total = Email codes in total an hour
admin-setting-email-checks-client = Code checks per IP in 10 minutes
admin-setting-patch-refresh = Game patch refresh (hours)
admin-setting-translation-batch = Translation: games in a batch
admin-translation-queue-on = 🌐 Translation queue is off — switch on
admin-translation-queue-on-confirm = Switch the translation queue on? It spends money on the model by itself.
admin-translation-queue-on-yes = Yes, switch on
admin-translation-queue-off = 🌐 Translation queue is on — switch off
admin-translation-queue-now-on = The translation queue is on
admin-translation-queue-now-off = The translation queue is off
admin-setting-translation-interval = Translation: every how many minutes
admin-setting-octopus-per-tick = Games the octopus assembles (a minute)

# The settings registry (#176, services/admin_registry.py): one label per
# setting, one title per group — the bot and the Mini App show the same ones.
admin-setting-rare-threshold = Rarity threshold, %
admin-setting-default-rarity = Newcomers' mode
admin-setting-rare-threshold-hint = Rare is what at most this share of players have. One threshold for every chat.
admin-setting-default-rarity-hint = The mode new people start with.
admin-setting-show-links = Profile links
admin-setting-store-collection = Store collection
admin-setting-store-collection-hint = The bot asks the stores and HowLongToBeat about games on its own: versions, DLC, playing times. Off — nothing is collected.
admin-setting-post-picture = Post picture
admin-setting-post-picture-hint = A small icon (Steam, Xbox 360) is enlarged and set on a card with this ground. Large pictures go as they are.
admin-setting-post-picture-size = Small icon's card
admin-setting-post-picture-scale = Small icon enlarged
admin-setting-post-picture-low-res = A small icon is
admin-setting-post-picture-low-res-hint = A picture smaller than this on its longer side is enlarged and set on a card; the rest go as they are. 128 takes only Steam's and Xbox 360's icons, 256 PS4's trophies too, 512 everything but large artwork.
admin-post-picture-low-res-value = under { $px } px
admin-post-picture-size-original = Original (no card)
admin-post-picture-off = As it is
admin-post-picture-color = On the icon's colour
admin-post-picture-cover = On the game's cover
admin-setting-chat-publishing = Publishing in the chat
admin-setting-chat-locale = Language
admin-setting-chat-tz = Time zone
admin-setting-digest = Digest from
admin-setting-chat-summary = Daily summary
admin-setting-chat-summary-time = Summary time
admin-setting-chat-flood-limit = Anti-flood: posts per window
admin-setting-chat-flood-window = Anti-flood: window (min)
admin-group-global-rules = Rules
admin-group-global-newcomers = New people
admin-group-global-lists = Lists
admin-group-global-hltb = HLTB
admin-group-global-timers = Timers
admin-group-global-poll_xbox = Status polling: Xbox
admin-group-global-poll_steam = Status polling: Steam
admin-group-global-poll_psn = Status polling: PlayStation
admin-setting-poll-in-game = In a game (min)
admin-setting-poll-online = Online, no game (min)
admin-setting-poll-offline = Offline (min)
admin-setting-poll-idle = Offline for long (min)
admin-setting-poll-idle-after = "For long" — after (min offline)
admin-setting-poll-dormant = Dormant account (min)
admin-setting-poll-dormant-after = "Dormant" — after (days offline)
admin-setting-poll-scan-online = Trophy scan: online (min)
admin-setting-poll-scan-offline = Trophy scan: offline (min)
admin-setting-poll-scan-dormant = Trophy scan: dormant (min)
admin-setting-poll-shared-slowdown = Without a personal token: rarer by (times)
admin-group-global-mail = Mail
admin-group-global-other = Other
admin-group-chat-main = General
admin-group-chat-summary = Daily summary
admin-group-chat-flood = Anti-flood
admin-settings-title = ⚙️ Settings
admin-settings-button = ⚙️ Settings ▸
admin-settings-group-title = ⚙️ Settings · { $group }
admin-settings-row = { $label }: { $value } ▸
admin-settings-pick = { $label }: pick a value.
admin-settings-type =
    { $label }
    Now: { $current }
    Send a number from { $minimum } to { $maximum }.{ $zero_hint }
admin-settings-zero-hint = { " " }0 — { $meaning }.
admin-settings-saved = ✅ { $label }: { $value }
admin-settings-choice-retry = No such value — pick one with a button.

# Platform keys (#17; Anthropic added 2026-09-09 — achievement-description
# translation only, same admin-settable-shared-credential shape)
admin-keys-title = 🔑 Platform keys
admin-keys-tap = Tap a key: its state, check, load and actions are inside.
admin-keys-personal-button = 👥 Personal PSN tokens · { $alive } ✅ · { $dead } ⚠️
admin-keys-back = ‹ Keys
admin-key-title = 🔑 <b>{ $label }</b>
admin-key-status-alive = Status: ✅ working
admin-key-status-dead = Status: ⚠️ not working
admin-key-status-unset = Status: ⚪️ not set
admin-key-checked = Checked: { $ago }
admin-key-usage = Requests: { $usage }
admin-key-psn-reads = Reads: { $shared } accounts without a personal token and the games catalog · personal tokens: { $alive } ✅ · { $dead } ⚠️
admin-psntok-title = 👥 <b>Personal PSN tokens</b>
admin-psntok-alive = ✅ <b>{ $name }</b> — { $who }, checked { $ago }
admin-psntok-dead = ⚠️ <b>{ $name }</b> — { $who }, not working { $ago }, the owner was told
admin-psntok-none = Nobody has added a personal token yet.
admin-psntok-note = The tokens themselves are shown to nobody. Without a personal token: { $shared } accounts (polled less often — see «Status polling: PlayStation»).
admin-psn-token-shared = Token: shared (polled less often)
admin-psn-token-alive = Token: 🔑 personal ✅ (checked { $ago })
admin-psn-token-dead = Token: 🔑 personal ⚠️ not working ({ $ago })
admin-keys-line = { $label }: { $state }
admin-keys-psn-label = PSN
admin-keys-steam-label = Steam
admin-keys-anthropic-label = Anthropic
admin-keys-youtube-label = YouTube
admin-keys-smtp-label = Mail (SMTP)
# One line under the field in the Mini App, where the long prompt does not fit.
admin-keys-psn-hint = The npsso value from ca.account.sony.com/api/v1/ssocookie, signed in at my.playstation.com.
admin-keys-steam-hint = A Steam Web API key: steamcommunity.com/dev/apikey.
admin-keys-anthropic-hint = An API key: console.anthropic.com → Settings → API Keys.
admin-keys-youtube-hint = A YouTube Data API v3 key from console.cloud.google.com.
admin-keys-smtp-hint = The login and SMTP key, space-separated: "login key".
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
admin-keys-youtube-add = Set the YouTube key
admin-keys-youtube-change = Change the YouTube key
admin-keys-youtube-clear = Remove the YouTube key
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
admin-keys-youtube-prompt =
    Send the YouTube Data API key in a single message — get one here:
    console.cloud.google.com → enable "YouTube Data API v3" →
    Credentials → Create credentials → API key (free).
admin-keys-youtube-invalid = That YouTube key didn't work — check it and send it again.
admin-keys-youtube-saved =
    YouTube key saved.

    { $text }

admin-keys-smtp-add = Set the mail login (SMTP)
admin-keys-smtp-change = Change the mail login (SMTP)
admin-keys-smtp-clear = Remove the mail login (SMTP)
admin-keys-smtp-prompt =
    Send the mail server's login and key in one message, space-separated:
    login key
    For Brevo: SMTP & API → SMTP — a login like …@smtp-brevo.com and an SMTP key
    (Generate a new SMTP key). For Gmail: the address and an app password.
    The server and the sender's address come from .env (SMTP_HOST, SMTP_FROM).
admin-keys-smtp-invalid = The mail server refused this login — check the login and key and send them again (two words, space-separated).
admin-keys-smtp-saved =
    Mail login saved — sign-in codes go out with it.

    { $text }

# PSN status and one-line messages
admin-keys-psn-invalid = That NPSSO didn't work — Sony rejected it. Check it and send it again.
admin-keys-setup-error = Couldn't build a PSN client — a technical error on the server ({ $error }). The NPSSO is probably not the problem — check the bot's logs.

# Limits and input prompts
admin-number-range-retry = The number has to be between { $minimum } and { $maximum }. Again?
{ $text }
admin-integer-retry = A whole number only here. Again?
admin-chat-not-found = Chat not found
admin-chat-not-found-period = Chat not found.

# Chat settings prompts
# Anti-flood filter (2026-09-09): after N individually-notified achievements
# for one person land in this chat within the window, further ones stop
# posting on their own and get grouped into one message once the window
# closes. 0 = off for this chat.
{ $text }
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

# Chat and cleanup actions
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
admin-send-promo-to-chat = 📢 Send promo to chat
admin-promo-sent = Promo message sent to chat
admin-promo-confirm = Send the promo message to «{ $title }»?
admin-promo-confirm-yes = 📢 Yes, send it
admin-promo-failed = Couldn't send the promo — the bot may not be in the chat.
admin-action-unknown = That action isn't available now.
admin-action-section-messages = Bot messages
admin-action-section-timers = Translation queue
admin-action-section-rules = Notification check

# New users and user cards
admin-users-empty = 👥 Nobody has connected yet.
admin-users-header = 👥 Users
admin-users-columns = Columns: last seen · achievements today / this month
admin-users-row = { $icon } { $name } · { $ago } · { $today} / { $month }{ $note }
admin-user-not-found = User not found.
admin-user-header = 👤 { $name } · id { $person_id }
# $tg_id and $person_id arrive as strings on purpose — as a number Fluent
# groups the digits, and an identifier is not a quantity.
admin-logins-title = Ways to sign in:
admin-logins-row = { "  " }{ $label }: { $value }
admin-logins-telegram = Telegram
admin-logins-email = Email
admin-logins-tg-id = id { $tg_id }
admin-logins-none = — none
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
admin-muted-row =   🔇 posting switched off by the owner
admin-steam-header = ⚫ Steam: { $name }
admin-steamid-tag = id { $external_id }
admin-psn-header = 🔵 PSN: { $name }
admin-psn-id-tag = account_id { $external_id }
admin-psn-level-tag = level { $level }

admin-nowhere = nowhere
admin-subscribed = Subscribed: { $chats }
admin-rarity-title = Posting
admin-rarity = Posting: { $mode }
admin-rarity-all = all
admin-rarity-rare = rare
admin-rarity-hidden = none
admin-excluded = 🚫 Excluded from the system: not polled, not published.
admin-restore = ↩️ Restore
admin-exclude = 🚫 Exclude from the system
admin-refresh-xbox = 🔄 Refresh XBOX
admin-refresh-steam = 🔄 Refresh Steam
admin-refresh-psn = 🔄 Refresh PSN
admin-reset-xbox = 🗑 Reset XBOX
admin-reset-steam = 🗑 Reset Steam
admin-reset-psn = 🗑 Reset PSN
# One pair per PSN account when a person holds several (#10).
admin-refresh-psn-account = 🔄 Refresh PSN: { $name }
admin-reset-psn-account = 🗑 Reset PSN: { $name }
admin-reset-confirm-prompt =
    Wipe this user's { $platform } data and sync it again from scratch?

    This can't be undone: the whole achievement/trophy history for that
    platform is deleted and read back from nothing (nothing is published to
    any chat — same as a first-time link).
admin-reset-confirm-yes = Yes, wipe and resync
admin-reset-avatar = 🖼 Reset avatar
admin-avatar-reset = Avatar reset to the Telegram photo
admin-picture-test = 🖼 Notification test
admin-picture-test-intro = 🖼 Notification test. The newest achievement earned on each platform ({ $count }) as the whole post a chat gets: as today, then a small icon with the current card size and scale — on the icon's colour and on the game's cover. Large pictures stay as they are.
admin-picture-test-high-res = High resolution — goes as it is
admin-picture-test-sent = Posts sent to your DM: { $count }
admin-picture-test-empty = No achievement with a picture yet
admin-picture-test-failed = Could not send the test to your DM
admin-delete-user = 🗑 Delete user
admin-delete-confirm-1 =
    Delete user { $name } (ID: { $tg_id })?

    All account links, user settings, and chat subscriptions will be removed.
admin-delete-confirm-1-yes = ⚠️ Yes, proceed
admin-delete-confirm-2 =
    Warning! This action cannot be undone!

    Permanently delete user { $name } (ID: { $tg_id }) from the database?
admin-delete-confirm-2-yes = 🔥 Permanently delete user
admin-delete-toast = User deleted
admin-delete-not-found = User not found
admin-back-to-users = ‹ Back to the list

# Chat cards
admin-chats-empty = The bot hasn't been added to any chat yet.
admin-chats-header = 💬 Chats  (title · how many people publish there)
admin-chat-list-row = { $mark }{ $title } · { $subscribers }
admin-chat-card =
    💬 { $title }

    Bot:           { $state }
    Publishing:    { $publishing }
    Subscribed:    { $subscribers } people
    Chat admin:    { $admin }
    Daily summary: { $summary }, at { $time }
    Timezone:      { $offset }
    Anti-flood:    { $flood }
    Language:      { $locale_name }

    { $names }
admin-chat-flood-value = { $limit } ach. / { $window } min
admin-chat-flood-off = off
admin-no-subscribers = No subscribers yet.
admin-subscribers-list = Subscribed: { $names }
admin-digest-never = never
admin-chat-messages-menu-button = 🗑 Messages ▸
admin-delete-last = 🗑 Last one
admin-wipe-bot-24h = 🗑 Bot's (24h)
admin-wipe-system-24h = 🗑 System (24h)
admin-wipe-system-all = 🗑 All system
admin-back-to-chats = ‹ Back to the list
admin-default-player = Player
admin-note-excluded =   excluded
admin-note-invalid =   login expired
admin-note-revoked =   unsubscribed

## Chat admins (#232)
admin-on = on
admin-off = off
admin-chat-admin-none = none
admin-chat-admin-button = 👤 Chat admin ▸
admin-chat-admin-pick =
    👤 Chat admin: { $admin }

    Who gets the role? Listed are those subscribed to the chat or who wrote in it.
admin-chat-admin-hand-on =
    👤 You are this chat's admin.

    Who gets the role? You will lose it. Listed are those subscribed to the chat or who wrote in it.
admin-chat-admin-nobody = Nobody to give the role to yet: a person has to subscribe to the chat or write in it.
admin-chat-admin-remove = ✖️ Remove the admin
admin-chat-admin-confirm = Make { $name } the admin of «{ $title }»?
admin-chat-admin-confirm-hand-on = Hand the admin role of «{ $title }» to { $name }? You will lose it.
admin-chat-admin-confirm-yes = Yes
admin-chat-admin-remove-confirm = Take the chat admin role of «{ $title }» from { $name }?
admin-chat-admin-set = The chat admin is now { $name }.
admin-chat-admin-removed = The chat has no admin now.
admin-chat-admin-handed-on = Done: { $name } is now the admin of «{ $title }».
admin-chat-admin-you =
    👤 You are now the admin of «{ $title }».

    Its settings and messages are in /admin, or under «Manage the chat» in the group's /panel.
admin-chat-admin-only = Only for the chat admin
admin-not-allowed = That's not for you.
admin-chats-mine-empty = You don't admin any chat yet.

## Roles (#232)
admin-role = Role: { $role }
admin-role-user = user
admin-role-admin = app admin
admin-role-superadmin = super-admin
admin-role-make_admin = ⭐ Make an admin
admin-role-make_superadmin = 👑 Make a super-admin
admin-role-unmake_admin = Remove the admin role
admin-role-unmake_superadmin = Remove super-admin (keep admin)
admin-role-make_admin-confirm = Make { $name } an app admin? They get the people, chats, settings and the season pass — not the keys, not deleting.
admin-role-make_superadmin-confirm = Make { $name } a super-admin? They get everything: keys, deleting people, roles.
admin-role-unmake_admin-confirm = Take the app admin role from { $name }?
admin-role-unmake_superadmin-confirm = Take super-admin from { $name }? They stay an app admin.
admin-role-confirm-yes = Yes
admin-role-done = Role: { $role }
