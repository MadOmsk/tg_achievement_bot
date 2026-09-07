# User-facing strings, Fluent format (bot/i18n.py wires this in).
#

# Only "ru" exists today — the bot is Russian-only by design (CLAUDE.md).
# This file is the migration target for text currently hardcoded in
# handlers/services as plain f-strings; nothing is required to move here at
# once. Migrate one handler at a time, pulling its literals in as they're
# touched anyway, rather than a single mass rewrite (see issue tracking i18n
# migration for the running checklist of what's moved and what's still
# inline).
# Search flow
hltb-unavailable = HowLongToBeat сейчас недоступен, попробуй позже.
hltb-session-stale = Сессия устарела, начни заново — /hltb
hltb-results-prompt = Что из этого совпадает с твоей игрой? Жми на нужный вариант.
hltb-prompt-title = Название игры? Точное не нужно — покажу варианты.
hltb-prompt-with-recent = Ответь на это сообщение (реплаем) или выбери из недавних:
hltb-prompt-reply-only = Ответь на это сообщение (реплаем).
hltb-no-results = По «{ $query }» ничего не нашёл, попробуй иначе.

# Result cards
hltb-cancel-button = ❌ Отмена

# $hours is a pre-formatted string ("12.5 ч" or "—") — the .1f rounding and
# the "no data" dash stay in Python (services/hltb.py's own float parsing),
# Fluent just places the already-formatted value into the sentence.
hltb-card-main = Основной сюжет · { $hours }
hltb-card-extra = Основной + доп. · { $hours }
hltb-card-completionist = Полное прохождение · { $hours }
hltb-card-platforms = Платформы: { $platforms }
hltb-card-genres = Жанры: { $genre }
hltb-card-link = <a href="{ $url }">Страница на HowLongToBeat ↗</a>
hltb-hours = { $hours } ч
hltb-no-data = —
