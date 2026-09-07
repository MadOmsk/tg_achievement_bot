# Administrator panel (handlers/admin.py). Keeping these strings here also
# makes callback alerts and generated cards follow the same locale as menus.
admin-unlimited = без ограничения
admin-disabled = выключено
admin-back = ‹ Назад
admin-cancel = Отмена
admin-yes = да
admin-no = нет
admin-enabled = включён
admin-disabled-state = выключен
admin-active = активен
admin-inactive = отключён

# Runtime settings
admin-setting-summary-rows = Строк в /summary
admin-setting-stats-games = Игр в /stats
admin-setting-hltb-results = Результатов поиска и подсказок HLTB
admin-setting-hltb-page = Результатов на странице (HLTB)
admin-setting-system-ttl = Автоудаление системных сообщений (мин)
admin-setting-online-interval = Интервал автообновления /online (мин)
admin-setting-online-ttl = Автообновление /online, часов
admin-setting-key-check = Проверка ключей / автообновление /admin (мин)

# PSN prompts
admin-psn-npsso-prompt =
    Пришли новый NPSSO одним сообщением — получить его: войди на
    my.playstation.com, затем открой
    https://ca.account.sony.com/api/v1/ssocookie и скопируй значение
    «npsso» из JSON на экране.
admin-psn-test-unconfigured =
    🏆 Трофеи PSN (тест)

    PSN ещё не настроен. Пришли NPSSO одним сообщением — получить его: войди на
    my.playstation.com, затем открой
    https://ca.account.sony.com/api/v1/ssocookie и скопируй значение
    «npsso» из JSON на экране.
admin-psn-test-prompt =
    🏆 Трофеи PSN (тест)

    Пришли PSN Online ID — покажу последние выбитые трофеи вживую, без кэша
    (имя, тир, редкость, скрытость и иконки одной медиа-группой).

# PSN status and one-line messages
admin-psn-change = Сменить NPSSO
admin-psn-npsso-invalid = NPSSO не подошёл — Sony его не приняла. Проверь и пришли ещё раз.
admin-psn-client-error = Не получилось создать клиент PSN — техническая ошибка на сервере ({ $error }). NPSSO тут, скорее всего, ни при чём — посмотри логи бота.
admin-psn-configured-prompt = PSN настроен. Пришли PSN Online ID, чтобы проверить трофеи.
admin-psn-token-dead = PSN сейчас недоступен — токен протух, обнови NPSSO через /admin.
admin-psn-private = Профиль есть, но трофеи закрыты для сервисного аккаунта.
admin-psn-not-found = Не нашёл: { $error }
admin-psn-no-trophies = { $online_id }: трофеев не нашёл (или все скрыты).
admin-psn-recent-header = 🏆 { $online_id } — последние { $count } трофеев:
admin-psn-rarity = , { $percent }% игроков
admin-psn-hidden =  (скрытый)
admin-psn-trophy-row = { $badge } { $name }{ $secret } — { $title }{ $rarity }
admin-psn-detail =     { $detail }

# Limits and input prompts
admin-limits-screen =
    ⚙️ Глобальные настройки

    Списки /summary и /stats можно сделать безлимитными (0) — они и так лежат
    в сворачиваемой цитате, урезать нечего.
admin-limit-prompt = { $label }: { $current }

    Пришли новое значение целым числом, от { $minimum } до { $maximum }{ $zero_hint }.
admin-number-range-retry = Число должно быть от { $minimum } до { $maximum }. Ещё раз?
admin-threshold-saved = Порог редкости: { $value }%

{ $text }
admin-integer-retry = Здесь только целое число. Ещё раз?
admin-timezone-button = Часовой пояс ▸
admin-timezone-manual = ✏️ Ввести вручную
admin-chat-not-found = Чат не найден
admin-chat-not-found-period = Чат не найден.

# Chat settings prompts
admin-chat-threshold-prompt =
    Порог «редкого» достижения в «{ $title }»: { $value }%

    Пришли новое значение одним числом, например 12 или 7.5 — от 0 до 100.
    Действует только на этот чат.
admin-chat-time-prompt = Время итога дня в «{ $title }»: { $time }
admin-chat-time-saved = Итог дня в { $time }
admin-chat-zone-prompt = Часовой пояс «{ $title }»: { $offset }
admin-chat-zone-manual-prompt =
    Часовой пояс «{ $title }»: { $offset }

    Пришли смещение одним сообщением, со знаком: например +3, -5 или +5:30.
admin-timezone-invalid = Это не похоже на реальный часовой пояс. Например: +3 или -5:30.
admin-timezone-saved = Часовой пояс: { $offset }

{ $text }

