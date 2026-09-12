# Achievement publication formatting (services/achievements.py).
# Platform labels
achievement-platform-xbox = XBOX
achievement-platform-xbox360 = XBOX 360
achievement-platform-steam = Steam
achievement-platform-psn = PlayStation
achievement-platform-unknown = { $platform }
achievement-unknown-game = неизвестная игра
achievement-word = достижение
achievement-word-trophy = трофей

# Message headers and item lines
achievement-single-header = <b>{ $gamertag }</b> получает { $word }
achievement-digest-header = <b>{ $gamertag }</b> получает { $phrase }
achievement-game-line = { $title } (<i>{ $platform }</i>)
achievement-name = { $badge } «{ $name }»
achievement-gamerscore = { $score } G
achievement-rarity = редкость { $percent }%

# Plural forms. The form is selected by Fluent itself from $count, using the
# CLDR plural rules of whichever locale this file belongs to — $pretty (the
# same number, thousands-separated for display) is what actually gets shown,
# because selecting on an already-formatted string would not work.
achievement-plural =
    { $count ->
        [one] { $pretty } достижение
        [few] { $pretty } достижения
       *[many] { $pretty } достижений
    }
achievement-trophy-plural =
    { $count ->
        [one] { $pretty } трофей
        [few] { $pretty } трофея
       *[many] { $pretty } трофеев
    }

# Прогресс по игре рядом с её названием (#46). Появляется только когда итог
# действительно известен: у PSN прогресс хранится процентом, а не счётом.
achievement-game-progress = { " " }· { $unlocked }/{ $total }
