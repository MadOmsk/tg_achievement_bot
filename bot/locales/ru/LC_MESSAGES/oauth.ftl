# Microsoft OAuth callback page (bot/web/oauth.py) — plain browser HTML, no
# aiogram I18nContext at all (this runs inside aiohttp, not an update
# handler), resolved via bot.i18n.gettext. One Fluent key per full
# title/text pair rather than per HTML tag — the markup itself (just the
# outer <h1>/<p> template in oauth.py) stays in Python; only the actual
# Russian copy moves here.
# OAuth result pages
oauth-cancelled-title = Вход отменён
oauth-cancelled-text = Можно закрыть вкладку и попробовать снова в боте.
oauth-missing-title = Чего-то не хватает
oauth-missing-text = Открой ссылку из бота заново.
oauth-token-exchange-failed-title = Microsoft не отдал токен
oauth-token-exchange-failed-text = Попробуй ещё раз: /connect_xbox
oauth-failed-title = Не получилось
oauth-success-title = Готово, { $gamertag }
oauth-success-text = Возвращайся в Telegram — там всё остальное.
