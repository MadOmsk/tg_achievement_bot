# Daily summary + /summary on demand (poller/daily.py). The scheduled tick
# has no I18nContext (no aiogram update at all); build_summary/full_leaderboard
# are also called from handlers/chat.py's /summary — resolved via
# bot.i18n.gettext everywhere in this module so both call sites agree.
#
# Month names are nominative here, not Russian's genitive ("June", not
# "июня"), and the two templates that use them put the day *after* the
# month — English word order, decided per locale in this file rather than
# by whoever calls it.
# Calendar labels and rolling windows
daily-month-01 = January
daily-month-02 = February
daily-month-03 = March
daily-month-04 = April
daily-month-05 = May
daily-month-06 = June
daily-month-07 = July
daily-month-08 = August
daily-month-09 = September
daily-month-10 = October
daily-month-11 = November
daily-month-12 = December
daily-window-day = 24 hours
daily-window-month = since { $month } 1

# Summary
daily-header = 📊 <b>Daily summary</b>, { $month } { $day }
# The month-end wrap-up (#14) — same leaderboard as the daily, month block
# only, no day stats. Sent on the last calendar day of the month at the
# chat's summary time, alongside that day's own daily summary.
daily-monthly-header = 📊 <b>The month in review</b>
daily-show-all-day = Show everyone (24h)
daily-show-all-month = Show everyone (this month)
daily-leaderboard-total-label = Total
daily-leaderboard-full-header = 📊 <b>{ $label }, in full</b>

# Monthly summary's own games block (#7, user request)
daily-games-header = <b>Games this month</b>
daily-unknown-game = untitled
