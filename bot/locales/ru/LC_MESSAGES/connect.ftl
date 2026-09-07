# /start, /connect_xbox, /disconnect_xbox and the timezone picker
# (bot/handlers/connect.py).
# Connection flow
connect-greeting =
    Привет! Я публикую в чат достижения XBOX — свои и других участников.

    Что умею:
    • ловлю новые достижения и пишу о них в чат;
    • фильтрую по редкости, если не хочешь публиковать всё подряд;
    • веду личную статистику и итог дня.

    Начнём со входа через Microsoft.
connect-timezone-prompt = 🕐 Твой часовой пояс?
connect-xbox-already-connected = XBOX уже подключён. Настройки — /panel.
connect-xbox-already-connected-relogin =
    XBOX уже подключён. Если нужно войти заново — сначала /disconnect_xbox.
connect-xbox-not-connected = XBOX и так не подключён.
connect-disconnect-yes = Да, отключить
connect-disconnect-cancel = Отмена
connect-disconnect-prompt =
    Отключить XBOX?

    Удалю токен и подписки. Историю достижений оставлю — она нужна статистике чата, и при повторном входе старые достижения не хлынут в чат заново.

    Само разрешение остаётся в аккаунте Microsoft — убрать его можно только самому: { $revoke_url }
connect-disconnected =
    Отключил. Вернуться можно в любой момент — /connect_xbox.

    Разрешение в аккаунте Microsoft убирается тут: { $revoke_url }
connect-relogin-prompt =
    Войди заново — старые достижения в чат не полетят, они уже отмечены как виденные.
connect-optout-done =
    Хорошо, больше не напоминаю. Историю достижений сохранил — вернуться можно в любой момент через /connect_xbox.
connect-timezone-skip-done = Хорошо, пропустил. Поменять — в /panel.
connect-timezone-set = Часовой пояс: { $offset }. Поменять можно в /panel.
connect-timezone-manual-hint =
    Пришли смещение одним сообщением, со знаком: например +3, -5 или +5:30.
connect-timezone-manual-invalid = Это не похоже на реальный часовой пояс. { $hint }
connect-login-button-hint =
    Жми кнопку и войди своим аккаунтом Microsoft. Пароль вижу не я — его спрашивает сам Microsoft.
