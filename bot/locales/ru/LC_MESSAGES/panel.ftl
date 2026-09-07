# The personal panel (/panel) — bot/handlers/panel.py.
# Connection status and sync
panel-login-active = ✅ активен
panel-login-invalid = ⚠️ требуется повторный вход
panel-login-revoked = — отключён
panel-group-hint = Настройки — в личке.
panel-refreshed = Обновил
panel-xbox-not-connected = Сначала подключи XBOX: /connect_xbox
panel-sync-cooldown = Уже синхронизировал. Ещё раз — через { $minutes } мин.
panel-syncing = Синхронизирую…
panel-default-player-name = Игрок
panel-sync-failed = Не получилось синхронизироваться, попробуй позже.
panel-sync-summary-found = Проверил игр: { $titles }. Новых достижений в чат: { $published }.
panel-sync-summary-none = Ничего нового — с последнего опроса ты никуда не заходил.
panel-xbox-already-disconnected = XBOX и так не подключён.

# Account and privacy controls
panel-disconnect-prompt =
    Отключить XBOX?

    Удалю токен и подписки. Историю достижений оставлю — она нужна статистике чата, и при повторном входе старые достижения не хлынут в чат заново.

    Само разрешение остаётся в аккаунте Microsoft — убрать его можно только самому: { $revoke_url }
panel-links-hidden-toast = Скрыл
panel-links-shown-toast = Показываю
panel-timezone-prompt = 🕐 Часовой пояс — по нему считаются «сегодня» и «за месяц».
panel-my-chats-title = 💬 Мои чаты
panel-my-chats-empty =

    Пока ни в одном чате тебя не видел — ни подписок, ни сообщений.
panel-back = ‹ Назад
panel-chat-card-title = 💬 { $title }
panel-publication-enabled = Публикация: ✅ включена
panel-publication-disabled = Публикация: ⏸ выключена
panel-achievements-mode = Ачивки: { $mode }
panel-digest-row = Сводка: { $threshold } ▸
panel-unsubscribe = Отписаться
panel-subscribe = Подписаться
panel-remove-from-list = Удалить из списка
panel-back-to-chat-list = ‹ К списку чатов
panel-digest-menu =
    Сводка вместо отдельных сообщений

    Если за один раз в одной игре выбито столько достижений или больше — в этот чат уйдёт одно сводное сообщение.
panel-digest-set-never-toast = Никогда
panel-digest-set-from-toast = От { $value }
panel-subscribed-toast = Подписал
panel-unsub-prompt = Перестать публиковать твои достижения в «{ $title }»?
panel-unsub-yes = Да, отписаться
panel-unsub-cancel = Отмена
panel-unsubscribed-toast = Отписал
panel-delete-prompt =
    Убрать «{ $title }» из списка? Как будто ты там никогда не был — не бан, снова окажешься в списке, если подпишешься или напишешь туда.
panel-delete-yes = Да, удалить
panel-deleted-toast = Убрал

# Panel content
panel-header-not-connected = 👤 Панель

    Вход XBOX: — не подключён
panel-login-steam-row = Вход Steam: { $name }
panel-login-psn-row = Вход PSN: { $name }
panel-no-gamertag = без геймертега
panel-header =
    👤 { $gamertag }  ·  gamerscore { $gamerscore }
panel-login-xbox-row = Вход XBOX:   { $status }
panel-login-steam-row-connected = Вход Steam:  { $name }
panel-login-psn-row-connected = Вход PSN:    { $name }
panel-publication-row = Публикация:  { $status }
panel-now-playing-row = Сейчас:      { $playing }
panel-today-row = Сегодня:     { $achievements } (+{ $score } G)
panel-month-row = За месяц:    { $achievements } (+{ $score } G)
panel-timezone-row = Часовой пояс: { $offset }
panel-reconnect-hint = Доступ к XBOX истёк — жми «Подключить заново» ниже.
panel-recent-title = Последние достижения:
panel-recent-item = 🏆 «{ $name }» — { $game }, { $ago }
panel-unknown-game = неизвестная игра
panel-no-presence-data = нет данных
panel-offline = не в сети ({ $ago })
panel-online-idle = в сети, не играет
panel-playing = играет — { $game }
panel-excluded = 🚫 исключён администратором
panel-not-subscribed-anywhere = — не подписан ни в одном чате
panel-subscribed-in = ✅ в { $chats }
