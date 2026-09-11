# PSN admin-card resync (poller/psn_fetcher.py's refresh_user, #27) — an
# admin-panel-triggered one-off call, no aiogram I18nContext of its own,
# resolved via bot.i18n.gettext. Mirrors steamfetcher.ftl.
psnfetcher-resync-failed = Couldn't resync PSN — details in the logs.
psnfetcher-resynced-backfill = The first sync had never finished — read the history back from scratch: { $stored } trophies. Nothing was posted to any chat.
psnfetcher-resynced-poll = Refreshed; new trophies: { $published }.
