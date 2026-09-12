# Subscription
chat-subscribe-groups-only = Эта команда для группового чата — там, где нужны публикации.
chat-subscribe-connect-first = Сначала подключи хотя бы одну платформу — кнопки ниже.
chat-subscribe-already = Ты уже публикуешься здесь.
chat-subscribe-your-achievements = твои
chat-subscribe-done = Готово. Ачивки { $gamertag } будут прилетать сюда.
    Настройки редкости и XBOX 360 — в личке, /panel.
chat-unsubscribe-not-subscribed = Ты здесь и не публиковался.
chat-unsubscribe-confirm-button = Да, отписаться
chat-cancel-button = Отмена
chat-unsubscribe-prompt = Перестать публиковать твои достижения в этом чате?
chat-not-your-button = Это не твоя кнопка.
chat-unsubscribe-done = Больше не публикую твои достижения в этом чате.

# Statistics and presence
chat-stats-game-row-tail = { $count } ач.{ $score_suffix }
chat-stats-no-gamertag = без геймертега
# No leading spaces here (2026-09-08 fix) — Fluent's own whitespace handling
# on a single-line value is not reliable enough to lean on for a "  ·  "
# separator (found live: it silently collapsed to one side only). The
# caller builds that separator itself, in Python, like every other segment
# joined onto this same line.
chat-stats-psn-level = уровень { $level }
chat-stats-today = Сегодня:   { $achievements }{ $breakdown }{ $score_suffix }
chat-stats-month = За месяц:  { $achievements }{ $breakdown }{ $score_suffix }
chat-stats-games-header = <b>Игры за { $days } дней</b>
chat-stats-nothing-connected = Этот человек ещё ничего не подключил.
chat-group-command-only = Список игроков — по чату, набери команду в группе.
chat-online-empty = Никого из подключённых в этом чате пока не видел.
chat-who-fallback-id = id{ $tg_id }
chat-who-prompt = Чья статистика интересует?
chat-user-not-found = Не нашёл такого пользователя.

# Summary and recent feed
chat-summary-group-only = Сводка считается по чату — набери команду в группе.
chat-summary-empty = В этом чате пока никто не подключил аккаунт — сводке не о ком.
chat-recent-group-only = Лента считается по чату — набери команду в группе.
chat-recent-empty = Пока пусто.
chat-recent-header = 🕘 <b>Последние достижения</b>
chat-recent-someone = кто-то
chat-untitled = без названия
chat-recent-row = { $badge } { $gamertag } — { $icon } { $game }, { $name }{ $tail } · { $ago }

# Group hub and chat actions
chat-unknown-user = Не знаю такого. Bot API не умеет искать людей по @имени — я запоминаю тех, кто писал в чат. Можно ответить на сообщение человека командой /stats.
chat-help-text = 🎮 Слежу за достижениями тех, кто играет на XBOX и в Steam, и публикую их сюда — с фильтром по редкости, статистикой каждого и итогом дня.

    Команды чата:
    /stats [@кто] — статистика: без аргумента своя, с ником — чужая
    /who — узнать стату конкретного игрока
    /online — кто сейчас в игре
    /recent [N] — последние достижения чата
    /summary — сводка за сутки и за месяц
    /hltb — показать сводку игры HowLongToBeat

    Настройки — в личке, /panel.
chat-hub-nobody = Пока здесь никто не публикуется.
chat-hub-publishing = Публикуются: { $names }
chat-hub-publish-button = ✅ Публиковать мои достижения
chat-hub-xbox-button = 🔗 XBOX
chat-hub-steam-button = 🎮 Steam
chat-hub-psn-button = 🎮 PSN
chat-hub-settings-button = ⚙️ Настройки
chat-subscribe-button-done = Готово, твои достижения будут прилетать сюда.
chat-delete-last-none = Не нашёл сообщений бота в этом чате.
chat-delete-last-failed = Не смог удалить — возможно, сообщение слишком старое.
chat-delete-last-done =
    🗑 Удалено сообщение:
    «{ $preview }»
chat-delete-last-done-generic = 🗑 Сообщение удалено.
