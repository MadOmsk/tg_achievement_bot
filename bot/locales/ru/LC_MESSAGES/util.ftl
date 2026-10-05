# Shared small helpers (bot/util.py) that produce user-facing text —
# humanize_ago() is shown in both the personal and admin panels; resolved
# via bot.i18n.gettext since util.py is a low-level module imported from
# contexts with and without an aiogram I18nContext available.
# Relative time
util-ago-never = никогда
util-ago-just-now = только что
util-ago-minutes = { $count } мин назад
util-ago-hours = { $count } ч назад
util-ago-days = { $count } дн назад
util-untitled-chat = без названия
