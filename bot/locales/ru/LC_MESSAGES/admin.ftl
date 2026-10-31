# Administrator panel (handlers/admin.py). Keeping these strings here also
# makes callback alerts and generated cards follow the same locale as menus.
admin-unlimited = без ограничения
admin-disabled = выключено
admin-no-delay = без задержки
admin-back = ‹ Назад
admin-cancel = Отмена
admin-yes = да
admin-no = нет
admin-active = в чате
admin-inactive = не в чате

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
admin-setting-translation-batch = Перевод: игр в пачке
admin-translation-queue-on = 🌐 Очередь перевода выключена — включить
admin-translation-queue-on-confirm = Включить очередь перевода? Она сама тратит деньги на модель.
admin-translation-queue-on-yes = Да, включить
admin-translation-queue-off = 🌐 Очередь перевода включена — выключить
admin-translation-queue-now-on = Очередь перевода включена
admin-translation-queue-now-off = Очередь перевода выключена
admin-setting-translation-interval = Перевод: раз в сколько минут
admin-setting-octopus-per-tick = Сборка игр осьминогом (в минуту)

# The settings registry (#176, services/admin_registry.py): one label per
# setting, one title per group — the bot and the Mini App show the same ones.
admin-setting-rare-threshold = Порог редкости, %
admin-setting-default-rarity = Режим новичков
admin-setting-rare-threshold-hint = Редкое — то, что есть не больше чем у этой доли игроков. Один порог на все чаты.
admin-setting-default-rarity-hint = С этим режимом начинают новые люди.
admin-setting-show-links = Ссылки на профили
admin-setting-store-collection = Сбор с магазинов
admin-setting-store-collection-hint = Бот сам спрашивает магазины и HowLongToBeat об играх: версии, DLC, время прохождения. Выключено — ничего не собирается.
admin-setting-post-picture = Картинка поста
admin-setting-post-picture-hint = Мелкая иконка (Steam, Xbox 360) увеличивается и встаёт на карточку с этим фоном. Большие картинки уходят как есть.
admin-setting-post-picture-size = Карточка мелкой иконки
admin-setting-post-picture-scale = Увеличение мелкой иконки
admin-setting-post-picture-low-res = Мелкая иконка — это
admin-setting-post-picture-low-res-hint = Картинка меньше этого размера по большей стороне увеличивается и встаёт на карточку, остальные уходят как есть. 128 — только иконки Steam и Xbox 360, 256 — ещё трофеи PS4, 512 — всё, кроме больших артов.
admin-post-picture-low-res-value = меньше { $px } px
admin-post-picture-size-original = Оригинал (без карточки)
admin-post-picture-off = Как есть
admin-post-picture-color = Фон цветом иконки
admin-post-picture-cover = Фон обложкой игры
admin-setting-chat-publishing = Публикации в чате
admin-setting-chat-locale = Язык
admin-setting-chat-tz = Часовой пояс
admin-setting-digest = Дайджест с
admin-setting-chat-summary = Итоги дня
admin-setting-chat-summary-time = Время итогов
admin-setting-chat-flood-limit = Антифлуд: постов за окно
admin-setting-chat-flood-window = Антифлуд: окно (мин)
admin-group-global-rules = Правила
admin-group-global-newcomers = Новые пользователи
admin-group-global-lists = Списки
admin-group-global-hltb = HLTB
admin-group-global-timers = Таймеры
admin-group-global-poll_xbox = Опрос статуса: Xbox
admin-group-global-poll_steam = Опрос статуса: Steam
admin-group-global-poll_psn = Опрос статуса: PlayStation
admin-setting-poll-in-game = В игре (мин)
admin-setting-poll-online = В сети, без игры (мин)
admin-setting-poll-offline = Не в сети (мин)
admin-setting-poll-idle = Давно не в сети (мин)
admin-setting-poll-idle-after = «Давно» — после (мин не в сети)
admin-setting-poll-dormant = Спящий аккаунт (мин)
admin-setting-poll-dormant-after = «Спящий» — после (дней не в сети)
admin-setting-poll-scan-online = Скан трофеев: в сети (мин)
admin-setting-poll-scan-offline = Скан трофеев: не в сети (мин)
admin-setting-poll-scan-dormant = Скан трофеев: спящий (мин)
admin-setting-poll-shared-slowdown = Без личного токена: реже в (раз)
admin-group-global-mail = Почта
admin-group-global-other = Прочее
admin-group-chat-main = Основное
admin-group-chat-summary = Итоги дня
admin-group-chat-flood = Антифлуд
admin-settings-title = ⚙️ Настройки
admin-settings-button = ⚙️ Настройки ▸
admin-settings-group-title = ⚙️ Настройки · { $group }
admin-settings-row = { $label }: { $value } ▸
admin-settings-pick = { $label }: выбери значение.
admin-settings-type =
    { $label }
    Сейчас: { $current }
    Пришли число от { $minimum } до { $maximum }.{ $zero_hint }
