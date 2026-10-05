# The app's own notifications (services/notifier.py, #164): one line each,
# the same in the list, a push and a Telegram DM.
notification-new-follower = У тебя новый подписчик — { $name }
notification-new-friend = Вы с { $name } теперь друзья
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
