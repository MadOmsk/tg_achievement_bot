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

# Plural forms
achievement-plural =
    { $form ->
        [one] { $count } достижение
        [few] { $count } достижения
       *[many] { $count } достижений
    }
achievement-trophy-plural =
    { $form ->
        [one] { $count } трофей
        [few] { $count } трофея
       *[many] { $count } трофеев
    }
