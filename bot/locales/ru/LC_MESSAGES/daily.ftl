# Daily summary + /summary on demand (poller/daily.py). The scheduled tick
# has no I18nContext (no aiogram update at all); build_summary/full_leaderboard
# are also called from handlers/chat.py's /summary — resolved via
# bot.i18n.gettext everywhere in this module so both call sites agree.
# Calendar labels and rolling windows
daily-month-01 = января
daily-month-02 = февраля
daily-month-03 = марта
daily-month-04 = апреля
daily-month-05 = мая
daily-month-06 = июня
daily-month-07 = июля
daily-month-08 = августа
daily-month-09 = сентября
daily-month-10 = октября
daily-month-11 = ноября
daily-month-12 = декабря
daily-window-day = 24 часа
daily-window-month = 30 дней

# Summary
daily-header = 📊 <b>Итог дня</b>, { $day } { $month }
daily-show-all-day = Показать всех (24ч)
daily-show-all-month = Показать всех (30д)
daily-leaderboard-total-label = Всего
daily-leaderboard-full-header = 📊 <b>{ $label }, полностью</b>
