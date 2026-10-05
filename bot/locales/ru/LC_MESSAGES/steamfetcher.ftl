# Steam admin card refresh (poller/steam_fetcher.py's refresh_user) — an
# admin-panel-triggered one-off call, no aiogram I18nContext of its own,
# resolved via bot.i18n.gettext.
# Achievement polling status
steamfetcher-refresh-failed = Не удалось обновить: { $error }
steamfetcher-no-profile = Steam не вернул профиль (скрыт или удалён).
steamfetcher-no-game = без игры
steamfetcher-online = в сети, { $where }
steamfetcher-offline = не в сети
steamfetcher-refreshed = Обновлено: { $state }; новых достижений { $published }.
steamfetcher-not-configured = Ключ Steam не настроен — задай его в «🔑 Ключи платформ».
