# Administrator panel (handlers/admin.py). Keeping these strings here also
# makes callback alerts and generated cards follow the same locale as menus.
admin-unlimited = без ограничения
admin-disabled = выключено
admin-no-delay = без задержки
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
admin-setting-recent-rows = Достижений в /recent
admin-setting-hltb-results = Результатов поиска и подсказок HLTB
admin-setting-hltb-page = Результатов на странице (HLTB)
admin-setting-system-ttl = Автоудаление системных сообщений (мин)
admin-setting-online-interval = Интервал автообновления /online (мин)
admin-setting-online-ttl = Автообновление /online, часов
admin-setting-key-check = Проверка ключей / автообновление /admin (мин)
admin-setting-monthly-delay = Задержка итогов месяца (мин)
admin-setting-account-reset-cooldown = Кулдаун после сброса (часы)
admin-setting-email-sends-client = Кодов на почту с одного IP в час
admin-setting-email-provider-daily = Лимит почтового сервиса в сутки
admin-setting-email-sends-total = Кодов на почту всего в час
admin-setting-email-checks-client = Проверок кода с одного IP за 10 минут
admin-setting-patch-refresh = Обновление патчей игр (часы)

# Platform keys (#17; Anthropic added 2026-09-09 — achievement-description
# translation only, same admin-settable-shared-credential shape)
admin-keys-title = 🔑 Ключи платформ
admin-keys-line = { $label }: { $state }
admin-keys-psn-label = PSN
admin-keys-steam-label = Steam
admin-keys-anthropic-label = Anthropic
admin-keys-youtube-label = YouTube
admin-keys-smtp-label = Почта (SMTP)
# One line under the field in the Mini App, where the long prompt does not fit.
admin-keys-psn-hint = Значение npsso с ca.account.sony.com/api/v1/ssocookie, войдя на my.playstation.com.
admin-keys-steam-hint = Ключ Steam Web API: steamcommunity.com/dev/apikey.
admin-keys-anthropic-hint = Ключ API: console.anthropic.com → Settings → API Keys.
admin-keys-youtube-hint = Ключ YouTube Data API v3 из console.cloud.google.com.
admin-keys-smtp-hint = Логин и SMTP-ключ через пробел: «логин ключ».
admin-keys-set = ✅ настроен
admin-keys-unset = ⚠️ не настроен
admin-keys-steam-add = Задать ключ Steam
admin-keys-steam-change = Сменить ключ Steam
admin-keys-steam-clear = Убрать ключ Steam
admin-keys-psn-add = Задать NPSSO (PSN)
admin-keys-psn-change = Сменить NPSSO (PSN)
admin-keys-psn-clear = Убрать NPSSO (PSN)
admin-keys-anthropic-add = Задать ключ Anthropic
admin-keys-anthropic-change = Сменить ключ Anthropic
admin-keys-anthropic-clear = Убрать ключ Anthropic
admin-keys-youtube-add = Задать ключ YouTube
admin-keys-youtube-change = Сменить ключ YouTube
admin-keys-youtube-clear = Убрать ключ YouTube
admin-keys-steam-prompt =
    Пришли Steam Web API key одним сообщением — получить его:
    https://steamcommunity.com/dev/apikey
admin-keys-steam-invalid = Ключ Steam не подошёл — проверь и пришли ещё раз.
admin-keys-steam-saved =
    Ключ Steam сохранён.

    { $text }
admin-keys-psn-prompt =
    Пришли NPSSO одним сообщением — получить его: войди на my.playstation.com,
    затем открой https://ca.account.sony.com/api/v1/ssocookie и скопируй
    значение «npsso» из JSON на экране.
admin-keys-psn-saved =
    NPSSO сохранён.

    { $text }
admin-keys-anthropic-prompt =
    Пришли Anthropic API key одним сообщением — получить его:
    console.anthropic.com → Settings → API Keys → Create Key
    (нужен привязанный способ оплаты — ключ платный, но перевод коротких
    описаний достижений стоит копейки на Haiku).
admin-keys-anthropic-invalid = Ключ Anthropic не подошёл — проверь и пришли ещё раз.
admin-keys-anthropic-saved =
    Ключ Anthropic сохранён.

    { $text }
admin-keys-youtube-prompt =
    Пришли ключ YouTube Data API одним сообщением — получить его:
    console.cloud.google.com → включить «YouTube Data API v3» →
    Credentials → Create credentials → API key (бесплатно).
admin-keys-youtube-invalid = Ключ YouTube не подошёл — проверь и пришли ещё раз.
admin-keys-youtube-saved =
    Ключ YouTube сохранён.

    { $text }

