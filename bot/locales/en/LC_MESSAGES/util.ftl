# Shared small helpers (bot/util.py) that produce user-facing text —
# humanize_ago() is shown in both the personal and admin panels; resolved
# via bot.i18n.gettext since util.py is a low-level module imported from
# contexts with and without an aiogram I18nContext available.
# Relative time
util-ago-never = never
util-ago-just-now = just now
util-ago-minutes = { $count } min ago
util-ago-hours = { $count } h ago
util-ago-days = { $count } d ago
util-untitled-chat = untitled
