# /online table rendering (services/online_view.py) — shared by
# handlers/chat.py (DI-available) and poller/online_refresh.py (no DI), so
# strings are resolved via bot.i18n.gettext rather than an injected
# I18nContext.
# Presence states
onlineview-playing = играет — { $where }
onlineview-online-idle = в сети, не играет
onlineview-offline = не в сети
onlineview-no-data = нет данных

# Table
onlineview-header = 🎮 <b>Онлайн-статус игроков</b>
onlineview-updated = <i>Обновлено: { $updated }</i>
onlineview-row = { $icon } { $name } — { $status }
