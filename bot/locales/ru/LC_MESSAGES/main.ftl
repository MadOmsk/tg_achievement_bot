# Entry-point messages (bot/main.py) — not aiogram handlers, so these are
# resolved via bot.i18n.gettext() rather than I18nContext DI.
# Backfill failure/success DMs (run() -> backfill())
# Startup and backfill
main-backfill-failed =
    Не смог перечитать твою историю достижений. Публикация пока выключена,
    чтобы не завалить чат — напиши /connect_xbox ещё раз чуть позже.
main-backfill-done = Готово: перечитал { $count } уже выбитых достижений — в чат они не полетят. Дальше публикую только новые.

# on_linked() — right after a successful Xbox OAuth callback
main-linked = ✅ Подключил XBOX: { $gamertag }
main-linked-subscribed-origin-chat = Заодно подписал на публикацию в чате, откуда ты пришёл.
main-linked-backfill-starting = Читаю твою историю достижений, это займёт минуту…
main-linked-refreshing = Обновляю статистику…

# Default gamertag placeholder used by startup catch-up when the user row
# has none cached yet.
main-default-player-name = Игрок

# Command menu (private chat scope)
# Bot command descriptions
main-cmd-panel = Моя панель и настройки
main-cmd-stats-private = Моя статистика
main-cmd-connect-xbox = Подключить XBOX
main-cmd-disconnect-xbox = Отключить XBOX
main-cmd-connect-steam = Подключить Steam
main-cmd-disconnect-steam = Отключить Steam
main-cmd-connect-psn = Подключить PSN
main-cmd-disconnect-psn = Отключить PSN
main-cmd-hltb = Сколько идти игру (HowLongToBeat)
main-cmd-help = Что я умею

# Command menu (group chat scope)
main-cmd-stats-group = Статистика игрока
main-cmd-online = Онлайн-статус игроков
main-cmd-who = Узнать стату юзера
main-cmd-recent = Последние достижения чата
main-cmd-summary = Сводка за сутки и за месяц
main-cmd-subscribe = Публиковать мои достижения здесь
main-cmd-unsubscribe = Перестать публиковать

# Second-instance guard (main())
main-already-running =
    Бот уже запущен — вторая копия не нужна.
    Два бота с одним токеном отбирают друг у друга сообщения Telegram.
    Состояние: manage.bat status
