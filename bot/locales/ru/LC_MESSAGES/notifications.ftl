# The app's own notifications (services/notifier.py, #164): one line each,
# the same in the list, a push and a Telegram DM.
notification-new-follower = У тебя новый подписчик — { $name }
notification-new-friend = Вы с { $name } теперь друзья
notification-game-news = { $post ->
    [patch] Новый патч
   *[other] Новость
} в { $game }: { $title }
notification-game-news-lead = { $post ->
    [patch] — новый патч
   *[other] — новость
}
notification-unknown = Что-то новое в приложении
notification-xbox-login-dead = Вход в Xbox слетел — подключи аккаунт заново, чтобы достижения снова приходили
# Новые достижения того, на кого подписан (owner, 2026-10-05). $trophies — yes для PSN.
notification-new-post = { $name } получает { $trophies ->
    [yes] { $count ->
        [one] { $pretty } трофей
        [few] { $pretty } трофея
       *[many] { $pretty } трофеев
    }
   *[no] { $count ->
        [one] { $pretty } достижение
        [few] { $pretty } достижения
       *[many] { $pretty } достижений
    }
} в { $game }
# The list's own form (owner, 2026-10-06): the name in bold, then the lead; the
# detail under it says what and where.
notification-new-follower-lead = — новый подписчик
notification-new-friend-lead = — теперь вы друзья
notification-new-post-lead = получает { $trophies ->
    [yes] { $count ->
        [1] трофей
        [one] { $pretty } трофей
        [few] { $pretty } трофея
       *[many] { $pretty } трофеев
    }
   *[no] { $count ->
        [1] достижение
        [one] { $pretty } достижение
        [few] { $pretty } достижения
       *[many] { $pretty } достижений
    }
}
notification-new-post-named = получает «{ $name }»{ $more ->
    [0] {""}
   *[other] {" "}и ещё { $more }
}
