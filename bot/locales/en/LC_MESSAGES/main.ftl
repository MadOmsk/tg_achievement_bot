# Entry-point messages (bot/main.py) — not aiogram handlers, so these are
# resolved via bot.i18n.gettext() rather than I18nContext DI.
# Backfill failure/success DMs (run() -> backfill())
# Startup and backfill
main-backfill-failed =
    I couldn't read back your achievement history. Publishing is off for now,
    so I don't flood the chat — run /connect_xbox again a little later.
main-backfill-done = Done: read back { $count } achievements you'd already unlocked — they won't be posted to the chat. From here on I only publish new ones.

# on_linked() — right after a successful Xbox OAuth callback
main-linked = ✅ XBOX connected: { $gamertag }
main-linked-subscribed-origin-chat = I also subscribed you to publishing in the chat you came from.
main-linked-backfill-starting = Reading your achievement history, this will take a minute…
main-linked-refreshing = Refreshing your stats…

# Default gamertag placeholder used by startup catch-up when the user row
# has none cached yet.
main-default-player-name = Player

# Command menu (private chat scope)
# Bot command descriptions
main-cmd-panel = My panel and settings
main-cmd-stats-private = My stats
main-cmd-connect-xbox = Connect XBOX
main-cmd-disconnect-xbox = Disconnect XBOX
main-cmd-connect-steam = Connect Steam
main-cmd-disconnect-steam = Disconnect Steam
main-cmd-connect-psn = Connect PSN
main-cmd-disconnect-psn = Disconnect PSN
main-cmd-hltb = How long is this game (HowLongToBeat)
main-cmd-help = What I can do

# Command menu (group chat scope)
main-cmd-stats-group = A player's stats
main-cmd-online = Who's online right now
main-cmd-who = Look up someone's stats
main-cmd-recent = The chat's latest achievements
main-cmd-summary = The day and the month in review
main-cmd-subscribe = Publish my achievements here
main-cmd-unsubscribe = Stop publishing here

# Second-instance guard (main())
main-already-running =
    The bot is already running — a second copy isn't needed.
    Two bots on one token steal each other's Telegram updates.
    State: manage.bat status
