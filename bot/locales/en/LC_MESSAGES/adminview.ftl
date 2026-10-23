# /admin home screen (services/admin_view.py) — shared by handlers/admin.py
# (DI-available) and poller/admin_refresh.py (no DI), so this module resolves
# strings through bot.i18n.gettext rather than an injected I18nContext.
# Credential health
adminview-key-alive-checked = ✅ alive, checked { $ago }
adminview-key-alive = ✅ alive
adminview-key-stale-checked = ⚠️ dead, checked { $ago }
adminview-key-stale = ⚠️ dead
adminview-psn-not-configured = ⚠️ not configured — set it in “🔑 Platform keys”
adminview-steam-not-configured = ⚠️ not configured — set it in “🔑 Platform keys”

# Admin home
adminview-home =
    ⚙️ Super-admin panel  ·  updated { $updated }

    Users: { $users } (excluded: { $excluded })
      XBOX:  { $xbox_linked } (signed in: { $xbox_active }, signed out: { $xbox_broken })
      PSN:   { $psn_linked }
      Steam: { $steam_linked }
    Chats:          { $chats }
    { $api_lines }
    PSN key:   { $psn_key_line }
    Steam key: { $steam_key_line }
    { $mail_line }
adminview-mail-usage = an hour { $hour }/{ $hour_limit } · a day { $day }/{ $day_limit }
adminview-api-xbox = XBOX API (median/max per account)
adminview-api-steam = Steam API
adminview-api-psn = PSN API
adminview-api-anthropic = Anthropic API
adminview-api-tokens = { $requests } req. · { $tokens } tok.
adminview-span-300 = 5 min
adminview-span-3600 = hour
adminview-span-86400 = day
adminview-mail-label = Sign-in emails ({ $server })
adminview-mail-label-none = Sign-in emails
adminview-btn-users = Users ▸
adminview-btn-chats = Chats ▸
adminview-btn-keys = 🔑 Platform keys ▸
