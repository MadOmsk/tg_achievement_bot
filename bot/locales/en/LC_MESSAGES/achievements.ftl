# Achievement publication formatting (services/achievements.py).
# Platform labels
achievement-platform-xbox = XBOX
achievement-platform-xbox360 = XBOX 360
achievement-platform-steam = Steam
achievement-platform-psn = PlayStation
achievement-platform-unknown = { $platform }
achievement-unknown-game = unknown game
achievement-word = an achievement
achievement-word-trophy = a trophy

# Message headers and item lines
achievement-single-header = <b>{ $gamertag }</b> gets { $word }
achievement-digest-header = <b>{ $gamertag }</b> gets { $phrase }
achievement-game-line = { $title } (<i>{ $platform }</i>)
achievement-name = { $badge } “{ $name }”
achievement-gamerscore = { $score } G
achievement-rarity = { $percent }% rarity
# Group teasers: person · platform-icon game, then the title + score. No
# "gets an achievement", no pictures — the Open button launches the Mini App.
# $platform is PLATFORM_ICON only (🟢/⚫/🔵), not the full platform_tag label.
achievement-teaser-header = <b>{ $gamertag }</b> · { $platform } { $game }
achievement-teaser-digest = <b>{ $gamertag }</b> · { $pretty }
achievement-teaser-game = { $platform } <i>{ $title }</i>
achievement-teaser-name = “{ $name }”
achievement-open-app = Look in the app

# Plural forms. The form is selected by Fluent itself from $count, using the
# CLDR plural rules of whichever locale this file belongs to — English has
# only one/other where Russian has one/few/many, which is exactly why the
# selection lives here and not in Python. $pretty (the same number,
# thousands-separated for display) is what actually gets shown.
achievement-plural =
    { $count ->
        [one] { $pretty } achievement
       *[other] { $pretty } achievements
    }
achievement-trophy-plural =
    { $count ->
        [one] { $pretty } trophy
       *[other] { $pretty } trophies
    }
