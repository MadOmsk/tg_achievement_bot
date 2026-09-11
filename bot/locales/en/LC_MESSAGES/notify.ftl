# Admin notifications (services/notify.py) — background-triggered, no
# aiogram I18nContext available, resolved via bot.i18n.gettext instead.
# Notification verbs and events
notify-verb-new = User added
notify-verb-reconnect = Reconnected
notify-user-connected = ➕ { $verb }: { $gamertag }
notify-user-disconnected = ➖ Disconnected: { $gamertag } ({ $reason })
notify-token-dead-line1 = ⚠️ A user's login has expired: { $name }
notify-token-dead-line2 = Their achievements aren't being published until they sign in again. They've already been reminded.
notify-service-key-dead = ⚠️ The shared { $label } key is dead — every { $label } account stopped being polled at once, { $fix }.
notify-service-key-dead-fix-panel = send a new key via the admin panel
notify-translation-key-dead = ⚠️ The Anthropic key is dead — new achievement descriptions have stopped being translated into the missing language (existing text is untouched), send a new key via the admin panel.
notify-who-no-username = no username
notify-who = tg_id { $tg_id } · { $username }
notify-reason-command = on their own via /disconnect_xbox
notify-reason-button = unsubscribed with the button

# Identity and platform labels
notify-id = id{ $tg_id }
notify-platform-steam = Steam
notify-platform-psn = PSN
notify-platform-unknown = { $platform }
