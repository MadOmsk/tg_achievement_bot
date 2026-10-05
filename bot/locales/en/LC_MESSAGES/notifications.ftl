# The app's own notifications (services/notifier.py, #164): one line each,
# the same in the list, a push and a Telegram DM.
notification-new-follower = You have a new follower — { $name }
notification-new-friend = You and { $name } are friends now
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