# User and message actions
admin-user-excluded = Исключён
admin-user-restored = Возвращён
admin-user-not-connected = Не подключён
admin-refreshing = Обновляю…
admin-refresh-failed = Не получилось обновить
admin-steam-not-connected = Steam не подключён

# Chat and cleanup actions
admin-chat-disabled = Отключён
admin-chat-enabled = Включён
admin-no-bot-messages = Не нашёл сообщений бота в этом чате.
admin-delete-old-failed = Не смог удалить — возможно, сообщение слишком старое.
admin-deleted-last = Удалил последнее сообщение.
admin-no-bot-messages-24h = За последние 24 часа сообщений бота не нашёл.
admin-confirm-delete = Да, стереть
admin-wipe-prompt =
    Стереть { $count } сообщений бота в «{ $title }» за последние { $hours } часа?

    Необратимо. Считаются только сообщения, отправленные с тех пор, как завели
    этот учёт, — более старые бот не помнит.
admin-wipe-done = Готово.
admin-wipe-partial = Частично — что-то не далось стереть.
admin-no-system-messages = Системных сообщений не нашёл.
admin-system-wipe-prompt =
    Стереть { $count } системных сообщений в «{ $title }»?

    Достижений, /stats, /summary и итога дня это не касается — только
    промежуточные сообщения (подсказки, подтверждения, /help и т.п.).

# New users and user cards
admin-new-users-screen =
    👤 Новые пользователи — настройки по умолчанию

    Действует только на подписки, оформленные с этого момента — уже существующие
    не трогает.
admin-default-rarity = Ачивки по умолчанию: { $rarity } ▸
admin-default-links = Профиль виден другим: { $visible } ▸
admin-users-empty = 👥 Пока никто не подключился.
admin-users-header = 👥 Пользователи  ({ $page }/{ $pages })
admin-users-columns = Колонки: когда был в сети · достижений сегодня / за месяц
admin-id = id{ $tg_id }
admin-users-row = { $icon } { $name } · { $ago } · { $today} / { $month }{ $note }
admin-user-not-found = Пользователь не найден.
admin-no-name = без имени
admin-user-header = 👤 { $name }
admin-login-not-connected = — не подключён
admin-login-active = ✅ активен, обновлён { $ago }
admin-login-invalid = ⚠️ протух
admin-login-revoked = 🔕 отключён самим пользователем
admin-no-data = нет данных
admin-no-game = без игры
admin-online-playing = { $ago }, { $game }
admin-online-idle = в сети, не играет
admin-xbox-line = 🟢 XBOX  ·  XUID { $xuid }  ·  gamerscore { $score }
admin-xbox-login =   Вход активен (XBOX): { $login }
admin-xbox-online =   В сети (XBOX):       { $online }
admin-steam-line = ⚫ Steam  ·  id { $external_id }
admin-display-name =   { $name }
admin-steam-online =   В сети (Steam):      { $online }
admin-psn-line = 🔵 PSN  ·  account_id { $external_id }
admin-nowhere = нигде
admin-subscribed = Подписан: { $chats }
admin-counters = Ачивок:   сегодня { $today } · за месяц { $month }
admin-excluded = 🚫 Исключён из системы: не опрашивается и не публикуется.
admin-restore = ↩️ Вернуть
admin-exclude = 🚫 Исключить из системы
admin-refresh-xbox = 🔄 Обновить XBOX
admin-refresh-steam = 🔄 Обновить Steam
admin-back-to-users = ‹ К списку

# Chat cards
admin-chats-empty = Бот пока не добавлен ни в один чат.
admin-chats-header = 💬 Чаты  (название · сколько человек публикуется)
admin-chat-list-row = { $mark }{ $title } · { $subscribers }
admin-chat-card =
    💬 { $title }

    Состояние:    { $state }
    Публикуется:  { $subscribers } чел.
    Порог редк.:  { $threshold }
    Итог дня:     { $summary }, в { $time }
    Часовой пояс: { $offset }
    Мин. G:       { $min_score }

    { $names }
admin-no-subscribers = Подписанных пока нет.
admin-subscribers-list = Подписаны: { $names }
admin-chat-threshold-button = Порог редкости: { $threshold } ▸
admin-chat-summary-button = Итог дня: { $state }
admin-chat-time-button = Время итога: { $time } ({ $offset }) ▸
admin-disable-chat = ⏸ Отключить чат
admin-enable-chat = ▶️ Включить чат
admin-delete-last = 🗑 Удалить последнее сообщение
admin-wipe-bot-24h = 🧹 Стереть сообщения бота (24ч)
admin-wipe-system-24h = 🧹 Удалить системные (24ч)
admin-wipe-system-all = 🧹 Удалить все системные
admin-back-to-chats = ‹ К списку
admin-default-player = Игрок
admin-note-excluded =   исключён
admin-note-invalid =   вход протух
admin-note-revoked =   отписался
