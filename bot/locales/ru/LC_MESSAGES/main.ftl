# Entry-point messages (bot/main.py) — not aiogram handlers, so these are
# resolved via bot.i18n.gettext() rather than I18nContext DI.

# on_linked() — right after a successful Xbox OAuth callback
main-linked = ✅ Подключил XBOX: { $gamertag }
main-linked-subscribed-origin-chat = Заодно подписал на публикацию в чате, откуда ты пришёл.

# Default gamertag placeholder used by startup catch-up when the user row
# has none cached yet.
main-default-player-name = Игрок

# Command menu (private chat scope)
# Bot command descriptions
main-cmd-panel = Моя панель и настройки
main-cmd-stats-private = Моя статистика
main-cmd-hltb = Сколько идти игру (HowLongToBeat)
main-cmd-help = Что я умею

# Command menu (group chat scope)
main-cmd-panel-group = Меню и кнопки чата
main-cmd-stats-group = Статистика игрока
main-cmd-online = Онлайн-статус игроков
main-cmd-who = Узнать стату юзера
main-cmd-recent = Последние достижения чата
main-cmd-summary-day = Сводка за сутки
main-cmd-summary-month = Сводка с 1 числа месяца
main-cmd-subscribe = Публиковать мои достижения здесь
main-cmd-unsubscribe = Перестать публиковать
main-cmd-app = Открыть приложение
main-menu-open-app = Приложение

# Second-instance guard (main())
main-already-running =
    Бот уже запущен — вторая копия не нужна.
    Два бота с одним токеном отбирают друг у друга сообщения Telegram.
    Состояние: manage.bat status

# Release announcements (services/release_notify.py)
main-release-announced = 🚀 <b>Бот обновлён до версии { $version }!</b>
main-release-summary-header = <b>Кратко о главных изменениях:</b>
main-release-details-prompt = Посмотрите подробный список изменений в этом обновлении:
main-release-button = 📖 Патчноутс
main-test-release-announced = 🧪 <b>Тестовый бот обновлён до версии { $version }!</b>
