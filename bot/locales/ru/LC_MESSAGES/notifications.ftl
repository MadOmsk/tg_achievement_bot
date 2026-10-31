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
notification-psn-token-dead = Личный токен PSN для { $name } больше не работает — аккаунт снова опрашивается общим токеном и реже. Добавь новый токен в панели: /panel → PlayStation
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
notification-season-start = { $named ->
    [yes] { $title } начался!
   *[no] Новый сезон начался!
}
    Кто первым доберётся до вершины?
notification-pass-reward = Новая награда в сезонном пропуске: { $title }
# Очки месяца дошли до уровня сезонного пропуска (owner, 2026-10-28):
# $reward — theme / game / code, $palette — тема уровня, $title — приз, $named — yes, когда он назван.
notification-pass-level = Новый уровень сезонного пропуска — { $reward ->
    [theme] тема «{ $palette ->
        [graphite] Графит
        [ocean] Океан
        [mint] Мята
        [ember] Янтарь
        [rose] Роза
       *[other] { $palette }
    }». Забери её
   *[other] приз{ $named ->
        [yes] {" "}«{ $title }»
       *[no] {""}
    }. Забери его
}
