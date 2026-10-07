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