admin-settings-zero-hint = { " " }0 — { $meaning }.
admin-settings-saved = ✅ { $label }: { $value }
admin-settings-choice-retry = Такого значения нет — выбери кнопкой.

# Platform keys (#17; Anthropic added 2026-09-09 — achievement-description
# translation only, same admin-settable-shared-credential shape)
admin-keys-title = 🔑 Ключи платформ
admin-keys-tap = Нажми на ключ — внутри статус, проверка, нагрузка и действия.
admin-keys-personal-button = 👥 Личные токены PSN · { $alive } ✅ · { $dead } ⚠️
admin-keys-back = ‹ Ключи
admin-key-title = 🔑 <b>{ $label }</b>
admin-key-status-alive = Статус: ✅ работает
admin-key-status-dead = Статус: ⚠️ не работает
admin-key-status-unset = Статус: ⚪️ не задан
admin-key-checked = Проверен: { $ago }
admin-key-usage = Запросы: { $usage }
admin-key-psn-reads = Читает: { $shared } акк. без личного токена и каталог игр · личных токенов: { $alive } ✅ · { $dead } ⚠️
admin-psntok-title = 👥 <b>Личные токены PSN</b>
admin-psntok-alive = ✅ <b>{ $name }</b> — { $who }, проверен { $ago }
admin-psntok-dead = ⚠️ <b>{ $name }</b> — { $who }, не работает { $ago }, владельцу написано
admin-psntok-none = Пока никто не добавил личный токен.
admin-psntok-note = Сами токены не показываются никому. Без личного токена: { $shared } акк. (опрос реже — настройка в «Опрос статуса: PlayStation»).
admin-psn-token-shared = Токен: общий (опрос реже)
admin-psn-token-alive = Токен: 🔑 личный ✅ (проверен { $ago })
admin-psn-token-dead = Токен: 🔑 личный ⚠️ не работает ({ $ago })
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
admin-number-range-retry = Число должно быть от { $minimum } до { $maximum }. Ещё раз?
{ $text }
admin-integer-retry = Здесь только целое число. Ещё раз?
admin-chat-not-found = Чат не найден
admin-chat-not-found-period = Чат не найден.

# Chat settings prompts
# Anti-flood filter (2026-09-09): after N individually-notified achievements
# for one person land in this chat within the window, further ones stop
# posting on their own and get grouped into one message once the window
# closes. 0 = off for this chat.
{ $text }
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

# Chat and cleanup actions
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
admin-promo-confirm = Отправить промо-сообщение в «{ $title }»?
admin-promo-confirm-yes = 📢 Да, отправить
admin-promo-failed = Не получилось отправить промо — бот, возможно, не в чате.
admin-action-unknown = Это действие сейчас недоступно.
admin-action-section-messages = Сообщения бота
admin-action-section-timers = Очередь перевода
admin-action-section-rules = Проверка уведомлений

