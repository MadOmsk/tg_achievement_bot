# Admin notifications (services/notify.py) — background-triggered, no
# aiogram I18nContext available, resolved via bot.i18n.gettext instead.
# Notification verbs and events
notify-verb-new = Добавлен пользователь
notify-verb-reconnect = Переподключился
notify-user-connected = ➕ { $verb }: { $gamertag }
notify-user-disconnected = ➖ Отключился: { $gamertag } ({ $reason })
notify-token-dead-line1 = ⚠️ У пользователя слетел вход: { $name }
notify-token-dead-line2 = Ачивки не публикуются, пока он не войдёт заново. Напоминание ему уже ушло.
notify-service-key-dead = ⚠️ Умер общий ключ { $label } — все аккаунты { $label } разом перестали опрашиваться, { $fix }.
notify-service-key-dead-fix-panel = пришли новый ключ через админ-панель
notify-translation-key-dead = ⚠️ Умер ключ Anthropic — новые описания ачивок перестали переводиться на недостающий язык (старый текст никуда не делся), пришли новый ключ через админ-панель.
notify-who-no-username = без username
notify-who = tg_id { $tg_id } · { $username }
notify-reason-command = сам через /disconnect_xbox
notify-reason-button = отписался кнопкой

# Identity and platform labels
notify-id = id{ $tg_id }
notify-platform-steam = Steam
notify-platform-psn = PSN
notify-platform-unknown = { $platform }
