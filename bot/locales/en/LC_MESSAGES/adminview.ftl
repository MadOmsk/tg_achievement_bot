# /admin home screen (services/admin_view.py) — shared by handlers/admin.py
# (DI-available) and poller/admin_refresh.py (no DI), so this module resolves
# strings through bot.i18n.gettext rather than an injected I18nContext.
# Credential health
adminview-key-alive-checked = ✅ alive, checked { $ago }
adminview-key-alive = ✅ alive
adminview-key-stale-checked = ⚠️ dead, checked { $ago }
adminview-key-stale = ⚠️ dead
adminview-usage-min = { $span } min
adminview-usage-sec = { $span }s
adminview-usage-part = { $used }/{ $limit } per { $label }
adminview-usage-none = no data
adminview-psn-not-configured = ⚠️ not configured — set it in “🔑 Platform keys”
adminview-steam-not-configured = ⚠️ not configured — set it in “🔑 Platform keys”

# Admin home
adminview-home =
    ⚙️ Administration  ·  updated { $updated }

    Users: { $users } (excluded: { $excluded })
      XBOX:  { $xbox_linked } (signed in: { $xbox_active }, signed out: { $xbox_broken })
      Steam: { $steam_linked }
      PSN:   { $psn_linked }
    Chats:          { $chats }
    XBOX API (achievements):  { $xbox_usage }
    Steam API (achievements): { $steam_usage }
    Steam key: { $steam_key_line }
    PSN key:   { $psn_key_line }
    PSN requests in the last 24h: { $psn_requests }
adminview-btn-newusers = 👤 New users ▸
adminview-btn-limits = ⚙️ Global settings ▸
adminview-btn-users = Users ▸
adminview-btn-chats = Chats ▸
adminview-btn-keys = 🔑 Platform keys ▸