admin-keys-smtp-add = Задать вход почты (SMTP)
admin-keys-smtp-change = Сменить вход почты (SMTP)
admin-keys-smtp-clear = Убрать вход почты (SMTP)
admin-keys-smtp-prompt =
    Пришли логин и ключ почтового сервера одним сообщением, через пробел:
    логин ключ
    Для Brevo: SMTP & API → SMTP — логин вида …@smtp-brevo.com и SMTP-ключ
    (Generate a new SMTP key). Для Gmail: адрес ящика и пароль приложения.
    Сервер и адрес отправителя берутся из .env (SMTP_HOST, SMTP_FROM).
admin-keys-smtp-invalid = Почтовый сервер не пустил с этими данными — проверь логин и ключ и пришли ещё раз (два слова через пробел).
admin-keys-smtp-saved =
    Вход почты сохранён — коды для входа уходят с ним.

    { $text }

# PSN status and one-line messages
admin-keys-psn-invalid = NPSSO не подошёл — Sony его не приняла. Проверь и пришли ещё раз.
admin-keys-setup-error = Не получилось создать клиент PSN — техническая ошибка на сервере ({ $error }). NPSSO тут, скорее всего, ни при чём — посмотри логи бота.

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
admin-rare-prompt =
    💎 Порог «редкого» достижения, один для всех чатов: { $value }%

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

# Anti-flood filter (2026-09-09): after N individually-notified achievements
# for one person land in this chat within the window, further ones stop
# posting on their own and get grouped into one message once the window
# closes. 0 = off for this chat.
admin-chat-flood-prompt =
    Антиспам-фильтр в «{ $title }»: { $value } ач.

    Пришли новое значение целым числом, от { $minimum } до { $maximum } (0 — выключить).
    Действует только на этот чат.
admin-chat-flood-window-prompt =
    Окно антиспам-фильтра в «{ $title }»: { $value } мин

    Пришли новое значение целым числом, от { $minimum } до { $maximum }.
    Действует только на этот чат.
admin-flood-saved = Антиспам-фильтр: { $value } ач.

{ $text }
admin-flood-window-saved = Окно антиспам-фильтра: { $value } мин

{ $text }

# User and message actions
admin-user-excluded = Исключён
admin-user-restored = Возвращён
admin-user-not-connected = Не подключён
admin-refreshing = Обновляю…
admin-refresh-failed = Не получилось обновить
# Вторая строка ответа «🔄 Обновить»: что нашлось с момента последнего
# известного достижения. Публикуется только то, что попадает в обычное окно
# догона, остальное молча сохраняется.
admin-sync-delta =
    { $titles ->
        [0] Новых игр с прошлого раза нет.
       *[other] Просмотрено игр: { $titles }, опубликовано: { $published }.
    }
admin-sync-delta-steam = Опубликовано с прошлого раза: { $published }.
admin-steam-not-connected = Steam не подключён
admin-psn-not-connected = PSN не подключён

# Chat and cleanup actions
admin-chat-disabled = Отключён
admin-chat-enabled = Включён
admin-no-bot-messages = Не нашёл сообщений бота в этом чате.
admin-delete-old-failed = Не смог удалить — возможно, сообщение слишком старое.
admin-deleted-last = 🗑 Удалил последнее сообщение.
# Toast text (2026-09-09) — Telegram caps this at 200 chars total, see
# handlers/admin.py's own TOAST_PREVIEW_MAX_CHARS/_toast_preview.
admin-deleted-last-preview = 🗑 Удалил: «{ $preview }»
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
admin-send-promo-to-chat = 📢 Отправить промо в чат
admin-promo-sent = Промо-сообщение отправлено в чат

# New users and user cards
admin-new-users-screen =
    👤 Новые пользователи — настройки по умолчанию

    Действует только на подписки, оформленные с этого момента — уже существующие
    не трогает.
admin-default-rarity = Достижения по умолчанию: { $rarity } ▸
admin-rare-row = 💎 Порог редкости: { $value }% ▸
admin-show-links = Ссылки на профили в карточках: { $visible } ▸
admin-users-empty = 👥 Пока никто не подключился.
admin-users-header = 👥 Пользователи
admin-users-columns = Колонки: когда был в сети · достижений сегодня / за месяц
admin-users-row = { $icon } { $name } · { $ago } · { $today} / { $month }{ $note }
admin-user-not-found = Пользователь не найден.
admin-user-header = 👤 { $name } · id { $person_id }
# $tg_id and $person_id arrive as strings on purpose — as a number Fluent
# groups the digits, and an identifier is not a quantity.
admin-logins-title = Способы входа:
admin-logins-row = { "  " }{ $label }: { $value }
admin-logins-telegram = Telegram
admin-logins-email = Почта
admin-logins-tg-id = id { $tg_id }
admin-logins-none = — нет
admin-login-not-connected = не подключён
admin-login-active = ✅ активен, обновлён { $ago }
admin-login-invalid = ⚠️ протух
admin-login-revoked = 🔕 отключён самим пользователем
admin-no-data = нет данных
admin-no-game = без игры
admin-online-playing = { $ago }, { $game }
admin-online-idle = в сети, не играет
admin-today-tag = сегодня { $count }
admin-gamerscore-tag = gamerscore { $score }

