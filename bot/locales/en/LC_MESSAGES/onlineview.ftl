# /online table rendering (services/online_view.py) — shared by
# handlers/chat.py (DI-available) and poller/online_refresh.py (no DI), so
# strings are resolved via bot.i18n.gettext rather than an injected
# I18nContext.
# Presence states
onlineview-playing = playing — { $where }
onlineview-online-idle = online, not playing
onlineview-offline = offline
onlineview-no-data = no data

# Table
onlineview-header = 🎮 <b>Who's online</b>
onlineview-updated = <i>Updated: { $updated }</i>
onlineview-row = { $icon } { $name } — { $status }
