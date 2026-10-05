# Shared keyboards (bot/handlers/keyboards.py) — buttons and small labels
# used across the connect flow, the panel, and per-chat cards. Split from
# bot.ftl the same way keyboards.py itself is shared code, not owned by any
# one feature (see the module's own docstring).
# Timezone and digest controls
kb-default = по умолчанию
kb-tz-other = Другой ▸
kb-tz-manual = ✏️ Ввести вручную
kb-tz-skip = ⏭ Пропустить
# Ways back and onward instead of a command to type (owner, 2026-09-30).
kb-open-panel = ⚙️ Панель
kb-back-to-panel = ‹ В панель
kb-back = ‹ Назад
kb-connect-xbox-again = 🎮 Подключить XBOX
kb-relogin-xbox = 🔄 Подключить XBOX заново
kb-open-xbox = 🟢 XBOX ▸
kb-unlink-xbox = 🔌 Отвязать XBOX
kb-tz-pick = 🕐 Выбрать часовой пояс
kb-connect-xbox = Подключить XBOX
kb-digest-never = никогда
kb-digest-from-n = от { $threshold } достижений
kb-rarity-hidden = никакие
kb-rarity-rare = только редкие
kb-rarity-all = любые

# Connection controls
kb-disconnect-confirm = 🔌 Да, отключить
kb-cancel = ✖️ Отмена
# /panel's own connect buttons (#33) — "Подключить X" with a 🎮 icon,
# uniformly for all three; deliberately wordier than the group hub's own
# short platform-name buttons (chat-hub-*-button), and distinct from
# connect_keyboard's own deep-link kb-connect-xbox above.
kb-panel-connect-xbox = 🎮 Подключить Xbox
kb-panel-connect-steam = 🎮 Подключить Steam
kb-panel-connect-psn = 🎮 Подключить PSN
kb-steam-disconnect = 🔌 Отвязать
kb-psn-disconnect = 🔌 Отвязать
kb-xbox-reconnect = 🔄 Подключить заново

# Panel controls
kb-timezone-row = 🕐 Часовой пояс: { $offset } ▸
kb-my-chats = 💬 Мои чаты ▸
# The person's rarity mode as a carousel: a tap moves to the next one (owner, 2026-09-30).
kb-publish-all = 📣 Публиковать: Все
kb-publish-rare = 💎 Публиковать: Редкие
kb-publish-hidden = 🔕 Публиковать: Никакие
kb-sync = 🔄 Синхронизировать
kb-profile = 👤 Профиль
kb-xbox-disconnect = 🔌 Отвязать
kb-profile-of = 👤 { $platform }
kb-publishes-on = 🔔 Публикуется
kb-publishes-off = 🔇 Не публикуется
# Some accounts of the platform post, some do not (#10).
kb-publishes-partly = 🔔 Частично
# /panel's platform buttons (#10): each opens that platform's own screen.
kb-platform-menu = { $icon } { $platform }{ $alert } ▸
kb-platform-menu-count = { $icon } { $platform } ({ $count }){ $alert } ▸
kb-locale = 🌐 Язык: { $name } ▸
kb-refresh = 🔄 Обновить
kb-open = ↗️ Открыть