# New users and user cards
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
admin-rarity-title = Публикация
admin-rarity = Публикация: { $mode }
admin-rarity-all = все
admin-rarity-rare = редкие
admin-rarity-hidden = никакие
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
admin-picture-test = 🖼 Тест уведомлений
admin-picture-test-intro = 🖼 Тест уведомлений. Последняя выбитая ачивка каждой платформы ({ $count }) — полным постом, как в чате: как сейчас, затем мелкая иконка с текущими размером карточки и увеличением — на фоне цвета иконки и на фоне обложки игры. Большие картинки остаются как есть.
admin-picture-test-high-res = Высокое разрешение — уходит как есть
admin-picture-test-sent = Постов отправлено в личку: { $count }
admin-picture-test-empty = Ещё ни одной ачивки с картинкой
admin-picture-test-failed = Не удалось отправить тест в личку
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

    Бот:          { $state }
    Публикации:   { $publishing }
    Подписано:    { $subscribers } чел.
    Админ чата:   { $admin }
    Итог дня:     { $summary }, в { $time }
    Часовой пояс: { $offset }
    Антифлуд:     { $flood }
    Язык:         { $locale_name }

    { $names }
admin-chat-flood-value = { $limit } ач. / { $window } мин
admin-chat-flood-off = выключен
admin-no-subscribers = Подписанных пока нет.
admin-subscribers-list = Подписаны: { $names }
admin-digest-never = никогда
admin-chat-messages-menu-button = 🗑 Сообщения ▸
admin-delete-last = 🗑 Последнее
admin-wipe-bot-24h = 🗑 Бота (24ч)
admin-wipe-system-24h = 🗑 Системные (24ч)
admin-wipe-system-all = 🗑 Все системные
admin-back-to-chats = ‹ К списку
admin-default-player = Игрок
admin-note-excluded =   исключён
admin-note-invalid =   вход протух
admin-note-revoked =   отписался

## Chat admins (#232)
admin-on = вкл
admin-off = выкл
admin-chat-admin-none = нет
admin-chat-admin-button = 👤 Админ чата ▸
admin-chat-admin-pick =
    👤 Админ чата: { $admin }

    Кому отдать роль? В списке те, кто подписан на чат или писал в нём.
admin-chat-admin-hand-on =
    👤 Ты админ этого чата.

    Кому передать роль? Ты её потеряешь. В списке те, кто подписан на чат или писал в нём.
admin-chat-admin-nobody = Здесь пока никого, кому можно отдать роль: человек должен подписаться на чат или написать в нём.
admin-chat-admin-remove = ✖️ Снять админа
admin-chat-admin-confirm = Сделать { $name } админом чата «{ $title }»?
admin-chat-admin-confirm-hand-on = Передать роль админа чата «{ $title }» пользователю { $name }? Ты её потеряешь.
admin-chat-admin-confirm-yes = Да
admin-chat-admin-remove-confirm = Снять { $name } с роли админа чата «{ $title }»?
admin-chat-admin-set = Админ чата теперь { $name }.
admin-chat-admin-removed = У чата больше нет админа.
admin-chat-admin-handed-on = Роль передана: { $name } теперь админ чата «{ $title }».
admin-chat-admin-you =
    👤 Ты теперь админ чата «{ $title }».

    Его настройки и сообщения — в /admin, или кнопкой «Управление чатом» в /panel группы.
admin-chat-admin-only = Доступно только для администратора чата
admin-not-allowed = Это не для тебя.
admin-chats-mine-empty = Ты пока не админ ни одного чата.

## Roles (#232)
admin-role = Роль: { $role }
admin-role-user = пользователь
admin-role-admin = админ приложения
admin-role-superadmin = суперадмин
admin-role-make_admin = ⭐ Сделать админом
admin-role-make_superadmin = 👑 Сделать суперадмином
admin-role-unmake_admin = Снять админа
admin-role-unmake_superadmin = Снять суперадмина (оставить админом)
admin-role-make_admin-confirm = Сделать { $name } админом приложения? Ему откроются люди, чаты, настройки и сезонный пропуск — без ключей и удаления.
admin-role-make_superadmin-confirm = Сделать { $name } суперадмином? Ему откроется всё: ключи, удаление людей, роли.
admin-role-unmake_admin-confirm = Снять с { $name } роль админа приложения?
admin-role-unmake_superadmin-confirm = Снять с { $name } суперадмина? Он останется админом приложения.
admin-role-confirm-yes = Да
admin-role-done = Роль: { $role }
