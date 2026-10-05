# HowLongToBeat lookup (bot/handlers/hltb.py, bot/services/hltb.py).
# Search flow
hltb-unavailable = HowLongToBeat is unavailable right now, try again later.
hltb-session-stale = That session has expired, start again — /hltb
hltb-results-prompt = Which of these is your game? Tap the right one.
hltb-prompt-title = Game title? It doesn't have to be exact — I'll show you options.
hltb-prompt-with-recent = Reply to this message, or pick one of your recent games:
hltb-prompt-reply-only = Reply to this message.
hltb-no-results = Found nothing for “{ $query }”, try another spelling.

# Result cards
hltb-cancel-button = ❌ Cancel

# $hours is a pre-formatted string ("12.5 h" or "—") — the .1f rounding and
# the "no data" dash stay in Python (services/hltb.py's own float parsing),
# Fluent just places the already-formatted value into the sentence.
hltb-card-main = Main story · { $hours }
hltb-card-extra = Main + extras · { $hours }
hltb-card-completionist = Completionist · { $hours }
hltb-card-platforms = Platforms: { $platforms }
hltb-card-genres = Genres: { $genre }
hltb-card-link = <a href="{ $url }">Page on HowLongToBeat ↗</a>
hltb-hours = { $hours } h
hltb-no-data = —
