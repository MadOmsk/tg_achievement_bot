# Entry-point messages (bot/main.py) — not aiogram handlers, so these are
# resolved via bot.i18n.gettext() rather than I18nContext DI.

# on_linked() — right after a successful Xbox OAuth callback
main-linked = ✅ XBOX connected: { $gamertag }
main-linked-subscribed-origin-chat = I also subscribed you to publishing in the chat you came from.

# Default gamertag placeholder used by startup catch-up when the user row
# has none cached yet.
main-default-player-name = Player

# Command menu (private chat scope)
# Bot command descriptions
main-cmd-panel = My panel and settings
main-cmd-stats-private = My stats
main-cmd-hltb = How long is this game (HowLongToBeat)
main-cmd-help = What I can do

# Command menu (group chat scope)
main-cmd-panel-group = Chat menu and buttons
main-cmd-stats-group = A player's stats
main-cmd-online = Who's online right now
main-cmd-who = Look up someone's stats
main-cmd-recent = The chat's latest achievements
main-cmd-summary-day = The last 24 hours in review
main-cmd-summary-month = The month so far in review
main-cmd-subscribe = Publish my achievements here
main-cmd-unsubscribe = Stop publishing here
main-cmd-app = Open the app
main-menu-open-app = App

# Second-instance guard (main())
main-already-running =
    The bot is already running — a second copy isn't needed.
    Two bots on one token steal each other's Telegram updates.
    State: manage.bat status

# Release announcements (services/release_notify.py)
main-release-announced = 🚀 <b>Bot has been updated to version { $version }!</b>
main-release-summary-header = <b>Highlights of this release:</b>
main-release-details-prompt = See what's new in this release:
main-release-button = 📖 Release Notes
main-test-release-announced = 🧪 <b>Test bot has been updated to version { $version }!</b>