# One block per platform (2026-09-08 rework) — header line first (nickname +
# id + lifetime count + today's count [+ completions/level]), then whatever
# admin-only diagnostics apply to that platform on their own indented lines.
admin-xbox-header = 🟢 XBOX: { $gamertag }
admin-xuid-tag = XUID { $xuid }
admin-login-row =   Вход: { $login }
admin-online-row =   В сети: { $online }
admin-muted-row =   🔇 публикация выключена владельцем
admin-steam-header = ⚫ Steam: { $name }
admin-steamid-tag = id { $external_id }
admin-psn-header = 🔵 PSN: { $name }
admin-psn-id-tag = account_id { $external_id }
admin-psn-level-tag = уровень { $level }

admin-nowhere = нигде
admin-subscribed = Подписан: { $chats }
admin-excluded = 🚫 Исключён из системы: не опрашивается и не публикуется.
admin-restore = ↩️ Вернуть
admin-exclude = 🚫 Исключить из системы
admin-refresh-xbox = 🔄 Обновить XBOX
admin-refresh-steam = 🔄 Обновить Steam
admin-refresh-psn = 🔄 Обновить PSN
admin-reset-xbox = 🗑 Сброс XBOX
admin-reset-steam = 🗑 Сброс Steam
admin-reset-psn = 🗑 Сброс PSN
# One pair per PSN account when a person holds several (#10).
admin-refresh-psn-account = 🔄 Обновить PSN: { $name }
admin-reset-psn-account = 🗑 Сброс PSN: { $name }
admin-reset-confirm-prompt =
    Стереть базу { $platform } для этого пользователя и синхронизировать заново?

    Это необратимо: вся история достижений/трофеев по этой платформе будет
    удалена и перечитана с нуля (в чат ничего не публикуется — как при
    первой привязке).
admin-reset-confirm-yes = Да, стереть и пересинхронизировать
admin-reset-avatar = 🖼 Сбросить аватар
admin-avatar-reset = Аватар сброшен на фото из Telegram
admin-delete-user = 🗑 Удалить пользователя
admin-delete-confirm-1 =
    Удалить пользователя { $name } (ID: { $tg_id })?

    Будут удалены все привязки к аккаунтам, настройки пользователя и подписки на чаты.
admin-delete-confirm-1-yes = ⚠️ Да, продолжить
admin-delete-confirm-2 =
    Внимание! Это действие необратимо!

    Безвозвратно стереть пользователя { $name } (ID: { $tg_id }) из базы данных?
admin-delete-confirm-2-yes = 🔥 Точно удалить пользователя
admin-delete-toast = Пользователь удалён
admin-delete-not-found = Пользователь не найден
admin-back-to-users = ‹ К списку

# Chat cards
admin-chats-empty = Бот пока не добавлен ни в один чат.
admin-chats-header = 💬 Чаты  (название · сколько человек публикуется)
admin-chat-list-row = { $mark }{ $title } · { $subscribers }
admin-chat-card =
    💬 { $title }

    Состояние:    { $state }
    Публикуется:  { $subscribers } чел.
    Дайджест:     { $digest }
    Итог дня:     { $summary }, в { $time }
    Часовой пояс: { $offset }
    Мин. G:       { $min_score }
    Антиспам:     { $flood }
    Язык:         { $locale_name }

    { $names }
admin-chat-flood-value = { $limit } ач. / { $window } мин
admin-chat-flood-off = выключен
admin-no-subscribers = Подписанных пока нет.
admin-subscribers-list = Подписаны: { $names }
admin-chat-digest-button = Дайджест: { $digest } ▸
admin-digest-from = от { $value } ач.
admin-digest-never = никогда
admin-chat-summary-button = Итог дня: { $state }
admin-chat-time-button = Время итога: { $time } ({ $offset }) ▸
admin-chat-flood-toggle-button = Антиспам-фильтр: { $state }
admin-chat-flood-button = Антиспам: { $limit } ач. ▸
admin-chat-summary-menu-button = Итог дня: { $state } ▸
admin-chat-flood-menu-button = Антиспам: { $value } ▸
admin-chat-messages-menu-button = 🗑 Сообщения ▸
admin-chat-locale-button = Язык: { $name }
admin-chat-flood-window-button = Окно антиспама: { $window } мин ▸
admin-disable-chat = ⏸ Отключить чат
admin-enable-chat = ▶️ Включить чат
admin-delete-last = 🗑 Последнее
admin-wipe-bot-24h = 🗑 Бота (24ч)
admin-wipe-system-24h = 🗑 Системные (24ч)
admin-wipe-system-all = 🗑 Все системные
admin-back-to-chats = ‹ К списку
admin-default-player = Игрок
admin-note-excluded =   исключён
admin-note-invalid =   вход протух
admin-note-revoked =   отписался
