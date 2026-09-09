# The personal panel (/panel) — bot/handlers/panel.py.
# Connection status and sync
panel-login-active = ✅ активен
panel-login-invalid = ⚠️ требуется повторный вход
panel-login-revoked = — отключён
# Distinct from panel-login-revoked above (2026-09-09): "отключён" implies a
# token existed and was deliberately disconnected, "не подключён" is for a
# person who never linked Xbox at all — same distinction Steam/PSN's own
# login rows already draw via visibility_status_text's "не проверено".
panel-login-not-connected = — не подключён
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
# Truly defensive only (2026-09-09) — every real call site ensures the user
# row exists before render_panel ever runs, so this bare fallback is not
# expected to actually render; it used to also hardcode a Xbox-specific
# "not connected" tail that no longer matches the real (per-platform,
# generalized) body shape below.
panel-header-not-connected = 👤 Панель
# Header (#18): the person's own Telegram identity, then one line per
# connected platform — built by the same function /stats' own header uses
# (services/achievements.py::platform_header_lines, #5) rather than a
# second, hand-duplicated copy of it.
panel-header-identity = 👤 { $name }
panel-login-xbox-row = Вход XBOX:   { $status }
# No "-connected" suffix (2026-09-09) — these render the same regardless of
# whether Xbox happens to be connected; the old plain (non-suffixed) keys
# only ever existed for the Xbox-gated early-return branch that used them,
# now removed, so this name freed up.
panel-login-steam-row = Вход Steam:  { $name }  ·  { $status }
panel-login-psn-row = Вход PSN:    { $name }  ·  { $status }
# Steam/PSN's achievement/trophy visibility, as of the last actual check
# (#5) — connect time, or any backfill/resync since. Xbox has no
# equivalent row here: its own token status (panel-login-xbox-row above)
# already answers a similar "can I actually read this account" question.
panel-visibility-visible = ✅ ачивки видны
panel-visibility-hidden = ⚠️ ачивки скрыты
panel-visibility-unknown = ❓ не проверено
panel-publication-row = Публикация:  { $status }
panel-now-playing-row = Сейчас:      { $playing }
panel-timezone-row = Часовой пояс: { $offset }
panel-reconnect-hint = Доступ к XBOX истёк — жми «Подключить заново» ниже.
panel-unknown-game = неизвестная игра
panel-no-presence-data = нет данных
panel-offline = не в сети ({ $ago })
panel-online-idle = в сети, не играет
panel-playing = играет — { $game }
panel-excluded = 🚫 исключён администратором
panel-not-subscribed-anywhere = — не подписан ни в одном чате
panel-subscribed-in = ✅ в { $chats }
