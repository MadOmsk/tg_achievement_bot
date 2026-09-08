# Connection and profile access
steam-not-configured = Подключение Steam пока не настроено — обратитесь к администратору.
steam-connect-group-redirect = Напиши мне в личку — подключим Steam там.
steam-private-only = Эта команда — в личке.
steam-already-connected = Steam уже подключён: { $name }.
steam-link-prompt = Пришли ссылку на свой профиль Steam (steamcommunity.com/id/...) или просто ник — подключу по нему.

    ⚠️ Игровая статистика должна быть публичной, иначе не смогу читать достижения: { $privacy_url } → «Игровая статистика» → «Всем».
steam-link-confirm-yes = Да, подключить
steam-link-confirm-no = Нет
steam-link-confirm-prompt = Похоже на профиль Steam. Подключить его?
steam-link-declined = Хорошо, не подключаю.
steam-unresolved-profile = Не нашёл такой профиль Steam. Пришли ссылку на профиль — например, https://steamcommunity.com/id/gaben.
steam-unresolved-profile-nickname-hint =

    Если присылал ник — я ищу именно по ссылке профиля, не по имени в клиенте: у Steam просто нет способа искать по нему. Ссылку можно скопировать в приложении или на steamcommunity.com → «Изменить профиль».
steam-profile-private = Профиль есть, но игровая статистика скрыта — я не смогу читать достижения. Сделай её публичной и попробуй снова: { $privacy_url } → «Игровая статистика» → «Всем».

# Backfill and disconnect
steam-connected = Подключил Steam: { $name }.
steam-backfill-started = Читаю твою историю достижений Steam, это может занять пару минут…
steam-backfill-failed = Не смог перечитать твою историю достижений Steam. Публикация пока выключена — привяжи аккаунт заново чуть позже: /connect_steam.
steam-backfill-done = Готово: перечитал { $count } уже выбитых достижений Steam — в чат они не полетят.
steam-game-details-private = Профиль подключил, но твоя игровая статистика скрыта отдельно от общей приватности профиля — достижения не прочитать. Сделай публичной именно её: { $privacy_url } → «Игровая статистика» → «Всем», и напиши /connect_steam ещё раз.
steam-disconnect-confirm-button = Да, отключить
steam-cancel-button = Отмена
steam-already-disconnected = Steam и так не подключён.
steam-disconnect-prompt = Отключить Steam ({ $name })?
steam-disconnected = Отключил Steam. Вернуться можно в любой момент.
