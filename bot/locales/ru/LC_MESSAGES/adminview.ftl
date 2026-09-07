# /admin home screen (services/admin_view.py) — shared by handlers/admin.py
# (DI-available) and poller/admin_refresh.py (no DI), so this module resolves
# strings through bot.i18n.gettext rather than an injected I18nContext.
# Credential health
adminview-key-alive-checked = ✅ жив, проверен { $ago }
adminview-key-alive = ✅ жив
adminview-key-stale-checked = ⚠️ протух, проверен { $ago }
adminview-key-stale = ⚠️ протух
adminview-usage-min = { $span } мин
adminview-usage-sec = { $span }с
adminview-usage-part = { $used }/{ $limit } за { $label }
adminview-usage-none = нет данных
adminview-psn-not-configured = не настроен — «🏆 Трофеи PSN» ниже примет NPSSO

# Admin home
adminview-home =
    ⚙️ Администрирование  ·  обновлено { $updated }

    Пользователей: { $users } (исключено: { $excluded })
      XBOX:  { $xbox_linked } (вход активен: { $xbox_active }, без входа: { $xbox_broken })
      Steam: { $steam_linked }
      PSN:   { $psn_linked }
    Чатов:          { $chats }
    API XBOX (достижения):  { $xbox_usage }
    API Steam (достижения): { $steam_usage }
    Ключ Steam: { $steam_key_line }
    Ключ PSN:   { $psn_key_line }
    Запросов к PSN за сутки: { $psn_requests }
adminview-btn-newusers = 👤 Новые пользователи ▸
adminview-btn-limits = ⚙️ Глобальные настройки ▸
adminview-btn-users = Пользователи ▸
adminview-btn-chats = Чаты ▸
adminview-btn-psntest = 🏆 Трофеи PSN (тест) ▸
