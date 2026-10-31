# The app's own notifications (services/notifier.py, #164): one line each,
# the same in the list, a push and a Telegram DM.
notification-new-follower = You have a new follower — { $name }
notification-new-friend = You and { $name } are friends now
notification-game-news = { $post ->
    [patch] A new patch
   *[other] News
} for { $game }: { $title }
notification-game-news-lead = { $post ->
    [patch] — a new patch
   *[other] — news
}
notification-unknown = Something new in the app
notification-xbox-login-dead = Your Xbox sign-in expired — connect the account again to keep getting achievements
notification-psn-token-dead = The personal PSN token for { $name } stopped working — the account is read with the shared token again, less often. Add a new one in the panel: /panel → PlayStation
# New achievements of somebody followed (owner, 2026-10-05). $trophies is yes on PSN.
notification-new-post = { $name } earned { $trophies ->
    [yes] { $count ->
        [one] { $pretty } trophy
       *[other] { $pretty } trophies
    }
   *[no] { $count ->
        [one] { $pretty } achievement
       *[other] { $pretty } achievements
    }
} in { $game }
# The list's own form (owner, 2026-10-06): the name in bold, then the lead; the
# detail under it says what and where.
notification-new-follower-lead = is following you now
notification-new-friend-lead = — you're friends now
notification-new-post-lead = earned { $trophies ->
    [yes] { $count ->
        [one] a trophy
       *[other] { $pretty } trophies
    }
   *[no] { $count ->
        [one] an achievement
       *[other] { $pretty } achievements
    }
}
notification-new-post-named = earned “{ $name }”{ $more ->
    [0] {""}
   *[other] {" "}and { $more } more
}
notification-season-start = { $named ->
    [yes] { $title } has started!
   *[no] A new season has started!
}
    Who will reach the top first?
notification-pass-reward = A new reward in the season pass: { $title }
# The month's points reached a level of the season pass (owner, 2026-10-28):
# $reward is theme / game / code, $palette the level's theme, $title the prize, $named yes when it has one.
notification-pass-level = A new season pass level — { $reward ->
    [theme] the { $palette ->
        [graphite] Graphite
        [ocean] Ocean
        [mint] Mint
        [ember] Amber
        [rose] Rose
       *[other] { $palette }
    } theme. Claim it
   *[other] a prize{ $named ->
        [yes] {" "}“{ $title }”
       *[no] {""}
    }. Claim it
}
