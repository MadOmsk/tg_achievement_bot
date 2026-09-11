# Subscription
chat-subscribe-groups-only = This command is for a group chat — that's where publishing happens.
chat-subscribe-connect-first = Connect at least one platform first — buttons below.
chat-subscribe-already = You're already publishing here.
chat-subscribe-your-achievements = your
chat-subscribe-done = Done. { $gamertag }'s achievements will land here.
    Rarity and XBOX 360 settings are in a DM, /panel.
chat-unsubscribe-not-subscribed = You weren't publishing here anyway.
chat-unsubscribe-confirm-button = Yes, unsubscribe
chat-cancel-button = Cancel
chat-unsubscribe-prompt = Stop publishing your achievements in this chat?
chat-not-your-button = That's not your button.
chat-unsubscribe-done = I'll stop publishing your achievements in this chat.

# Statistics and presence
chat-stats-game-row-tail = { $count } ach.{ $score_suffix }
chat-stats-no-gamertag = no gamertag
# No leading spaces here (2026-09-08 fix) — Fluent's own whitespace handling
# on a single-line value is not reliable enough to lean on for a "  ·  "
# separator (found live: it silently collapsed to one side only). The
# caller builds that separator itself, in Python, like every other segment
# joined onto this same line.
chat-stats-psn-level = level { $level }
chat-stats-today = Today:      { $achievements }{ $breakdown }{ $score_suffix }
chat-stats-month = This month: { $achievements }{ $breakdown }{ $score_suffix }
chat-stats-games-header = <b>Games in the last { $days } days</b>
chat-stats-nothing-connected = This person hasn't connected anything yet.
chat-group-command-only = The player list is per chat — run the command in a group.
chat-online-empty = I haven't seen anyone connected in this chat yet.
chat-who-fallback-id = id{ $tg_id }
chat-who-prompt = Whose stats do you want?
chat-user-not-found = I couldn't find that user.

# Summary and recent feed
chat-summary-group-only = The summary is per chat — run the command in a group.
chat-summary-cooldown = A summary was sent recently. You can ask again in { $minutes } min.
chat-summary-empty = Nobody in this chat has connected an account yet — there's no one to sum up.
chat-recent-group-only = The feed is per chat — run the command in a group.
chat-recent-empty = Nothing here yet.
chat-recent-header = 🕘 <b>Latest achievements</b>
chat-recent-someone = someone
chat-untitled = untitled
chat-recent-row = { $badge } { $gamertag } — { $icon } { $game }, { $name }{ $tail } · { $ago }

# Group hub and chat actions
chat-unknown-user = I don't know them. The Bot API can't look people up by @name — I remember the ones who have written in the chat. You can also reply to their message with /stats.
chat-help-text = 🎮 I watch the achievements of everyone playing on XBOX and Steam and post them here — with a rarity filter, personal stats, and a daily summary.

    Chat commands:
    /stats [@who] — stats: yours with no argument, someone else's with a name
    /who — look up a specific player's stats
    /online — who's in a game right now
    /recent [N] — the chat's latest achievements
    /summary — the day and the month in review
    /hltb — a game's HowLongToBeat summary

    Settings are in a DM, /panel.
chat-hub-nobody = Nobody is publishing here yet.
chat-hub-publishing = Publishing: { $names }
chat-hub-publish-button = ✅ Publish my achievements
chat-hub-xbox-button = 🔗 XBOX
chat-hub-steam-button = 🎮 Steam
chat-hub-psn-button = 🎮 PSN
chat-hub-settings-button = ⚙️ Settings
chat-subscribe-button-done = Done, your achievements will land here.
chat-delete-last-none = I found no messages of mine in this chat.
chat-delete-last-failed = Couldn't delete it — the message may be too old.
chat-delete-last-done =
    🗑 Deleted this message:
    “{ $preview }”
chat-delete-last-done-generic = 🗑 Message deleted.
