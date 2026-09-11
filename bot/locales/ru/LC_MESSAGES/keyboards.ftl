# Shared keyboards (bot/handlers/keyboards.py) — buttons and small labels
# used across the connect flow, the panel, and per-chat cards. Split from
# bot.ftl the same way keyboards.py itself is shared code, not owned by any
# one feature (see the module's own docstring).
# Timezone and digest controls
kb-default = по умолчанию
kb-tz-other = Другой ▸
kb-tz-manual = ✏️ Ввести вручную
kb-tz-skip = Пропустить
kb-connect-xbox = Подключить XBOX
kb-digest-never = никогда
kb-digest-from-n = от { $threshold } достижений
kb-rarity-hidden = не показывать
kb-rarity-rare = только редкие
kb-rarity-all = любые

# Connection controls
kb-disconnect-confirm = Да, отключить
kb-cancel = Отмена
# /panel's own connect buttons (#33) — "Подключить X" with a 🎮 icon,
# uniformly for all three; deliberately wordier than the group hub's own
# short platform-name buttons (chat-hub-*-button), and distinct from
# connect_keyboard's own deep-link kb-connect-xbox above.
kb-panel-connect-xbox = 🎮 Подключить Xbox
kb-panel-connect-steam = 🎮 Подключить Steam
kb-panel-connect-psn = 🎮 Подключить PSN
kb-steam-disconnect = 🔕 Отключить Steam
kb-psn-disconnect = 🔕 Отключить PSN
kb-xbox-reconnect = 🔄 Подключить заново

# Panel controls
kb-timezone-row = Часовой пояс: { $offset } ▸
kb-my-chats = 💬 Мои чаты ▸
kb-sync = 🔄 Синхронизировать
kb-profile-visible = Профиль виден другим: { $visible } ▸
kb-profile-visible-yes = да
kb-profile-visible-no = нет
kb-profile = 👤 Профиль
kb-xbox-disconnect = 🔕 Отключить XBOX
kb-locale = Язык: { $name } ▸
kb-refresh = Обновить
kb-back = ‹ Назад
kb-open = Открыть
