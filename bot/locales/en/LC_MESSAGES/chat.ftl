# Subscription
chat-subscribe-groups-only = This command is for a group chat — that's where publishing happens.
chat-subscribe-connect-first = Connect at least one platform first — buttons below.
chat-subscribe-already = You're already publishing here.
chat-subscribe-done = Done. { $gamertag }'s achievements will land here.
    Rarity and XBOX 360 settings are in a DM, /panel.
chat-unsubscribe-not-subscribed = You weren't publishing here anyway.
chat-unsubscribe-confirm-button = Yes, unsubscribe
chat-cancel-button = Cancel
chat-unsubscribe-prompt = Stop publishing your achievements in this chat?
chat-not-your-button = That's not your button.
chat-unsubscribe-done = I'll stop publishing your achievements in this chat.

# Statistics and presence
chat-stats-no-gamertag = no gamertag
# No leading spaces here (2026-09-08 fix) — Fluent's own whitespace handling
# on a single-line value is not reliable enough to lean on for a "  ·  "
# separator (found live: it silently collapsed to one side only). The
# caller builds that separator itself, in Python, like every other segment
# joined onto this same line.
chat-stats-psn-level = level { $level }
chat-stats-today = Last 24h:  { $achievements }{ $breakdown }{ $value }
chat-stats-month = Since { $month } 1:  { $achievements }{ $breakdown }{ $value }
chat-stats-games-header = <b>Games { $window }</b>
chat-stats-nothing-connected = This person hasn't connected anything yet.
chat-group-command-only = The player list is per chat — run the command in a group.
chat-online-empty = I haven't seen anyone connected in this chat yet.
chat-who-prompt = Whose stats do you want?
chat-user-not-found = I couldn't find that user.

# Summary and recent feed
chat-summary-group-only = The summary is per chat — run the command in a group.
chat-summary-empty = Nobody in this chat has connected an account yet — there's no one to sum up.
chat-recent-group-only = The feed is per chat — run the command in a group.
chat-recent-empty = Nothing here yet.
chat-recent-header = 🕘 <b>Latest achievements</b>
chat-untitled = untitled
chat-recent-row = { $badge } { $gamertag } — { $icon } { $game } · { $name }{ $tail } · { $ago }

# Group hub and chat actions
chat-unknown-user = I don't know them. The Bot API can't look people up by @name — I remember the ones who have written in the chat. You can also reply to their message with /stats.
chat-help-text = 🎮 I watch the achievements and trophies of everyone playing on XBOX, PlayStation and Steam and post them here — with a rarity filter, personal stats, and a daily summary.

    Chat commands:
    /app — open the app
    /stats [@who] — stats: yours with no argument, someone else's with a name
    /who — look up a specific player's stats
    /online — who's in a game right now
    /recent [N] — the chat's latest achievements
    /summary_day — the last 24 hours in review
    /summary_month — the month so far in review
    /hltb — a game's HowLongToBeat summary

    Settings are in a DM, /panel.
chat-help-version = <i>Version { $version }</i>
chat-hub-nobody = Nobody is publishing here yet.
chat-hub-publishing = Publishing: { $names }
chat-hub-publish-button = ✅ Publish my achievements
chat-hub-xbox-button = 🔗 XBOX
chat-hub-steam-button = 🎮 Steam
chat-hub-psn-button = 🎮 PSN
chat-hub-settings-button = ⚙️ Settings
chat-hub-open-app = Open the app
chat-app-hint = Open in the app:
chat-app-no-url = The app is not configured yet (no MINI_APP_URL).
chat-subscribe-button-done = Done, your achievements will land here.
chat-delete-last-none = I found no messages of mine in this chat.
chat-delete-last-failed = Couldn't delete it — the message may be too old.
chat-delete-last-done =
    🗑 Deleted this message:
    “{ $preview }”
chat-delete-last-done-generic = 🗑 Message deleted.
