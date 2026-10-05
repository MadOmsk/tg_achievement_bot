# Steam admin card refresh (poller/steam_fetcher.py's refresh_user) — an
# admin-panel-triggered one-off call, no aiogram I18nContext of its own,
# resolved via bot.i18n.gettext.
# Achievement polling status
steamfetcher-refresh-failed = Couldn't refresh: { $error }
steamfetcher-no-profile = Steam returned no profile (hidden or deleted).
steamfetcher-no-game = no game
steamfetcher-online = online, { $where }
steamfetcher-offline = offline
steamfetcher-refreshed = Refreshed: { $state }; new achievements: { $published }.
steamfetcher-not-configured = The Steam key isn't set — set it in “🔑 Platform keys”.
