# PSN admin-card resync (poller/psn_fetcher.py's refresh_user, #27) — an
# admin-panel-triggered one-off call, no aiogram I18nContext of its own,
# resolved via bot.i18n.gettext. Mirrors steamfetcher.ftl.
psnfetcher-resync-failed = Не удалось пересинхронизировать PSN — подробности в логах.
psnfetcher-resynced-backfill = Первичная синхронизация не была завершена — перечитал историю заново: { $stored } трофеев. В чат ничего не полетело.
psnfetcher-resynced-poll = Обновлено; новых трофеев { $published }.
