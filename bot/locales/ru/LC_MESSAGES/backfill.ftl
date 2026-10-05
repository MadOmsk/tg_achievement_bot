# The status of reading an account's history (handlers/backfill.py): one
# message, redrawn every few seconds, ending as the result (owner, 2026-09-30).
backfill-starting = ⏳ Синхронизирую историю { $platform }…
backfill-progress =
    ⏳ Синхронизирую историю { $platform }…
    { $bar }
    { $detail }
backfill-detail-games = Готово { $done } из { $total } { $total ->
    [one] игры
   *[other] игр
} · найдено { $found }
backfill-detail-steps = Шаг { $done } из { $total } · найдено { $found }
backfill-done-games =
    ✅ История { $platform } синхронизирована: { $found } из { $total } { $total ->
        [one] игры
       *[other] игр
    }.
    В чат они не полетят — дальше публикую только новые.
backfill-done =
    ✅ История { $platform } синхронизирована: { $found }.
    В чат они не полетят — дальше публикую только новые.
backfill-private-games = ⚠️ У { $count } { $count ->
    [one] игры
   *[other] игр
} закрыта приватность — их трофеи прочитать не удалось. Открой приватность этих игр в PS App.
backfill-hidden-psn =
    ⚠️ Трофеи { $platform } скрыты — прочитать историю не получилось.
    Открой их: PS App → Настройки → Приватность → «Уровень трофеев и коллекция игр» → «Все пользователи».
backfill-steam-private =
    ⚠️ Профиль Steam подключил, но игровая статистика скрыта отдельно от профиля — достижения не прочитать.

    Сделай публичной именно её: { $privacy_url } → «Игровая статистика» → «Всем».
backfill-failed =
    ⚠️ Не смог дочитать историю { $platform }.
    Публикация пока выключена, чтобы не завалить чат старыми достижениями.
backfill-retry = 🔄 Попробовать снова
backfill-recheck = 🔄 Проверить снова
backfill-panel = ⚙️ Панель
backfill-gone = Этот аккаунт больше не привязан.
