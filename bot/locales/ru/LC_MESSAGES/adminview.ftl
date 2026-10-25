# /admin home screen (services/admin_view.py) — shared by handlers/admin.py
# (DI-available) and poller/admin_refresh.py (no DI), so this module resolves
# strings through bot.i18n.gettext rather than an injected I18nContext.
# Credential health
adminview-key-alive-checked = ✅ жив, проверен { $ago }
adminview-key-alive = ✅ жив
adminview-key-stale-checked = ⚠️ протух, проверен { $ago }
adminview-key-stale = ⚠️ протух
adminview-psn-not-configured = ⚠️ не настроен — задай в «🔑 Ключи платформ»
adminview-steam-not-configured = ⚠️ не настроен — задай в «🔑 Ключи платформ»

# Admin home
adminview-home =
    ⚙️ Панель суперадмина  ·  обновлено { $updated }

    Пользователей: { $users } (исключено: { $excluded })
      XBOX:  { $xbox_linked } (вход активен: { $xbox_active }, без входа: { $xbox_broken })
      PSN:   { $psn_linked }
      Steam: { $steam_linked }
    Чатов:          { $chats }
    { $api_lines }
    Ключ PSN:   { $psn_key_line }
    Ключ Steam: { $steam_key_line }
    { $mail_line }
adminview-mail-usage = за час { $hour }/{ $hour_limit } · за сутки { $day }/{ $day_limit }
adminview-api-xbox = API XBOX (медиана/макс. на аккаунт)
adminview-api-steam = API Steam
adminview-api-psn = API PSN
adminview-api-anthropic = API Anthropic
adminview-api-tokens = { $requests } запр. · { $tokens } ток.
adminview-span-300 = 5 мин
adminview-span-3600 = час
adminview-span-86400 = сутки
adminview-octopus = 🐙 Осьминог
adminview-octopus-on = вкл, { $per_tick } за тик
adminview-octopus-off = выкл
adminview-octopus-queue = в очереди { $queue }{ $retrying ->
    [0] {""}
   *[other] {" "}(ждут повтора { $retrying })
}
adminview-octopus-done = за час { $hour } · за сутки { $day }
adminview-octopus-failed = ошибок за час { $failed }
adminview-octopus-last = последний: { $name }, { $at } (версий { $versions }, на проверку { $review })
adminview-mail-label = Писем с кодами ({ $server })
adminview-mail-label-none = Писем с кодами
adminview-btn-users = Пользователи ▸
adminview-btn-chats = Чаты ▸
adminview-btn-keys = 🔑 Ключи платформ ▸
